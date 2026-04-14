class SkBaseException(Exception):
    def __init__(self, message: str, status_code: int = 500, error_code: str = "INTERNAL_ERROR"):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(self.message)

class AuthException(SkBaseException):
    def __init__(self, message: str, error_code: str = "UNAUTHORIZED"):
        super().__init__(message, status_code=401, error_code=error_code)

class ValidationException(SkBaseException):
    def __init__(self, message: str, error_code: str = "VALIDATION_ERROR"):
        super().__init__(message, status_code=422, error_code=error_code)

class ResourceNotFoundException(SkBaseException):
    def __init__(self, message: str, error_code: str = "NOT_FOUND"):
        super().__init__(message, status_code=404, error_code=error_code)

class ConflictException(SkBaseException):
    def __init__(self, message: str, error_code: str = "CONFLICT"):
        super().__init__(message, status_code=409, error_code=error_code)

class RateLimitException(SkBaseException):
    def __init__(self, message: str, error_code: str = "TOO_MANY_REQUESTS"):
        super().__init__(message, status_code=429, error_code=error_code)
