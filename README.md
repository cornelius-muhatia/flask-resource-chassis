# flask-resource-chassis
Extends flask restful api. Actions supported include:
1. Resource Creation
1. Resource Update
1. Listing resource supporting:
    1. Ordering by field
    1. Filtering by field, created_at  and updated_at
    1. Search
1. Delete resource

## Table of Content
- [Installation](#installation)
- [Minimal setup](#minimal-setup)
- [Swagger Documentation](#swagger-documentation)
- [Authorization and Authentication](#authorization-and-authentication)
    - [Scope and Permission Definition](#scopes-and-permission-definition)
- [Audit Logs](#audit-logs)
- [Publish Library](#publishing-to-pypi-repository)

## Installation
Installation with pip
```shell script 
pip install flask-resource-chassis
```
Additional Dependencies
```shell script
pip install flask
pip install flask-apispec
pip install marshmallow-sqlalchemy
pip install Flask-SQLAlchemy
pip install flask-marshmallow
pip install Authlib
pip install flask-restful
pip install requests
```

## Minimal Setup
Here is a simple Flask-Resource-Chassis Application
```python
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from flask_resource_chassis import ChassisResourceList, ChassisResource
from flask_restful import Api

app = Flask(__name__)
db = SQLAlchemy(app)
marshmallow = Marshmallow(app)


class Person(db.Model):
    """
    A simple SQLAlchemy model for interfacing with person sql table
    """
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(254), nullable=False)
    age = db.Column(db.Integer)
    national_id = db.Column(db.String, nullable=False)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)


db.create_all()  # Create tables


class PersonSchema(marshmallow.SQLAlchemyAutoSchema):
    """
    Marshmallow schema for input serialization and output deserialization
    """
    class Meta:
        model = Person
        load_instance = True
        include_fk = True


class PersonApiList(ChassisResourceList):
    """
    Responsible for handling post and listing persons records
    """

    def __init__(self):
        super().__init__(app, db, PersonSchema, "Person Resource")


class PersonApi(ChassisResource):
    """
    Responsible for handling patch, deletion and fetching a single record
    """

    def __init__(self):
        super().__init__(app, db, PersonSchema, "Person Resource")


# Restful api configuration
api = Api(app)
api.add_resource(PersonApiList, "/v1/person/")
api.add_resource(PersonApi, "/v1/person/<int:id>/")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
```
Save the script in run.py  file and run it using python3.
```shell script
python3 run.py
```
You can test the application using curl or Postman. Examples:
1. Creating person
    ```shell script 
    curl --location --request POST 'localhost:5000/v1/person/' \
    --header 'Content-Type: application/json' \
    --data-raw '{
        "full_name": "Test Name",
        "age": 25,
        "national_id": "3434343347"
    }'
    ```
1. Fetch Single Record
    ```shell script 
    curl --location --request GET 'localhost:5000/v1/person/1/'
    ```
1. Update Record
    ```shell script 
    curl --location --request PATCH 'localhost:5000/v1/person/1/' \
    --header 'Content-Type: application/json' \
    --data-raw '{
        "full_name": "Second Test",
        "age": 30,
        "national_id": "453212521"
    }'
    ```
1. Delete Record
    ```shell script
    curl --location --request DELETE 'localhost:5000/v1/person/1/'
    ```
> **A full implementation can be found in [demo folder](demo)**
 
 ## Swagger Documentation
 You can enable swagger documentation by adding the api spec configuration and swagger doc resources. For example from 
 the minimal setup above add the following script after Restful api configuration 
```python 
# Swagger documentation configuration
from apispec import APISpec
from apispec.ext.marshmallow import MarshmallowPlugin
from flask_apispec import FlaskApiSpec
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
```
You should be able  to access swagger-ui from [localhost:5000/swagger-ui](http://localhost:5000/swagger-ui)

## Authorization and Authentication
Authentication is supported using AuthLib ResourceProtector. To enable authentication pass resource protector instance 
on Resource Initialization:
```python
from authlib.oauth2.rfc6750 import BearerTokenValidator
from flask_resource_chassis.utils import RemoteToken, CustomResourceProtector
from flask_resource_chassis import Scope


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


class PersonApiList(ChassisResourceList):
    """
    Responsible for handling post and listing persons records
    """

    def __init__(self):
        super().__init__(app, db, PersonSchema, "Person Resource", resource_protector=resource_protector,
                         create_scope=Scope(scopes="create"), create_permissions=["can_create"],
                         fetch_scope=Scope(scopes="read create", operator="OR"))
```
 ### Scopes and Permission Definition
 1. ChassisResourceList scopes and permissions
     - Define resource creation scopes using `create_scope=Scope(scopes="{scope_name}")` parameter. You can provide multiple
     scopes separating them by space. An operator(OR/AND) is expected for scope comparison i.e. 
     `create_scope=Scope(scopes="scope1 scope2", operator="AND")`
     - For GET(Listing resource) request provide the following scope parameter`fetch_scope=Scope(scopes="{scope_name}")`
     - POST(resource creation) define the following permission parameter `create_permissions=["permission_one", "permission_two"]`
     - GET(Listing resource) define the following permission parameter `fetch_permissions=["permission_one"]`
1. ChassisResource scopes and permissions
    - Scopes for GET(Listing resources) request define using parameter `fetch_scope=Scope(scopes="scope1 scope2 scope3", operator="OR"`)
    - Scopes for PATCH(Update resource) request use parameter `update_scope=Scope(scopes="scope1 scope2", operator="OR")`
    - Scopes for DELETE(Delete resource) request use parameter `delete_scope=Scope(scopes="scope1 scope2", operator="AND")`
    - For GET, PATCH, DELETE permissions use parameters `fetch_permissions=["scope1", "scope2"]`, 
    `update_permissions=["scope1", "scope2"]`, `delete_permissions=["scope1", "scope2"]` respectively.
> Note: All permissions are compared using OR operator

## Audit Logs
For audit logs implement `LoggerService`  class. An example can be found in the [demo](demo)

## Publishing to pypi repository
- Specify release version in [setup.py](setup.py) file.
- Build release files using the following command:
    ```
  python setup.py sdist
  ```
  Release files will be saved in dist/ folder
- Upload distribution to [pypi repository](https://pypi.org):
    ``` 
  twine upload dist/*
  ```