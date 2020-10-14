# -*- coding: utf-8 -*-
# Copyright 2020 authors and contributors All Rights Reserved.
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
from collections.abc import Iterable

from sqlalchemy.orm.state import InstanceState

from .exceptions import ValidationError
from .utils import RemoteToken


def get_primary_key(entity):
    """
    Gets primary key column from entity
    :param entity: SqlAlchemy model
    :return: SqlAlchemy Column
    """
    for column in getattr(entity, "__table__").c:
        if column.primary_key:
            return column
    return None


class LoggerService:

    def log_success_creation(self, description, entity, record_id=None, token: RemoteToken = None):
        """
        Logs success creation event

        :param description: audit log description
        :param entity: entity being affected by the action
        :param record_id: record id/database id
        :param token: RemoteToken object
        """
        pass

    def log_failed_creation(self, description, entity, token: RemoteToken = None):
        """
        Logs failed creation event

        :param description: audit log description
        :param entity: entity being affected by the action
        :param token: RemoteToken object
        """
        pass

    def log_success_update(self, description, entity, record_id, notes="", token: RemoteToken = None):
        """
        Logs success update event

        :param description: error description
        :param entity:  entity being affected by the action
        :param record_id: record/row id
        :param notes: deletion notes
        :param token: RemoteToken object
        """
        pass

    def log_failed_update(self, description, entity, record_id,  notes="", token: RemoteToken = None):
        """
        Logs failed update event

        :param description: error description
        :param entity: entity being affected by the action
        :param record_id: record/row id
        :param notes: deletion notes
        :param token: RemoteToken object
        """
        pass

    def log_failed_deletion(self, description, entity, record_id, notes="", token: RemoteToken = None):
        """
        Logs failed deletion event

        :param description: error description
        :param entity: entity being affected by the action
        :param record_id: record/row id
        :param notes: deletion notes
        :param token: RemoteToken object
        """
        pass

    def log_success_deletion(self, description, entity, record_id, notes="", token: RemoteToken = None):
        """
        Logs success deletion event

        :param description: error description
        :param entity: entity being affected by the action
        :param record_id: record/row id
        :param notes: deletion notes
        :param token: RemoteToken object
        """
        pass


class ChassisService:
    """Supports chassis resource database actions like entity creation update and deletions"""

    def __init__(self, app, db, entity):
        """
        Instantiates ChassisService object

        :param app: Flask application object
        :param db: SQLAlchemy database object
        :param entity: SQLAlchemy model/entity
        """
        self.app = app
        self.db = db
        self.entity = entity

    def create(self, entity):
        """
        Creates new entity

        :param entity: SQLAlchemy model
        :return: Newly created SQLAlchemy model with default fields populated
        """
        self.app.logger.debug("Inserting new record: Payload: %s", str(entity))
        self.db.session.add(entity)
        self.db.session.commit()
        return entity

    def update(self, entity, model_id):
        """
        Updates entity
        :param entity: Entity
        :param model_id: Entity primary id value
        :return: Updated entity
        :throws: ValidationError if entity with model_id doesn't exist
        """
        self.app.logger.debug("Updating record: Payload: %s", str(entity))
        primary_key = get_primary_key(entity)
        filters = {
            "is_deleted": False,
            primary_key.name: model_id
        }
        db_entity = self.db.session.query(entity.__table__).filter_by(**filters).first()
        if db_entity is None:
            raise ValidationError("Sorry record doesn't exist")
        update_vals = {}

        for key, val in entity.__dict__.items():
            if isinstance(getattr(entity, key), Iterable) and not isinstance(getattr(entity, key), str):
                self.app.logger.warn("Found many to many field (%s). Unfortunately current implementation "
                                     "doesn't support many to many fields update", getattr(entity, key))
            elif not isinstance(val, InstanceState) and key != primary_key.name:
                update_vals[key] = val
        # filters
        stm = entity.__table__.update().values(**update_vals).where(
            primary_key == model_id)
        self.db.session.execute(stm)
        self.db.session.commit()
        # Reload entity again after update
        return self.db.session.query(entity.__table__).filter_by(**filters).first()

    def delete(self, record_id):
        """
        Deleting record using record_id
        :param record_id: Record id
        """
        self.app.logger.debug("Deleting record. Record id %s", str(record_id))
        primary_column = get_primary_key(self.entity)
        filters = {primary_column.name: record_id}
        if hasattr(self.entity, "is_deleted"):
            filters["is_deleted"] = False
        record = self.entity.query.filter_by(**filters).first()
        if record is None:
            raise ValidationError("Record doesn't exist")
        if hasattr(self.entity, "is_deleted"):
            record.is_deleted = True
        else:
            self.db.session.delete(record)
        self.db.session.commit()
