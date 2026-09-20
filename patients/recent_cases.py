"""Bounded dashboard cursors and conflict baselines for the notes editor."""
import hashlib

from django.core import signing
from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_datetime


def notes_digest(value):
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def notes_baseline(case, user):
    return signing.dumps({"case": case.pk, "patient": case.patient_id, "user": user.pk,
                          "notes": notes_digest(case.notes)}, salt="recent-case-notes", compress=True)


def read_notes_baseline(token, case, user):
    try:
        data = signing.loads(token, salt="recent-case-notes", max_age=43200)
        if data["case"] != case.pk or data["user"] != user.pk:
            raise ValueError
        if not isinstance(data["notes"], str) or len(data["notes"]) != 64:
            raise ValueError
        return data
    except (signing.BadSignature, TypeError, KeyError, ValueError, AttributeError):
        raise ValidationError("Reload the notes editor before saving.", code="invalid_baseline")


def encode_recent_cursor(case, user, binding):
    return signing.dumps({"created": case.created_at.isoformat(), "id": case.pk,
                          "user": user.pk, "binding": binding}, salt="recent-case-page", compress=True)


def decode_recent_cursor(token, user, binding):
    try:
        data = signing.loads(token, salt="recent-case-page", max_age=1800)
        created = parse_datetime(data["created"])
        if (data["user"] != user.pk or data["binding"] != binding or created is None
                or created.tzinfo is None or type(data["id"]) is not int or data["id"] <= 0):
            raise ValueError
        return created, data["id"]
    except (signing.BadSignature, TypeError, KeyError, ValueError, AttributeError):
        raise ValidationError("Refresh recent patients to continue.", code="invalid_cursor")
