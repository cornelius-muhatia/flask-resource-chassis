from datetime import datetime
from unittest import TestCase

from flask import Flask
from flask_sqlalchemy import SQLAlchemy, Model
from sqlalchemy import Integer, String, Column, func

from flask_resource_chassis.flask_resource_chassis import ChassisService, ValidationError


class Test(Model):
    id = Column(Integer, primary_key=True)
    name = Column(String(5), nullable=False)


class TestChassisService(TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.db = SQLAlchemy(self.app)

        class Gender(self.db.Model):
            id = self.db.Column(self.db.Integer, primary_key=True)
            gender = self.db.Column(self.db.String(254), nullable=False)
            is_deleted = self.db.Column(self.db.Boolean, nullable=False, default=False)
            is_active = self.db.Column(self.db.Boolean, nullable=False, default=True)
            created_at = self.db.Column(self.db.DateTime, nullable=False, server_default=func.now(),
                                        default=datetime.utcnow)
        self.Gender = Gender
        self.service = ChassisService(self.app, self.db, self.Gender)
        self.db.create_all()

    def test_create(self):
        """
        Tests entity successful creation
        """
        gender = self.Gender()
        gender.gender = "Male"
        gender = self.service.create(gender)
        self.assertIsNotNone(gender.id)

    def test_update(self):
        """
        Test ChassisService update() method. Test cases include:
        1. Successful entity update
        2. id validation
        """
        gender = self.Gender()
        gender.gender = "Female"
        gender = self.service.create(gender)
        try:
            self.service.update(self.Gender(), -1)
            self.fail("Chassis service id validation failed")
        except ValidationError:
            pass
        gender2 = self.Gender()
        gender2.gender = "Trans-Gender"
        gender2.is_active = False
        self.service.update(gender2, gender.id)
        gender3 = self.Gender.query.filter_by(id=gender.id).first()
        self.assertEqual(gender3.gender, gender2.gender)
        self.assertEqual(gender3.is_active, gender2.is_active)
        self.assertEqual(gender3.created_at, gender.created_at)

    def test_delete(self):
        """
        Test ChassisService delete() method
        """
        gender = self.Gender()
        gender.gender = "Female"
        gender = self.service.create(gender)
        self.service.delete(gender.id)
        gender = self.Gender.query.filter_by(id=gender.id).first()
        self.assertTrue(gender.is_deleted)



