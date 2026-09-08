from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from patients.identity_recovery import verify_patient_identities


class Command(BaseCommand):
    help = "Verify stored patient identity/ledger/aliases; optionally repair only an upward allocation floor."

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default")
        parser.add_argument("--repair-floor", action="store_true")

    def handle(self, *args, **options):
        try:
            result = verify_patient_identities(using=options["database"], repair_floor=options["repair_floor"])
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc
        self.stdout.write(
            "IDENTITY_VERIFY_OK patients={patients} bindings={bindings} high_water={high_water} "
            "scope=stored-snapshot".format(**result)
        )
