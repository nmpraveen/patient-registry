import logging
import os
import secrets
import sys
import threading
import time
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from . import database_bundle
from .models import PatientDataBackupSchedule, PatientDataBackupTrigger


LOGGER = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 30
LOCK_LEASE = timedelta(minutes=10)
_scheduler_started = False
_scheduler_lock = threading.Lock()
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


def scheduler_should_start():
    if os.environ.get("DISABLE_PATIENT_BACKUP_SCHEDULER") == "1":
        return False
    disabled_commands = {
        "makemigrations",
        "migrate",
        "showmigrations",
        "test",
        "shell",
        "dbshell",
        "createsuperuser",
        "collectstatic",
        "backup_patient_data",
    }
    return not any(command in sys.argv for command in disabled_commands)


def start_background_scheduler():
    global _scheduler_started
    if not scheduler_should_start():
        return
    with _scheduler_lock:
        if _scheduler_started:
            return
        thread = threading.Thread(
            target=_scheduler_loop,
            name="patient-backup-scheduler",
            daemon=True,
        )
        thread.start()
        _scheduler_started = True


def _scheduler_loop():
    while True:
        try:
            run_due_scheduled_backup()
        except Exception:
            LOGGER.exception("Patient backup scheduler loop failed.")
        time.sleep(POLL_INTERVAL_SECONDS)


def run_due_scheduled_backup(reference_time=None):
    reference_time = reference_time or timezone.now()
    schedule = PatientDataBackupSchedule.get_solo()
    due_runs = schedule.due_scheduled_runs(reference_time)
    if not due_runs:
        return False

    lock_token = secrets.token_hex(16)
    lock_until = reference_time + LOCK_LEASE
    claimed = PatientDataBackupSchedule.objects.filter(pk=schedule.pk).filter(
        Q(run_lock_until__isnull=True) | Q(run_lock_until__lt=reference_time)
    ).update(run_lock_until=lock_until, run_lock_token=lock_token)
    if not claimed:
        return False

    try:
        schedule = PatientDataBackupSchedule.get_solo()
        due_runs = schedule.due_scheduled_runs(reference_time)
        if not due_runs:
            return False
        ran_any = False
        for due_run in due_runs:
            config = SCHEDULED_RUN_CONFIG[due_run["schedule_key"]]
            database_bundle.write_backup_bundle(
                keep=config["keep"](schedule),
                exported_at=reference_time,
                trigger=config["trigger"],
                schedule_key=due_run["schedule_key"],
            )
            ran_any = True
        return ran_any
    except Exception as exc:
        PatientDataBackupSchedule.record_backup_failure(
            error=str(exc),
            trigger=PatientDataBackupTrigger.SCHEDULED,
        )
        LOGGER.exception("Scheduled patient-data backup failed.")
        return False
    finally:
        PatientDataBackupSchedule.objects.filter(pk=schedule.pk, run_lock_token=lock_token).update(
            run_lock_until=None,
            run_lock_token="",
        )
