import logging
import secrets
from datetime import timedelta
from enum import StrEnum

from django.db.models import Q
from django.utils import timezone

from . import database_bundle
from .models import PatientDataBackupSchedule, PatientDataBackupTrigger


LOGGER = logging.getLogger(__name__)
LOCK_LEASE = timedelta(minutes=10)
SCHEDULED_RUN_CONFIG = {
    "daily": {
        "trigger": PatientDataBackupTrigger.DAILY_SCHEDULED,
        "keep": lambda schedule: schedule.retention_count,
    },
    "monthly": {
        "trigger": PatientDataBackupTrigger.MONTHLY_SCHEDULED,
        "keep": lambda schedule: None,
    },
    "yearly": {
        "trigger": PatientDataBackupTrigger.YEARLY_SCHEDULED,
        "keep": lambda schedule: None,
    },
}


class ScheduledBackupRunResult(StrEnum):
    CREATED = "created"
    NOT_DUE = "not-due"
    LOCK_HELD = "lock-held"


def run_due_scheduled_backup(reference_time=None):
    reference_time = reference_time or timezone.now()
    schedule = PatientDataBackupSchedule.get_solo()
    due_runs = schedule.due_scheduled_runs(reference_time)
    if not due_runs:
        return ScheduledBackupRunResult.NOT_DUE

    lock_token = secrets.token_hex(16)
    lock_until = reference_time + LOCK_LEASE
    claimed = PatientDataBackupSchedule.objects.filter(pk=schedule.pk).filter(
        Q(run_lock_until__isnull=True) | Q(run_lock_until__lt=reference_time)
    ).update(run_lock_until=lock_until, run_lock_token=lock_token)
    if not claimed:
        return ScheduledBackupRunResult.LOCK_HELD

    try:
        schedule = PatientDataBackupSchedule.get_solo()
        due_runs = schedule.due_scheduled_runs(reference_time)
        if not due_runs:
            return ScheduledBackupRunResult.NOT_DUE
        for due_run in due_runs:
            config = SCHEDULED_RUN_CONFIG[due_run["schedule_key"]]
            database_bundle.write_backup_bundle(
                keep=config["keep"](schedule),
                exported_at=reference_time,
                trigger=config["trigger"],
                schedule_key=due_run["schedule_key"],
            )
        return ScheduledBackupRunResult.CREATED
    except Exception as exc:
        PatientDataBackupSchedule.record_backup_failure(
            error=str(exc),
            trigger=PatientDataBackupTrigger.SCHEDULED,
        )
        LOGGER.exception("Scheduled patient-data backup failed.")
        raise
    finally:
        PatientDataBackupSchedule.objects.filter(pk=schedule.pk, run_lock_token=lock_token).update(
            run_lock_until=None,
            run_lock_token="",
        )
