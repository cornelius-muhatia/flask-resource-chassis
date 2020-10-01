# from unittest import TestCase
from datetime import datetime

from apispec import APISpec
from apispec.ext.marshmallow import MarshmallowPlugin
from authlib.oauth2.rfc6750 import InsufficientScopeError, BearerTokenValidator, InvalidTokenError
from flask import Flask
from flask_apispec import FlaskApiSpec, doc
from flask_marshmallow import Marshmallow
# from flask_restful import Api
from flask_restful import Api
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event, func, Column, Index

from flask_resource_chassis.flask_resource_chassis import ChassisResourceList, ChassisResource, Scope
from flask_resource_chassis.flask_resource_chassis.exceptions import AccessDeniedError
from flask_resource_chassis.flask_resource_chassis.utils import validation_error_handler, CustomResourceProtector, \
    RemoteToken

test_app = Flask(__name__)

db = SQLAlchemy(test_app)

marshmallow = Marshmallow(test_app)


class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(254), nullable=False)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)


class Gender(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    gender = db.Column(db.String(254), nullable=False)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class Person(db.Model):
    __table_args__ = (Index("unique_national_id", "national_id", unique=True,
                            postgresql_where=(Column("is_deleted").isnot(True)),
                            sqlite_where=Column('is_deleted').isnot(True)),)
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(254), nullable=False)
    age = db.Column(db.Integer)
    gender_id = db.Column(db.Integer, db.ForeignKey(Gender.id, ondelete='RESTRICT'), nullable=False, doc="Gender Doc")
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), default=datetime.utcnow)
    national_id = db.Column(db.String)
    location_id = db.Column(db.Integer, db.ForeignKey(Location.id, ondelete='RESTRICT'), doc="Location")

    gender = db.relationship('Gender')


@event.listens_for(Gender.__table__, 'after_create')
def insert_default_grant(target, connection, **kw):
    db.session.add(Gender(gender="Male", is_active=False))
    db.session.add(Gender(gender="Female"))
    db.session.commit()


@event.listens_for(Location.__table__, 'after_create')
def insert_default_grant(target, connection, **kw):
    db.session.add(Location(name="Mars"))
    db.session.add(Location(name="Earth"))
    db.session.commit()


db.create_all()


class DefaultRemoteTokenValidator(BearerTokenValidator):

    def __init__(self, realm=None):
        super().__init__(realm)
        self.token_cls = RemoteToken

    def authenticate_token(self, token_string):
        if token_string == "admin_token":
            return self.token_cls(dict(active="true", scope="create update delete",
                                       authorities=["can_create", "can_update", "can_delete"],
                                       user_id="26957b74-47d0-40df-96a1-f104f3828552"))
        elif token_string == "guest_token":
            return self.token_cls(dict(active="true", scope="", authorities=[],
                                       user_id="26957b74-47d0-40df-96a1-f104f3828552"))
        else:
            return None

    def request_invalid(self, request):
        return False

    def token_revoked(self, token):
        return token.is_revoked()


resource_protector = CustomResourceProtector()
resource_protector.register_token_validator(DefaultRemoteTokenValidator())


class PersonSchema(marshmallow.SQLAlchemyAutoSchema):
    class Meta:
        model = Person
        load_instance = True
        include_fk = True


@doc(tags=["Test Resource"])
class TestApiList(ChassisResourceList):

    def __init__(self):
        super().__init__(test_app, db, PersonSchema, "Test Resource", resource_protector=resource_protector,
                         create_scope=Scope(scopes="create"), create_permissions=["can_create"],
                         fetch_scope=Scope(scopes="read create", operator="OR"))


@doc(tags=["Test Resource"])
class TestApi(ChassisResource):

    def __init__(self):
        super().__init__(test_app, db, PersonSchema, "Test Resource", resource_protector=resource_protector,
                         update_scope=Scope(scopes="update"), delete_scope=Scope(scopes="delete"),
                         delete_permissions=["can_delete"], update_permissions=["can_update"],
                         fetch_scope=Scope(scopes="read update delete", operator="OR"))


# Restful api configuration
api = Api(test_app)
api.add_resource(TestApiList, "/v1/person")
api.add_resource(TestApi, "/v1/person/<int:id>")
# Swagger documentation configuration
test_app.config.update({
    'APISPEC_SPEC': APISpec(
        title='Test Chassis Service',
        version='1.0.0-b1',
        openapi_version="2.0",
        # openapi_version="3.0.2",
        plugins=[MarshmallowPlugin()],
        info=dict(
            description="Handles common resources shared by the entire architecture",
            license={
                "name": "Apache 2.0",
                "url": "https://www.apache.org/licenses/LICENSE-2.0.html"
            }
        )
    ),
    'APISPEC_SWAGGER_URL': '/swagger/',
})
docs = FlaskApiSpec(test_app)
docs.register(TestApiList)
docs.register(TestApi)

test_app.register_error_handler(422, validation_error_handler)


@test_app.errorhandler(InvalidTokenError)
def unauthorized(error):
    test_app.logger.error("Authorization error: %s", error)
    return {"message": "You are not authorized to perform this request. "
                       "Ensure you have a valid credentials before trying again"}, 401


@test_app.errorhandler(AccessDeniedError)
def access_denied(error):
    test_app.logger.error("Access denied error: %s", error)
    return {"message": "Sorry you don't have sufficient permissions to access this resource"}, 403


@test_app.errorhandler(InsufficientScopeError)
def scope_access_denied(error):
    test_app.logger.error("Access denied error: %s", error)
    return {"message": "The access token has insufficient scopes to access resource. "
                       "Ensure the Oauth2 client as the required scope"}, 403
