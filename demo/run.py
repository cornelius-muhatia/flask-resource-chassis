# Copyright (C)  Authors and contributors All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
from datetime import datetime

from authlib.oauth2.rfc6750 import BearerTokenValidator
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from flask_restful import Api
from sqlalchemy import Column, Index, func, event

from flask_resource_chassis.flask_resource_chassis import LoggerService, ChassisResourceList, ChassisResource, Scope
from flask_resource_chassis.flask_resource_chassis.exceptions import AccessDeniedError
from flask_resource_chassis.flask_resource_chassis.utils import RemoteToken, CustomResourceProtector

from apispec import APISpec
from apispec.ext.marshmallow import MarshmallowPlugin
from flask_apispec import FlaskApiSpec
from authlib.oauth2.rfc6750 import InsufficientScopeError, InvalidTokenError

app = Flask(__name__)
db = SQLAlchemy(app)
marshmallow = Marshmallow(app)


class Gender(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    gender = db.Column(db.String(254), nullable=False)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class Person(db.Model):
    """
    A simple SQLAlchemy model for interfacing with person sql table
    """
    __table_args__ = (Index("unique_national_id", "national_id", unique=True,
                            postgresql_where=(Column("is_deleted").isnot(True)),
                            sqlite_where=Column('is_deleted').isnot(True)),)
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(254), nullable=False)
    age = db.Column(db.Integer)
    gender_id = db.Column(db.Integer, db.ForeignKey(Gender.id, ondelete='RESTRICT'), nullable=False, doc="Gender Doc")
    national_id = db.Column(db.String, nullable=False)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    created_by_id = db.Column(db.Text())
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), default=datetime.utcnow)

    gender = db.relationship('Gender')


@event.listens_for(Gender.__table__, 'after_create')
def insert_default_grant(target, connection, **kw):
    db.session.add(Gender(gender="Male", is_active=False))
    db.session.add(Gender(gender="Female"))
    db.session.commit()


db.create_all()  # Create tables


class PersonSchema(marshmallow.SQLAlchemyAutoSchema):
    """
    Marshmallow schema for input serialization and output deserialization
    """

    class Meta:
        model = Person
        load_instance = True
        include_fk = True


class DefaultRemoteTokenValidator(BearerTokenValidator):
    """
    Mock token validator for testing
    """

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


class CustomAuditLogger(LoggerService):

    def log_success_creation(self, description, entity, record_id=None, token: RemoteToken = None):
        app.logger.info(f"============= Audit Trails ============= \nActivity: Creation\nStatus: Completed\n"
                        f"Description: {description}\nEntity: {str(entity)}\nRecord ID: {record_id}\n"
                        f"User id: {token.get_user_id()}")

    def log_failed_creation(self, description, entity, token: RemoteToken = None):
        app.logger.error(f"============= Audit Trails ============= \nActivity: Creation\nStatus: Failed\n"
                         f"Description: {description}\nEntity: {str(entity)}\nUser id: {token.get_user_id()}")

    def log_success_update(self, description, entity, record_id, notes="", token: RemoteToken = None):
        app.logger.info(f"============= Audit Trails ============= \nActivity: Update\nStatus: Completed\n"
                        f"Description: {description}\nEntity: {str(entity)}\nRecord ID: {record_id}\n"
                        f"User id: {token.get_user_id()}")

    def log_failed_update(self, description, entity, record_id, notes="", token: RemoteToken = None):
        app.logger.error(f"============= Audit Trails ============= \nActivity: Update\nStatus: Failed\n"
                         f"Description: {description}\nEntity: {str(entity)}\nUser id: {token.get_user_id()}")

    def log_failed_deletion(self, description, entity, record_id, notes="", token: RemoteToken = None):
        app.logger.error(f"============= Audit Trails ============= \nActivity: Deletion\nStatus: Failed\n"
                         f"Description: {description}\nEntity: {str(entity)}\nUser id: {token.get_user_id()}")

    def log_success_deletion(self, description, entity, record_id, notes="", token: RemoteToken = None):
        app.logger.info(f"============= Audit Trails ============= \nActivity: Deletion\nStatus: Completed\n"
                        f"Description: {description}\nEntity: {str(entity)}\nRecord ID: {record_id}\n"
                        f"User id: {token.get_user_id()}")


class PersonApiList(ChassisResourceList):
    """
    Responsible for handling post and listing persons records
    """

    def __init__(self):
        super().__init__(app, db, PersonSchema, "Person Resource", resource_protector=resource_protector,
                         create_scope=Scope(scopes="create"), create_permissions=["can_create"],
                         fetch_scope=Scope(scopes="read create", operator="OR"),
                         fetch_permissions=["can_read", "can_update", "can_delete", "can_read"],
                         logger_service=CustomAuditLogger())


class PersonApi(ChassisResource):
    """
    Responsible for handling patch, deletion and fetching a single record
    """

    def __init__(self):
        super().__init__(app, db, PersonSchema, "Person Resource", resource_protector=resource_protector,
                         update_scope=Scope(scopes="update"), delete_scope=Scope(scopes="delete"),
                         delete_permissions=["can_delete"], update_permissions=["can_update"],
                         fetch_scope=Scope(scopes="read update delete", operator="OR"),
                         fetch_permissions=["can_read", "can_update", "can_delete", "can_read"],
                         logger_service=CustomAuditLogger())


# Restful api configuration
api = Api(app)
api.add_resource(PersonApiList, "/v1/person/")
api.add_resource(PersonApi, "/v1/person/<int:id>/")
# Swagger documentation configuration
app.config.update({
    'APISPEC_SPEC': APISpec(
        title='Test Chassis Service',
        version='1.0.0-b1',
        openapi_version="2.0",
        plugins=[MarshmallowPlugin()],
        info=dict(
            description="Flask resource chassis swagger documentation demo",
            license={
                "name": "Apache 2.0",
                "url": "https://www.apache.org/licenses/LICENSE-2.0.html"
            }
        )
    ),
    'APISPEC_SWAGGER_URL': '/swagger/',
})

docs = FlaskApiSpec(app)
docs.register(PersonApiList)
docs.register(PersonApi)


@app.errorhandler(InvalidTokenError)
def unauthorized(error):
    app.logger.error("Authorization error: %s", error)
    return {"message": "You are not authorized to perform this request. "
                       "Ensure you have a valid credentials before trying again"}, 401


@app.errorhandler(AccessDeniedError)
def access_denied(error):
    app.logger.error("Access denied error: %s", error)
    return {"message": "Sorry you don't have sufficient permissions to access this resource"}, 403


@app.errorhandler(InsufficientScopeError)
def scope_access_denied(error):
    app.logger.error("Access denied error: %s", error)
    return {"message": "The access token has insufficient scopes to access resource. "
                       "Ensure the Oauth2 client as the required scope"}, 403


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5010)
