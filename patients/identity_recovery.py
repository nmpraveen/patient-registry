"""Identity-only checkpoints for offline recovery; never contain demographics."""

import hashlib
import json
from uuid import UUID

from django.core.exceptions import ValidationError

from .identity import identity_allocation_lock, identity_checkpoint, parse_mtno, reconcile_identity_allocator
from .models import Case, Patient

CHECKPOINT_FORMAT = "medtrack-identity-checkpoint-v1"
MAX_CHECKPOINT_BYTES = 128 * 1024 * 1024
MAX_HIGH_WATER = 9223372036854775807


def validate_identity_checkpoint(checkpoint):
    if not isinstance(checkpoint, dict):
        raise ValidationError("Identity checkpoint must be an object.")
    floor = checkpoint.get("high_water")
    if type(floor) is not int or not 0 <= floor <= MAX_HIGH_WATER:
        raise ValidationError("Identity high-water must be a nonnegative signed bigint.")
    bindings = checkpoint.get("bindings")
    if not isinstance(bindings, list):
        raise ValidationError("Identity checkpoint requires issuance bindings.")
    by_mtno, by_uuid = {}, {}
    for binding in bindings:
        if not isinstance(binding, dict):
            raise ValidationError("Invalid identity issuance binding.")
        mtno, raw_uuid = binding.get("mtno"), binding.get("identity_uuid")
        number = parse_mtno(mtno)
        try:
            identity_uuid = str(UUID(raw_uuid))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValidationError("Invalid identity UUID.") from exc
        if raw_uuid != identity_uuid or identity_uuid == str(UUID(int=0)):
            raise ValidationError("Identity UUID must be canonical and nonzero.")
        if mtno in by_mtno or identity_uuid in by_uuid:
            raise ValidationError("Duplicate identity issuance binding.")
        if number > floor:
            raise ValidationError("Identity high-water is below an issued MTNO.")
        by_mtno[mtno] = identity_uuid
        by_uuid[identity_uuid] = mtno
    return by_mtno


def encode_identity_checkpoint(checkpoint):
    validate_identity_checkpoint(checkpoint)
    data = json.dumps(checkpoint, sort_keys=True, separators=(",", ":")).encode()
    return json.dumps({
        "format": CHECKPOINT_FORMAT,
        "checkpoint": checkpoint,
        "sha256": hashlib.sha256(data).hexdigest(),
    }, sort_keys=True, indent=2) + "\n"


def decode_identity_checkpoint(raw):
    if len(raw) > MAX_CHECKPOINT_BYTES:
        raise ValidationError("Identity checkpoint exceeds the size limit.")
    try:
        envelope = json.loads(raw)
        if not isinstance(envelope, dict) or envelope.get("format") != CHECKPOINT_FORMAT:
            raise ValueError
        checkpoint = envelope["checkpoint"]
        validate_identity_checkpoint(checkpoint)
        data = json.dumps(checkpoint, sort_keys=True, separators=(",", ":")).encode()
        if envelope.get("sha256") != hashlib.sha256(data).hexdigest():
            raise ValueError
    except (ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
        raise ValidationError("Invalid identity checkpoint envelope or checksum.") from exc
    return checkpoint


def verify_patient_identities(*, using="default", repair_floor=False):
    """Verify stored lineage. Does not claim knowledge of post-snapshot issuance."""
    with identity_allocation_lock(using=using):
        checkpoint = identity_checkpoint(using=using)
        if repair_floor:
            # The shared service reconciles retained ledger/Patient maxima upward.
            checkpoint = reconcile_identity_allocator(using=using)
        bindings = validate_identity_checkpoint(checkpoint)
        patients = list(Patient.objects.using(using).values("id", "mtno", "identity_uuid", "merged_into_id"))
        by_id = {patient["id"]: patient for patient in patients}
        for patient in patients:
            if bindings.get(patient["mtno"]) != str(patient["identity_uuid"]):
                raise ValidationError("Patient identity does not match the issuance ledger.")
            target_id = patient["merged_into_id"]
            if target_id is not None:
                target = by_id.get(target_id)
                if target is None or target_id == patient["id"] or target["merged_into_id"] is not None:
                    raise ValidationError("Patient aliases must reference one unmerged survivor.")
        if Case.objects.using(using).filter(patient__isnull=True).exists():
            raise ValidationError("Unlinked legacy cases require reviewed reconciliation.")
        if Case.objects.using(using).filter(patient__merged_into__isnull=False).exists():
            raise ValidationError("Cases may not remain attached to merged source patients.")
        return {"patients": len(patients), "bindings": len(bindings), "high_water": checkpoint["high_water"]}
