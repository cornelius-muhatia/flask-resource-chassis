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
from unittest import TestCase
from unittest.mock import patch

import requests

from flask_resource_chassis.oauth_client import OAuth2Requests, SaslOauthTokenProvider


class TestOAuth2Requests(TestCase):

    @patch.object(requests, 'post')
    def test_retrieve_token(self, requests_post):
        oauth2_requests = OAuth2Requests("test_client_id", "test_client_secret",
                                         "http://localhost:5002/oauth/token")
        response = MockRequestsResponse()
        response.set_response_dict(dict(access_token="test_token", expires_in=6000, scope=""))
        requests_post.return_value = MockRequestsResponse()

        self.assertRaises(Exception, oauth2_requests.retrieve_access_token)
        response = MockRequestsResponse()
        response.set_response_dict(dict(access_token="test_token", expires_in=6000, scope=""))
        requests_post.return_value = response
        oauth2_requests.retrieve_access_token()
        self.assertEqual(oauth2_requests.access_token.token, "test_token", "OAuth2Requests token test")
        self.assertEqual(oauth2_requests.access_token.expires_in, 6000, "OAuth2Requests expires_in test")

        oauth2_requests = OAuth2Requests("test_client_id", "test_client_secret",
                                         "http://localhost:5002/oauth/token")
        self.assertIsNotNone(oauth2_requests.access_token, "OAuth2Requests access_token auto init test")

        response.set_response_dict(dict(access_token="test_token", expires_in=-1, scope=""))
        requests_post.return_value = response
        oauth2_requests.retrieve_access_token()
        self.assertFalse(oauth2_requests.access_token.is_active(), "OAuth2Request active test")
        response.set_response_dict(dict(access_token="test_token", expires_in=6000, scope=""))
        requests_post.return_value = response
        oauth2_requests.retrieve_access_token()
        self.assertTrue(oauth2_requests.access_token.is_active(), "OAuth2Request active second test")


class MockRequestsResponse:

    def __int__(self):
        self.text_str = ""
        self.status_code = 502
        self.response_dict = dict()

    @property
    def text(self):
        return self.text_str

    def set_response_dict(self, response_dict, status_code=200):
        self.text_str = str(response_dict)
        self.status_code = status_code
        self.response_dict = response_dict

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self.response_dict

    def close(self):
        print("closed oauth2 request response")


class TestSaslOauthTokenProvider(TestCase):

    def setUp(self):
        oauth2_requests = OAuth2Requests("test_client_id", "test_client_secret",
                                         "http://localhost:5002/oauth/token")
        self.token_provider = SaslOauthTokenProvider(oauth2_requests)

    def test_extensions(self):
        self.assertIsNotNone(self.token_provider.extensions(), "Extensions test")

    @patch.object(requests, 'post')
    def test_token(self, requests_post):
        response = MockRequestsResponse()
        response.set_response_dict(dict(access_token="test_token", expires_in=6000, scope=""))
        requests_post.return_value = response
        self.assertEqual(self.token_provider.token(), "test_token", "Access token test")
