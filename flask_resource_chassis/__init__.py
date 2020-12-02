import inspect

from flask_apispec import use_kwargs, marshal_with, doc, MethodResource, Ref
from marshmallow import Schema, fields
from sqlalchemy import desc, asc, not_, or_, and_

from .exceptions import ConflictError, ValidationError
from .schemas import ResponseWrapper, DjangoPageSchema, error_response, val_error_response
from .services import ChassisService, LoggerService, get_primary_key
from .utils import CustomResourceProtector


class Scope:

    def __init__(self, scopes=None, operator=None):
        self.scopes = scopes
        self.operator = operator


def authenticate(resource_protector, scope=None, permissions=None):
    """
    Used to authenticate request using CustomResourceProtector

    :param resource_protector: CustomResourceProtector
    :param scope: Scope with scopes string and operator (And/Or)::

        Scope(scopes="resource.create resource.read", operator="Or")

    :param permissions: A list of permission tags
    """
    scope_ = scope.scopes if scope else None
    operator = scope.operator if scope and scope.operator else "AND"

    @resource_protector(scope=scope_, operator=operator, has_any_authority=permissions)
    def authenticate_(*args, **kwargs):
        return args[0]

    return authenticate_()


def validate_foreign_keys(model, db):
    """
    Used to validate foreign keys:
    1. Checks of foreign key exists
    2. If foreign key entity has field is_active checks if the entity is active

    :throws ValidationError: If validation fails
    """
    entity_table = getattr(model, "__table__")
    for column in entity_table.c:
        # print("Person column", column, column.name, column.foreign_keys)
        if column.foreign_keys:
            for key in column.foreign_keys:
                # print(f"Details", key, key.column.name, key.constraint)
                payload = getattr(model, "__dict__")
                if column.name in payload:
                    filters = {
                        "is_deleted": False,
                        key.column.name: payload.get(column.name)
                    }
                    fk_model = db.session.query(key.constraint.referred_table).filter_by(**filters).first()
                    if fk_model is None:
                        if column.doc:
                            raise ValidationError(f"Sorry {column.doc} doesn't exist")
                        else:
                            raise ValidationError(f"Associated entity({key.constraint.referred_table}) doesn't exist")
                    elif hasattr(fk_model, "is_active") and not getattr(fk_model, "is_active"):
                        if column.doc:
                            raise ValidationError(f"Sorry {column.doc} is not active")
                        else:
                            raise ValidationError(f"Associated entity({key.constraint.referred_table}) is not active")


def validate_unique_constraints(model, db, model_id=None):
    """
    Validates unique constraints ignoring records flagged as deleted

    :param model: SQLAlchemy ORM Model
    :param db: SQLAlchemy database instance
    :param model_id: If id is provided unique constraints are checked against other records exclude record with the
    provided id
    :throws ValidationError: If unique constraints check fails
    """
    entity_table = getattr(model, "__table__")
    for index in entity_table.indexes:
        if index.unique:
            filters = {
                "is_deleted": False
            }
            for column in index.columns:
                if column.name in model.__dict__:
                    filters[column.name] = model.__dict__[column.name]
            if len(filters) == 1:
                continue
            if model_id:
                pk_col = get_primary_key(model)
                query = db.session.query(entity_table).filter_by(**filters)
                query = query.filter(not_(pk_col == model_id))
                unique_model = query.first()
            else:
                unique_model = db.session.query(entity_table).filter_by(**filters).first()
            if unique_model:
                raise ValidationError("Similar record already exists")


@marshal_with(ResponseWrapper, code=400, description="Validation errors")
class ChassisResourceList(MethodResource):
    schema = Schema.from_dict(dict())
    # response_schema = Schema.from_dict(dict())
    page_response_schema = Schema.from_dict(dict())
    fetch_schema = None

    def __init__(self, app, db, schema, record_name=None, logger_service: LoggerService = None,
                 resource_protector: CustomResourceProtector = None, create_scope: Scope = None,
                 fetch_scope: Scope = None, create_permissions=None, fetch_permissions=None):
        """

        :param app: Flask application reference
        :param db: Flask SQLAlchemy reference
        :param schema: Current model Marshmallow Schema with model reference
        """
        self.app = app
        self.service = ChassisService(app, db, schema.Meta.model)
        self.db = db
        if record_name is None:
            self.record_name = "Resource"
        else:
            self.record_name = record_name

        self.schema = schema

        # class ResponseSchema(ResponseWrapper):
        #     data = fields.Nested(schema)

        class RecordPageSchema(DjangoPageSchema):
            results = fields.List(fields.Nested(schema))

        # self.response_schema = ResponseSchema()
        self.page_response_schema = RecordPageSchema()
        self.logger_service = logger_service
        self.resource_protector = resource_protector
        self.create_scopes = create_scope
        self.fetch_scopes = fetch_scope
        self.create_permissions = create_permissions
        self.fetch_permissions = fetch_permissions
        # Fetch schema fields
        fetch_fields = dict(page_size=fields.Int(required=False), page=fields.Int(required=False),
                            ordering=fields.Str(required=False), q=fields.Str(required=False))
        if hasattr(self.schema.Meta.model, "created_at"):
            fetch_fields["created_after"] = fields.Date(required=False)
            fetch_fields["created_before"] = fields.Date(required=False)
        if hasattr(self.schema.Meta.model, "updated_at"):
            fetch_fields["updated_after"] = fields.Date(required=False)
            fetch_fields["updated_before"] = fields.Date(required=False)
        for column in getattr(self.schema.Meta.model, "__table__").c:
            if column.primary_key == False and column.name != "created_at" and column.name != "updated_at" and \
                    column.name != "is_deleted" and column.name != "created_by_id":
                fetch_fields[column.name] = fields.Str(required=False)

        self.fetch_schema = Schema.from_dict(fetch_fields)

    @marshal_with(Ref("schema"), code=201, description="Request processed successfully")
    @use_kwargs(Ref('schema'))
    def post(self, payload=None):
        self.app.logger.info("Creating new %s. Payload: %s", self.record_name, str(payload))
        token = None
        if self.resource_protector:
            self.app.logger.debug("Resource protector is present handling authorization")
            token = authenticate(self.resource_protector, self.create_scopes, self.create_permissions)
            if hasattr(payload, "created_by_id"):
                self.app.logger.debug("Found created by field populating session user id")
                setattr(payload, "created_by_id", token.get_user_id())
        # Validating foreign keys and unique constraints
        try:
            validate_foreign_keys(payload, self.db)
            validate_unique_constraints(payload, self.db)
        except ValidationError as ex:
            self.app.logger.debug(f"Failed to create entity {self.record_name}. {ex.message}")
            if self.logger_service:
                self.logger_service.log_failed_creation(f"Failed to create {self.record_name}. {ex.message}",
                                                        payload.__class__, token=token)
            return {"message": ex.message}, 400
        self.service.create(payload)
        if self.logger_service:
            self.logger_service.log_success_creation(f"Created {self.record_name} successfully", payload.__class__,
                                                     payload.id, token=token)
        return payload, 201

    @doc(description="View Records. Currently only supports one column sorting:"
                     "<ul>"
                     "<li>For ascending specify ordering parameter with column name</li>"
                     "<li>For descending specify ordering parameter with a negative sign on the column name e.g. "
                     "<b><i>ordering=-id</i></b></li> "
                     "</ul>")
    @marshal_with(Ref("page_response_schema"), code=200)
    @use_kwargs(Ref("fetch_schema"), location="query")
    def get(self, page_size=None, page=None, ordering=None, q=None, created_after=None, created_before=None,
            updated_after=None, updated_before=None, **kwargs):
        """
        Fetching records
        :param page_size: Pagination page size
        :param page: pagination page starting with 1
        :param ordering: Column ordering
        :param q: Search query param
        :param created_after: From creation date filter
        :param created_before: To creation date filter
        :param updated_after: From updated date filter
        :param updated_before: To updated date filter
        :return: A list of records
        """
        if page_size is None:
            page_size = 10
        if page is None:
            page = 1
        self.app.logger.info(f"Fetching {self.record_name}: Request size %s, page %s", page_size, page)
        if self.resource_protector:
            self.app.logger.debug("Resource protector is present handling authorization")
            authenticate(self.resource_protector, self.fetch_scopes, self.fetch_permissions)
        if hasattr(self.schema.Meta.model, "is_deleted"):
            query = self.schema.Meta.model.query.filter_by(is_deleted=False)
        else:
            query = self.schema.Meta.model.query
        # If q param exists search columns using q param
        if q:
            self.app.logger.debug("Found query param searching columns...")
            search_query = []
            for column in getattr(self.schema.Meta.model, "__table__").c:
                search_query.append(column.like('%' + q + "%"))
            query = query.filter(or_(*search_query))
        # Filter using creation date
        if (created_after or created_before) and hasattr(self.schema.Meta.model, "created_at"):
            self.app.logger.debug("Found created date filter. Filtering created from %s to %s",
                                  created_after, created_before)
            if created_before is None:
                query = query.filter(self.schema.Meta.model.created_at >= created_after)
            elif created_after is None:
                query = query.filter(self.schema.Meta.model.created_at <= created_before)
            else:
                query = query.filter(and_(self.schema.Meta.model.created_at >= created_after,
                                          self.schema.Meta.model.created_at <= created_before))
        # Filter using update date
        if (updated_after or updated_before) and hasattr(self.schema.Meta.model, "updated_at"):
            self.app.logger.debug("Found updated date filter. Filtering updated from %s to %s",
                                  updated_after, updated_before)
            if updated_before is None:
                query = query.filter(self.schema.Meta.model.updated_at >= updated_after)
            elif updated_after is None:
                query = query.filter(self.schema.Meta.model.updated_at <= updated_before)
            else:
                query = query.filter(and_(self.schema.Meta.model.updated_at >= updated_after,
                                          self.schema.Meta.model.updated_at <= updated_before))
        # Filtering using other columns
        if kwargs:
            query = query.filter_by(**kwargs)

        # Ordering query
        if ordering is not None:
            ordering = ordering.strip()
            if ordering[0] == "-":
                query = query.order_by(desc(ordering[1:]))
            else:
                query = query.order_by(asc(ordering))
        else:
            self.app.logger.debug("Ordering(%s) not specified skipping ordering", ordering)

        response = query.paginate(page=page, per_page=page_size)
        return {"count": response.total, "current_page": response.page, "page_size": response.per_page,
                "total_pages": response.pages, "results": response.items}


@marshal_with(ResponseWrapper, code=400, description="Validation errors")
class ChassisResource(MethodResource):
    schema = Schema.from_dict(dict())
    response_schema = Schema.from_dict(dict())

    def __init__(self, app, db, schema, record_name=None, logger_service: LoggerService = None,
                 resource_protector: CustomResourceProtector = None, update_scope: Scope = None,
                 fetch_scope: Scope = None, delete_scope: Scope = None, update_permissions=None,
                 fetch_permissions=None, delete_permissions=None):
        self.app = app
        self.service = ChassisService(app, db, schema.Meta.model)
        self.db = db
        if record_name is None:
            self.record_name = "Resource"
        else:
            self.record_name = record_name

        self.schema = schema

        class ResponseSchema(ResponseWrapper):
            data = fields.Nested(schema)

        class RecordPageSchema(DjangoPageSchema):
            results = fields.List(fields.Nested(schema))

        self.response_schema = ResponseSchema()
        self.page_response_schema = RecordPageSchema()
        self.logger_service = logger_service
        self.resource_protector = resource_protector
        self.update_scopes = update_scope
        self.fetch_scopes = fetch_scope
        self.delete_scopes = delete_scope
        self.update_permissions = update_permissions
        self.fetch_permissions = fetch_permissions
        self.delete_permissions = delete_permissions

    @doc(description="View Record")
    @marshal_with(Ref("schema"), code=200)
    @marshal_with(error_response, code=404)
    def get(self, **kwargs):
        """
        Fetch record using id
        :return: area details on success or error 404 status if area doesn't exist
        """
        if self.resource_protector:
            self.app.logger.debug("Resource protector is present handling authorization")
            authenticate(self.resource_protector, self.fetch_scopes, self.fetch_permissions)
        record_id = None
        for key, value in kwargs.items():
            record_id = value
            break
        primary_column = get_primary_key(self.schema.Meta.model)
        filters = {primary_column.name: record_id}
        if hasattr(self.schema.Meta.model, "is_deleted"):
            filters["is_deleted"] = False
        record = self.schema.Meta.model.query.filter_by(**filters).first()
        if record is None:
            self.app.logger.error("Failed to find record with id %s", record_id)
            return {"status": 404, "errors": {"detail": "Record doesn't exist"}}, 404
        else:
            return record

    # @require_oauth("location.manage_areas", has_any_authority=["change_area"])
    @doc(description="Update Record")
    @use_kwargs(Ref("schema"))
    @marshal_with(Ref("schema"), code=200)
    @marshal_with(val_error_response, code=400, description="Validation errors")
    @marshal_with(error_response, code=404, description="Record doesn't exist")
    def patch(self, *args, **kwargs):
        """
        Updates records
        :param args: additional arguments
        """
        record_id = None
        # Get record id
        for key, value in kwargs.items():
            record_id = value
            break
        # Get payload
        payload = None
        for arg in args:
            if isinstance(arg, self.schema.Meta.model):
                payload = arg
                break
        self.app.logger.info(f"Updating {self.record_name}. Payload: %s.", payload)
        token = None
        if self.resource_protector:
            self.app.logger.debug("Resource protector is present handling authorization")
            token = authenticate(self.resource_protector, self.update_scopes, self.update_permissions)
        try:
            validate_foreign_keys(payload, self.db)
            validate_unique_constraints(payload, self.db, record_id)
            # attrs = inspect.getmembers(payload, lambda a: not (inspect.isroutine(a)))
            # for attr in attrs:
            #     print(attr)
            record = self.service.update(payload, record_id)
            if self.logger_service:
                self.logger_service.log_success_update(f"Updated {self.record_name} successfully",
                                                       payload.__class__, record_id, token=token)
            return record, 200
        except (ConflictError, ValidationError) as ex:
            if self.logger_service:
                self.logger_service.log_failed_update(f"Failed to update {self.record_name}. {ex.message}",
                                                      payload.__class__, record_id, token=token)
            return {"status": 400, "errors": [ex.message]}, 400
        # except ValidationError as ex:
        #     if self.logger_service:
        #         self.logger_service.log_failed_update(f"Failed to update {self.record_name}. {ex.message}",
        #                                               payload.__class__, record_id, token=token)
        #     return {"status": 400, "errors": {"detail": ex.message}}, 400

    @doc(description="Delete Record")
    @marshal_with(Schema(), code=204)
    @marshal_with(val_error_response, code=404, description="Record doesn't exist")
    def delete(self, *args, **kwargs):
        """
        Delete record
        :return: response with status 204 on success
        """
        record_id = None
        for key, value in kwargs.items():
            record_id = value
            break
        # payload = None
        # for arg in args:
        #     if isinstance(self.schema.Meta.model, arg):
        #         payload = arg
        #         payload.id = record_id
        #         break
        self.app.logger.info(f"Deleting {self.record_name} with id %s", record_id)
        token = None
        if self.resource_protector:
            self.app.logger.debug("Resource protector is present handling authorization")
            token = authenticate(self.resource_protector, self.delete_scopes, self.delete_permissions)
        try:
            self.service.delete(record_id)
            if self.logger_service:
                self.logger_service.log_success_deletion(f"Deleted {self.record_name} successfully",
                                                         self.schema.Meta.model.__class__, record_id, token=token)
            return {}, 204
        except ValidationError as ex:
            if self.logger_service:
                self.logger_service.log_failed_deletion(f"Failed to delete {self.record_name}. {ex.message}",
                                                        self.schema.Meta.model.__class__, record_id, token=token)
            return {"errors": [
                "Record doesn't exist"
            ], "status": 404}, 404
