from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from staff_announcements.models import Announcement
from staff_reminders.models import Reminder
from .models import Contact
from .test_support import staff_user, web_login


class StaffOperationsIntegrationTests(TestCase):
    def setUp(self):
        self.manager = staff_user("integration-manager", manager=True)

    @override_settings(ALLOW_MOCK_DATA_SEEDING=True)
    def test_seed_command_and_all_authenticated_routes(self):
        call_command("seed_staff_operations", owner=self.manager.username, stdout=StringIO())
        self.assertEqual(Contact.objects.count(), 1)
        self.assertEqual(Announcement.objects.count(), 1)
        self.assertEqual(Reminder.objects.count(), 1)
        api = APIClient()
        api.force_authenticate(self.manager)
        web_login(self.client, self.manager)
        for feature in ("directory", "announcements", "reminders"):
            response = api.get(f"/api/staff/{feature}/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["count"], 1)
            self.assertIn("server_now", response.data)
            page = self.client.get(f"/staff/{feature}/")
            self.assertEqual(page.status_code, 200)
            self.assertContains(page, "/staff/reminders/")
            self.assertContains(page, "/staff/directory/")
            self.assertContains(page, "/staff/announcements/")

    def test_runtime_allowlists_include_every_operational_app(self):
        from scripts.build_context_receipt import is_allowlisted
        from scripts.scan_container_image import RUNTIME_ROOT_ALLOWLIST
        dockerfile = (Path(settings.BASE_DIR) / "Dockerfile").read_text()
        ignore = (Path(settings.BASE_DIR) / ".dockerignore").read_text()
        for app in ("staff_directory", "staff_announcements", "staff_reminders"):
            self.assertIn(app, RUNTIME_ROOT_ALLOWLIST)
            self.assertTrue(is_allowlisted(f"{app}/models.py"))
            self.assertFalse(is_allowlisted(f"{app}/output/secret.json"))
            self.assertIn(f"COPY {app} /app/{app}", dockerfile)
            self.assertIn(f"!{app}/**", ignore)
