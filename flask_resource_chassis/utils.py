from .schemas import ResponseWrapper


def validation_error_handler(err):
    """
    Used to parse use_kwargs validation errors
    """
    headers = err.data.get("headers", None)
    messages = err.data.get("messages", ["Invalid request."])
    schema = ResponseWrapper()
    data = messages.get("json", None)
    error_msg = "Sorry validation errors occurred"
    if headers:
        return schema.dump({"data": data, "message": error_msg}), 400, headers
    else:
        return schema.dump({"data": data, "message": error_msg}), 400