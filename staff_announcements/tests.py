from datetime import timedelta
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from staff_directory.test_support import staff_user, web_login
from .models import Announcement
from .services import announcements_for, banner_for, save_announcement


class AnnouncementTests(TestCase):
    def setUp(self):
        self.manager = staff_user("manager", manager=True)
        self.reader = staff_user("reader")
        self.now = timezone.now()
        self.data = {"text": "Synthetic staff briefing", "priority": "normal", "audience": "all_staff",
                     "starts_at": self.now - timedelta(hours=1), "ends_at": self.now + timedelta(hours=1)}
        self.item = save_announcement(self.manager, self.data)
        self.api = APIClient()
        self.api.force_authenticate(self.reader)

    def test_start_inclusive_end_exclusive(self):
        self.assertTrue(announcements_for(self.reader, now=self.item.starts_at).exists())
        self.assertFalse(announcements_for(self.reader, now=self.item.ends_at).exists())
        self.assertFalse(announcements_for(self.reader, now=self.item.starts_at - timedelta(microseconds=1)).exists())

    def test_expired_and_future_hidden_in_list_detail_banner(self):
        for starts_at, ends_at in [(self.now - timedelta(days=2), self.now - timedelta(days=1)),
                                  (self.now + timedelta(days=1), self.now + timedelta(days=2))]:
            item = save_announcement(self.manager, {**self.data, "starts_at": starts_at, "ends_at": ends_at})
            self.assertEqual(self.api.get(f"/api/staff/announcements/{item.pk}/").status_code, 404)
        self.assertEqual(self.api.get("/api/staff/announcements/").data["count"], 1)
        self.assertEqual(banner_for(self.reader).pk, self.item.pk)

    def test_selected_roles_no_manager_or_superuser_implicit_audience_bypass(self):
        from patients.models import RoleSetting
        role = RoleSetting.objects.get(role_name="Operations reader")
        scoped = save_announcement(self.manager, {**self.data, "text": "Reader only", "audience": "selected_roles",
                                                   "audience_roles": [role]})
        self.assertEqual(self.api.get(f"/api/staff/announcements/{scoped.pk}/").status_code, 200)
        self.api.force_authenticate(self.manager)
        self.assertEqual(self.api.get(f"/api/staff/announcements/{scoped.pk}/").status_code, 404)
        self.assertEqual(self.api.get(f"/api/staff/announcements/{scoped.pk}/?manage=true").status_code, 200)

    def test_management_permissions_and_stale_edits(self):
        path = f"/api/staff/announcements/{self.item.pk}/"
        self.assertEqual(self.api.get("/api/staff/announcements/?manage=true").status_code, 403)
        self.assertEqual(self.api.patch(path, {"version": 1, "text": "Denied"}, format="json").status_code, 403)
        self.api.force_authenticate(self.manager)
        self.assertEqual(self.api.patch(path, {"version": 1, "text": "Updated"}, format="json").status_code, 200)
        self.assertEqual(self.api.patch(path, {"version": 1, "text": "Stale"}, format="json").status_code, 409)
        self.item.refresh_from_db()
        self.assertEqual(self.item.text, "Updated")
        self.assertEqual(self.item.publisher_id, self.manager.pk)

    def test_invalid_schedule_audience_and_blank_text_rejected(self):
        self.api.force_authenticate(self.manager)
        for fields in ({"ends_at": self.data["starts_at"]}, {"audience": "selected_roles"},
                       {"text": "  "}, {"priority": "critical"}):
            payload = {**self.data, **fields}
            payload["starts_at"] = payload["starts_at"].isoformat()
            payload["ends_at"] = payload["ends_at"].isoformat()
            self.assertEqual(self.api.post("/api/staff/announcements/", payload, format="json").status_code, 400)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Announcement.objects.filter(pk=self.item.pk).update(ends_at=self.item.starts_at)

    def test_disabled_hidden_and_priority_banner(self):
        urgent = save_announcement(self.manager, {**self.data, "priority": "urgent"})
        self.assertEqual(banner_for(self.reader).pk, urgent.pk)
        save_announcement(self.manager, {"version": 1, "is_active": False}, pk=urgent.pk)
        self.assertEqual(banner_for(self.reader).pk, self.item.pk)

    def test_priority_precedes_pagination_and_management_retains_recency(self):
        urgent = save_announcement(self.manager, {**self.data, "priority": "urgent"})
        Announcement.objects.bulk_create([
            Announcement(publisher=self.manager, **{**self.data, "text": f"Newer normal {index}",
                         "starts_at": self.now - timedelta(minutes=30)})
            for index in range(51)
        ])
        response = self.api.get("/api/staff/announcements/")
        self.assertEqual(response.data["count"], 53)
        self.assertEqual(len(response.data["results"]), 50)
        self.assertEqual(response.data["results"][0]["id"], urgent.pk)
        self.assertEqual(banner_for(self.reader).pk, urgent.pk)
        self.api.force_authenticate(self.manager)
        managed = self.api.get("/api/staff/announcements/?manage=true")
        self.assertNotIn(urgent.pk, [row["id"] for row in managed.data["results"]])

    def test_deleted_publisher_web_detail_has_fallback(self):
        self.manager.delete()
        self.item.refresh_from_db()
        self.assertIsNone(self.item.publisher_id)
        web_login(self.client, self.reader)
        response = self.client.get(f"/staff/announcements/{self.item.pk}/")
        self.assertContains(response, "Published by Former staff member")

    def test_deleted_publisher_can_be_updated_without_inventing_publisher(self):
        self.manager.delete()
        replacement = staff_user("replacement", manager=True)
        self.api.force_authenticate(replacement)
        response = self.api.patch(f"/api/staff/announcements/{self.item.pk}/",
                                  {"version": 1, "text": "Updated preserved announcement"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.version, 2)
        self.assertEqual(self.item.text, "Updated preserved announcement")
        self.assertIsNone(self.item.publisher_id)
        web_login(self.client, replacement)
        response = self.client.post(f"/staff/announcements/{self.item.pk}/edit/", {
            **self.data, "version": 2, "text": "Web edit of preserved announcement", "is_active": True,
            "starts_at": self.item.starts_at.isoformat(), "ends_at": self.item.ends_at.isoformat(),
        })
        self.assertRedirects(response, f"/staff/announcements/{self.item.pk}/?manage=true")
        self.item.refresh_from_db()
        self.assertEqual(self.item.version, 3)
        self.assertEqual(self.item.text, "Web edit of preserved announcement")
        self.assertIsNone(self.item.publisher_id)

    def test_time_and_publisher_payload_and_no_store(self):
        response = self.api.get(f"/api/staff/announcements/{self.item.pk}/")
        self.assertEqual(response.data["publisher"]["id"], self.manager.pk)
        self.assertIn("server_now", response.data)
        self.assertIn("no-store", response["Cache-Control"])

    def test_plain_text_render_and_static_banner(self):
        save_announcement(self.manager, {"version": 1, "text": "<script>alert(1)</script>"}, pk=self.item.pk)
        web_login(self.client, self.reader)
        response = self.client.get(f"/staff/announcements/{self.item.pk}/")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "data-announcement-expires=")
        self.assertNotContains(response, "<marquee")
        self.assertEqual(self.client.get("/staff/announcements/new/").status_code, 403)

    def test_audit_failure_rolls_back_new_record(self):
        with patch("staff_directory.access.record_audit_event", side_effect=RuntimeError("synthetic")):
            with self.assertRaises(RuntimeError):
                save_announcement(self.manager, self.data)
        self.assertEqual(Announcement.objects.count(), 1)
