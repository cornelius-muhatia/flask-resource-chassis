from flask_apispec import use_kwargs, marshal_with, doc, MethodResource


class ChassisResource(MethodResource):

    def __init__(self, app, record_name=None):
        self.app = app
        if record_name is None:
            self.record_name = "Resource"
        else:
            self.record_name = record_name

    def post(self, token=None, payload=None, *args):
        self.app.logger.info("Creating new %s. Payload: %s", self.record_name, str(payload))
        return {"message": "Request was successful"}, 201

    def get(self):
        self.app.logger.info("Fetching %s records", self.record_name)
