from django.core.exceptions import PermissionDenied
from django.utils import timezone
from rest_framework.exceptions import APIException
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from patients.audit import record_audit_event
from patients.models import AuditEvent
from patients.policy import effective_role_policy, has_capability
from patients.task_editing import lock_edit_actor


def is_authorized_staff(user):
    policy = effective_role_policy(user, fresh=True)
    return bool(user.is_authenticated and user.is_active and (user.is_superuser or policy.role_names))


def require_staff(user, *, manage=False):
    if not is_authorized_staff(user) or (manage and not has_capability(user, "manage_settings", fresh=True)):
        raise PermissionDenied("You do not have access to this staff operation.")


def mutation_actor(user, *, manage=False, request=None):
    actor = lock_edit_actor(user)
    require_staff(actor, manage=manage)
    if request is not None:
        token = getattr(request, "auth", None)
        if token is not None:
            from api.authentication import validate_token_security_context
            validate_token_security_context(token, actor)
        elif not hasattr(request, "auth") and hasattr(request, "session"):
            from patients.auth_security import AUTH_VERSION_SESSION_KEY, current_auth_version
            if request.session.get(AUTH_VERSION_SESSION_KEY) != current_auth_version(actor):
                raise PermissionDenied("Your session changed. Sign in again.")
    return actor


class StaffPermission(BasePermission):
    def has_permission(self, request, view):
        return is_authorized_staff(request.user)


class StaleVersion(APIException):
    status_code = 409
    default_detail = "This record changed. Refresh before saving."
    default_code = "stale_version"


class StaffPagination(PageNumberPagination):
    page_size = 50

    def get_paginated_response_schema(self, schema):
        result = super().get_paginated_response_schema(schema)
        result["properties"]["server_now"] = {"type": "string", "format": "date-time"}
        result.setdefault("required", []).append("server_now")
        return result

    def get_paginated_response(self, data):
        return Response({
            "count": self.page.paginator.count,
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
            "results": data,
            "server_now": timezone.now().isoformat(),
        })


def audit_change(actor, instance, action, fields):
    record_audit_event(
        category=AuditEvent.Category.DATA,
        action=action,
        actor=actor,
        object_type=instance._meta.label_lower,
        object_id=instance.pk,
        metadata={"fields": sorted(fields), "version": instance.version},
    )
