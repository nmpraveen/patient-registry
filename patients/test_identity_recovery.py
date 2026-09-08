"""Synthetic identity-bundle and older-restore checkpoint regressions."""

import hashlib
import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connections
from django.db.models.query import QuerySet
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from . import database_bundle as bundle
from .identity import identity_allocation_lock, identity_checkpoint, parse_mtno, reconcile_identity_allocator
from .identity_recovery import decode_identity_checkpoint, encode_identity_checkpoint, verify_patient_identities
from .models import (
    AuditEvent, CallLog, CallOutcome, Case, DepartmentConfig, Patient,
    PatientIdentityIssuance, PatientMergeRecovery,
)


def archive_payload(payload, version=4):
    data = bundle._json_bytes(payload)
    manifest = {"schema_version": version, "counts": bundle.compute_payload_counts(payload),
                "patient_data_sha256": hashlib.sha256(data).hexdigest()}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(bundle.PATIENT_DATA_FILENAME, data)
        archive.writestr(bundle.MANIFEST_FILENAME, json.dumps(manifest))
    return buffer.getvalue()


class IdentityRecoveryTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        backup_patch = patch.object(bundle, "default_backup_dir", return_value=Path(self.directory.name))
        backup_patch.start()
        self.addCleanup(backup_patch.stop)
        self.category, _ = DepartmentConfig.objects.get_or_create(name="Medicine")

    def patient(self, uhid="", name="Synthetic"):
        return Patient.objects.create(uhid=uhid, first_name=name, last_name="Example")

    def case(self, patient):
        return Case.objects.create(patient=patient, uhid=patient.uhid, first_name=patient.first_name,
                                   last_name=patient.last_name, category=self.category,
                                   metadata={"entry_mode": "quick_entry", "details_pending": True})

    def assert_rejected_before_delete(self, payload, message=None, version=4):
        before = list(Patient.objects.order_by("pk").values_list("pk", "mtno", "identity_uuid"))
        checkpoint = identity_checkpoint()
        original_delete = QuerySet.delete
        calls = []

        def track_delete(queryset):
            if queryset.model in (Patient, Case):
                calls.append(queryset.model)
            return original_delete(queryset)

        with patch.object(QuerySet, "delete", track_delete):
            with self.assertRaises(bundle.BundleValidationError) as error:
                bundle.import_bundle_bytes(archive_payload(payload, version))
        if message:
            self.assertIn(message, str(error.exception))
        self.assertEqual(calls, [])
        self.assertEqual(list(Patient.objects.order_by("pk").values_list("pk", "mtno", "identity_uuid")), before)
        self.assertEqual(identity_checkpoint(), checkpoint)

    def test_reserved_hospital_namespace_rejects_all_bundle_versions_before_delete(self):
        patient = self.patient("HOSP-SYNTHETIC")
        self.case(patient)
        _, original = bundle.load_bundle_archive(bundle.create_bundle_archive()[0])
        checkpoint = identity_checkpoint()
        for version in (1, 2, 3, 4):
            with self.subTest(version=version):
                payload = deepcopy(original)
                payload["patients"][0]["uhid"] = patient.mtno
                payload["cases"][0]["uhid"] = patient.mtno
                payload["cases"][0]["patient_uhid"] = patient.mtno
                if version < 4:
                    payload.pop("identity")
                self.assert_rejected_before_delete(payload, "reserved MTNO", version=version)
                with self.assertRaisesMessage(bundle.BundleValidationError, "reserved MTNO"):
                    bundle._replace_patient_data(payload)
                patient.refresh_from_db()
                self.assertEqual(patient.uhid, "HOSP-SYNTHETIC")
                self.assertEqual(identity_checkpoint(), checkpoint)

    def test_two_blank_uhids_and_merged_source_round_trip_with_call_reason(self):
        survivor = self.patient()
        second = self.patient(name="Second")
        source = self.patient("TMP-20260907-001", "Alias")
        Patient.objects.filter(pk=source.pk).update(merged_into=survivor)
        case = self.case(survivor)
        self.case(survivor)
        self.case(second)
        CallLog.objects.create(case=case, reason="Synthetic follow-up", outcome=CallOutcome.NO_ANSWER,
                               client_event_at=timezone.now())
        before = {(p.mtno, str(p.identity_uuid), p.uhid) for p in Patient.objects.all()}
        archive, manifest, _ = bundle.create_bundle_archive()
        self.assertEqual(manifest["schema_version"], 4)
        bundle.import_bundle_bytes(archive)
        self.assertEqual({(p.mtno, str(p.identity_uuid), p.uhid) for p in Patient.objects.all()}, before)
        self.assertEqual(Patient.objects.filter(uhid="").count(), 2)
        self.assertEqual(Patient.objects.get(mtno=source.mtno).merged_into.mtno, survivor.mtno)
        self.assertEqual(CallLog.objects.get().reason, "Synthetic follow-up")
        self.assertEqual(PatientMergeRecovery.objects.count(), 0)
        self.assertEqual(verify_patient_identities()["patients"], 3)

    def test_foreign_collision_and_inverse_uuid_collision_reject_before_deletion(self):
        self.case(self.patient())
        original = bundle.build_patient_data_payload()
        payload = deepcopy(original)
        changed_uuid = str(uuid4())
        payload["patients"][0]["identity_uuid"] = changed_uuid
        payload["identity"]["bindings"][0]["identity_uuid"] = changed_uuid
        self.assert_rejected_before_delete(payload, "Identity import rejected")
        payload = deepcopy(original)
        old_mtno = payload["patients"][0]["mtno"]
        payload["patients"][0]["mtno"] = "MT-900000"
        payload["identity"]["bindings"] = [{"mtno": "MT-900000", "identity_uuid": payload["patients"][0]["identity_uuid"]}]
        payload["identity"]["high_water"] = 900000
        for case in payload["cases"]:
            if case["patient_mtno"] == old_mtno:
                case["patient_mtno"] = "MT-900000"
        self.assert_rejected_before_delete(payload, "Identity import rejected")

    def test_graph_rejects_missing_self_chain_cycle_duplicate_and_noncanonical_ids(self):
        first, second, third = [self.patient(name=name) for name in ("First", "Second", "Third")]
        self.case(third)
        original = bundle.build_patient_data_payload()
        for edges in ({first.mtno: first.mtno}, {first.mtno: "MT-999999"},
                      {first.mtno: second.mtno, second.mtno: third.mtno},
                      {first.mtno: second.mtno, second.mtno: first.mtno}):
            with self.subTest(edges=edges):
                payload = deepcopy(original)
                for row in payload["patients"]:
                    row["merged_into_mtno"] = edges.get(row["mtno"])
                self.assert_rejected_before_delete(payload, "Merged aliases")
        for mtno in ("mt-000001", "MT-1", "MT-000000", "MT-0000001", " MT-000001", "MT-9223372036854775808"):
            payload = deepcopy(original)
            payload["identity"]["bindings"][0]["mtno"] = mtno
            self.assert_rejected_before_delete(payload)
        payload = deepcopy(original)
        payload["patients"].append(deepcopy(payload["patients"][0]))
        self.assert_rejected_before_delete(payload, "Duplicate patient")
        payload = deepcopy(original)
        payload["cases"][0]["patient_mtno"] = "MT-999999"
        self.assert_rejected_before_delete(payload, "Case must reference")

    def test_legacy_versions_preserve_unique_existing_uhid_and_allocate_new_identity(self):
        existing = self.patient("LEGACY-001")
        case = self.case(existing)
        CallLog.objects.create(case=case, reason="Stage two reason", outcome=CallOutcome.NO_ANSWER)
        source = bundle.build_patient_data_payload()
        for version in (1, 2, 3):
            with self.subTest(version=version):
                payload = deepcopy(source)
                payload.pop("identity")
                for row in payload["patients"]:
                    row.pop("mtno")
                    row.pop("identity_uuid")
                    row.pop("merged_into_mtno")
                for row in payload["cases"]:
                    row.pop("patient_mtno")
                    row["patient_uhid"] = row["uhid"]
                if version == 1:
                    payload.pop("patients")
                bundle.import_bundle_bytes(archive_payload(payload, version))
                restored = Patient.objects.get(uhid=existing.uhid)
                self.assertEqual((restored.mtno, restored.identity_uuid), (existing.mtno, existing.identity_uuid))
                self.assertEqual(CallLog.objects.get().reason, "Stage two reason")
        legacy = deepcopy(payload)
        legacy["patients"] = [{"uhid": "LEGACY-NEW", "first_name": "Other", "last_name": "Example"}]
        legacy["cases"] = []
        floor = identity_checkpoint()["high_water"]
        bundle.import_bundle_bytes(archive_payload(legacy, 2))
        self.assertGreater(parse_mtno(Patient.objects.get().mtno), floor)

    def test_retained_deleted_issuance_and_high_water_survive_older_bundle(self):
        self.patient("OLD")
        archive, _, _ = bundle.create_bundle_archive()
        later = self.patient("LATER")
        later_mtno, later_uuid = later.mtno, later.identity_uuid
        later.delete()
        reconcile_identity_allocator(minimum_high_water=2000)
        bundle.import_bundle_bytes(archive)
        self.assertTrue(PatientIdentityIssuance.objects.filter(mtno=later_mtno, identity_uuid=later_uuid).exists())
        self.assertGreater(parse_mtno(self.patient().mtno), 2000)

    def test_protected_recovery_export_succeeds_and_import_rejects_before_deletion(self):
        source, target = self.patient("SOURCE"), self.patient("TARGET")
        case = self.case(target)
        Patient.objects.filter(pk=source.pk).update(merged_into=target)
        recovery = PatientMergeRecovery.objects.create(
            source_patient=source, target_patient=target, moved_case_ids=[case.pk],
            merge_audit_event=AuditEvent.objects.order_by("pk").first(),
        )
        payload = bundle.build_patient_data_payload()
        self.assert_rejected_before_delete(payload, "protected merge recovery evidence")
        self.assertTrue(PatientMergeRecovery.objects.filter(pk=recovery.pk).exists())

    def test_checkpoint_applies_outgoing_floor_and_binding_then_allocates_above_it(self):
        self.patient("SNAPSHOT")
        checkpoint = identity_checkpoint()
        later_uuid = str(uuid4())
        checkpoint["bindings"].append({"mtno": "MT-002500", "identity_uuid": later_uuid})
        checkpoint["high_water"] = 3000
        raw = encode_identity_checkpoint(checkpoint).encode()
        path = Path(self.directory.name) / "outgoing.json"
        path.write_bytes(raw)
        call_command("patient_identity_checkpoint", "apply", input=str(path), expected_sha256=hashlib.sha256(raw).hexdigest(), stdout=io.StringIO())
        self.assertEqual(PatientIdentityIssuance.objects.get(mtno="MT-002500").identity_uuid, __import__("uuid").UUID(later_uuid))
        self.assertGreater(parse_mtno(self.patient().mtno), 3000)
        call_command("verify_patient_identity", stdout=io.StringIO())

    def test_checkpoint_missing_digest_tampering_and_collision_leave_floor_unchanged(self):
        patient = self.patient()
        before = identity_checkpoint()
        path = Path(self.directory.name) / "checkpoint.json"
        call_command("patient_identity_checkpoint", "export", output=str(path), stdout=io.StringIO())
        with self.assertRaises(CommandError):
            call_command("patient_identity_checkpoint", "apply", input=str(path))
        with self.assertRaises(CommandError):
            call_command("patient_identity_checkpoint", "apply", input=str(path), expected_sha256="0" * 64)
        envelope = json.loads(path.read_text())
        envelope["checkpoint"]["high_water"] += 100
        with self.assertRaises(ValidationError):
            decode_identity_checkpoint(json.dumps(envelope))
        collision = deepcopy(before)
        collision["bindings"] = [{"mtno": patient.mtno, "identity_uuid": str(uuid4())}]
        raw = encode_identity_checkpoint(collision).encode()
        path.write_bytes(raw)
        with self.assertRaises(CommandError):
            call_command("patient_identity_checkpoint", "apply", input=str(path), expected_sha256=hashlib.sha256(raw).hexdigest())
        self.assertEqual(identity_checkpoint(), before)

    def test_snapshot_verification_detects_stale_allocator_then_repairs_only_upward(self):
        patient = self.patient()
        # Simulate a restored reserved issuance beyond its stored counter. The
        # production monotonic trigger remains enabled throughout the test.
        PatientIdentityIssuance.objects.create(mtno="MT-900000", identity_uuid=uuid4())
        with self.assertRaises(ValidationError):
            verify_patient_identities()
        result = verify_patient_identities(repair_floor=True)
        self.assertGreaterEqual(result["high_water"], 900000)
        self.assertGreater(parse_mtno(self.patient().mtno), parse_mtno(patient.mtno))

    def test_legacy_conflicting_identity_and_alias_chain_reject_before_delete(self):
        self.case(self.patient("LEGACY"))
        original = bundle.build_patient_data_payload()
        payload = deepcopy(original)
        payload.pop("patients")
        second = deepcopy(payload["cases"][0])
        second["bundle_id"] = "another-case"
        second["first_name"] = "Different"
        payload["cases"].append(second)
        self.assert_rejected_before_delete(payload, "conflicting identity", version=1)
        payload = deepcopy(original)
        payload["patients"][0]["merged_into_uhid"] = "LEGACY"
        self.assert_rejected_before_delete(payload, "Merged aliases", version=3)


class IdentityImportConcurrencyTests(TransactionTestCase):
    setUp = IdentityRecoveryTests.setUp
    patient = IdentityRecoveryTests.patient

    def test_create_waits_for_import_and_uses_its_higher_retained_floor(self):
        if connections["default"].vendor != "postgresql":
            self.skipTest("PostgreSQL independent connections required")
        self.patient("SYNTHETIC-IMPORT")
        payload = bundle.build_patient_data_payload()
        payload["identity"]["high_water"] = 4000
        locked, creator_started, release = Event(), Event(), Event()

        def importer():
            close_old_connections()
            try:
                with bundle._replacement_lock():
                    locked.set()
                    if not release.wait(10):
                        raise AssertionError("Import barrier timed out")
                    bundle._replace_patient_data(payload)
            finally:
                connections.close_all()

        def creator():
            close_old_connections()
            try:
                creator_started.set()
                return self.patient("SYNTHETIC-CREATE").mtno
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            importing = pool.submit(importer)
            self.assertTrue(locked.wait(10))
            creating = pool.submit(creator)
            self.assertTrue(creator_started.wait(10))
            self.assertFalse(creating.done())
            release.set()
            importing.result(timeout=15)
            self.assertGreater(parse_mtno(creating.result(timeout=15)), 4000)
        self.assertEqual(Patient.objects.count(), 2)
