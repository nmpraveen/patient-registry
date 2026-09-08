from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from staff_directory.seed import seed_demo_operations


class Command(BaseCommand):
    help = "Seed synthetic staff operations in an explicitly enabled demo environment."

    def add_arguments(self, parser):
        parser.add_argument("--owner", required=True, help="Existing settings manager username.")

    def handle(self, *args, **options):
        if not settings.ALLOW_MOCK_DATA_SEEDING:
            raise CommandError("Mock-data seeding is disabled.")
        try:
            owner = get_user_model().objects.get(username=options["owner"])
        except get_user_model().DoesNotExist as exc:
            raise CommandError("Owner does not exist.") from exc
        seed_demo_operations(owner)
        if apps.is_installed("staff_reminders"):
            from staff_reminders.seed import seed_demo_reminders
            seed_demo_reminders(owner)
        self.stdout.write(self.style.SUCCESS("Synthetic staff operations seeded."))
