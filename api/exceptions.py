from rest_framework import exceptions
from rest_framework.views import exception_handler


def _messages(value):
    if isinstance(value, dict):
        return [str(value)]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def mobile_api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None
    if isinstance(exc, exceptions.ValidationError):
        detail = exc.detail
        if isinstance(detail, dict):
            errors = {str(field): _messages(messages) for field, messages in detail.items()}
        else:
            errors = {"non_field_errors": _messages(detail)}
        response.data = {
            "code": "invalid_request",
            "message": "Request validation failed.",
            "errors": errors,
        }
    elif isinstance(exc, exceptions.Throttled):
        response.data = {"code": "throttled", "message": "Too many requests. Try again later."}
    elif isinstance(exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)):
        response.data = {"code": "authentication_failed", "message": "Authentication is required."}
    elif isinstance(exc, exceptions.PermissionDenied):
        response.data = {"code": "permission_denied", "message": "This operation is not permitted."}
    elif response.status_code == 404:
        response.data = {"code": "not_found", "message": "The requested object was not found."}
    return response
