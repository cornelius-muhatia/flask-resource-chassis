from marshmallow import fields, Schema


class ResponseWrapper(Schema):
    message = fields.Str()
    data = fields.Dict()


DjangoPageSchema = Schema.from_dict(dict(
    count=fields.Int(),
    current_page=fields.Int(),
    page_size=fields.Int(),
    results=fields.List(fields.Dict()),
    total_pages=fields.Int()
))

ErrorDetails = Schema.from_dict(dict(
    detail=fields.Str()
))


class ErrorResponseSchema(Schema):
    errors = fields.Nested(ErrorDetails)
    status = fields.Int()


class ValidationErrorSchema(Schema):
    errors = fields.List(fields.Str)
    status = fields.Int()


error_response = ErrorResponseSchema()
val_error_response = ValidationErrorSchema()
