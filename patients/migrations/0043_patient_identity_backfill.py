"""Preserve source data; stop at ambiguous legacy identity instead of guessing."""
import uuid
import re

from django.db import migrations


def backfill(apps, schema_editor):
    using = schema_editor.connection.alias
    Patient = apps.get_model("patients", "Patient")
    Case = apps.get_model("patients", "Case")
    Allocator = apps.get_model("patients", "PatientIdentityAllocator")
    Issuance = apps.get_model("patients", "PatientIdentityIssuance")
    allocator, _ = Allocator.objects.using(using).select_for_update().get_or_create(pk=1)
    patients = list(Patient.objects.using(using).order_by("pk"))
    by_uhid = {}
    for patient in patients:
        canonical = " ".join(patient.uhid.split()).upper()
        if re.fullmatch(r"MT-[0-9]+", canonical):
            raise RuntimeError("Legacy UHID uses the reserved MTNO namespace; reviewed reconciliation is required, no identifiers were rewritten.")
        if canonical and (canonical != patient.uhid or canonical in by_uhid):
            raise RuntimeError("Legacy UHID requires explicit identity reconciliation; no identifiers were rewritten.")
        if canonical:
            by_uhid[canonical] = patient
    by_id = {patient.pk: patient for patient in patients}
    for patient in patients:
        if patient.merged_into_id:
            target = by_id.get(patient.merged_into_id)
            if target is None or target.pk == patient.pk or target.merged_into_id:
                raise RuntimeError("Legacy merge topology requires explicit identity reconciliation.")

    identity_fields = ["prefix", "first_name", "last_name", "patient_name", "gender", "blood_group",
                       "date_of_birth", "place", "age", "phone_number", "alternate_phone_number"]
    for uhid in Case.objects.using(using).values_list("uhid", flat=True):
        if re.fullmatch(r"MT-[0-9]+", " ".join(uhid.split()).upper()):
            raise RuntimeError("Legacy case UHID uses the reserved MTNO namespace; reviewed reconciliation is required, no identifiers were rewritten.")
    # Preflight the whole exact-UHID group before linking or allocating. A blank
    # first record cannot establish compatibility between later nonblank values.
    orphan_cases = list(Case.objects.using(using).filter(patient_id__isnull=True).order_by("pk"))
    evidence_by_uhid = {}
    for case in orphan_cases:
        if not case.uhid or case.uhid != " ".join(case.uhid.split()).upper():
            raise RuntimeError("Patientless legacy case requires a reviewed identity mapping before migration.")
        patient = by_uhid.get(case.uhid)
        if patient and patient.merged_into_id:
            raise RuntimeError("Conflicting patientless legacy identity requires reviewed reconciliation.")
        if case.uhid not in evidence_by_uhid:
            evidence_by_uhid[case.uhid] = {
                field: getattr(patient, field) if patient else None for field in identity_fields
            }
        evidence = evidence_by_uhid[case.uhid]
        for field in identity_fields:
            value = getattr(case, field)
            if value in (None, ""):
                continue
            if evidence[field] not in (None, "") and evidence[field] != value:
                raise RuntimeError("Conflicting patientless legacy identity requires reviewed reconciliation.")
            evidence[field] = value

    # Consistent evidence only validates linkage; it does not rewrite or fill
    # historical demographics from other rows.
    for case in orphan_cases:
        patient = by_uhid.get(case.uhid)
        if patient is None:
            patient = Patient.objects.using(using).create(
                uhid=case.uhid, is_temporary_id=case.uhid.startswith("TMP-"),
                created_by_id=case.created_by_id, **{field: getattr(case, field) for field in identity_fields},
            )
            Patient.objects.using(using).filter(pk=patient.pk).update(created_at=case.created_at, updated_at=case.updated_at)
            by_uhid[case.uhid] = patient
            patients.append(patient)
        Case.objects.using(using).filter(pk=case.pk).update(patient_id=patient.pk)

    for value in Issuance.objects.using(using).values_list("mtno", flat=True):
        allocator.high_water = max(allocator.high_water, int(value[3:]))
    for patient in patients:
        if patient.mtno:
            number = int(patient.mtno[3:])
            if number <= 0 or patient.mtno != f"MT-{number:06d}":
                raise RuntimeError("Invalid existing MTNO; reconcile before migration.")
            allocator.high_water = max(allocator.high_water, number)
    for patient in sorted(patients, key=lambda row: row.pk):
        if not patient.mtno:
            allocator.high_water += 1
            patient.mtno = f"MT-{allocator.high_water:06d}"
        patient.identity_uuid = patient.identity_uuid or uuid.uuid4()
        issuance, _ = Issuance.objects.using(using).get_or_create(mtno=patient.mtno, defaults={"identity_uuid": patient.identity_uuid})
        if issuance.identity_uuid != patient.identity_uuid:
            raise RuntimeError("Conflicting MTNO issuance; reconcile before migration.")
        Patient.objects.using(using).filter(pk=patient.pk).update(mtno=patient.mtno, identity_uuid=patient.identity_uuid)
    allocator.save(using=using, update_fields=["high_water"])


def irreversible(apps, schema_editor):
    raise RuntimeError("Issued patient identities cannot be removed. Use verified full recovery and preserve the outgoing identity checkpoint.")


class Migration(migrations.Migration):
    dependencies = [("patients", "0042_patient_identity_add")]
    operations = [migrations.RunPython(backfill, irreversible)]
