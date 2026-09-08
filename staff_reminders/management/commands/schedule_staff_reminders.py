import json
from datetime import date
from django.core.management.base import BaseCommand, CommandError
from staff_reminders.services import schedule_reminders


class Command(BaseCommand):
    help = "Materialize bounded in-app reminder occurrences; no external delivery."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=500)
        parser.add_argument("--per-reminder", type=int, default=24)
        parser.add_argument("--as-of", type=date.fromisoformat)

    def handle(self, *args, **options):
        try:
            result = schedule_reminders(as_of=options["as_of"], limit=options["limit"], per_reminder=options["per_reminder"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, sort_keys=True))
