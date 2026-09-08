"""All reminder writes serialize on the definition, including scheduling/completion."""
import calendar
from datetime import date
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from patients.audit import record_audit_event
from patients.models import AuditEvent
from patients.task_editing import lock_edit_actor
from .models import Reminder, ReminderOccurrence
from .policy import assignees, require_staff, visible_reminders


class StaleReminder(ValidationError):
    pass


def hospital_today():
    return timezone.localdate(timezone.now(), timezone=ZoneInfo(settings.TIME_ZONE))


def occurrence_date(anchor, recurrence, index):
    if index == 0:
        return anchor
    months = {"MONTHLY": 1, "EVERY_TWO_MONTHS": 2, "YEARLY": 12}.get(recurrence)
    if months is None:
        return None
    absolute = anchor.year * 12 + anchor.month - 1 + months * index
    year, month0 = divmod(absolute, 12)
    if year > 9999:
        return None
    return date(year, month0 + 1, min(anchor.day, calendar.monthrange(year, month0 + 1)[1]))


def notice_date(due, days):
    return date.fromordinal(max(1, due.toordinal() - days))


def set_next_notice(reminder):
    due = occurrence_date(reminder.due_date, reminder.recurrence, reminder.next_index)
    reminder.next_notice_date = notice_date(due, reminder.advance_notice_days) if due else None


def audit(reminder, actor, action, **metadata):
    record_audit_event(category=AuditEvent.Category.DATA, action=f"staff_reminder.{action}", actor=actor,
                       object_type="staff_reminder", object_id=reminder.pk, metadata=metadata)


def locked_actor(actor, request=None):
    actor = lock_edit_actor(actor)
    require_staff(actor)
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


@transaction.atomic
def create_reminder(actor, values, *, request=None):
    actor = locked_actor(actor, request)
    if not assignees().filter(pk=values["assignee_id"]).exists():
        raise ValidationError({"assignee_id": "Choose active authorised staff."})
    reminder = Reminder(owner=actor, **values)
    reminder.full_clean()
    set_next_notice(reminder)
    reminder.save()
    ReminderOccurrence.objects.create(reminder=reminder, index=0, due_date=reminder.due_date,
                                      notice_date=notice_date(reminder.due_date, reminder.advance_notice_days))
    audit(reminder, actor, "created")
    return reminder


@transaction.atomic
def update_reminder(actor, pk, values, version, *, request=None):
    actor = locked_actor(actor, request)
    reminder = get_object_or_404(visible_reminders(actor).select_for_update(), pk=pk)
    if reminder.version != version:
        raise StaleReminder("Reminder changed. Refresh before saving.")
    allowed = {"title", "assignee_id", "advance_notice_days", "is_active"}
    if set(values) - allowed:
        raise ValidationError("The recurrence anchor cannot be changed. Deactivate and create a new reminder.")
    if "assignee_id" in values and not assignees().filter(pk=values["assignee_id"]).exists():
        raise ValidationError({"assignee_id": "Choose active authorised staff."})
    changes = {field: [getattr(reminder, field), value] for field, value in values.items() if getattr(reminder, field) != value}
    for field, value in values.items():
        setattr(reminder, field, value)
    reminder.version += 1
    reminder.full_clean()
    set_next_notice(reminder)
    reminder.save()
    if "advance_notice_days" in changes:
        pending = list(reminder.occurrences.filter(completed_at__isnull=True))
        for occurrence in pending:
            occurrence.notice_date = notice_date(occurrence.due_date, reminder.advance_notice_days)
        ReminderOccurrence.objects.bulk_update(pending, ["notice_date"])
    audit(reminder, actor, "updated", changes=changes)
    return reminder


@transaction.atomic
def complete_occurrence(actor, pk, version, *, request=None):
    actor = locked_actor(actor, request)
    # Resolve through current scope before acknowledging even an already completed ID.
    occurrence = get_object_or_404(ReminderOccurrence.objects.filter(reminder__in=visible_reminders(actor)), pk=pk)
    reminder = get_object_or_404(visible_reminders(actor).select_for_update(), pk=occurrence.reminder_id)
    occurrence.refresh_from_db()
    if occurrence.completed_at is not None:
        return occurrence
    if reminder.version != version:
        raise StaleReminder("Reminder changed. Refresh before completing.")
    if not reminder.is_active:
        raise ValidationError("This reminder is inactive.")
    occurrence.completed_at = timezone.now()
    occurrence.completed_by = actor
    occurrence.save(update_fields=["completed_at", "completed_by"])
    audit(reminder, actor, "completed", occurrence_id=occurrence.pk, due_date=occurrence.due_date.isoformat())
    return occurrence


def schedule_reminders(*, as_of=None, limit=500, per_reminder=24):
    """Bounded resumable catch-up; no notifications sent and no web request hooks.

    A single definition lock covers insert plus cursor advance. Crashes roll both back;
    concurrent runners skip locked rows. Remaining overdue work is visible in the result.
    """
    as_of = as_of or hospital_today()
    if not 1 <= limit <= 5000 or not 1 <= per_reminder <= 120:
        raise ValueError("limit must be 1..5000 and per_reminder 1..120")
    created = processed = 0
    seen = []
    while created < limit and processed < limit:
        with transaction.atomic():
            reminder = (Reminder.objects.select_for_update(skip_locked=True, of=("self",)).filter(
                is_active=True, assignee__is_active=True, next_notice_date__lte=as_of,
            ).exclude(pk__in=seen).order_by("next_notice_date", "pk").first())
            if reminder is None:
                break
            seen.append(reminder.pk)
            processed += 1
            for _ in range(min(per_reminder, limit - created)):
                if reminder.next_notice_date is None or reminder.next_notice_date > as_of:
                    break
                due = occurrence_date(reminder.due_date, reminder.recurrence, reminder.next_index)
                _, inserted = ReminderOccurrence.objects.get_or_create(
                    reminder=reminder, index=reminder.next_index,
                    defaults={"due_date": due, "notice_date": reminder.next_notice_date},
                )
                created += int(inserted)
                reminder.next_index += 1
                set_next_notice(reminder)
            reminder.last_scheduled_at = timezone.now()
            reminder.save(update_fields=["next_index", "next_notice_date", "last_scheduled_at"])
    remaining = Reminder.objects.filter(is_active=True, assignee__is_active=True, next_notice_date__lte=as_of).count()
    return {"as_of": as_of.isoformat(), "created": created, "processed": processed, "remaining_definitions": remaining}
