from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from patients.auth_security import current_auth_version
from patients.models import AuditEvent
from .access import StaleVersion
from .models import Contact, Favourite
from .services import save_contact, set_favourite
from .test_support import staff_user, web_login

PAYLOAD = {"name": "Synthetic switchboard", "role_specialty": "Reception", "organization": "Demo clinic",
           "phones": [{"label": "Office", "number": "+1 (202) 555-0100", "extension": "12"}],
           "notes": "Synthetic operations only"}


class DirectoryTests(TestCase):
    def setUp(self):
        self.manager = staff_user("manager", manager=True)
        self.reader = staff_user("reader")
        self.other = staff_user("other")
        self.contact = save_contact(self.manager, PAYLOAD)
        self.api = APIClient()
        self.api.force_authenticate(self.reader)

    def test_no_implicit_staff_flag_or_anonymous_access(self):
        outsider = get_user_model().objects.create_user(username="outsider", is_staff=True)
        self.api.force_authenticate(outsider)
        self.assertEqual(self.api.get("/api/staff/directory/").status_code, 403)
        self.api.force_authenticate(None)
        self.assertEqual(self.api.get("/api/staff/directory/").status_code, 401)

    def test_reader_with_no_case_scope_reads_but_cannot_manage(self):
        response = self.api.get("/api/staff/directory/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["name"], PAYLOAD["name"])
        self.assertIn("server_now", response.data)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.api.post("/api/staff/directory/", PAYLOAD, format="json").status_code, 403)
        self.assertEqual(self.api.patch(f"/api/staff/directory/{self.contact.pk}/",
                                       {"version": 1, "name": "Forbidden"}, format="json").status_code, 403)

    def test_favourite_set_is_idempotent_and_user_isolated(self):
        path = f"/api/staff/directory/{self.contact.pk}/favourite/"
        for _ in range(2):
            response = self.api.put(path, {"is_favourite": True}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data["is_favourite"])
        self.assertEqual(Favourite.objects.count(), 1)
        self.assertEqual(self.api.get("/api/staff/directory/?favourites=true").data["count"], 1)
        self.api.force_authenticate(self.other)
        self.assertEqual(self.api.get("/api/staff/directory/?favourites=true").data["count"], 0)
        self.api.put(path, {"is_favourite": False}, format="json")
        self.assertEqual(Favourite.objects.count(), 1)
        self.api.force_authenticate(self.reader)
        self.api.put(path, {"is_favourite": False}, format="json")
        self.assertFalse(Favourite.objects.exists())

    def test_archive_disappears_for_readers_and_rejects_favourite(self):
        self.api.force_authenticate(self.manager)
        response = self.api.patch(f"/api/staff/directory/{self.contact.pk}/",
                                  {"version": 1, "is_active": False}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["version"], 2)
        self.assertEqual(self.api.get("/api/staff/directory/?include_inactive=true").data["count"], 1)
        self.api.force_authenticate(self.reader)
        self.assertEqual(self.api.get("/api/staff/directory/").data["count"], 0)
        self.assertEqual(self.api.get(f"/api/staff/directory/{self.contact.pk}/").status_code, 404)
        self.assertEqual(self.api.get("/api/staff/directory/?include_inactive=true").status_code, 403)
        self.assertEqual(self.api.put(f"/api/staff/directory/{self.contact.pk}/favourite/",
                                      {"is_favourite": True}, format="json").status_code, 404)

    def test_stale_edit_no_lost_update_and_audit(self):
        self.api.force_authenticate(self.manager)
        path = f"/api/staff/directory/{self.contact.pk}/"
        self.assertEqual(self.api.patch(path, {"version": 1, "name": "Updated"}, format="json").status_code, 200)
        self.assertEqual(self.api.patch(path, {"version": 1, "name": "Stale"}, format="json").status_code, 409)
        self.contact.refresh_from_db()
        self.assertEqual(self.contact.name, "Updated")
        event = AuditEvent.objects.filter(action="staff_directory.updated").get()
        self.assertEqual(event.metadata["version"], 2)
        self.assertIsNone(event.case_id)
        self.assertIsNone(event.patient_id)

    def test_invalid_phone_and_bounds(self):
        self.api.force_authenticate(self.manager)
        for phones in ([], [{"number": "javascript:alert(1)"}], [{"number": "-----"}],
                       [{"number": "2025550100", "extension": "abc"}],
                       [{"number": "2025550100"}] * 11):
            self.assertEqual(self.api.post("/api/staff/directory/", {**PAYLOAD, "phones": phones},
                                            format="json").status_code, 400)
        self.assertEqual(Contact.objects.count(), 1)

    def test_search_and_bounded_pages(self):
        self.assertEqual(self.api.get("/api/staff/directory/?q=555").data["count"], 1)
        Contact.objects.bulk_create([Contact(**{**PAYLOAD, "name": f"Contact {i:03}"}) for i in range(55)])
        page = self.api.get("/api/staff/directory/")
        self.assertEqual(len(page.data["results"]), 50)
        self.assertIsNotNone(page.data["next"])

    def test_audit_failure_rolls_back_update(self):
        with patch("staff_directory.access.record_audit_event", side_effect=RuntimeError("synthetic audit failure")):
            with self.assertRaises(RuntimeError):
                save_contact(self.manager, {"version": 1, "name": "Rollback"}, pk=self.contact.pk)
        self.contact.refresh_from_db()
        self.assertEqual(self.contact.name, PAYLOAD["name"])

    def test_revoked_jwt_and_removed_role(self):
        token = RefreshToken.for_user(self.reader)
        token["auth_version"] = current_auth_version(self.reader)
        self.api.force_authenticate(None)
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        self.assertEqual(self.api.get("/api/staff/directory/").status_code, 200)
        self.reader.groups.clear()
        self.assertEqual(self.api.get("/api/staff/directory/").status_code, 401)

    def test_revocation_between_authentication_and_write_lock_denies_update(self):
        from patients.auth_security import bump_auth_version
        from patients.task_editing import lock_edit_actor
        token = RefreshToken.for_user(self.manager)
        token["auth_version"] = current_auth_version(self.manager)
        self.api.force_authenticate(None)
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

        def revoke_then_lock(user):
            bump_auth_version(user, reason="synthetic race")
            return lock_edit_actor(user)

        with patch("staff_directory.access.lock_edit_actor", side_effect=revoke_then_lock):
            response = self.api.patch(f"/api/staff/directory/{self.contact.pk}/",
                                      {"version": 1, "name": "Denied"}, format="json")
        self.assertEqual(response.status_code, 401)
        self.contact.refresh_from_db()
        self.assertEqual(self.contact.name, PAYLOAD["name"])

    def test_seed_guard_idempotence_and_patient_bundle_exclusion(self):
        import json
        from django.core.management.base import CommandError
        from django.test import override_settings
        from patients.database_bundle import build_patient_data_payload
        from .seed import seed_demo_operations
        with override_settings(ALLOW_MOCK_DATA_SEEDING=False):
            with self.assertRaises(CommandError):
                seed_demo_operations(self.manager)
        with override_settings(ALLOW_MOCK_DATA_SEEDING=True):
            seed_demo_operations(self.manager)
            seed_demo_operations(self.manager)
        self.assertEqual(Contact.objects.filter(name="Demo staff switchboard").count(), 1)
        self.assertNotIn("Demo staff switchboard", json.dumps(build_patient_data_payload()))

    def test_web_safe_render_favourite_csrf_and_edit(self):
        web_login(self.client, self.reader)
        response = self.client.get(f"/staff/directory/{self.contact.pk}/")
        self.assertContains(response, "tel:+12025550100;ext=12")
        self.assertEqual(self.client.get(f"/staff/directory/{self.contact.pk}/edit/").status_code, 403)
        web_login(self.client, self.manager)
        response = self.client.get(f"/staff/directory/{self.contact.pk}/edit/")
        self.assertContains(response, 'name="version"')
        self.assertContains(response, 'name="phones-TOTAL_FORMS"')
        from django.test import Client
        csrf = Client(enforce_csrf_checks=True)
        web_login(csrf, self.reader)
        self.assertEqual(csrf.post(f"/staff/directory/{self.contact.pk}/favourite/",
                                   {"is_favourite": "true"}).status_code, 403)


class DirectoryConcurrencyTests(TransactionTestCase):
    def test_two_writers_only_one_expected_version_wins(self):
        manager1 = staff_user("manager1", manager=True)
        manager2 = staff_user("manager2", manager=True)
        contact = save_contact(manager1, PAYLOAD)
        barrier = Barrier(2)

        def update(user_id):
            close_old_connections()
            try:
                user = get_user_model().objects.get(pk=user_id)
                barrier.wait(timeout=10)
                try:
                    save_contact(user, {"version": 1, "name": f"Writer {user_id}"}, pk=contact.pk)
                    return "saved"
                except StaleVersion:
                    return "stale"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(update, [manager1.pk, manager2.pk]))
        self.assertCountEqual(results, ["saved", "stale"])
        contact.refresh_from_db()
        self.assertEqual(contact.version, 2)
