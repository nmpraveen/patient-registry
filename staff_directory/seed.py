from datetime import timedelta

from django.conf import settings
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone

from staff_announcements.models import Announcement
from staff_announcements.services import save_announcement
from .access import mutation_actor
from .models import Contact
from .services import save_contact, set_favourite


@transaction.atomic
def seed_demo_operations(owner):
    if not settings.ALLOW_MOCK_DATA_SEEDING:
        raise CommandError("Mock-data seeding is disabled.")
    mutation_actor(owner, manage=True)
    name = "Demo staff switchboard"
    contact = Contact.objects.filter(name=name, organization="Synthetic hospital").first()
    if contact is None:
        contact = save_contact(owner, {
            "name": name, "role_specialty": "Reception", "organization": "Synthetic hospital",
            "phones": [{"label": "Office", "number": "+1 202 555 0100", "extension": "12"},
                       {"label": "On call", "number": "+1 202 555 0101", "extension": ""}],
            "notes": "Synthetic demo contact.",
        })
    if contact.is_active:
        set_favourite(owner, contact.pk, True)
    text = "Demo: staff briefing at the reception desk."
    now = timezone.now()
    if not Announcement.objects.filter(text=text, ends_at__gt=now, is_active=True).exists():
        save_announcement(owner, {"text": text, "priority": "important", "audience": "all_staff",
                                 "starts_at": now, "ends_at": now + timedelta(days=7)})
    return contact
