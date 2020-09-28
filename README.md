# flask-resource-chassis
Extends flask restful api. Actions supported include:
1. Resource Creation
1. Resource Update
1. Listing resource supporting:
    1. Ordering by field
1. Delete resource

## Installation
Installation with pip
```shell script 
pip install flask-resource-chassis
```

## Quickstart
Here is a quick setup
```python
from flask import Flask
from apispec import APISpec
from flask_apispec import FlaskApiSpec, doc
from flask_marshmallow import Marshmallow
from flask_restful import Api
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event, Index, Column
from flask_resource_chassis.flask_resource_chassis import ChassisResource, ChassisResourceList, Scope
from flask_resource_chassis.flask_resource_chassis.exceptions import AccessDeniedError
from flask_resource_chassis.flask_resource_chassis.utils import validation_error_handler, CustomResourceProtector, \
    RemoteToken
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

    gender = db.relationship('Gender')


@event.listens_for(Gender.__table__, 'after_create')
def insert_default_grant(target, connection, **kw):
    db.session.add(Gender(gender="Male", is_active=False))
    db.session.add(Gender(gender="Female"))
    db.session.commit()


db.create_all()


class PersonSchema(marshmallow.SQLAlchemyAutoSchema):
    class Meta:
        model = Person
        load_instance = True
        include_fk = True



class DefaultRemoteTokenValidator(BearerTokenValidator):

    def __init__(self, realm=None):
        super().__init__(realm)
        self.token_cls = RemoteToken

    def authenticate_token(self, token_string):
        if token_string == "admin_token":
            return self.token_cls(dict(active="true", scope="create", authorities=["can_create"],
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


@doc(tags=["Test Resource"])
class TestApiList(ChassisResourceList):

    def __init__(self):
        super().__init__(app, db, PersonSchema, "Test Resource", resource_protector=resource_protector,
                         create_scope=Scope(scopes="create"), create_permissions=["can_create"],
                         fetch_scope=Scope(scopes="read create", operator="OR"))


@doc(tags=["Test Resource"])
class TestApi(ChassisResource):

    def __init__(self):
        super().__init__(app, db, PersonSchema, "Test Resource", resource_protector=resource_protector,
                         update_scope=Scope(scopes="update"), delete_scope=Scope(scopes="delete"), 
                         delete_permissions=["can_delete"], update_permissions=["can_create"], 
                         fetch_scope=Scope(scopes="read update delete", operator="OR"))



# Restful api configuration
api = Api(app)
api.add_resource(TestApiList, "/v1/person/")
api.add_resource(TestApi, "/v1/person/<int:id>/")
# Swagger documentation configuration
app.config.update({
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
docs = FlaskApiSpec(app)
docs.register(TestApiList)
docs.register(TestApi)

app.register_error_handler(422, validation_error_handler)


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
```
