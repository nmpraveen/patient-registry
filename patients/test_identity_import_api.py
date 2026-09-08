"""Real API requests contending with patient replacement on separate connections."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models import MobileWriteReceipt
from api.views import CaseDetailView
from . import database_bundle as bundle
from .forms import CaseForm
from .models import DepartmentConfig, ensure_default_departments


@skipUnless(connection.vendor == "postgresql", "PostgreSQL independent connections required")
class IdentityImportApiConcurrencyTests(TransactionTestCase):
    def test_import_serializes_unkeyed_keyed_and_replayed_case_edits(self):
        ensure_default_departments()
        actor = get_user_model().objects.create_superuser("identity-import-actor", password="synthetic-only")
        category = DepartmentConfig.objects.get(name="Surgery")
        for mode in ("unkeyed", "keyed", "replay"):
            with self.subTest(mode=mode), TemporaryDirectory() as directory:
                form = CaseForm(data={
                    "patient_mode": "new", "uhid": "SYNTH-" + mode.upper(), "prefix": "MR",
                    "first_name": "Synthetic", "last_name": "Example", "age": 35,
                    "phone_number": "9000000001", "category": category.pk,
                    "subcategory": "GENERAL_SURGERY", "surgical_pathway": "SURVEILLANCE",
                    "review_date": str(timezone.localdate() + timedelta(days=5)),
                }, actor=actor)
                form.instance.created_by = actor
                self.assertTrue(form.is_valid(), form.errors)
                case = form.save()
                data = {"diagnosis": "Synthetic edited", "base_values": {"diagnosis": case.diagnosis},
                        "base_updated_at": case.updated_at.isoformat()}
                if mode != "unkeyed":
                    data["client_write_id"] = "identity-import-" + mode

                def request_edit():
                    request = APIRequestFactory().patch("/api/cases/identity-probe/", data, format="json")
                    force_authenticate(request, user=actor)
                    return CaseDetailView.as_view()(request, pk=case.pk)

                if mode == "replay":
                    self.assertEqual(request_edit().status_code, 200)
                    self.assertTrue(MobileWriteReceipt.objects.filter(target_id=str(case.pk)).exists())
                archive = bundle.create_bundle_archive()[0]
                import_locked, api_attempted = Event(), Event()
                original_preflight = bundle._preflight_replacement

                def gated_preflight(payload):
                    result = original_preflight(payload)
                    if not import_locked.is_set():
                        import_locked.set()
                        if not api_attempted.wait(10):
                            raise AssertionError("API did not attempt the dataset gate")
                    return result

                def importer():
                    close_old_connections()
                    try:
                        bundle.import_bundle_bytes(archive)
                        return "imported"
                    finally:
                        connections.close_all()

                def editor():
                    close_old_connections()
                    try:
                        if not import_locked.wait(10):
                            raise AssertionError("Import did not lock its real target rows")

                        def observe_gate(execute, sql, params, many, context):
                            if "api_mobiledatasetstate" in sql.lower() and "FOR UPDATE" in sql:
                                api_attempted.set()
                            return execute(sql, params, many, context)

                        with connection.cursor() as cursor:
                            cursor.execute("SET lock_timeout = '10s'")
                        with connection.execute_wrapper(observe_gate):
                            return request_edit().status_code
                    finally:
                        connections.close_all()

                with patch.object(bundle, "default_backup_dir", return_value=Path(directory)), \
                        patch.object(bundle, "_preflight_replacement", gated_preflight), \
                        ThreadPoolExecutor(max_workers=2) as pool:
                    importing = pool.submit(importer)
                    editing = pool.submit(editor)
                    self.assertEqual(importing.result(timeout=20), "imported")
                    # The old integer target was replaced while the request waited.
                    # Authorization rechecks current rows instead of mutating a replacement.
                    self.assertEqual(editing.result(timeout=20), 404)
                self.assertFalse(MobileWriteReceipt.objects.exists())
