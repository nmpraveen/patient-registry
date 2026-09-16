"""Upgrade proof without downgrading the current identity-protected schema."""
from contextlib import contextmanager
from unittest import skipUnless
from uuid import uuid4

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


@skipUnless(connection.vendor == "postgresql", "PostgreSQL historical migration proof")
class PhoneBookMigrationTests(TransactionTestCase):
    before = ("patients", "0044_patient_identity_enforce")
    after = ("patients", "0045_rolesetting_can_manage_phonebook")

    @contextmanager
    def historical_schema(self):
        schema = "test_phonebook_migration_" + uuid4().hex
        quoted = connection.ops.quote_name(schema)
        with connection.cursor() as cursor:
            cursor.execute("SHOW search_path")
            original = cursor.fetchone()[0]
            cursor.execute(f"CREATE SCHEMA {quoted}")
            cursor.execute("SELECT set_config('search_path', %s, false)", [schema])
        try:
            executor = MigrationExecutor(connection)
            executor.migrate([self.before])
            yield executor.loader.project_state([self.before]).apps
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('search_path', %s, false)", [original])
                cursor.execute(f"DROP SCHEMA {quoted} CASCADE")

    def test_upgrade_preserves_custom_flags_and_managers_and_grants_reception_only(self):
        with self.historical_schema() as apps:
            Role = apps.get_model("patients", "RoleSetting")
            Role.objects.all().delete()
            for name, manager in (("Reception", False), ("Custom manager", True), ("Nurse", False),
                                  ("reception", False), ("Custom reader", False)):
                Role.objects.create(role_name=name, can_manage_settings=manager,
                                    can_task_edit=True, case_data_scope="NONE")
            old_rows = list(Role.objects.order_by("pk").values())
            executor = MigrationExecutor(connection)
            executor.migrate([self.after])
            NewRole = executor.loader.project_state([self.after]).apps.get_model("patients", "RoleSetting")
            for old, new in zip(old_rows, NewRole.objects.order_by("pk").values(), strict=True):
                self.assertEqual(new.pop("can_manage_phonebook"), old["can_manage_settings"] or old["role_name"] == "Reception")
                self.assertEqual(old, new)
