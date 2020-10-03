import functools
import time
import unittest
import uuid
from abc import ABC

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

    def __init__(self, http_client, endpoint="/v1", resource_name="Record", test_case=None, admin_token=None,
                 guest_token=None):
        self.client = http_client
        self.test_case = test_case if test_case else unittest.TestCase()
        self.admin_token = admin_token
        self.guest_token = guest_token
        self.resource_name = resource_name
        self.endpoint = endpoint

    def creation_test(self, payload, unique_fields=None, rel_fields=None):
        """
        Record creation tests. Unit tests:
        1. Authorization test if guest or admin token are supplied
        2. ACL test if guest token is present
        3. Validation Test (Including unique fields and rel_fields tests if provided)
        4. Success Tests
        """
        if self.admin_token or self.guest_token:
            response = self.client.post(self.endpoint,
                                        # headers={"Authorization": f"Bearer {self.admin_token}"},
                                        content_type='application/json',
                                        data=json.dumps(payload))
            self.test_case.assertEqual(response.status_code, 401,
                                       f"{self.resource_name} creation authorization test.")
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
        response = self.client.get(f"{self.endpoint}{response.json.get('id')}/",
                                   headers={"Authorization": f"Bearer {self.admin_token}"},
                                   content_type='application/json')
        self.test_case.assertEqual(response.status_code, 200,
                                   f"{self.resource_name} fetch single record success test.")
        for key, value in payload.items():
            self.test_case.assertEqual(value, response.json.get(key), f"{self.resource_name} {key} verification")

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
                payload2 = payload
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

    def fetch_test(self, payload):
        pass


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
        elif dialect.name == 'postgresql':
            return str(value)
        else:
            if not isinstance(value, uuid.UUID):
                return "%.32x" % uuid.UUID(value).int
            else:
                # hexstring
                return "%.32x" % value.int

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not isinstance(value, uuid.UUID):
                value = uuid.UUID(value)
            return value
