"""Shared task edit baselines and clinical activity descriptions."""

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import ValidationError

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
