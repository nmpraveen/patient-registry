"""Reception maintenance is independent of settings administration."""
from unittest.mock import patch
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from rest_framework.test import APIClient

from patients.auth_security import current_auth_version
from patients.forms import RoleSettingForm
from patients.models import AuditEvent, CaseDataScope, RoleSetting, ensure_default_role_settings
from patients.policy import effective_role_policy, has_capability
from .models import Contact
from .services import save_contact
from .test_support import staff_user, web_login
from .tests import PAYLOAD


class PhoneBookPermissionTests(TestCase):
    def setUp(self):
        ensure_default_role_settings()
        self.role = RoleSetting.objects.get(role_name="Reception")
        self.reception = get_user_model().objects.create_user("synthetic-reception", password="synthetic-only-password")
        group, _ = Group.objects.get_or_create(name=self.role.role_name)
        self.reception.groups.add(group)
        self.api = APIClient()
        self.api.force_authenticate(self.reception)

    def test_default_reception_manages_contacts_without_settings_or_scope_expansion(self):
        profile = self.api.get("/api/me/").data
        self.assertTrue(profile["capabilities"]["manage_phonebook"])
        self.assertFalse(profile["capabilities"]["manage_settings"])
        self.assertEqual(profile["data_scope"]["case_data_scope"], CaseDataScope.ASSIGNED)
        created = self.api.post("/api/staff/directory/", PAYLOAD, format="json")
        self.assertEqual(created.status_code, 201)
        path = f'/api/staff/directory/{created.data["id"]}/'
        self.assertEqual(self.api.patch(path, {"version": 1, "name": "Synthetic edited"}, format="json").status_code, 200)
        self.assertEqual(self.api.patch(path, {"version": 1, "name": "Stale"}, format="json").status_code, 409)
        self.assertEqual(self.api.patch(path, {"version": 2, "is_active": False}, format="json").status_code, 200)
        self.assertEqual(self.api.get(path).status_code, 404)
        self.assertEqual(self.api.get(path + "?include_inactive=true").status_code, 200)
        self.assertEqual(self.api.patch(path + "?include_inactive=true", {"version": 3, "is_active": True}, format="json").status_code, 200)
        self.assertEqual(Contact.objects.get().version, 4)
        event = AuditEvent.objects.get(action="staff_directory.created")
        self.assertEqual(event.actor_user_id, self.reception.pk)
        self.assertIsNone(event.patient_id)
        self.assertIsNone(event.case_id)

    def test_web_add_edit_and_admin_restrictions(self):
        web_login(self.client, self.reception)
        self.assertContains(self.client.get("/staff/directory/"), "Add contact")
        self.assertContains(self.client.get("/staff/directory/new/"), 'name="phones-TOTAL_FORMS"')
        response = self.client.post("/staff/directory/new/", {
            "name": "Synthetic web contact", "version": 1, "is_active": "on",
            "phones-TOTAL_FORMS": 1, "phones-INITIAL_FORMS": 0,
            "phones-MIN_NUM_FORMS": 1, "phones-MAX_NUM_FORMS": 10,
            "phones-0-number": "2025550100", "phones-0-label": "Desk",
        })
        contact = Contact.objects.get()
        self.assertRedirects(response, f"/staff/directory/{contact.pk}/")
        self.assertContains(self.client.get(f"/staff/directory/{contact.pk}/"), "Edit contact")
        for path in ("/patients/settings/", "/patients/settings/users/", "/patients/settings/database/",
                     "/patients/settings/device-access/", "/patients/settings/theme/",
                     "/staff/announcements/new/", "/staff/announcements/?manage=true"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(self.api.post("/api/staff/announcements/", {
            "text": "Forbidden", "starts_at": "2026-09-16T00:00:00Z",
            "ends_at": "2026-09-17T00:00:00Z", "audience": "all_staff",
        }, format="json").status_code, 403)
        manager = staff_user("synthetic-settings-manager", manager=True)
        from staff_reminders.services import create_reminder
        reminder = create_reminder(manager, {"title": "Synthetic private reminder", "assignee_id": manager.pk,
            "due_date": date(2026, 9, 17), "recurrence": "ONCE", "advance_notice_days": 0})
        self.assertEqual(self.api.get(f"/api/staff/reminders/{reminder.pk}/").status_code, 404)

    def test_permission_off_hides_controls_and_denies_direct_writes(self):
        contact = save_contact(self.reception, PAYLOAD)
        self.role.can_manage_phonebook = False
        self.role.save()
        ensure_default_role_settings()  # Page rendering must not re-grant a revoked default.
        self.role.refresh_from_db()
        self.assertFalse(self.role.can_manage_phonebook)
        self.assertFalse(self.api.get("/api/me/").data["capabilities"]["manage_phonebook"])
        web_login(self.client, self.reception)
        self.assertNotContains(self.client.get("/staff/directory/"), "Add contact")
        self.assertNotContains(self.client.get(f"/staff/directory/{contact.pk}/"), "Edit contact")
        for path in ("/staff/directory/new/", f"/staff/directory/{contact.pk}/edit/"):
            self.assertEqual(self.client.get(path).status_code, 403)
            self.assertEqual(self.client.post(path, {"name": "Forbidden"}).status_code, 403)
        self.assertEqual(self.api.post("/api/staff/directory/", PAYLOAD, format="json").status_code, 403)
        self.assertEqual(self.api.patch(f"/api/staff/directory/{contact.pk}/", {"version": 1, "name": "Forbidden"}, format="json").status_code, 403)
        self.assertEqual(self.api.get("/api/staff/directory/?include_inactive=true").status_code, 403)
        self.assertEqual(self.api.put(f"/api/staff/directory/{contact.pk}/favourite/", {"is_favourite": True}, format="json").status_code, 200)

    def test_settings_permission_does_not_implicitly_grant_phonebook(self):
        self.role.can_manage_settings = True
        self.role.can_manage_phonebook = False
        self.role.save()
        self.assertEqual(self.api.post("/api/staff/directory/", PAYLOAD, format="json").status_code, 403)
        self.assertEqual(self.api.get("/api/staff/directory/?include_inactive=true").status_code, 403)

    def test_role_editor_can_toggle_phonebook_without_granting_settings(self):
        manager = staff_user("synthetic-role-manager", manager=True)
        web_login(self.client, manager)
        url = "/patients/settings/users/"
        self.assertContains(self.client.get(url + f"?tab=roles&role={self.role.pk}"), "Manage PhoneBook contacts")
        version = current_auth_version(self.reception)
        for allowed in (False, True):
            payload = {"action": "update_role", "tab": "roles", "role_id": self.role.pk}
            for field in RoleSettingForm().fields:
                value = getattr(self.role, field)
                if field == "can_manage_phonebook":
                    value = allowed
                if isinstance(value, bool):
                    if value:
                        payload["role-edit-" + field] = "on"
                else:
                    payload["role-edit-" + field] = value
            self.assertEqual(self.client.post(url, payload).status_code, 302)
            self.role.refresh_from_db()
            self.assertEqual(self.role.can_manage_phonebook, allowed)
            self.assertFalse(self.role.can_manage_settings)
        self.assertGreater(current_auth_version(self.reception), version)
        self.assertTrue(AuditEvent.objects.filter(action="role.updated", metadata__changed_fields__contains=["can_manage_phonebook"]).exists())
        web_login(self.client, self.reception)
        self.assertEqual(self.client.post(url, payload).status_code, 403)

    def test_fresh_locked_check_denies_revocation_even_with_cached_policy(self):
        self.assertTrue(has_capability(self.reception, "manage_phonebook"))
        from patients.task_editing import lock_edit_actor

        def revoke_then_lock(user):
            RoleSetting.objects.filter(pk=self.role.pk).update(can_manage_phonebook=False)
            return lock_edit_actor(user)

        with patch("staff_directory.access.lock_edit_actor", side_effect=revoke_then_lock):
            self.assertEqual(self.api.post("/api/staff/directory/", PAYLOAD, format="json").status_code, 403)
        self.assertFalse(Contact.objects.exists())

    def test_phonebook_only_role_union_does_not_expand_clinical_or_settings_scope(self):
        role = RoleSetting.objects.create(role_name="Synthetic PhoneBook", can_manage_phonebook=True)
        reader = staff_user("synthetic-phonebook-only")
        reader.groups.add(Group.objects.create(name=role.role_name))
        policy = effective_role_policy(reader, fresh=True)
        self.assertEqual(policy.case_data_scope, CaseDataScope.NONE)
        self.assertEqual(policy.capabilities, frozenset({"manage_phonebook"}))
        self.assertEqual(role.field_capabilities()["can_manage_phonebook"], True)
        self.assertEqual(role.capabilities()["manage_phonebook"], True)
        self.assertIsNotNone(save_contact(reader, PAYLOAD).pk)
        reader.is_active = False
        reader.save()
        with self.assertRaises(PermissionDenied):
            save_contact(reader, PAYLOAD)

    def test_superuser_without_roles_can_manage_but_inactive_cannot(self):
        user = get_user_model().objects.create_superuser("synthetic-phonebook-super", password="synthetic-only-password")
        self.assertIsNotNone(save_contact(user, PAYLOAD).pk)
        user.is_active = False
        user.save()
        with self.assertRaises(PermissionDenied):
            save_contact(user, PAYLOAD)
