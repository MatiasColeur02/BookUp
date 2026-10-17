class NotFoundError(Exception):
    """Raised when a requested entity does not exist."""


class ConflictError(Exception):
    """Raised when an operation conflicts with the current state of an entity."""


class UnauthorizedError(Exception):
    """Raised when the caller could not be identified (missing/invalid credentials)."""


class ForbiddenError(Exception):
    """Raised when the caller is known but not allowed to perform the operation."""


class AuthUnavailableError(Exception):
    """Raised when the caller cannot be verified because the identity provider (the
    Cognito JWKS) does not answer. Not the caller's fault: a 503, not a 401."""
