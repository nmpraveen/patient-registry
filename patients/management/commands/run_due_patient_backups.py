from django.core.management.base import BaseCommand, CommandError

from patients.backup_scheduler import ScheduledBackupRunResult, run_due_scheduled_backup


class Command(BaseCommand):
    help = "Run any due patient-data backup schedules once, for a supervised host timer."

    def handle(self, *args, **options):
        result = run_due_scheduled_backup()
        if result == ScheduledBackupRunResult.CREATED:
            self.stdout.write(self.style.SUCCESS("DUE_PATIENT_BACKUPS_OK result=created"))
        elif result in {ScheduledBackupRunResult.NOT_DUE, ScheduledBackupRunResult.LOCK_HELD}:
            self.stdout.write(f"DUE_PATIENT_BACKUPS_OK result={result.value}")
        else:
            raise CommandError(f"Unexpected scheduled backup result: {result!r}")
