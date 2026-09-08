from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import uuid
from unittest import skipUnless
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import DatabaseError, close_old_connections, connection, connections, transaction
from django.test import TestCase, TransactionTestCase

from .identity import identity_checkpoint, parse_mtno, reconcile_identity_allocator, register_identity_binding
from .models import Patient, PatientIdentityAllocator, PatientIdentityIssuance


class PatientIdentityTests(TestCase):
    def test_blank_uhids_remain_distinct_and_deleted_number_is_not_reissued(self):
        first = Patient.objects.create(first_name="Synthetic")
        second = Patient.objects.create(first_name="Synthetic")
        self.assertEqual(first.uhid, "")
        self.assertNotEqual(first.mtno, second.mtno)
        number = parse_mtno(second.mtno)
        second.delete()
        third = Patient.objects.create(first_name="Synthetic")
        self.assertGreater(parse_mtno(third.mtno), number)
        self.assertTrue(PatientIdentityIssuance.objects.filter(mtno=second.mtno).exists())

    def test_validation_does_not_allocate_and_uhid_assignment_preserves_identity(self):
        patient = Patient(first_name="Synthetic", last_name="Example")
        before = identity_checkpoint()
        patient.full_clean(exclude=["created_by", "merged_into"])
        self.assertEqual(identity_checkpoint(), before)
        patient.save()
        identity = patient.mtno, patient.identity_uuid
        patient.uhid = " hospital-001 "
        patient.save()
        patient.refresh_from_db()
        self.assertEqual((patient.mtno, patient.identity_uuid), identity)
        self.assertEqual(patient.uhid, "HOSPITAL-001")

    def test_model_guard_and_database_guards_reject_identity_mutation(self):
        patient = Patient.objects.create(first_name="Synthetic")
        original = patient.mtno
        patient.mtno = "MT-900000"
        with self.assertRaises(ValidationError):
            patient.save()
        if connection.vendor == "postgresql":
            for action in (
                lambda: Patient.objects.filter(pk=patient.pk).update(mtno="MT-900000"),
                lambda: PatientIdentityIssuance.objects.filter(mtno=original).update(identity_uuid=uuid.uuid4()),
                lambda: PatientIdentityIssuance.objects.filter(mtno=original).delete(),
                lambda: PatientIdentityAllocator.objects.filter(pk=1).update(high_water=0),
                lambda: PatientIdentityAllocator.objects.filter(pk=1).delete(),
            ):
                with self.assertRaises(DatabaseError), transaction.atomic():
                    action()
        patient.refresh_from_db()
        self.assertEqual(patient.mtno, original)

    def test_reconciliation_is_idempotent_upward_and_collision_atomic(self):
        patient = Patient.objects.create(first_name="Synthetic")
        binding = {"mtno": "MT-001000", "identity_uuid": str(uuid.uuid4())}
        checkpoint = reconcile_identity_allocator(minimum_high_water=2000, bindings=[binding])
        self.assertEqual(reconcile_identity_allocator(bindings=[binding]), checkpoint)
        with self.assertRaises(ValidationError):
            reconcile_identity_allocator(bindings=[
                {"mtno": "MT-003000", "identity_uuid": str(uuid.uuid4())},
                {"mtno": patient.mtno, "identity_uuid": str(uuid.uuid4())},
            ])
        self.assertEqual(identity_checkpoint(), checkpoint)
        self.assertEqual(Patient.objects.create().mtno, "MT-002001")

    def test_import_binding_rejects_reusing_uuid_and_invalid_canonical_mtno(self):
        patient = Patient.objects.create()
        with self.assertRaises(ValidationError):
            register_identity_binding(mtno="MT-009999", identity_uuid=patient.identity_uuid)
        for invalid in ("MT-000000", "MT-1", "MT-0000001", "mt-000001", " MT-000001", "MT-9223372036854775808"):
            with self.subTest(value=invalid), self.assertRaises(ValidationError):
                parse_mtno(invalid)

    def test_audit_failure_rolls_back_patient_and_issuance(self):
        checkpoint = identity_checkpoint()
        with patch("patients.signals.record_audit_event", side_effect=RuntimeError("synthetic audit failure")):
            with self.assertRaises(RuntimeError), transaction.atomic():
                Patient.objects.create(first_name="Synthetic")
        self.assertEqual(Patient.objects.count(), 0)
        self.assertEqual(identity_checkpoint(), checkpoint)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL lock/constraint proof")
class PatientIdentityConcurrencyTests(TransactionTestCase):
    def test_concurrent_allocations_have_distinct_bindings(self):
        barrier = Barrier(4)

        def create():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL lock_timeout = '10s'")
                    patient = Patient.objects.create(first_name="Synthetic")
                    return patient.mtno, patient.identity_uuid
            finally:
                connections["default"].close()

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(create) for _ in range(4)]
            identities = [future.result(timeout=20) for future in futures]
        self.assertEqual(len(set(number for number, _ in identities)), 4)
        self.assertEqual(len(set(binding for _, binding in identities)), 4)
        self.assertEqual(PatientIdentityIssuance.objects.count(), 4)
