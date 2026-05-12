from fastapi import HTTPException

class AppError(HTTPException):
    """Base exception class for application errors."""
    def __init__(self, status_code: int, code: str, message: str, headers: dict = None):
        # We pass detail as a dict to maintain compatibility with FastAPI's default exception handler
        # if the custom handler is not used, and to allow the custom handler to extract both format types.
        super().__init__(
            status_code=status_code, 
            detail={"code": code, "message": message, "detail": message},
            headers=headers
        )
        self.code = code
        self.message = message

class AuthError(AppError):
    """Raised when authentication fails."""
    def __init__(self, message: str = "Authentication failed", code: str = "AUTH_ERROR", headers: dict = None):
        super().__init__(status_code=401, code=code, message=message, headers=headers)

class AuthorizationError(AppError):
    """Raised when an authenticated user lacks required access."""
    def __init__(self, message: str = "Access denied", code: str = "ACCESS_DENIED"):
        super().__init__(status_code=403, code=code, message=message)

class ValidationError(AppError):
    """Raised when input validation fails."""
    def __init__(self, message: str = "Validation error", code: str = "VALIDATION_ERROR"):
        super().__init__(status_code=400, code=code, message=message)

class DatabaseError(AppError):
    """Raised when a database operation fails."""
    def __init__(self, message: str = "Database operation failed", code: str = "DB_ERROR"):
        super().__init__(status_code=500, code=code, message=message)
