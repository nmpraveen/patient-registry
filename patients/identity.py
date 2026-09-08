"""Permanent identity allocation and scoped query predicates.

Creation/import order: allocator -> issuance -> Patient -> Case. Existing-patient
edits and merge/recovery never allocate. Issuance survives patient replacement.
"""

from contextlib import contextmanager
import re
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

MAX_IDENTITY_NUMBER = 9223372036854775807


def format_mtno(number):
    if type(number) is not int or not 1 <= number <= MAX_IDENTITY_NUMBER:
        raise ValidationError("Invalid MTNO allocation number.")
    return f"MT-{number:06d}"


def parse_mtno(value):
    if not isinstance(value, str) or not re.fullmatch(r"MT-[0-9]{6,19}", value):
        raise ValidationError("Invalid canonical MTNO.")
    number = int(value[3:])
    if format_mtno(number) != value:
        raise ValidationError("Invalid canonical MTNO.")
    return number


def _identity_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError("Invalid patient identity binding.") from exc


@contextmanager
def identity_allocation_lock(*, using="default"):
    from .models import PatientIdentityAllocator, PatientIdentityIssuance

    with transaction.atomic(using=using):
        allocator, created = PatientIdentityAllocator.objects.using(using).select_for_update().get_or_create(pk=1)
        if created:
            # Fresh test/empty DB, or recovery of a missing singleton: never lower retained issuance.
            allocator.high_water = max(
                (parse_mtno(value) for value in PatientIdentityIssuance.objects.using(using).values_list("mtno", flat=True)),
                default=0,
            )
            allocator.save(using=using, update_fields=["high_water"])
        yield allocator


def _register_binding(allocator, *, mtno, identity_uuid, using):
    from .models import Patient, PatientIdentityIssuance

    number = parse_mtno(mtno)
    identity_uuid = _identity_uuid(identity_uuid)
    ledger = PatientIdentityIssuance.objects.using(using)
    candidates = list(ledger.filter(Q(mtno=mtno) | Q(identity_uuid=identity_uuid)))
    if any(item.mtno != mtno or item.identity_uuid != identity_uuid for item in candidates):
        raise ValidationError("Imported identity conflicts with a permanently issued MTNO.")
    if Patient.objects.using(using).filter(Q(mtno=mtno) | Q(identity_uuid=identity_uuid)).exclude(
        mtno=mtno, identity_uuid=identity_uuid,
    ).exists():
        raise ValidationError("Imported identity conflicts with an existing patient.")
    if not candidates:
        ledger.create(mtno=mtno, identity_uuid=identity_uuid)
    if number > allocator.high_water:
        allocator.high_water = number
        allocator.save(using=using, update_fields=["high_water"])


def register_identity_binding(*, mtno, identity_uuid, using="default"):
    with identity_allocation_lock(using=using) as allocator:
        _register_binding(allocator, mtno=mtno, identity_uuid=identity_uuid, using=using)


def reserve_patient_identity(patient, *, using="default"):
    with identity_allocation_lock(using=using) as allocator:
        if not patient.mtno:
            patient.mtno = format_mtno(allocator.high_water + 1)
        if not patient.identity_uuid:
            patient.identity_uuid = uuid.uuid4()
        _register_binding(allocator, mtno=patient.mtno, identity_uuid=patient.identity_uuid, using=using)


def _checkpoint(allocator, using):
    from .models import PatientIdentityIssuance

    return {
        "high_water": allocator.high_water,
        "bindings": [
            {"mtno": row.mtno, "identity_uuid": str(row.identity_uuid)}
            for row in PatientIdentityIssuance.objects.using(using).order_by("mtno")
        ],
    }


def identity_checkpoint(*, using="default"):
    with identity_allocation_lock(using=using) as allocator:
        return _checkpoint(allocator, using)


def reconcile_identity_allocator(*, minimum_high_water=0, bindings=(), using="default"):
    from .models import Patient, PatientIdentityIssuance

    if type(minimum_high_water) is not int or not 0 <= minimum_high_water <= MAX_IDENTITY_NUMBER:
        raise ValidationError("Invalid identity high-water checkpoint.")
    with identity_allocation_lock(using=using) as allocator:
        all_bindings = list(bindings)
        all_bindings.extend(Patient.objects.using(using).values("mtno", "identity_uuid"))
        all_bindings.extend(PatientIdentityIssuance.objects.using(using).values("mtno", "identity_uuid"))
        for binding in all_bindings:
            if not isinstance(binding, dict) or "mtno" not in binding or "identity_uuid" not in binding:
                raise ValidationError("Invalid identity checkpoint binding.")
            _register_binding(allocator, mtno=binding["mtno"], identity_uuid=binding["identity_uuid"], using=using)
        if minimum_high_water > allocator.high_water:
            allocator.high_water = minimum_high_water
            allocator.save(using=using, update_fields=["high_water"])
        return _checkpoint(allocator, using)


def patient_identifier_query(query, *, lookup="icontains"):
    """Apply only to already-scoped survivor querysets; aliases expose no demographics."""
    from .models import Patient

    alias_targets = Patient.objects.filter(merged_into__isnull=False).filter(
        Q(**{f"mtno__{lookup}": query}) | Q(**{f"uhid__{lookup}": query})
    ).values("merged_into_id")
    return (
        Q(**{f"mtno__{lookup}": query}) | Q(**{f"uhid__{lookup}": query})
        | Q(pk__in=alias_targets)
    )


def case_identifier_query(query, *, lookup="icontains"):
    from .models import Patient

    matches = Patient.objects.filter(merged_into__isnull=True).filter(patient_identifier_query(query, lookup=lookup))
    return Q(patient_id__in=matches.values("pk")) | Q(**{f"uhid__{lookup}": query})
