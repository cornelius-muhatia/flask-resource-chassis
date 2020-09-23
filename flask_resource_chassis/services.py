from sqlalchemy import PrimaryKeyConstraint, Table
from sqlalchemy.orm.state import InstanceState

from sqlalchemy.inspection import inspect as alchemy_inspect
from .exceptions import ValidationError


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

    def log_success_creation(self, description, entity, record_id=None, user_id=None):
        """
        Logs success creation event

        :param user_id: Session user id
        :param description: audit log description
        :param entity: entity being affected by the action
        :param record_id: record id/database id
        """
        pass

    def log_failed_creation(self, description, entity, user_id=None):
        """
        Logs failed creation event

        :param user_id:
        :param description: audit log description
        :param entity: entity being affected by the action
        """
        pass

    def log_success_update(self, description, entity, record_id, user_id=None, notes=""):
        """
        Logs success update event

        :param user_id: session user id
        :param description: error description
        :param entity:  entity being affected by the action
        :param record_id: record/row id
        :param notes: deletion notes
        """
        pass

    def log_failed_update(self, description, entity, record_id, user_id=None, notes=""):
        """
        Logs failed update event

        :param user_id: session user id
        :param description: error description
        :param entity: entity being affected by the action
        :param record_id: record/row id
        :param notes: deletion notes
        """
        pass

    def log_failed_deletion(self, description, entity, record_id, user_id=None, notes=""):
        """
        Logs failed deletion event

        :param user_id: session user id
        :param description: error description
        :param entity: entity being affected by the action
        :param record_id: record/row id
        :param notes: deletion notes
        """
        pass

    def log_success_deletion(self, description, entity, record_id, user_id=None, notes=""):
        """
        Logs success deletion event

        :param user_id: session user id
        :param description: error description
        :param entity: entity being affected by the action
        :param record_id: record/row id
        :param notes: deletion notes
        """
        pass


class ChassisService:

    def __init__(self, app, db, entity):
        self.app = app
        self.db = db
        self.entity = entity

    def create(self, entity):
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
            if not isinstance(val, InstanceState) and key != primary_key.name:
                update_vals[key] = val
        # filters
        stm = entity.__table__.update().values(**update_vals).where(
            primary_key == model_id)
        self.db.session.execute(stm)
        self.db.session.commit()
        return entity

    def delete(self, record_id):
        """
        Deleting record using record_id
        :param record_id: Record id
        """
        self.app.logger.debug("Deleting record. Record id %s", str(record_id))
        record = self.entity.query.filter_by(id=record_id, is_deleted=False).first()
        if record is None:
            raise ValidationError("Record doesn't exist")
        record.is_deleted = True
        self.db.session.commit()
