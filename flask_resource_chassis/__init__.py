import inspect

from flask import jsonify
from flask_apispec import use_kwargs, marshal_with, doc, MethodResource, Ref
from marshmallow import Schema, fields
from sqlalchemy import desc, asc, CheckConstraint, not_

from .exceptions import ConflictError, ValidationError
from .schemas import ResponseWrapper, DjangoPageSchema, error_response, val_error_response
from .services import ChassisService, LoggerService, get_primary_key
from authlib.oauth2.rfc6749 import TokenMixin
from authlib.oauth2.rfc6750 import InsufficientScopeError, InvalidTokenError

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
                filters = {
                    "is_deleted": False,
                    key.column.name: getattr(model, "__dict__").get(column.name)
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
                filters[column.name] = model.__dict__[column.name]

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
    response_schema = Schema.from_dict(dict())
    page_response_schema = Schema.from_dict(dict())

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

        class ResponseSchema(ResponseWrapper):
            data = fields.Nested(schema)

        class RecordPageSchema(DjangoPageSchema):
            results = fields.List(fields.Nested(schema))

        self.response_schema = ResponseSchema()
        self.page_response_schema = RecordPageSchema()
        self.logger_service = logger_service
        self.resource_protector = resource_protector
        self.create_scopes = create_scope
        self.fetch_scopes = fetch_scope
        self.create_permissions = create_permissions
        self.fetch_permissions = fetch_permissions

    @marshal_with(Ref("response_schema"), code=201, description="Request processed successfully")
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
        return {"message": "Request was successful", "data": payload}, 201

    # @require_oauth(has_any_authority=["view_area", "add_area", "change_area"])
    @doc(description="View Records. Currently only supports one column sorting:"
                     "<ul>"
                     "<li>For ascending specify ordering parameter with column name</li>"
                     "<li>For descending specify ordering parameter with a negative sign on the column name e.g. "
                     "<b><i>ordering=-id</i></b></li> "
                     "</ul>")
    @marshal_with(Ref("page_response_schema"), code=200)
    @use_kwargs({"page_size": fields.Int(required=False), "page": fields.Int(required=False),
                 "ordering": fields.Str(required=False)}, location="query")
    def get(self, page_size=None, page=None, ordering=None):
        """
        Fetching records
        :param page_size: Pagination page size
        :param page: pagination page starting with 1
        :param ordering: Column ordering
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
        query = self.schema.Meta.model.query.filter_by(is_deleted=False)
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
        record = self.schema.Meta.model.query.filter_by(id=record_id, is_deleted=False).first()
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
                payload.id = record_id
                break
        self.app.logger.info(f"Updating {self.record_name}. Payload: %s.", payload)
        token = None
        if self.resource_protector:
            self.app.logger.debug("Resource protector is present handling authorization")
            token = authenticate(self.resource_protector, self.update_scopes, self.update_permissions)
        try:
            validate_foreign_keys(payload, self.db)
            validate_unique_constraints(payload, self.db, True)
            # attrs = inspect.getmembers(payload, lambda a: not (inspect.isroutine(a)))
            # for attr in attrs:
            #     print(attr)
            record = self.service.update(payload, record_id)
            if self.logger_service:
                self.logger_service.log_success_update(f"Updated {self.record_name} successfully",
                                                       payload.__class__, payload.id, token=token)
            return record
        except ConflictError as ex:
            if self.logger_service:
                self.logger_service.log_failed_update(f"Failed to update {self.record_name}. {ex.message}",
                                                      payload.__class__, payload.id, token=token)
            return {"status": 400, "errors": [ex.message]}, 400
        except ValidationError as ex:
            if self.logger_service:
                self.logger_service.log_failed_update(f"Failed to update {self.record_name}. {ex.message}",
                                                      payload.__class__, payload.id, token=token)
            return {"status": 404, "errors": {"detail": ex.message}}, 404

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
        payload = None
        for arg in args:
            if isinstance(self.schema.Meta.model, arg):
                payload = arg
                payload.id = record_id
                break
        self.app.logger.info(f"Deleting {self.record_name} with id %s", record_id)
        token = None
        if self.resource_protector:
            self.app.logger.debug("Resource protector is present handling authorization")
            token = authenticate(self.resource_protector, self.delete_scopes, self.delete_permissions)
        try:
            self.service.delete(record_id)
            if self.logger_service:
                self.logger_service.log_success_deletion(f"Deleted {self.record_name} successfully",
                                                         payload.__class__, record_id, token=token)
            return {}, 204
        except ValidationError as ex:
            if self.logger_service:
                self.logger_service.log_failed_deletion(f"Failed to delete {self.record_name}. {ex.message}",
                                                        payload.__class__, record_id, token=token)
            return {"errors": [
                "Record doesn't exist"
            ], "status": 404}, 404