from authlib.oauth2 import OAuth2Error


class ValidationError(Exception):
    """
    Mainly used for input validation errors
    """

    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors
        self.message = message


class ConflictError(Exception):
    """
    Mainly used for conflict validation
    """

    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors
        self.message = message


class InternalServerError(Exception):
    """
    Mainly used for internal server error
    """

    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors
        self.message = message


class AccessDeniedError(Exception):
    """
    Access denied error
    """
    def __init__(self, message='The request requires higher privileges than ', errors=None):
        super().__init__(message)
        self.errors = errors
        self.message = message
