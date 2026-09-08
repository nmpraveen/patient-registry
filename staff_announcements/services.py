from django.db import transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404
from django.utils import timezone

from patients.policy import effective_role_policy
from staff_directory.access import audit_change, mutation_actor, require_staff, StaleVersion
from .models import Announcement


def announcements_for(user, *, manage=False, now=None):
    require_staff(user, manage=manage)
    queryset = Announcement.objects.select_related("publisher").prefetch_related("audience_roles")
    if manage:
        return queryset
    now = now or timezone.now()
    roles = effective_role_policy(user).role_names
    return queryset.filter(is_active=True, starts_at__lte=now, ends_at__gt=now).filter(
        Q(audience=Announcement.Audience.ALL_STAFF)
        | Q(audience=Announcement.Audience.SELECTED_ROLES, audience_roles__role_name__in=roles)
    ).distinct().annotate(
        priority_rank=Case(When(priority="urgent", then=Value(0)),
                           When(priority="important", then=Value(1)),
                           default=Value(2), output_field=IntegerField())
    ).order_by("priority_rank", "-starts_at", "-pk")


def banner_for(user):
    return announcements_for(user).first()


@transaction.atomic
def save_announcement(user, data, *, pk=None, request=None):
    actor = mutation_actor(user, manage=True, request=request)
    data = dict(data)
    expected = data.pop("version", None)
    roles = data.pop("audience_roles", None)
    if pk is None:
        announcement = Announcement(publisher=actor)
    else:
        announcement = get_object_or_404(Announcement.objects.select_for_update(), pk=pk)
        if expected != announcement.version:
            raise StaleVersion()
        announcement.version += 1
    for field, value in data.items():
        setattr(announcement, field, value)
    announcement.full_clean()
    announcement.save()
    if roles is not None:
        announcement.audience_roles.set(roles)
    audit_change(actor, announcement, "staff_announcements.created" if pk is None else "staff_announcements.updated",
                 [*data, *(["audience_roles"] if roles is not None else [])])
    return announcement
