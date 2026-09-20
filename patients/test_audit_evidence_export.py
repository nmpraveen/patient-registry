"""PostgreSQL commit-inversion coverage for the separate acknowledgement ledger."""

from pathlib import Path
import json
import tempfile
import threading
from unittest import skipUnless

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase

from patients.models import AuditEvent, AuditEvidenceExportAck, AuditEvidenceExportState
from scripts.security_evidence_state import UNACKNOWLEDGED, acknowledge_segment, reconcile_acknowledgements


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL transaction visibility")
class AuditEvidenceExportTests(TransactionTestCase):
    def event(self):
        return AuditEvent.objects.create(category="IAM", action="synthetic-export-test")

    def eligible(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT event_id FROM patients_auditevent WHERE " + UNACKNOWLEDGED + " ORDER BY id")
            return {row[0] for row in cursor.fetchall()}

    def execute(self, sql):
        with connection.cursor() as cursor:
            cursor.execute(sql)

    def segment(self, root, event, sequence=1, chain="1" * 64):
        segment = root / "segments" / f"segment-{sequence:08d}-20260920T120000Z"
        segment.mkdir(parents=True)
        (segment / "segment.meta").write_text(f"sequence={sequence}\n")
        (segment / "chain.env").write_text(f"chain_sha256={chain}\n")
        (segment / "audit-events.jsonl").write_text(json.dumps({"event_id": str(event.event_id)}) + "\n")
        return segment

    def test_late_lower_id_commit_remains_eligible_after_higher_id_ack(self):
        allocated = threading.Event()
        release = threading.Event()
        result = {}

        def lower_transaction():
            close_old_connections()
            try:
                with transaction.atomic():
                    result["lower"] = self.event()
                    allocated.set()
                    if not release.wait(15):
                        raise RuntimeError("Commit-inversion test timed out")
            except Exception as exc:
                result["error"] = exc
                allocated.set()
            finally:
                close_old_connections()

        worker = threading.Thread(target=lower_transaction)
        worker.start()
        try:
            self.assertTrue(allocated.wait(10))
            if "error" in result:
                raise result["error"]
            higher = self.event()
            self.assertGreater(higher.pk, result["lower"].pk)
            self.assertEqual(self.eligible(), {higher.event_id})
            with tempfile.TemporaryDirectory() as directory:
                acknowledge_segment(self.segment(Path(directory), higher), self.execute)
            self.assertEqual(self.eligible(), set())
        finally:
            release.set()
            worker.join(15)
        self.assertFalse(worker.is_alive())
        if "error" in result:
            raise result["error"]
        self.assertEqual(self.eligible(), {result["lower"].event_id})

    def test_unacknowledged_publication_is_replayed_and_ack_is_idempotent(self):
        event = self.event()
        with tempfile.TemporaryDirectory() as directory:
            segment = self.segment(Path(directory), event)
            self.assertIn(event.event_id, self.eligible())
            acknowledge_segment(segment, self.execute)
            acknowledge_segment(segment, self.execute)
        self.assertEqual(AuditEvidenceExportAck.objects.count(), 1)
        self.assertFalse(self.eligible())
        self.assertTrue(AuditEvent.objects.filter(event_id=event.event_id).exists())

    def test_database_ahead_of_restored_evidence_does_not_suppress_future_event(self):
        old = self.event()
        future = self.event()
        AuditEvidenceExportAck.objects.create(event_id=future.event_id, segment_sequence=2,
            segment_chain_sha256="2" * 64, segment_name="segment-00000002-20260920T120000Z")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.segment(root, old)
            (root / "state").mkdir()
            (root / "state/checkpoint.env").write_text("sequence=1\n")
            reconcile_acknowledgements(root, self.execute)
        self.assertEqual(self.eligible(), {future.event_id})

    def test_existing_history_outside_retained_segments_is_not_blindly_acknowledged(self):
        historical = self.event()
        retained = self.event()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.segment(root, retained, sequence=200)
            (root / "state").mkdir()
            (root / "state/checkpoint.env").write_text("sequence=200\nlast_audit_id=999999\n")
            reconcile_acknowledgements(root, self.execute)
        self.assertEqual(self.eligible(), {historical.event_id})

    def test_proven_checkpoint_skips_reprocessing_earlier_event_files(self):
        event = self.event()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            segment = self.segment(root, event)
            (root / "state").mkdir()
            (root / "state/checkpoint.env").write_text("sequence=1\nchain_sha256=" + "1" * 64 + "\n")
            reconcile_acknowledgements(root, self.execute)
            state = AuditEvidenceExportState.objects.get(pk=1)
            # The full-chain verifier owns integrity checking; reconciliation
            # must not parse old event payloads again after DB ancestry proof.
            (segment / "audit-events.jsonl").write_text("not read on incremental reconciliation\n")
            reconcile_acknowledgements(root, self.execute, (state.segment_sequence, state.segment_chain_sha256))
        self.assertEqual(AuditEvidenceExportAck.objects.count(), 1)

    def test_unknown_database_chain_replays_only_verified_retained_uuids(self):
        old = self.event()
        retained = self.event()
        AuditEvidenceExportAck.objects.create(event_id=old.event_id, segment_sequence=1,
            segment_chain_sha256="f" * 64, segment_name="segment-00000001-20260920T120000Z")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.segment(root, retained)
            (root / "state").mkdir()
            (root / "state/checkpoint.env").write_text("sequence=1\n")
            reconcile_acknowledgements(root, self.execute, (1, "f" * 64))
        self.assertEqual(self.eligible(), {old.event_id})

    def test_failed_second_batch_cannot_publish_partial_acknowledgement_progress(self):
        events = AuditEvent.objects.bulk_create([
            AuditEvent(category="IAM", action="synthetic-batch") for _ in range(501)
        ])
        inserts = 0

        def interrupted_execute(sql):
            nonlocal inserts
            if sql.startswith("INSERT INTO patients_auditevidenceexportack"):
                inserts += 1
                if inserts == 2:
                    raise RuntimeError("synthetic interrupted pipe")
            self.execute(sql)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            segment = self.segment(root, events[0])
            (segment / "audit-events.jsonl").write_text("".join(
                json.dumps({"event_id": str(event.event_id)}) + "\n" for event in events
            ))
            (root / "state").mkdir()
            (root / "state/checkpoint.env").write_text("sequence=1\n")
            try:
                with self.assertRaisesRegex(RuntimeError, "interrupted pipe"):
                    reconcile_acknowledgements(root, interrupted_execute)
            finally:
                # The CLI terminates its failed psql process; closing that
                # connection performs this same rollback automatically.
                self.execute("ROLLBACK")
        self.assertEqual(AuditEvidenceExportAck.objects.count(), 0)
        self.assertEqual(AuditEvidenceExportState.objects.count(), 0)
        self.assertEqual(len(self.eligible()), 501)
