from django.conf import settings
from django.core.exceptions import PermissionDenied
from .models import Reminder
from .services import create_reminder, hospital_today


def seed_demo_reminders(owner, assignee=None):
    """Explicit seed hook; caller supplies synthetic staff, never clinical objects."""
    if not settings.ALLOW_MOCK_DATA_SEEDING:
        raise PermissionDenied("Mock data seeding is disabled.")
    title = "Demo: check office supplies"
    existing = Reminder.objects.filter(owner=owner, title=title).first()
    if existing:
        return existing
    return create_reminder(owner, {"title": title, "assignee_id": (assignee or owner).pk,
                                  "due_date": hospital_today(), "advance_notice_days": 3,
                                  "recurrence": Reminder.Recurrence.EVERY_TWO_MONTHS})
