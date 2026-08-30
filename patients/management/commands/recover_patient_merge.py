from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError

from patients.merge_recovery import inspect_patient_merge_recovery, recover_patient_merge


class Command(BaseCommand):
    help = "Dry-run or consume one bounded patient-merge recovery record."

    def add_arguments(self, parser):
        parser.add_argument("recovery_id")
        parser.add_argument("--actor", required=True, help="Active superuser recorded as the recovery actor.")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--confirm", default="")

    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username=options["actor"]).first()
        if actor is None:
            raise CommandError("Recovery actor was not found.")
        recovery_id = options["recovery_id"]
        confirmation = f"RECOVER MERGE {recovery_id}"
        try:
            preview = inspect_patient_merge_recovery(recovery_id=recovery_id, actor=actor)
            if options["dry_run"]:
                self.stdout.write(
                    f"DRY RUN recovery={preview['recovery_id']} source_patient_id={preview['source_patient_id']} "
                    f"target_patient_id={preview['target_patient_id']} moved_case_ids={preview['moved_case_ids']} "
                    f"expires_at={preview['expires_at'].isoformat()}"
                )
                return
            if options["confirm"] != confirmation:
                raise CommandError(f'Exact confirmation required: --confirm "{confirmation}"')
            moved_count = recover_patient_merge(recovery_id=recovery_id, actor=actor)
        except (PermissionDenied, ValidationError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Recovered merge {recovery_id}; restored {moved_count} recorded case(s)."
            )
        )
