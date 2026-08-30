from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .audit import record_audit_event
from .models import AuditEvent, Case, Patient, PatientMergeRecovery


def _locked_recovery_state(*, recovery_id, actor):
    if not (
        getattr(actor, "is_authenticated", False)
        and getattr(actor, "is_active", False)
        and getattr(actor, "is_superuser", False)
    ):
        raise PermissionDenied("Patient merge recovery requires an active superuser.")

    recovery = (
        PatientMergeRecovery.objects.select_for_update()
        .select_related("source_patient", "target_patient")
        .filter(recovery_id=recovery_id)
        .first()
    )
    if recovery is None:
        raise ValidationError("Patient merge recovery record was not found.")
    if recovery.consumed_at is not None:
        raise ValidationError("Patient merge recovery was already consumed.")
    if recovery.expires_at <= timezone.now():
        raise ValidationError("Patient merge recovery has expired; use a database restore.")

    patient_ids = sorted([recovery.source_patient_id, recovery.target_patient_id])
    locked_patients = {
        patient.pk: patient
        for patient in Patient.objects.select_for_update().filter(pk__in=patient_ids).order_by("pk")
    }
    if len(locked_patients) != 2:
        raise ValidationError("A merge patient record is missing; use a database restore.")
    source = locked_patients[recovery.source_patient_id]
    target = locked_patients[recovery.target_patient_id]
    if source.merged_into_id != target.pk or target.merged_into_id is not None:
        raise ValidationError("Merge topology changed; use a database restore.")

    related_recoveries = list(
        PatientMergeRecovery.objects.select_for_update()
        .filter(
            Q(source_patient_id__in=patient_ids)
            | Q(target_patient_id__in=patient_ids)
        )
        .order_by("created_at", "pk")
    )
    if any(
        item.pk != recovery.pk and item.created_at > recovery.created_at
        for item in related_recoveries
    ):
        raise ValidationError("A later merge or recovery conflicts with this record; use a database restore.")

    case_ids = recovery.moved_case_ids
    if type(case_ids) is not list or any(type(case_id) is not int or case_id <= 0 for case_id in case_ids):
        raise ValidationError("Merge recovery case evidence is invalid; use a database restore.")
    if len(case_ids) != len(set(case_ids)):
        raise ValidationError("Merge recovery case evidence is duplicated; use a database restore.")
    cases = list(Case.objects.select_for_update().filter(pk__in=case_ids).order_by("pk"))
    if len(cases) != len(case_ids) or any(case.patient_id != target.pk for case in cases):
        raise ValidationError("A recorded case moved after the merge; use a database restore.")
    if Case.objects.select_for_update().filter(patient_id=source.pk).exists():
        raise ValidationError("The preserved source has later cases; use a database restore.")
    return recovery, source, target, cases


def inspect_patient_merge_recovery(*, recovery_id, actor):
    with transaction.atomic():
        recovery, source, target, cases = _locked_recovery_state(
            recovery_id=recovery_id,
            actor=actor,
        )
        return {
            "recovery_id": str(recovery.recovery_id),
            "source_patient_id": source.pk,
            "target_patient_id": target.pk,
            "moved_case_ids": [case.pk for case in cases],
            "expires_at": recovery.expires_at,
        }


def recover_patient_merge(*, recovery_id, actor):
    with transaction.atomic():
        recovery, source, target, cases = _locked_recovery_state(
            recovery_id=recovery_id,
            actor=actor,
        )
        source.merged_into = None
        source.save(update_fields=["merged_into", "updated_at"])

        for case in cases:
            case.patient = source
            case.sync_identity_from_patient()
            case.save(
                update_fields=[
                    "patient",
                    "uhid",
                    "prefix",
                    "first_name",
                    "last_name",
                    "patient_name",
                    "gender",
                    "blood_group",
                    "date_of_birth",
                    "place",
                    "age",
                    "phone_number",
                    "alternate_phone_number",
                    "updated_at",
                ]
            )

        audit_event = record_audit_event(
            category=AuditEvent.Category.CLINICAL,
            action="patient.merge_recovered",
            actor=actor,
            object_type="patient_merge_recovery",
            object_id=recovery.recovery_id,
            patient_id=source.pk,
            metadata={
                "source_patient_id": source.pk,
                "target_patient_id": target.pk,
                "moved_case_ids": [case.pk for case in cases],
                "merge_audit_event_id": str(recovery.merge_audit_event.event_id),
            },
        )
        recovery.consumed_at = timezone.now()
        recovery.consumed_by = actor
        recovery.recovery_audit_event = audit_event
        recovery.save(
            update_fields=["consumed_at", "consumed_by", "recovery_audit_event"]
        )
        return len(cases)
