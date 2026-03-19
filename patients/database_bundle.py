import hashlib
import io
import json
import subprocess
import zipfile
from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from .models import (
    CallLog,
    Case,
    CaseActivityLog,
    DepartmentConfig,
    PatientDataBackupSchedule,
    PatientDataBackupTrigger,
    Task,
    TaskStatus,
    VitalEntry,
)


BUNDLE_SCHEMA_VERSION = 1
PATIENT_DATA_FILENAME = "patient_data.json"
MANIFEST_FILENAME = "manifest.json"
BACKUP_FILENAME_PREFIX = "patient-data-bundle"
DEFAULT_BACKUP_KEEP = 30
IMPORT_CONFIRMATION_PHRASE = "REPLACE PATIENT DATA"
BACKUP_KIND_DAILY = "daily"
BACKUP_KIND_MONTHLY = "monthly"
BACKUP_KIND_YEARLY = "yearly"
BACKUP_KIND_MANUAL = "manual"
BACKUP_KIND_IMPORT_SAFETY = "import-safety"


class BundleValidationError(Exception):
    pass


def default_backup_dir():
    return Path(settings.BASE_DIR) / "backups"


def list_backup_bundles(limit=5, backup_kind=None):
    backup_dir = default_backup_dir()
    if not backup_dir.exists():
        return []
    bundles = sorted(
        backup_dir.glob(_backup_glob_pattern(backup_kind)),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return bundles[:limit] if limit else bundles


def build_bundle_filename(exported_at=None, backup_kind=None):
    exported_at = exported_at or timezone.now()
    stamp = exported_at.astimezone(dt_timezone.utc).strftime("%Y%m%d-%H%M%S-%fZ")
    kind_suffix = f"-{backup_kind}" if backup_kind else ""
    return f"{BACKUP_FILENAME_PREFIX}{kind_suffix}-{stamp}.zip"


def create_bundle_archive(exported_at=None, backup_kind=None):
    exported_at = exported_at or timezone.now()
    payload = build_patient_data_payload()
    counts = compute_payload_counts(payload)
    patient_data_bytes = _json_bytes(payload)
    manifest = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "exported_at": exported_at.astimezone(dt_timezone.utc).isoformat(),
        "app_version": _app_version(),
        "counts": counts,
        "patient_data_sha256": hashlib.sha256(patient_data_bytes).hexdigest(),
    }
    git_commit = _git_commit()
    if git_commit:
        manifest["git_commit"] = git_commit
    manifest_bytes = _json_bytes(manifest)

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle_zip:
        bundle_zip.writestr(PATIENT_DATA_FILENAME, patient_data_bytes)
        bundle_zip.writestr(MANIFEST_FILENAME, manifest_bytes)
    return archive.getvalue(), manifest, build_bundle_filename(exported_at, backup_kind=backup_kind)


def write_backup_bundle(
    *,
    output_dir=None,
    keep=DEFAULT_BACKUP_KEEP,
    exported_at=None,
    trigger=PatientDataBackupTrigger.MANUAL,
    backup_kind=None,
    schedule_key=None,
):
    output_dir = Path(output_dir) if output_dir else default_backup_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    backup_kind = backup_kind or backup_kind_for_trigger(trigger)
    archive_bytes, manifest, filename = create_bundle_archive(exported_at=exported_at, backup_kind=backup_kind)
    bundle_path = output_dir / filename
    bundle_path.write_bytes(archive_bytes)

    pruned = prune_backup_bundles(output_dir, keep=keep, backup_kind=backup_kind)
    PatientDataBackupSchedule.record_backup_success(
        backup_path=bundle_path,
        trigger=trigger,
        backup_at=exported_at or timezone.now(),
        schedule_key=schedule_key,
    )
    return bundle_path, manifest, pruned


def prune_backup_bundles(output_dir, *, keep, backup_kind=None):
    output_dir = Path(output_dir)
    if keep is None:
        return []
    keep = max(int(keep), 0)
    bundle_paths = sorted(
        output_dir.glob(_backup_glob_pattern(backup_kind)),
        key=lambda path: path.stat().st_mtime,
    )
    if keep == 0:
        to_remove = bundle_paths
    else:
        to_remove = bundle_paths[:-keep]
    for path in to_remove:
        path.unlink(missing_ok=True)
    return to_remove


def import_bundle_bytes(bundle_bytes, *, keep=DEFAULT_BACKUP_KEEP):
    _, payload = load_bundle_archive(bundle_bytes)
    safety_backup_path, _, _ = write_backup_bundle(
        keep=keep,
        trigger=PatientDataBackupTrigger.IMPORT_SAFETY,
        backup_kind=BACKUP_KIND_IMPORT_SAFETY,
    )
    counts = _replace_patient_data(payload)
    return {"counts": counts, "safety_backup_path": safety_backup_path}


def backup_kind_for_trigger(trigger):
    return {
        PatientDataBackupTrigger.DAILY_SCHEDULED: BACKUP_KIND_DAILY,
        PatientDataBackupTrigger.MONTHLY_SCHEDULED: BACKUP_KIND_MONTHLY,
        PatientDataBackupTrigger.YEARLY_SCHEDULED: BACKUP_KIND_YEARLY,
        PatientDataBackupTrigger.IMPORT_SAFETY: BACKUP_KIND_IMPORT_SAFETY,
        PatientDataBackupTrigger.MANUAL: BACKUP_KIND_MANUAL,
        PatientDataBackupTrigger.SCHEDULED: BACKUP_KIND_DAILY,
    }.get(trigger, BACKUP_KIND_MANUAL)


def _backup_glob_pattern(backup_kind=None):
    if backup_kind:
        return f"{BACKUP_FILENAME_PREFIX}-{backup_kind}-*.zip"
    return f"{BACKUP_FILENAME_PREFIX}-*.zip"


def load_bundle_archive(bundle_bytes):
    try:
        with zipfile.ZipFile(io.BytesIO(bundle_bytes)) as bundle_zip:
            names = set(bundle_zip.namelist())
            required_names = {PATIENT_DATA_FILENAME, MANIFEST_FILENAME}
            missing_names = required_names - names
            if missing_names:
                raise BundleValidationError(
                    f"Backup archive is missing required file(s): {', '.join(sorted(missing_names))}."
                )
            patient_data_bytes = bundle_zip.read(PATIENT_DATA_FILENAME)
            manifest_bytes = bundle_zip.read(MANIFEST_FILENAME)
    except zipfile.BadZipFile as exc:
        raise BundleValidationError("Uploaded file is not a valid ZIP archive.") from exc

    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleValidationError("Backup manifest is not valid JSON.") from exc

    try:
        payload = json.loads(patient_data_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleValidationError("Patient data file is not valid JSON.") from exc

    _validate_manifest_and_payload(manifest, payload, patient_data_bytes)
    return manifest, payload


def build_patient_data_payload():
    cases = (
        Case.objects.select_related("category", "created_by", "archived_by")
        .prefetch_related(
            Prefetch(
                "tasks",
                queryset=Task.objects.select_related("assigned_user", "created_by").order_by("due_date", "pk"),
            ),
            Prefetch(
                "vitals",
                queryset=VitalEntry.objects.select_related("created_by", "updated_by").order_by("recorded_at", "pk"),
            ),
            Prefetch(
                "activity_logs",
                queryset=CaseActivityLog.objects.select_related("user", "task").order_by("created_at", "pk"),
            ),
            Prefetch(
                "call_logs",
                queryset=CallLog.objects.select_related("staff_user", "task").order_by("created_at", "pk"),
            ),
        )
        .order_by("uhid")
    )

    categories_by_name = {}
    serialized_cases = []
    for case in cases:
        categories_by_name.setdefault(case.category.name, _serialize_category(case.category))
        serialized_cases.append(_serialize_case(case))

    return {
        "categories": [categories_by_name[name] for name in sorted(categories_by_name)],
        "cases": serialized_cases,
    }


def compute_payload_counts(payload):
    counts = {
        "categories": len(payload.get("categories", [])),
        "cases": len(payload.get("cases", [])),
        "tasks": 0,
        "vitals": 0,
        "activity_logs": 0,
        "call_logs": 0,
    }
    for case_data in payload.get("cases", []):
        counts["tasks"] += len(case_data.get("tasks", []))
        counts["vitals"] += len(case_data.get("vitals", []))
        counts["activity_logs"] += len(case_data.get("activity_logs", []))
        counts["call_logs"] += len(case_data.get("call_logs", []))
    return counts


def _serialize_category(category):
    return {
        "name": category.name,
        "auto_follow_up_days": category.auto_follow_up_days,
        "predefined_actions": category.predefined_actions,
        "metadata_template": category.metadata_template,
        "theme_bg_color": category.theme_bg_color,
        "theme_text_color": category.theme_text_color,
    }


def _serialize_case(case):
    return {
        "uhid": case.uhid,
        "first_name": case.first_name,
        "last_name": case.last_name,
        "gender": case.gender,
        "date_of_birth": _serialize_date(case.date_of_birth),
        "place": case.place,
        "age": case.age,
        "phone_number": case.phone_number,
        "alternate_phone_number": case.alternate_phone_number,
        "category_name": case.category.name,
        "status": case.status,
        "is_archived": case.is_archived,
        "archived_at": _serialize_datetime(case.archived_at),
        "archived_by_username": _username(case.archived_by),
        "diagnosis": case.diagnosis,
        "ncd_flags": case.ncd_flags,
        "referred_by": case.referred_by,
        "high_risk": case.high_risk,
        "anc_high_risk_reasons": case.anc_high_risk_reasons,
        "rch_number": case.rch_number,
        "rch_bypass": case.rch_bypass,
        "lmp": _serialize_date(case.lmp),
        "edd": _serialize_date(case.edd),
        "usg_edd": _serialize_date(case.usg_edd),
        "surgical_pathway": case.surgical_pathway,
        "surgery_done": case.surgery_done,
        "review_frequency": case.review_frequency,
        "review_date": _serialize_date(case.review_date),
        "surgery_date": _serialize_date(case.surgery_date),
        "gravida": case.gravida,
        "para": case.para,
        "abortions": case.abortions,
        "living": case.living,
        "metadata": case.metadata,
        "notes": case.notes,
        "created_by_username": _username(case.created_by),
        "created_at": _serialize_datetime(case.created_at),
        "updated_at": _serialize_datetime(case.updated_at),
        "tasks": [_serialize_task(task) for task in case.tasks.all()],
        "vitals": [_serialize_vital(entry) for entry in case.vitals.all()],
        "activity_logs": [_serialize_activity_log(entry) for entry in case.activity_logs.all()],
        "call_logs": [_serialize_call_log(entry) for entry in case.call_logs.all()],
    }


def _serialize_task(task):
    return {
        "bundle_id": str(task.pk),
        "title": task.title,
        "due_date": _serialize_date(task.due_date),
        "status": task.status,
        "assigned_user_username": _username(task.assigned_user),
        "task_type": task.task_type,
        "frequency_label": task.frequency_label,
        "notes": task.notes,
        "completed_at": _serialize_datetime(task.completed_at),
        "created_by_username": _username(task.created_by),
        "created_at": _serialize_datetime(task.created_at),
        "updated_at": _serialize_datetime(task.updated_at),
    }


def _serialize_vital(entry):
    return {
        "recorded_at": _serialize_datetime(entry.recorded_at),
        "bp_systolic": entry.bp_systolic,
        "bp_diastolic": entry.bp_diastolic,
        "pr": entry.pr,
        "spo2": entry.spo2,
        "weight_kg": _serialize_decimal(entry.weight_kg),
        "hemoglobin": _serialize_decimal(entry.hemoglobin),
        "created_by_username": _username(entry.created_by),
        "updated_by_username": _username(entry.updated_by),
        "created_at": _serialize_datetime(entry.created_at),
        "updated_at": _serialize_datetime(entry.updated_at),
    }


def _serialize_activity_log(entry):
    return {
        "event_type": entry.event_type,
        "note": entry.note,
        "user_username": _username(entry.user),
        "task_bundle_id": str(entry.task_id) if entry.task_id else None,
        "created_at": _serialize_datetime(entry.created_at),
    }


def _serialize_call_log(entry):
    return {
        "outcome": entry.outcome,
        "notes": entry.notes,
        "staff_user_username": _username(entry.staff_user),
        "task_bundle_id": str(entry.task_id) if entry.task_id else None,
        "created_at": _serialize_datetime(entry.created_at),
    }


def _validate_manifest_and_payload(manifest, payload, patient_data_bytes):
    if not isinstance(manifest, dict):
        raise BundleValidationError("Backup manifest must be a JSON object.")
    if manifest.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise BundleValidationError(
            f"Backup schema version {manifest.get('schema_version')} is not supported."
        )
    checksum = manifest.get("patient_data_sha256")
    if not checksum or not isinstance(checksum, str):
        raise BundleValidationError("Backup manifest is missing the patient-data checksum.")
    if hashlib.sha256(patient_data_bytes).hexdigest() != checksum:
        raise BundleValidationError("Backup checksum mismatch. The archive may be incomplete or modified.")
    if not isinstance(payload, dict):
        raise BundleValidationError("Patient data must be a JSON object.")

    categories = payload.get("categories")
    cases = payload.get("cases")
    if not isinstance(categories, list):
        raise BundleValidationError("Patient data is missing a valid categories list.")
    if not isinstance(cases, list):
        raise BundleValidationError("Patient data is missing a valid cases list.")

    expected_counts = manifest.get("counts")
    if not isinstance(expected_counts, dict):
        raise BundleValidationError("Backup manifest is missing record counts.")
    actual_counts = compute_payload_counts(payload)
    if expected_counts != actual_counts:
        raise BundleValidationError("Backup manifest counts do not match the patient data payload.")

    category_names = set()
    for category in categories:
        name = (category or {}).get("name")
        if not name:
            raise BundleValidationError("Every exported category must include a name.")
        if name in category_names:
            raise BundleValidationError(f"Backup contains duplicate category definitions for {name}.")
        category_names.add(name)

    existing_category_names = set(
        DepartmentConfig.objects.filter(name__in={case.get("category_name") for case in cases if isinstance(case, dict)})
        .values_list("name", flat=True)
    )

    seen_uhids = set()
    for case_data in cases:
        if not isinstance(case_data, dict):
            raise BundleValidationError("Every exported case must be a JSON object.")
        uhid = case_data.get("uhid")
        if not uhid:
            raise BundleValidationError("Every exported case must include a UHID.")
        if uhid in seen_uhids:
            raise BundleValidationError(f"Backup contains duplicate UHIDs: {uhid}.")
        seen_uhids.add(uhid)

        category_name = case_data.get("category_name")
        if not category_name:
            raise BundleValidationError(f"Case {uhid} is missing a category reference.")
        if category_name not in category_names and category_name not in existing_category_names:
            raise BundleValidationError(
                f"Case {uhid} references category {category_name}, which is not bundled or available locally."
            )

        tasks = case_data.get("tasks", [])
        vitals = case_data.get("vitals", [])
        activity_logs = case_data.get("activity_logs", [])
        call_logs = case_data.get("call_logs", [])
        for section_name, records in (
            ("tasks", tasks),
            ("vitals", vitals),
            ("activity_logs", activity_logs),
            ("call_logs", call_logs),
        ):
            if not isinstance(records, list):
                raise BundleValidationError(f"Case {uhid} has an invalid {section_name} list.")

        task_ids = set()
        for task_data in tasks:
            bundle_id = (task_data or {}).get("bundle_id")
            if not bundle_id:
                raise BundleValidationError(f"Case {uhid} contains a task without a bundle identifier.")
            if bundle_id in task_ids:
                raise BundleValidationError(f"Case {uhid} contains duplicate task identifiers.")
            task_ids.add(bundle_id)

        for log_data in activity_logs:
            task_bundle_id = (log_data or {}).get("task_bundle_id")
            if task_bundle_id and task_bundle_id not in task_ids:
                raise BundleValidationError(
                    f"Case {uhid} contains an activity log referencing an unknown task identifier."
                )

        for call_data in call_logs:
            task_bundle_id = (call_data or {}).get("task_bundle_id")
            if task_bundle_id and task_bundle_id not in task_ids:
                raise BundleValidationError(
                    f"Case {uhid} contains a call log referencing an unknown task identifier."
                )


def _replace_patient_data(payload):
    usernames = sorted(_collect_usernames(payload))
    user_model = get_user_model()
    users_by_username = {
        user.username: user for user in user_model.objects.filter(username__in=usernames)
    }

    categories_by_name = {category.name: category for category in DepartmentConfig.objects.all()}
    category_payload_by_name = {
        category["name"]: category for category in payload.get("categories", []) if isinstance(category, dict)
    }

    with transaction.atomic():
        for category_name, category_data in category_payload_by_name.items():
            if category_name in categories_by_name:
                continue
            category = DepartmentConfig(
                name=category_name,
                auto_follow_up_days=_optional_int(category_data.get("auto_follow_up_days"), default=30),
                predefined_actions=category_data.get("predefined_actions") or [],
                metadata_template=category_data.get("metadata_template") or {},
                theme_bg_color=category_data.get("theme_bg_color") or "",
                theme_text_color=category_data.get("theme_text_color") or "",
            )
            category.full_clean()
            category.save()
            categories_by_name[category_name] = category

        Case.objects.all().delete()
        _import_payload(payload, categories_by_name, users_by_username)

    return compute_payload_counts(payload)


def _import_payload(payload, categories_by_name, users_by_username):
    for case_data in payload.get("cases", []):
        category = categories_by_name[case_data["category_name"]]
        case = Case(
            uhid=case_data["uhid"],
            first_name=case_data.get("first_name", ""),
            last_name=case_data.get("last_name", ""),
            gender=case_data.get("gender", ""),
            date_of_birth=_parse_date(case_data.get("date_of_birth"), "date_of_birth"),
            place=case_data.get("place", ""),
            age=_optional_int(case_data.get("age")),
            phone_number=case_data.get("phone_number", ""),
            alternate_phone_number=case_data.get("alternate_phone_number", ""),
            category=category,
            status=case_data.get("status", ""),
            is_archived=bool(case_data.get("is_archived", False)),
            archived_at=_parse_datetime(case_data.get("archived_at"), "archived_at"),
            archived_by=users_by_username.get(case_data.get("archived_by_username")),
            diagnosis=case_data.get("diagnosis", ""),
            ncd_flags=case_data.get("ncd_flags") or [],
            referred_by=case_data.get("referred_by", ""),
            high_risk=bool(case_data.get("high_risk", False)),
            anc_high_risk_reasons=case_data.get("anc_high_risk_reasons") or [],
            rch_number=case_data.get("rch_number", ""),
            rch_bypass=bool(case_data.get("rch_bypass", False)),
            lmp=_parse_date(case_data.get("lmp"), "lmp"),
            edd=_parse_date(case_data.get("edd"), "edd"),
            usg_edd=_parse_date(case_data.get("usg_edd"), "usg_edd"),
            surgical_pathway=case_data.get("surgical_pathway", ""),
            surgery_done=bool(case_data.get("surgery_done", False)),
            review_frequency=case_data.get("review_frequency", ""),
            review_date=_parse_date(case_data.get("review_date"), "review_date"),
            surgery_date=_parse_date(case_data.get("surgery_date"), "surgery_date"),
            gravida=_optional_int(case_data.get("gravida")),
            para=_optional_int(case_data.get("para")),
            abortions=_optional_int(case_data.get("abortions")),
            living=_optional_int(case_data.get("living")),
            metadata=case_data.get("metadata") or {},
            notes=case_data.get("notes", ""),
            created_by=users_by_username.get(case_data.get("created_by_username")),
        )
        case.full_clean(exclude=_blank_model_fields(case, "created_by", "archived_by"))
        case.save()
        _restore_timestamps(
            case,
            created_at=_parse_datetime(case_data.get("created_at"), "case created_at"),
            updated_at=_parse_datetime(case_data.get("updated_at"), "case updated_at"),
        )

        task_map = {}
        for task_data in case_data.get("tasks", []):
            completed_at = _parse_datetime(task_data.get("completed_at"), "task completed_at")
            if task_data.get("status") == TaskStatus.COMPLETED and completed_at is None:
                completed_at = _parse_datetime(task_data.get("updated_at"), "task updated_at") or _parse_datetime(
                    task_data.get("created_at"), "task created_at"
                )
            task = Task(
                case=case,
                title=task_data.get("title", ""),
                due_date=_parse_date(task_data.get("due_date"), "task due_date"),
                status=task_data.get("status", TaskStatus.SCHEDULED),
                assigned_user=users_by_username.get(task_data.get("assigned_user_username")),
                task_type=task_data.get("task_type", ""),
                frequency_label=task_data.get("frequency_label", ""),
                notes=task_data.get("notes", ""),
                completed_at=completed_at,
                created_by=users_by_username.get(task_data.get("created_by_username")),
            )
            task.full_clean(exclude=_blank_model_fields(task, "assigned_user", "created_by"))
            task.save()
            _restore_timestamps(
                task,
                created_at=_parse_datetime(task_data.get("created_at"), "task created_at"),
                updated_at=_parse_datetime(task_data.get("updated_at"), "task updated_at"),
            )
            task_map[task_data["bundle_id"]] = task

        for vital_data in case_data.get("vitals", []):
            vital = VitalEntry(
                case=case,
                recorded_at=_parse_datetime(vital_data.get("recorded_at"), "vital recorded_at"),
                bp_systolic=_optional_int(vital_data.get("bp_systolic")),
                bp_diastolic=_optional_int(vital_data.get("bp_diastolic")),
                pr=_optional_int(vital_data.get("pr")),
                spo2=_optional_int(vital_data.get("spo2")),
                weight_kg=_parse_decimal(vital_data.get("weight_kg"), "vital weight_kg"),
                hemoglobin=_parse_decimal(vital_data.get("hemoglobin"), "vital hemoglobin"),
                created_by=users_by_username.get(vital_data.get("created_by_username")),
                updated_by=users_by_username.get(vital_data.get("updated_by_username")),
            )
            vital.full_clean(exclude=_blank_model_fields(vital, "created_by", "updated_by"))
            vital.save()
            _restore_timestamps(
                vital,
                created_at=_parse_datetime(vital_data.get("created_at"), "vital created_at"),
                updated_at=_parse_datetime(vital_data.get("updated_at"), "vital updated_at"),
            )

        for log_data in case_data.get("activity_logs", []):
            activity_log = CaseActivityLog(
                case=case,
                task=task_map.get(log_data.get("task_bundle_id")),
                user=users_by_username.get(log_data.get("user_username")),
                event_type=log_data.get("event_type", ""),
                note=log_data.get("note", ""),
            )
            activity_log.full_clean(exclude=_blank_model_fields(activity_log, "user", "task"))
            activity_log.save()
            created_at = _parse_datetime(log_data.get("created_at"), "activity log created_at")
            if created_at:
                CaseActivityLog.objects.filter(pk=activity_log.pk).update(created_at=created_at)

        for call_data in case_data.get("call_logs", []):
            call_log = CallLog(
                case=case,
                task=task_map.get(call_data.get("task_bundle_id")),
                outcome=call_data.get("outcome", ""),
                notes=call_data.get("notes", ""),
                staff_user=users_by_username.get(call_data.get("staff_user_username")),
            )
            call_log.full_clean(exclude=_blank_model_fields(call_log, "task", "staff_user"))
            call_log.save()
            created_at = _parse_datetime(call_data.get("created_at"), "call log created_at")
            if created_at:
                CallLog.objects.filter(pk=call_log.pk).update(created_at=created_at)


def _restore_timestamps(instance, *, created_at=None, updated_at=None):
    update_fields = {}
    if created_at is not None and hasattr(instance, "created_at"):
        update_fields["created_at"] = created_at
    if updated_at is not None and hasattr(instance, "updated_at"):
        update_fields["updated_at"] = updated_at
    if not update_fields:
        return
    instance.__class__.objects.filter(pk=instance.pk).update(**update_fields)
    for field_name, value in update_fields.items():
        setattr(instance, field_name, value)


def _collect_usernames(payload):
    usernames = set()
    for case_data in payload.get("cases", []):
        for key in ("created_by_username", "archived_by_username"):
            username = case_data.get(key)
            if username:
                usernames.add(username)
        for task_data in case_data.get("tasks", []):
            for key in ("assigned_user_username", "created_by_username"):
                username = task_data.get(key)
                if username:
                    usernames.add(username)
        for vital_data in case_data.get("vitals", []):
            for key in ("created_by_username", "updated_by_username"):
                username = vital_data.get(key)
                if username:
                    usernames.add(username)
        for log_data in case_data.get("activity_logs", []):
            username = log_data.get("user_username")
            if username:
                usernames.add(username)
        for call_data in case_data.get("call_logs", []):
            username = call_data.get("staff_user_username")
            if username:
                usernames.add(username)
    return usernames


def _blank_model_fields(instance, *field_names):
    return [field_name for field_name in field_names if getattr(instance, field_name, None) is None]


def _parse_date(value, field_name):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise BundleValidationError(f"Invalid {field_name} value: {value}.") from exc


def _parse_datetime(value, field_name):
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise BundleValidationError(f"Invalid {field_name} value: {value}.") from exc
    if timezone.is_naive(parsed):
        return parsed.replace(tzinfo=dt_timezone.utc)
    return parsed.astimezone(dt_timezone.utc)


def _parse_decimal(value, field_name):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BundleValidationError(f"Invalid {field_name} value: {value}.") from exc


def _optional_int(value, default=None):
    if value in (None, ""):
        return default
    return int(value)


def _serialize_date(value):
    return value.isoformat() if value else None


def _serialize_datetime(value):
    return value.astimezone(dt_timezone.utc).isoformat() if value else None


def _serialize_decimal(value):
    return str(value) if value is not None else None


def _username(user):
    return getattr(user, "username", None)


def _json_bytes(value):
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")


def _app_version():
    version_path = Path(settings.BASE_DIR) / "VERSION"
    if version_path.exists():
        return version_path.read_text(encoding="utf-8").strip()
    return ""


def _git_commit():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=settings.BASE_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()
