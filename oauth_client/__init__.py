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

import requests


class OAuthToken:
    """ Access token object """
    # Access token string
    token = None
    # Access token scopes
    scopes = ""
    # Token expiry in seconds
    expires_in = 0
    # Timestamp token was issued
    issued_at = 0

    def is_active(self):
        """
        Checks if token is active using issued_at time and token expiry
        :return: true if active otherwise false
        """
        return (self.issued_at + self.expires_in) > datetime.timestamp(datetime.utcnow())


class OAuth2Requests(requests.Session):
    """
    Enables oauth2 bearer token request on requests. Retrieves and refreshes access token automatically
    """

    def __init__(self, oauth_client_id, oauth_client_secret, oauth_url, scopes=None):
        """
        :param oauth_client_id: oauth2 client id
        :param oauth_client_secret: oauth2 client secret
        :param oauth_url: oauth2 server url
        :param scopes: Oauth2 scopes
        """
        super().__init__()
        self.oauth_url = oauth_url
        self.oauth_client_secret = oauth_client_secret
        self.oauth_client_id = oauth_client_id
        self.scopes = scopes
        self.oauth_token = None

    def retrieve_access_token(self):
        """
        Requests new access token from the authorization server.
        :raises Exception: In case of http connection error
        """
        print(f"OAuth2Requests: Retrieving a new access token from server "
              f"{self.oauth_url} for client {self.oauth_client_id}")
        response = requests.post(self.oauth_url, auth=(self.oauth_client_id, self.oauth_client_secret),
                                 data=dict(grant_type="client_credentials", scope=self.scopes))
        if response.ok:
            body = response.json()
            self.oauth_token = OAuthToken()
            self.oauth_token.token = body.get("access_token")
            self.oauth_token.expires_in = body.get("expires_in")
            self.oauth_token.scopes = body.get("scope")
            # Remove 2 seconds to account for connection time
            self.oauth_token.issued_at = datetime.timestamp(datetime.utcnow()) - 2000
            response.close()
        else:
            text = response.text
            response.close()
            raise Exception(f"Failed to retrieve access token from authorization server. Details: {text}")

    def request(
            self,
            method,
            url,
            data=None,
            headers=None,
            **kwargs
    ):
        if self.oauth_token is None:
            self.retrieve_access_token()
        # print(f"Retrieved access token: {self.oauth_token.token}")
        response = self._make_request(method, url, data=data, headers=headers, **kwargs)
        # If authorization error reload token
        if response.status_code == 401:
            self.retrieve_access_token()
            return self._make_request(method, url, data=data, headers=headers, **kwargs)
        else:
            return response

    def _make_request(
            self,
            method,
            url,
            data=None,
            headers=None,
            **kwargs):
        if headers:
            headers['Authorization'] = f"Bearer {self.oauth_token.token}"
        else:
            headers = dict(Authorization=f"Bearer {self.oauth_token.token}")
        return super(OAuth2Requests, self).request(method, url, data=data, headers=headers, **kwargs)

    @property
    def access_token(self):
        """
        Gets access token. If token has expired an new one is requested.
        :return: returns OAuthToken
        """
        if self.oauth_token and self.oauth_token.is_active():
            return self.oauth_token
        else:
            self.retrieve_access_token()
            return self.oauth_token


class SaslOauthTokenProvider:
    """
    A Token Provider must be used for the SASL OAuthBearer protocol.
    """

    def __init__(self, oauth2_requests):
        """
        :param oauth2_requests: Expects an instance of OAuth2Requests
        """
        self.oauth2_requests = oauth2_requests

    def token(self):
        """
        Retrieves access token from authorization server
        :return: access_token
        :rtype: str
        """
        print("Retrieving access token from authorization server for kafka connection")
        return self.oauth2_requests.access_token.token

    def extensions(self):
        """
        This is an OPTIONAL method that may be implemented.

        Returns a map of key-value pairs that can
        be sent with the SASL/OAUTHBEARER initial client request. If
        not implemented, the values are ignored. This feature is only available
        in Kafka >= 2.1.0.
        """
        return {}