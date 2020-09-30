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