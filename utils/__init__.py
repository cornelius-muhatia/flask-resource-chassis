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
import os
import traceback

import requests


def get_kafka_hosts(consul_url="http://localhost:8500"):
    """
    Fetch kafka hosts from consul agent
    :param consul_url: Consul address
    """
    try:
        response = requests.get(f"{consul_url}/v1/kv/kafka-service-hosts")
        if response.ok:
            hosts = base64.decodebytes(response.json()[0].get("Value").encode()).decode()
            return hosts.split(",")
        else:
            raise Exception(f"Failed to retrieve kafka hosts. {response.raw}")
    except Exception:
        traceback.print_stack()
        print("Failed to retrieve kafka hosts from consul agent trying to fetch from "
              "environment variable KAFKA_SERVICE_HOSTS")
        kafka_hosts = os.environ.get("KAFKA_SERVICE_HOSTS", None)
        if kafka_hosts:
            return kafka_hosts.split(",")
        else:
            print("Failed to retrieve kafka hosts from environment variable(KAFKA_SERVICE_HOSTS). "
                  "Giving up!")
    return []
