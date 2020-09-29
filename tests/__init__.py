# from unittest import TestCase
#
# from apispec import APISpec
# from apispec.ext.marshmallow import MarshmallowPlugin
# from flask import Flask
# from flask_apispec import FlaskApiSpec, doc
# from flask_marshmallow import Marshmallow
# from flask_restful import Api
# from flask_sqlalchemy import SQLAlchemy
# from sqlalchemy import event
#
# from flask_resource_chassis import ChassisResourceList, ChassisResource
# from flask_resource_chassis.utils import validation_error_handler
#
# test_app = Flask(__name__)
#
# db = SQLAlchemy(test_app)
#
# marshmallow = Marshmallow(test_app)
#
#
# class Gender(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     gender = db.Column(db.String(254), nullable=False)
#     is_deleted = db.Column(db.Boolean, nullable=False, default=False)
#     is_active = db.Column(db.Boolean, nullable=False, default=True)
#
#
# class Person(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     full_name = db.Column(db.String(254), nullable=False)
#     age = db.Column(db.Integer)
#     gender_id = db.Column(db.Integer, db.ForeignKey(Gender.id, ondelete='RESTRICT'), nullable=False, doc="Gender Doc")
#     is_deleted = db.Column(db.Boolean, nullable=False, default=False)
#
#     gender = db.relationship('Gender')
#
#
# @event.listens_for(Gender.__table__, 'after_create')
# def insert_default_grant(target, connection, **kw):
#     db.session.add(Gender(gender="Male", is_active=False))
#     db.session.add(Gender(gender="Female"))
#     db.session.commit()
#
#
# class PersonSchema(marshmallow.SQLAlchemyAutoSchema):
#     class Meta:
#         model = Person
#         load_instance = True
#         include_fk = True
#
# #
# # @doc(tags=["Test Resource"])
# # class TestApiList(ChassisResourceList):
# #
# #     def __init__(self):
# #         super().__init__(test_app, db, PersonSchema, "Test Resource")
# #
# #
# # @doc(tags=["Test Resource"])
# # class TestApi(ChassisResource):
# #
# #     def __init__(self):
# #         super().__init__(test_app, db, PersonSchema, "Test Resource")
# #
# #
# # # Restful api configuration
# # api = Api(test_app)
# # api.add_resource(TestApiList, "/v1/person")
# # api.add_resource(TestApi, "/v1/person/<int:id>/")
# # # Swagger documentation configuration
# # test_app.config.update({
# #     'APISPEC_SPEC': APISpec(
# #         title='Test Chassis Service',
# #         version='1.0.0-b1',
# #         openapi_version="2.0",
# #         # openapi_version="3.0.2",
# #         plugins=[MarshmallowPlugin()],
# #         info=dict(
# #             description="Handles common resources shared by the entire architecture",
# #             license={
# #                 "name": "Apache 2.0",
# #                 "url": "https://www.apache.org/licenses/LICENSE-2.0.html"
# #             }
# #         )
# #     ),
# #     'APISPEC_SWAGGER_URL': '/swagger/',
# # })
# # docs = FlaskApiSpec(test_app)
# # docs.register(TestApiList)
# # docs.register(TestApi)
# #
# # test_app.register_error_handler(422, validation_error_handler)
# #
# # if __name__ == '__main__':
# #     test_app.run(debug=True, host='0.0.0.0', port=5011)