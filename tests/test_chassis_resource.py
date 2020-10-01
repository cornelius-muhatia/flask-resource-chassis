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
from datetime import datetime, timedelta
from unittest import TestCase

from authlib.oauth2.rfc6750 import InvalidTokenError
from flask import Flask, json
from flask_resource_chassis.tests import test_app, Person, db, Gender


class TestResourceChassis(TestCase):

    def setUp(self):
        self.client = test_app.test_client()

        @test_app.errorhandler(InvalidTokenError)
        def unauthorized(error):
            test_app.logger.error("Authorization error: %s", error)
            return {"message": "You are not authorized to perform this request. "
                               "Ensure you have a valid credentials before trying again"}, 401

    def test_creation(self):
        """
        Tests chassis resource creation action. Test cases include:
        1. Validation errors (Required fields, unique fields and relational fields)
        2. Authorization test
        3. Access control tests
        4. Successful and validation tests
        """
        response = self.client.post("/v1/person")
        self.assertEqual(response.status_code, 400)
        payload = {
            "full_name": "Test Name",
            "gender_id": 2,
            "national_id": "1123456"
        }
        try:
            # Authorization tests
            response = self.client.post("/v1/person", data=json.dumps(payload), content_type='application/json')
            # self.fail("Authorization fail test. " + str(response.json) + " status " + str(response.status_code))
        except InvalidTokenError:
            pass
        # Test ACL Validation
        # response = self.client.post("/v1/person", headers={"Authorization": f"Bearer guest_token"},
        #                             data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 403)
        # Successfully tests
        response = self.client.post("/v1/person", headers={"Authorization": f"Bearer admin_token"},
                                    data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        # Unique tests
        response = self.client.post("/v1/person", headers={"Authorization": f"Bearer admin_token"},
                                    data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        # Relational fields tests
        payload["gender_id"] = -1
        response = self.client.post("/v1/person", headers={"Authorization": f"Bearer admin_token"},
                                    data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        # Active relational field tests
        payload["gender_id"] = 1
        response = self.client.post("/v1/person", headers={"Authorization": f"Bearer admin_token"},
                                    data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        # Data validation
        response = self.client.get("/v1/person/1", headers={"Authorization": f"Bearer admin_token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json.get("full_name"), payload["full_name"])
        self.assertEqual(response.json.get("gender_id"), 2)
        self.assertEqual(response.json.get("national_id"), "1123456")

    def test_fetch(self):
        """
        Test fetch multiple and single records. Test cases:
        1. Validation test
        2. Access control test
        3. Fetching resources
            1. Filter using fields
            2. Filter using date range (created_at and updated_at)
        """
        # response = self.client.get("/v1/person/1")
        # self.assertEqual(response.status_code, 401)
        # response = self.client.get("/v1/person/1", headers={"Authorization": f"Bearer guest_token"})
        # self.assertEqual(response.status_code, 403)
        response = self.client.get("/v1/person/1", headers={"Authorization": f"Bearer admin_token"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json.get("created_at"))
        self.assertIsNotNone(response.json.get("full_name"))
        self.assertIsNotNone(response.json.get("gender_id"))

        person = Person()
        person.full_name = "Test User2"
        person.gender_id = 2
        person.national_id = "22222222"
        db.session.add(person)

        gender = Gender()
        gender.gender = "Transgender"
        db.session.add(gender)
        db.session.commit()

        person2 = Person()
        person2.full_name = "Test User3"
        person2.gender_id = gender.id
        person2.national_id = "3333333334"
        db.session.add(person2)
        db.session.commit()

        response = self.client.get("/v1/person", headers={"Authorization": "Bearer admin_token"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json.get("count") >= 3)
        self.assertTrue(response.json.get("current_page") >= 1)
        self.assertEqual(response.json.get("page_size"), 10)

        response = self.client.get("/v1/person?page_size=1", headers={"Authorization": "Bearer admin_token"})
        self.assertTrue(response.json.get("count") >= 3)
        self.assertTrue(response.json.get("current_page"), 1)
        self.assertEqual(response.json.get("page_size"), 1)

        response = self.client.get("/v1/person?page_size=1&page=2", headers={"Authorization": "Bearer admin_token"})
        self.assertTrue(response.json.get("count") >= 3)
        self.assertTrue(response.json.get("current_page"), 2)
        self.assertEqual(response.json.get("page_size"), 1)

        response = self.client.get("/v1/person?q=Test%20User3", headers={"Authorization": "Bearer admin_token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json.get("count"), 1)
        self.assertEqual(response.json.get("current_page"), 1)

        response = self.client.get("/v1/person?q=Test%20User333434343", headers={"Authorization": "Bearer admin_token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json.get("count"), 0)
        self.assertEqual(response.json.get("current_page"), 1)

        db.session.add(person2)
        response = self.client.get("/v1/person?national_id=" + person2.national_id,
                                   headers={"Authorization": "Bearer admin_token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json.get("count"), 1)
        self.assertEqual(response.json.get("current_page"), 1)

        db.session.add(person2)
        response = self.client.get("/v1/person?national_id=738438438438438",
                                   headers={"Authorization": "Bearer admin_token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json.get("count"), 0)
        self.assertEqual(response.json.get("current_page"), 1)

        response = self.client.get("/v1/person?created_before=1997-01-01",
                                   headers={"Authorization": "Bearer admin_token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json.get("count"), 0)
        self.assertEqual(response.json.get("current_page"), 1)

        before_date = datetime.now() + timedelta(days=1)
        before_date = before_date.strftime('%Y-%m-%d')
        response = self.client.get("/v1/person?created_before=" + before_date,
                                   headers={"Authorization": "Bearer admin_token"})
        self.assertEqual(response.status_code, 200, "Created before tests " + str(response.json))
        self.assertEqual(response.json.get("count"), 3)
        self.assertEqual(response.json.get("current_page"), 1)

        response = self.client.get("/v1/person?created_after=" + before_date,
                                   headers={"Authorization": "Bearer admin_token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json.get("count"), 0)
        self.assertEqual(response.json.get("current_page"), 1)

        response = self.client.get("/v1/person?updated_before=" + before_date,
                                   headers={"Authorization": "Bearer admin_token"})
        self.assertEqual(response.status_code, 200, "Updated before " + str(response.json))
        self.assertEqual(response.json.get("count"), 3)
        self.assertEqual(response.json.get("current_page"), 1)

        response = self.client.get("/v1/person?updated_after=" + before_date,
                                   headers={"Authorization": "Bearer admin_token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json.get("count"), 0)
        self.assertEqual(response.json.get("current_page"), 1)

    def test_update(self):
        """
        Test resource update. Test cases:
        1. Validation tests include unique fields and foreign key validation
        2. Authorization tests
        3. ACL tests
        4. Successful tests
        """
        response = self.client.patch("/v1/person/3")
        self.assertEqual(response.status_code, 400)
        payload = {
            "full_name": "Test Update",
            "gender_id": 2,
            "national_id": "900000"
        }
        response = self.client.patch("/v1/person/3", data=json.dumps(payload), content_type='application/json')
        # self.assertEqual(response.status_code, 401)
        # Successfully tests
        response = self.client.patch("/v1/person/3", headers={"Authorization": f"Bearer admin_token"},
                                     data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        response = self.client.get("/v1/person/3", headers={"Authorization": f"Bearer admin_token"})
        # Field verifications
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json.get("full_name"), payload["full_name"])
        self.assertEqual(response.json.get("gender_id"), payload["gender_id"])
        self.assertEqual(response.json.get("national_id"), payload["national_id"])
        # Relational fields tests
        payload["gender_id"] = -1
        response = self.client.patch("/v1/person/3", headers={"Authorization": f"Bearer admin_token"},
                                     data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        # Relational field active test
        payload["gender_id"] = 1
        response = self.client.patch("/v1/person/3", headers={"Authorization": f"Bearer admin_token"},
                                     data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        # Unique fields validation
        person = Person()
        person.full_name = "Delete User"
        person.national_id = "9922333"
        person.gender_id = 2
        db.session.add(person)
        db.session.commit()

        payload["gender_id"] = 2
        payload["national_id"] = person.national_id
        response = self.client.patch("/v1/person/3", headers={"Authorization": f"Bearer admin_token"},
                                     data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 400, "National ID unique verification")
        db.session.add(person)
        person.is_deleted = True
        response = self.client.patch("/v1/person/3", headers={"Authorization": f"Bearer admin_token"},
                                     data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)

    def test_deletion(self):
        response = self.client.delete("/v1/person/1")
        # self.assertEqual(response.status_code, 401)
        # Validation tests
        response = self.client.delete("/v1/person/-4", headers={"Authorization": f"Bearer admin_token"})
        self.assertEqual(response.status_code, 404)
        person = Person()
        person.full_name = "Delete User"
        person.national_id = "9922333"
        person.gender_id = 2
        db.session.add(person)
        db.session.commit()

        user_id = person.id

        response = self.client.delete("/v1/person/" + str(user_id), headers={"Authorization": f"Bearer admin_token"})
        self.assertEqual(response.status_code, 204)
        # Validation test
        response = self.client.delete("/v1/person/" + str(user_id), headers={"Authorization": f"Bearer admin_token"})
        self.assertEqual(response.status_code, 404)


