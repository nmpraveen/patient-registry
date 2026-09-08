from django.contrib.auth import get_user_model
from django.db.models import Q
from django.core.exceptions import PermissionDenied

from patients.models import RoleSetting
from patients.policy import effective_role_policy, has_capability
from .models import Reminder


def authorized_staff(user):
    policy = effective_role_policy(user, fresh=True)
    return bool(user.is_authenticated and user.is_active and (user.is_superuser or policy.role_names))


def require_staff(user):
    if not authorized_staff(user):
        raise PermissionDenied


def visible_reminders(user):
    require_staff(user)
    rows = Reminder.objects.all()
    if not has_capability(user, "manage_settings", fresh=True):
        rows = rows.filter(Q(owner=user) | Q(assignee=user))
    return rows


def assignees():
    return get_user_model().objects.filter(is_active=True).filter(
        Q(is_superuser=True) | Q(groups__name__in=RoleSetting.objects.values("role_name"))
    ).distinct().order_by("username", "pk")
