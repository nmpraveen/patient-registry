from contextvars import ContextVar
from functools import wraps
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils.crypto import salted_hmac

from .models import AuditEvent


_current_request = ContextVar("medtrack_audit_request", default=None)
SENSITIVE_METADATA_KEY_PARTS = {
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
}
AUDITED_BULK_BYPASS_INVENTORY = {
    "patients.database_bundle._import_payload": "Covered by one outer transaction and patient_data.imported.",
    "patients.database_bundle._restore_timestamps": "Technical timestamp restoration inside the import transaction.",
    "patients.auth_security": "Security-state and throttle updates have explicit IAM audit or are non-domain counters.",
    "patients.backup_scheduler": "Scheduler lease counters are non-clinical operational state.",
}


def install_user_audit_boundary():
    User = get_user_model()
    for model in (User, Group):
        if getattr(model, "_medtrack_mandatory_audit_boundary", False):
            continue
        original_save = model.save

        @wraps(original_save)
        def audited_save(instance, *args, _original_save=original_save, **kwargs):
            if transaction.get_connection().in_atomic_block:
                return _original_save(instance, *args, **kwargs)
            with transaction.atomic():
                return _original_save(instance, *args, **kwargs)

        model.save = audited_save
        model._medtrack_mandatory_audit_boundary = True


def set_current_request(request):
    return _current_request.set(request)


def reset_current_request(token):
    _current_request.reset(token)


def current_request():
    return _current_request.get()


def _digest(value, *, salt):
    if not value:
        return ""
    return salted_hmac(salt, str(value)).hexdigest()


def _clean_metadata(value, *, depth=0):
    if depth > 3:
        return "[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:256]
    if isinstance(value, (list, tuple, set)):
        return [_clean_metadata(item, depth=depth + 1) for item in list(value)[:50]]
    if isinstance(value, dict):
        cleaned = {}
        for key, item in list(value.items())[:50]:
            clean_key = str(key)[:80]
            normalized_key = clean_key.casefold()
            if any(part in normalized_key for part in SENSITIVE_METADATA_KEY_PARTS):
                cleaned[clean_key] = "[redacted]"
            else:
                cleaned[clean_key] = _clean_metadata(item, depth=depth + 1)
        return cleaned
    return str(value)[:256]


def record_audit_event(
    *,
    category,
    action,
    outcome=AuditEvent.Outcome.SUCCESS,
    actor=None,
    request=None,
    source=None,
    object_type="",
    object_id="",
    patient_id=None,
    case_id=None,
    metadata=None,
):
    request = request or current_request()
    if actor is None and request is not None:
        request_user = getattr(request, "user", None)
        if getattr(request_user, "is_authenticated", False):
            actor = request_user

    request_id = ""
    session_key_hash = ""
    source_ip_hash = ""
    device_credential_id = None
    if request is not None:
        request_id = (request.headers.get("X-Request-ID") or str(uuid.uuid4()))[:64]
        session = getattr(request, "session", None)
        if session is not None:
            session_key_hash = _digest(session.session_key, salt="patients.audit.session")
            device_credential_id = session.get("medtrack_device_credential_id")
        source_ip_hash = _digest(request.META.get("REMOTE_ADDR", ""), salt="patients.audit.ip")
        if source is None:
            source = "api" if request.path.startswith("/api/") else "web"

    return AuditEvent.objects.create(
        category=category,
        action=action[:80],
        outcome=outcome,
        actor_user_id=getattr(actor, "pk", None),
        actor_username=(getattr(actor, "get_username", lambda: "")() or "")[:150] if actor else "",
        source=(source or "system")[:32],
        request_id=request_id,
        session_key_hash=session_key_hash,
        source_ip_hash=source_ip_hash,
        device_credential_id=device_credential_id,
        object_type=(object_type or "")[:80],
        object_id=str(object_id or "")[:80],
        patient_id=patient_id,
        case_id=case_id,
        metadata=_clean_metadata(metadata or {}),
    )


def audited_bulk_update(
    queryset,
    *,
    category,
    action,
    changed_fields,
    actor=None,
    request=None,
    patient_id=None,
    **updates,
):
    object_type = queryset.model._meta.label_lower
    with transaction.atomic():
        objects = list(queryset.select_for_update().order_by("pk"))
        if not objects:
            return 0
        object_ids = [instance.pk for instance in objects]
        updated = queryset.model.objects.filter(pk__in=object_ids).update(**updates)
        for instance in objects:
            instance_patient_id = patient_id
            if instance_patient_id is None:
                instance_patient_id = getattr(instance, "patient_id", None)
            instance_case_id = instance.pk if object_type == "patients.case" else getattr(instance, "case_id", None)
            record_audit_event(
                category=category,
                action=action,
                actor=actor,
                request=request,
                object_type=object_type,
                object_id=instance.pk,
                patient_id=instance_patient_id,
                case_id=instance_case_id,
                metadata={"changed_fields": sorted(changed_fields)},
            )
        return updated
