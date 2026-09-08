"""Historical migration proofs in disposable PostgreSQL schemas, never a downgrade fixture."""

from contextlib import contextmanager
from unittest import skipUnless
from uuid import uuid4

from django.db import DatabaseError, connection, transaction
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


@skipUnless(connection.vendor == "postgresql", "PostgreSQL historical migration proof")
class PatientIdentityMigrationTests(TransactionTestCase):
    before = ("patients", "0042_patient_identity_add")
    after = ("patients", "0044_patient_identity_enforce")

    @contextmanager
    def historical_schema(self):
        # Isolate the migration recorder and tables from the current test schema.
        # This deliberately does not remove guards to manufacture an old state.
        schema = "test_identity_migration_" + uuid4().hex
        quoted = connection.ops.quote_name(schema)
        with connection.cursor() as cursor:
            cursor.execute("SHOW search_path")
            original_path = cursor.fetchone()[0]
            cursor.execute(f"CREATE SCHEMA {quoted}")
            cursor.execute("SELECT set_config('search_path', %s, false)", [schema])
        try:
            executor = MigrationExecutor(connection)
            executor.migrate([self.before])
            yield executor.loader.project_state([self.before]).apps
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('search_path', %s, false)", [original_path])
                cursor.execute(f"DROP SCHEMA {quoted} CASCADE")

    def seed_orphans(self, apps, names):
        Case = apps.get_model("patients", "Case")
        Department = apps.get_model("patients", "DepartmentConfig")
        department = Department.objects.create(name="Synthetic identity migration")
        return [Case.objects.create(
            uhid="SYNTH-SHARED", first_name=name, patient_name=name,
            category=department, metadata={"entry_mode": "quick_entry"},
        ) for name in names]

    def assert_conflict_is_atomic(self, *, existing_patient):
        with self.historical_schema() as apps:
            Patient = apps.get_model("patients", "Patient")
            Case = apps.get_model("patients", "Case")
            Allocator = apps.get_model("patients", "PatientIdentityAllocator")
            Issuance = apps.get_model("patients", "PatientIdentityIssuance")
            if existing_patient:
                Patient.objects.create(uhid="SYNTH-SHARED", first_name="", patient_name="")
            self.seed_orphans(apps, ("", "Synthetic Alice", "Synthetic Bob"))
            patients_before = list(Patient.objects.order_by("pk").values())
            cases_before = list(Case.objects.order_by("pk").values())
            floor_before = list(Allocator.objects.values())
            with self.assertRaisesMessage(RuntimeError, "Conflicting patientless legacy identity"):
                MigrationExecutor(connection).migrate([self.after])
            self.assertEqual(list(Patient.objects.order_by("pk").values()), patients_before)
            self.assertEqual(list(Case.objects.order_by("pk").values()), cases_before)
            self.assertEqual(list(Allocator.objects.values()), floor_before)
            self.assertEqual(Issuance.objects.count(), 0)
            self.assertNotIn(
                ("patients", "0043_patient_identity_backfill"),
                MigrationExecutor(connection).loader.applied_migrations,
            )

    def test_blank_first_orphan_does_not_hide_later_conflicting_identity(self):
        self.assert_conflict_is_atomic(existing_patient=False)

    def test_blank_existing_patient_does_not_hide_conflicting_orphan_group(self):
        self.assert_conflict_is_atomic(existing_patient=True)

    def test_blank_and_consistent_group_links_without_rewriting_history(self):
        with self.historical_schema() as apps:
            self.seed_orphans(apps, ("", "Synthetic Alice", "Synthetic Alice"))
            Case = apps.get_model("patients", "Case")
            old_rows = list(Case.objects.order_by("pk").values())
            executor = MigrationExecutor(connection)
            executor.migrate([self.after])
            final_apps = executor.loader.project_state([self.after]).apps
            Patient = final_apps.get_model("patients", "Patient")
            Issuance = final_apps.get_model("patients", "PatientIdentityIssuance")
            patient = Patient.objects.get()
            self.assertEqual(patient.uhid, "SYNTH-SHARED")
            self.assertEqual(patient.first_name, "")
            self.assertEqual(patient.created_at, old_rows[0]["created_at"])
            self.assertEqual(patient.updated_at, old_rows[0]["updated_at"])
            self.assertEqual(Issuance.objects.get().mtno, patient.mtno)
            new_rows = list(Case.objects.order_by("pk").values())
            for old, new in zip(old_rows, new_rows, strict=True):
                self.assertIsNone(old.pop("patient_id"))
                self.assertEqual(new.pop("patient_id"), patient.pk)
                self.assertEqual(new, old)

    def test_refused_downgrade_retains_enforcement_and_applied_migration(self):
        with self.historical_schema() as apps:
            self.seed_orphans(apps, ("Synthetic Alice",))
            executor = MigrationExecutor(connection)
            executor.migrate([self.after])
            final_apps = executor.loader.project_state([self.after]).apps
            Patient = final_apps.get_model("patients", "Patient")
            Issuance = final_apps.get_model("patients", "PatientIdentityIssuance")
            Allocator = final_apps.get_model("patients", "PatientIdentityAllocator")
            patient = Patient.objects.get()
            original = (patient.mtno, patient.identity_uuid)
            ledger_before = list(Issuance.objects.order_by("mtno").values())
            floor_before = list(Allocator.objects.values())
            with self.assertRaises(IrreversibleError):
                MigrationExecutor(connection).migrate([self.before])
            self.assertIn(self.after, MigrationExecutor(connection).loader.applied_migrations)
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT tgname FROM pg_trigger
                    JOIN pg_class ON pg_class.oid = tgrelid
                    JOIN pg_namespace ON pg_namespace.oid = relnamespace
                    WHERE nspname = current_schema() AND NOT tgisinternal
                    AND tgname IN ('patient_identity_guard', 'patient_issuance_guard', 'patient_allocator_guard')
                """)
                self.assertEqual({row[0] for row in cursor.fetchall()}, {
                    "patient_identity_guard", "patient_issuance_guard", "patient_allocator_guard",
                })
                cursor.execute("""
                    SELECT 1 FROM pg_constraint JOIN pg_namespace ON pg_namespace.oid = connamespace
                    WHERE nspname = current_schema() AND conname = 'patient_mtno_present'
                """)
                self.assertIsNotNone(cursor.fetchone())
            for operation in (
                lambda: Patient.objects.filter(pk=patient.pk).update(mtno="MT-999999"),
                lambda: Issuance.objects.filter(mtno=patient.mtno).delete(),
                lambda: Allocator.objects.filter(pk=1).update(high_water=0),
            ):
                with self.assertRaises(DatabaseError), transaction.atomic():
                    operation()
            patient.refresh_from_db()
            self.assertEqual((patient.mtno, patient.identity_uuid), original)
            self.assertEqual(list(Issuance.objects.order_by("mtno").values()), ledger_before)
            self.assertEqual(list(Allocator.objects.values()), floor_before)
