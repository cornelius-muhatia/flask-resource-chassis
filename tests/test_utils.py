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
import base64
from unittest import TestCase
from unittest.mock import patch

import requests

from flask_resource_chassis.flask_resource_chassis.utils import get_kafka_hosts


class MessageServiceTests(TestCase):

    @patch.object(requests, 'get')
    def test_kafka_config(self, requests_get):
        response = get_kafka_hosts()
        self.assertTrue(len(response) == 0, "Messaging service get kafka hosts exceptions test")

        class ReturnValue:
            def ok(self):
                return True

            def json(self):
                return [{"Value": base64.encodebytes("172.17.0.1,172.17.0.2".encode()).decode()}]

        requests_get.return_value = ReturnValue()
        response = get_kafka_hosts()
        self.assertEqual(len(response), 2, "Messaging service get hosts verification test")