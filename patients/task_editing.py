"""Shared task edit baselines and clinical activity descriptions."""

from django.contrib.auth import HASH_SESSION_KEY, get_user_model
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.crypto import constant_time_compare

from .models import RoleSetting, UserSecurityState


TASK_FIELDS = ("title", "due_date", "status", "assigned_user", "task_type", "frequency_label", "notes")


def task_values(task):
    return {
        "title": task.title, "due_date": task.due_date.isoformat(), "status": task.status,
        "assigned_user": task.assigned_user_id, "task_type": task.task_type,
        "frequency_label": task.frequency_label, "notes": task.notes,
    }


def task_edit_token(task, user):
    return signing.dumps({"task": task.pk, "user": user.pk, "values": task_values(task)}, salt="task-edit", compress=True)


def read_task_edit_token(token, task, user):
    try:
        payload = signing.loads(token, salt="task-edit")
        if payload["task"] != task.pk or payload["user"] != user.pk:
            raise ValueError
        return payload["values"]
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        raise ValidationError("Refresh the task editor before saving; the original edit baseline is missing or invalid.")


def changed_field_conflicts(current, base, fields):
    return sorted(field for field in fields if field not in current or field not in base or current[field] != base[field])


def task_change_note(task, previous):
    current = task_values(task)
    changes = [f"{field.replace('_', ' ')}: {previous[field] or '—'} → {current[field] or '—'}"
               for field in TASK_FIELDS if previous[field] != current[field]]
    return f"Task updated: {task.title}" + ("; " + "; ".join(changes) if changes else " (no field changes)")


def lock_edit_actor(user):
    """Use the mobile write lock order for web and mobile task mutations."""
    locked = get_user_model().objects.select_for_update().get(pk=user.pk)
    UserSecurityState.objects.select_for_update().get_or_create(user=locked)
    through = get_user_model().groups.through
    list(through.objects.select_for_update().filter(user_id=locked.pk).order_by("pk").values_list("pk", flat=True))
    names = list(locked.groups.order_by("name").values_list("name", flat=True))
    list(RoleSetting.objects.select_for_update().filter(role_name__in=names).order_by("pk"))
    return locked


def lock_web_edit_actor(request):
    """Revalidate the original web session after acquiring mutation locks.

    Call inside the mutation transaction, before reading authorization or case
    scope. Middleware authenticates before these locks and may have observed a
    session that was revoked while the request waited for another writer.
    """
    from .auth_security import (
        AUTH_VERSION_SESSION_KEY, DEVICE_CREDENTIAL_SESSION_KEY,
        current_auth_version, parse_positive_auth_version, user_requires_device_approval,
    )
    from .models import StaffDeviceCredential, StaffDeviceCredentialStatus

    actor = lock_edit_actor(request.user)
    denial = "Your session changed. Sign in again."
    try:
        bound_version = parse_positive_auth_version(request.session.get(AUTH_VERSION_SESSION_KEY))
    except ValueError:
        raise PermissionDenied(denial)
    session_hash = request.session.get(HASH_SESSION_KEY)
    if (not actor.is_active or bound_version != current_auth_version(actor)
            or not isinstance(session_hash, str) or not session_hash
            or not constant_time_compare(session_hash, actor.get_session_auth_hash())):
        raise PermissionDenied(denial)
    if user_requires_device_approval(actor):
        device_id = request.session.get(DEVICE_CREDENTIAL_SESSION_KEY)
        if type(device_id) is not int or device_id <= 0 or not StaffDeviceCredential.objects.filter(
            pk=device_id, user=actor, status=StaffDeviceCredentialStatus.APPROVED,
        ).exists():
            raise PermissionDenied(denial)
    return actor
