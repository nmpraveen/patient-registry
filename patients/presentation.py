"""Shared current-age presentation; entered age is used only without a DOB."""
from django.utils import timezone


def current_age(record, *, today=None):
    if record.date_of_birth:
        today = today or timezone.localdate()
        born = record.date_of_birth
        return max(0, today.year - born.year - ((today.month, today.day) < (born.month, born.day)))
    return record.age
