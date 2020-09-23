import functools
import time

import requests
from authlib.integrations.flask_oauth2 import ResourceProtector
from authlib.oauth2.rfc6749 import MissingAuthorizationError, TokenMixin
from authlib.oauth2.rfc6750 import BearerTokenValidator, InvalidTokenError
from requests.auth import HTTPBasicAuth

from .exceptions import AccessDeniedError
from .schemas import ResponseWrapper


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