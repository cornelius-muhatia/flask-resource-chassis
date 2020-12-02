import functools
import time
import unittest
import urllib.parse
import uuid
from abc import ABC
from collections import Iterable
from datetime import datetime, timedelta

import requests
from authlib.integrations.flask_oauth2 import ResourceProtector
from authlib.oauth2.rfc6749 import MissingAuthorizationError, TokenMixin
from authlib.oauth2.rfc6750 import BearerTokenValidator, InvalidTokenError
from flask import json
from requests.auth import HTTPBasicAuth
from sqlalchemy import TypeDecorator, CHAR

from .exceptions import AccessDeniedError
from .schemas import ResponseWrapper
from sqlalchemy.dialects.postgresql import UUID


def unauthorized(error):
    print("Authorization error", error)
    return {"message": "You are not authorized to perform this request. "
                       "Ensure you have a valid credentials before trying again"}, 401


def validation_error_handler(err):
    """
    Used to parse use_kwargs validation errors
    """
    headers = err.data.get("headers", None)
    messages = err.data.get("messages", ["Invalid request."])
    schema = ResponseWrapper()
    data = messages.get("json", None)
    error_msg = "Sorry validation errors occurred"
    if headers:
        return schema.dump({"data": data, "message": error_msg}), 400, headers
    else:
        return schema.dump({"data": data, "message": error_msg}), 400


class DefaultRemoteTokenValidator(BearerTokenValidator):

    def __init__(self, token_introspect_url, client_id, client_secret, realm=None):
        super().__init__(realm)
        self.token_cls = RemoteToken
        self.token_introspect_url = token_introspect_url
        self.client_id = client_id
        self.client_secret = client_secret

    def authenticate_token(self, token_string):
        res = requests.post(self.token_introspect_url, data={'token': token_string},
                            auth=HTTPBasicAuth(self.client_id, self.client_secret))
        print("Retrospect token response", res.status_code, res.json())
        if res.ok:
            return self.token_cls(res.json())

        return None

    def request_invalid(self, request):
        return False

    def token_revoked(self, token):
        return token.is_revoked()


class RemoteToken(TokenMixin):

    def __init__(self, token):
        self.token = token

    def get_client_id(self):
        return self.token.get('client_id', None)

    def get_scope(self):
        return self.token.get('scope', None)

    def get_expires_in(self):
        return self.token.get('exp', 0)

    def get_expires_at(self):
        expires_at = self.get_expires_in() + self.token.get('iat', 0)
        if expires_at == 0:
            expires_at = time.time() + 3600  # Expires in an hour
        return expires_at

    def is_revoked(self):
        return not self.token.get('active', False)

    def get_authorities(self):
        return self.token.get("authorities", [])

    def get_user_id(self):
        return self.token.get("user_id", None)


class CustomResourceProtector(ResourceProtector):
    def __call__(self, scope=None, operator='AND', optional=False, has_any_authority=None):
        """
        Adds authority/permission validation

        :param scope: client scope
        :param operator:
        :param optional:
        :param has_any_authority: User/oauth client permissions
        :return: decorator function
        """

        def wrapper(f):
            @functools.wraps(f)
            def decorated(*args, **kwargs):
                try:
                    token = self.acquire_token(scope, operator)
                    if token is None:
                        raise Exception(f"Validating token request. {str(token)}")
                    args = args + (token,)
                    if has_any_authority:
                        def filter_permission(perm):
                            if perm in has_any_authority:
                                return True
                            else:
                                return False

                        filters = filter(filter_permission, token.get_authorities())
                        if not any(filters):
                            raise AccessDeniedError()
                except MissingAuthorizationError as error:
                    print("Authentication error ", error)
                    if optional:
                        return f(*args, **kwargs)
                    # self.raise_error_response(error)
                    raise InvalidTokenError(error.description)
                return f(*args, **kwargs)

            return decorated

        return wrapper


def is_valid_uuid(val):
    """
    Check if a string is a valid uuid
    :param val: uuid String
    :return: Returns true if is a string is a valid uuid else False
    """
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False


class TestChassis:

    def __init__(self, http_client, endpoint="/v1", schema=None, test_case=None, admin_token=None,
                 guest_token=None):
        self.client = http_client
        self.test_case = test_case if test_case else unittest.TestCase()
        self.admin_token = admin_token
        self.guest_token = guest_token
        self.schema = schema
        self.resource_name = schema.Meta.model.__name__
        self.endpoint = endpoint

    def get_primary_key(self, entity=None):
        """
        Gets primary key column from entity
        :param entity: SqlAlchemy model
        :return: SqlAlchemy Column
        """
        if entity is None:
            entity = self.schema.Meta.model
        for column in getattr(entity, "__table__").c:
            if column.primary_key:
                return column
        return None

    def creation_test(self, payload, unique_fields=None, rel_fields=None):
        """
        Record creation tests. Unit tests:
        1. Authorization test if guest or admin token are supplied
        2. ACL test if guest token is present
        3. Validation Test (Including unique fields and rel_fields tests if provided)
        4. Success Tests

        :param payload: Request payload
        :param unique_fields: Unique fields
        :param rel_fields: Relational fields
        """
        if self.admin_token or self.guest_token:
            response = self.client.post(self.endpoint,
                                        content_type='application/json',
                                        data=json.dumps(payload))
            self.test_case.assertEqual(response.status_code, 401,
                                       f"{self.resource_name} creation authorization test. {str(response.json)}")
        if self.guest_token:
            response = self.client.post(self.endpoint,
                                        headers={"Authorization": f"Bearer {self.guest_token}"},
                                        content_type='application/json',
                                        data=json.dumps(payload))
            self.test_case.assertEqual(response.status_code, 403,
                                       f"{self.resource_name} creation ACL test.")
        if self.admin_token:
            response = self.client.post(self.endpoint,
                                        headers={"Authorization": f"Bearer {self.admin_token}"},
                                        content_type='application/json',
                                        data=json.dumps(payload))
        else:
            response = self.client.post(self.endpoint,
                                        content_type='application/json',
                                        data=json.dumps(payload))
        self.test_case.assertEqual(response.status_code, 201,
                                   f"{self.resource_name} creation success test.")
        if self.admin_token:
            response = self.client.get(f"{self.endpoint}/{response.json.get('id')}",
                                       headers={"Authorization": f"Bearer {self.admin_token}"},
                                       content_type='application/json')
        else:
            response = self.client.get(f"{self.endpoint}/{response.json.get('id')}",
                                       content_type='application/json')
        self.test_case.assertEqual(response.status_code, 200,
                                   f"{self.resource_name} fetch single record success test.")
        self.verify_fields(payload, response)

        if unique_fields:
            if self.admin_token:
                response = self.client.post(self.endpoint,
                                            headers={"Authorization": f"Bearer {self.admin_token}"},
                                            content_type='application/json',
                                            data=json.dumps(payload))
            else:
                response = self.client.post(self.endpoint,
                                            content_type='application/json',
                                            data=json.dumps(payload))
            self.test_case.assertEqual(response.status_code, 400, f"{self.resource_name} creation unique test.")
        if rel_fields:
            for rel_field in rel_fields:
                payload2 = payload.copy()
                if is_valid_uuid(rel_field):
                    payload2[rel_field] = str(uuid.uuid4())
                else:
                    payload2[rel_field] = 34111
                response = self.client.post(self.endpoint,
                                            headers={"Authorization": f"Bearer {self.admin_token}"},
                                            content_type='application/json',
                                            data=json.dumps(payload2))
                self.test_case.assertEqual(response.status_code, 400,
                                           f"{self.resource_name} creation {rel_field} validation test.")

    def fetch_test(self, *args):
        """
        Test fetch and filter. Test cases:
        1. Authorization test if guest or admin token are supplied
        2. ACL test if guest token is present
        3. Validation Test (Including unique fields and rel_fields tests if provided)
        4. Success Tests

        :param args: Models arguments
        """
        entity_id = getattr(args[0], self.get_primary_key(args[0]).name)
        payload = getattr(args[0], "_sa_instance_state").object.__dict__
        if self.admin_token or self.guest_token:
            response = self.client.get(self.endpoint)
            self.test_case.assertEqual(response.status_code, 401,
                                       f"{self.resource_name} fetch authorization test.")
        if self.guest_token:
            response = self.client.get(self.endpoint, headers={"Authorization": f"Bearer {self.guest_token}"})
            self.test_case.assertEqual(response.status_code, 403,
                                       f"{self.resource_name} fetch ACL test.")

        if self.admin_token:
            response = self.client.get(f"{self.endpoint}",
                                       headers={"Authorization": f"Bearer {self.admin_token}"})
        else:
            response = self.client.get(f"{self.endpoint}",
                                       content_type='application/json')
        self.test_case.assertEqual(response.status_code, 200,
                                   f"{self.resource_name} fetch record success test.")
        self.test_case.assertTrue((response.json.get("count") >= len(args)),
                                  f"Fetch {self.resource_name} test verify count")
        self.test_case.assertTrue((response.json.get("current_page") == 1),
                                  f"Fetch {self.resource_name} test verify page")

        # Test filters
        primary_column = None
        from sqlalchemy.sql.sqltypes import Integer, String
        for column in getattr(args[0], "__table__").c:
            query = urllib.parse.urlencode({column.name: payload.get(column.name)})
            if column.primary_key:
                primary_column = column
            elif column.name == "created_at":  # Found date time column applying date filter
                self.handle_creation_test(len(args))
            elif column.name == "updated_at":
                self.handle_update_at_test(len(args))
            elif isinstance(column.type, Integer) and payload.get(column.name):
                query2 = urllib.parse.urlencode({column.name: "-999999999"})
                if self.admin_token:
                    response = self.client.get(f"{self.endpoint}?{query}",
                                               headers={"Authorization": f"Bearer {self.admin_token}"})
                    response2 = self.client.get(f"{self.endpoint}?{query2}",
                                                headers={"Authorization": f"Bearer {self.admin_token}"})
                else:
                    response = self.client.get(f"{self.endpoint}?{query}")
                    response2 = self.client.get(f"{self.endpoint}?{query2}")
                self.test_case.assertTrue((response.json.get("count") >= 1),
                                          f"Fetch {self.resource_name} test verify {column.name} count")
                self.test_case.assertEqual(response2.json.get("count"), 0,
                                           f"Fetch {self.resource_name} test verify {column.name} count")
            elif isinstance(column.type, String) and payload.get(column.name) is not None:
                if self.admin_token:
                    response = self.client.get(f"{self.endpoint}?{query}",
                                               headers={"Authorization": f"Bearer {self.admin_token}"})
                    response2 = self.client.get(f"{self.endpoint}?{column.name}={str(uuid.uuid4())}",
                                                headers={"Authorization": f"Bearer {self.admin_token}"})
                else:
                    response = self.client.get(f"{self.endpoint}?{query}")
                    response2 = self.client.get(f"{self.endpoint}?{column.name}={str(uuid.uuid4())}",
                                                headers={"Authorization": f"Bearer {self.admin_token}"})
                self.test_case.assertTrue((response.json.get("count") >= 1),
                                          f"Fetch {self.resource_name} test verify {column.name} count")
                self.test_case.assertEqual(response2.json.get("count"), 0,
                                           f"Fetch {self.resource_name} test verify {column.name} count")
        # Test search
        if self.admin_token:
            response = self.client.get(f"{self.endpoint}?q={str(uuid.uuid4())}",
                                       headers={"Authorization": f"Bearer {self.admin_token}"})
        else:
            response = self.client.get(f"{self.endpoint}?q={str(uuid.uuid4())}")
        self.test_case.assertEqual(response.json.get("count"), 0,
                                   f"Search {self.resource_name} test verify result count")
        # Test ordering
        if len(args) > 1 and payload.get("created_at"):
            if self.admin_token:
                response = self.client.get(f"{self.endpoint}?ordering=created_at",
                                           headers={"Authorization": f"Bearer {self.admin_token}"})
                response2 = self.client.get(f"{self.endpoint}?ordering=-created_at",
                                            headers={"Authorization": f"Bearer {self.admin_token}"})
            else:
                response = self.client.get(f"{self.endpoint}?ordering=created_at")
                response2 = self.client.get(f"{self.endpoint}?ordering=-created_at")
            self.test_case.assertLess(response.json.get('results')[0].get('created_at'),
                                      response.json.get('results')[1].get('created_at'),
                                      f"Ordering {self.resource_name} by ascending")
            self.test_case.assertGreater(response2.json.get('results')[0].get('created_at'),
                                         response2.json.get('results')[1].get('created_at'),
                                         f"Ordering {self.resource_name} by descending")

    def handle_creation_test(self, entities_count):
        """
        Handle created_at date filter
        :param entities_count: Available saved records in the database
        """
        if self.admin_token:
            response = self.client.get(f"{self.endpoint}?created_before=1997-01-01",
                                       headers={"Authorization": f"Bearer {self.admin_token}"})
        else:
            response = self.client.get(f"{self.endpoint}?created_before=1997-01-01")
        self.test_case.assertEqual(response.status_code, 200, f"{self.resource_name} creation date before filter test")
        self.test_case.assertEqual(response.json.get("count"), 0,
                                   f"{self.resource_name} creation date before filter count test")

        before_date = datetime.now() + timedelta(days=1)
        before_date = before_date.strftime('%Y-%m-%d')
        if self.admin_token:
            response = self.client.get(f"{self.endpoint}?created_before=" + before_date,
                                       headers={"Authorization": f"Bearer {self.admin_token}"})
        else:
            response = self.client.get(f"{self.endpoint}?created_before=" + before_date)
        self.test_case.assertEqual(response.status_code, 200, f"{self.resource_name} creation date before filter test")
        self.test_case.assertTrue(response.json.get("count") >= entities_count,
                                  f"{self.resource_name} creation date before filter count {entities_count} test")
        if self.admin_token:
            response = self.client.get(f"{self.endpoint}?created_after=" + before_date,
                                       headers={"Authorization": f"Bearer {self.admin_token}"})
        else:
            response = self.client.get(f"{self.endpoint}?created_after=" + before_date)
        self.test_case.assertEqual(response.status_code, 200, f"{self.resource_name} creation date before filter test")
        self.test_case.assertEqual(response.json.get("count"), 0,
                                   f"{self.resource_name} creation date before filter count test")

        if self.admin_token:
            response = self.client.get(f"{self.endpoint}?created_before=1997-01-01&created_after=1997-01-02",
                                       headers={"Authorization": f"Bearer {self.admin_token}"})
        else:
            response = self.client.get(f"{self.endpoint}?created_before=1997-01-01&created_after=1997-01-02")
        self.test_case.assertEqual(response.status_code, 200,
                                   f"{self.resource_name} creation date before and after filter test")
        self.test_case.assertEqual(response.json.get("count"), 0,
                                   f"{self.resource_name} creation date before and after filter count test")

    def handle_update_at_test(self, entities_count):
        """
        Handle update_at date filter unit tests
        :param entities_count: Available saved records in the database
        """
        before_date = datetime.now() + timedelta(days=1)
        before_date = before_date.strftime('%Y-%m-%d')
        if self.admin_token:
            response = self.client.get(f"{self.endpoint}?updated_before=" + before_date,
                                       headers={"Authorization": f"Bearer {self.admin_token}"})
        else:
            response = self.client.get(f"{self.endpoint}?updated_before=" + before_date)
        self.test_case.assertEqual(response.status_code, 200,
                                   f"{self.resource_name} Updated before " + str(response.json))
        self.test_case.assertTrue(response.json.get("count") >= entities_count)
        self.test_case.assertEqual(response.json.get("current_page"), 1)
        if self.admin_token:
            response = self.client.get(f"{self.endpoint}?updated_after=" + before_date,
                                       headers={"Authorization": f"Bearer {self.admin_token}"})
        else:
            response = self.client.get(f"{self.endpoint}?updated_after=" + before_date)
        self.test_case.assertEqual(response.status_code, 200,
                                   f"{self.resource_name} Updated before " + str(response.json))
        self.test_case.assertEqual(response.json.get("count"), 0)
        self.test_case.assertEqual(response.json.get("current_page"), 1)
        if self.admin_token:
            response = self.client.get(f"{self.endpoint}?updated_before=1997-01-01&updated_after=1997-01-02",
                                       headers={"Authorization": f"Bearer {self.admin_token}"})
        else:
            response = self.client.get(f"{self.endpoint}?updated_before=1997-01-01&updated_after=1997-01-02")
        self.test_case.assertEqual(response.status_code, 200,
                                   f"{self.resource_name} Updated before and after creation date filter test")
        self.test_case.assertEqual(response.json.get("count"), 0,
                                   f"{self.resource_name} Updated before and after creation date filter count test")

    def verify_fields(self, payload, response):
        """
        Verify payload fields against response field or saved database entity

        :param payload: Request json payload
        :param response: Request json response
        """
        primary_column = self.get_primary_key()
        filters = {primary_column.name: response.json.get(primary_column.name)}
        db_entity = self.schema.Meta.model.query.filter_by(**filters).first()
        for key, value in payload.items():
            if isinstance(value, Iterable) and not isinstance(value, str):
                pass
            elif hasattr(self.schema.Meta, "load_only"):
                if key not in self.schema.Meta.load_only:
                    self.test_case.assertEqual(value, response.json.get(key),
                                               f"{self.resource_name} {key} verification")
                else:
                    pass
                    # Implement mechanism for ignoring other attributes
                    # self.test_case.assertEqual(value, getattr(db_entity, key),
                    #                            f"{self.resource_name} {key} verification")
            else:
                self.test_case.assertEqual(value, response.json.get(key), f"{self.resource_name} {key} verification")

    def updated_test(self, record_id, payload, rel_fields=None):
        """
        Handles update tests. Tests include:
        1. Authorization tests
        2. ACL tests
        3. Required field and foreign key validation tests

        :param record_id: Record id
        :param payload: Request payload
        :param rel_fields: Relational fields
        """
        if self.admin_token or self.guest_token:
            response = self.client.patch(self.endpoint + "/" + str(record_id),
                                         content_type='application/json',
                                         data=json.dumps(payload))
            self.test_case.assertEqual(response.status_code, 401,
                                       f"{self.resource_name} update authorization test. {str(response.json)}")
        if self.guest_token:
            response = self.client.patch(self.endpoint + "/" + str(record_id),
                                         headers={"Authorization": f"Bearer {self.guest_token}"},
                                         content_type='application/json',
                                         data=json.dumps(payload))
            self.test_case.assertEqual(response.status_code, 403,
                                       f"{self.resource_name} update ACL test.")
        self.validation_test(payload, record_id)
        if self.admin_token:
            response = self.client.patch(self.endpoint + "/" + str(record_id),
                                         headers={"Authorization": f"Bearer {self.admin_token}"},
                                         content_type='application/json',
                                         data=json.dumps(payload))
        else:
            response = self.client.patch(self.endpoint + "/" + str(record_id),
                                         content_type='application/json',
                                         data=json.dumps(payload))
        self.test_case.assertEqual(response.status_code, 200,
                                   f"{self.resource_name} update success test.")
        self.verify_fields(payload, response)

        if rel_fields:
            for rel_field in rel_fields:
                payload2 = payload.copy()
                if is_valid_uuid(rel_field):
                    payload2[rel_field] = str(uuid.uuid4())
                else:
                    payload2[rel_field] = 34111
                response = self.client.patch(self.endpoint + "/" + str(record_id),
                                             headers={"Authorization": f"Bearer {self.admin_token}"},
                                             content_type='application/json',
                                             data=json.dumps(payload2))
                self.test_case.assertEqual(response.status_code, 400,
                                           f"{self.resource_name} creation {rel_field} validation test.")

    def validation_test(self, payload, record_id=None):
        """
        Handles the following validation:
        1. Required fields
        :param payload: A dictionary of valid payload
        :param record_id: If provided
        """
        for key, field in self.schema._declared_fields.items():
            if field and not field.dump_only:
                if field.required:
                    payload2 = payload.copy()
                    if record_id:
                        payload2.pop(key)
                        if self.admin_token:
                            response = self.client.patch(self.endpoint + "/" + str(record_id),
                                                         headers={"Authorization": f"Bearer {self.admin_token}"},
                                                         content_type='application/json',
                                                         data=json.dumps(payload2))
                        else:
                            response = self.client.patch(self.endpoint + "/" + str(record_id),
                                                         content_type='application/json',
                                                         data=json.dumps(payload2))
                        self.test_case.assertEqual(response.status_code, 400,
                                                   f"{self.resource_name} update {key} field required validation test.")
                        if key == 'age':
                            self.test_case.fail(f"Response {key}: {response.json}")

    def deletion_test(self, record_id):
        """
        Handles deletion tests. Test cases include:
        1. Authorization rest if admin token is specified
        2. Access control test if guest token is specified
        3. Deletion success request and verification
        :param record_id: record id of an existing record
        """
        if self.admin_token or self.guest_token:
            response = self.client.delete(self.endpoint + "/" + str(record_id),
                                          content_type='application/json')
            self.test_case.assertEqual(response.status_code, 401,
                                       f"{self.resource_name} delete authorization test. {str(response.json)}")
        if self.guest_token:
            response = self.client.delete(self.endpoint + "/" + str(record_id),
                                          headers={"Authorization": f"Bearer {self.guest_token}"},
                                          content_type='application/json')
            self.test_case.assertEqual(response.status_code, 403,
                                       f"{self.resource_name} delete ACL test.")
        if self.admin_token:
            response = self.client.delete(self.endpoint + "/" + str(record_id),
                                          headers={"Authorization": f"Bearer {self.admin_token}"},
                                          content_type='application/json')
        else:
            response = self.client.delete(self.endpoint + "/" + str(record_id),
                                          content_type='application/json')
        self.test_case.assertEqual(response.status_code, 204,
                                   f"{self.resource_name} delete success test.")
        # Verify record has been deleted
        if self.admin_token:
            response = self.client.get(f"{self.endpoint}/{record_id}",
                                       headers={"Authorization": f"Bearer {self.admin_token}"},
                                       content_type='application/json')
        else:
            response = self.client.get(f"{self.endpoint}/{record_id}",
                                       content_type='application/json')
        self.test_case.assertEqual(response.status_code, 404,
                                   f"{self.resource_name} verify deletion.")

class GUID(TypeDecorator):
    """Platform-independent GUID type.
    Uses PostgreSQL's UUID type, otherwise uses
    CHAR(32), storing as stringified hex values.
    """
    impl = CHAR

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(UUID())
        else:
            return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        else:
            return str(value)
        # elif dialect.name == 'postgresql':
        #     return str(value)
        # else:
        #     if not isinstance(value, uuid.UUID):
        #         return "%.32x" % uuid.UUID(value).int
        #     else:
        #         # hexstring
        #         return "%.32x" % value.int

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not isinstance(value, uuid.UUID):
                value = uuid.UUID(value)
            return value
