import unittest
from unittest.mock import patch, Mock
import hashlib
import io
import json
from pathlib import Path
import tempfile

from scripts.offsite_health_state import can_reuse, object_identity, verify


class OffsiteIdentityTests(unittest.TestCase):
    def test_reuse_requires_same_identity_hash_and_fresh_full_hash(self):
        identity = {"ID": "opaque", "Size": 50, "ModTime": "fixed", "Hashes": {"md5": "abc"}}
        receipt = {"identity": identity, "sha256": "a" * 64, "hashed_epoch": 100}
        self.assertTrue(can_reuse(receipt, identity, "a" * 64, 110, 20))
        self.assertFalse(can_reuse(receipt, dict(identity, Size=51), "a" * 64, 110, 20))
        self.assertFalse(can_reuse(receipt, identity, "b" * 64, 110, 20))
        self.assertFalse(can_reuse(receipt, identity, "a" * 64, 121, 20))
        self.assertFalse(can_reuse(receipt, identity, "a" * 64, 99, 20))

    def test_provider_without_stable_identity_or_hash_cannot_skip_stream(self):
        self.assertIsNone(object_identity({"Size": 5, "Hashes": {"md5": "abc"}}))
        self.assertIsNone(object_identity({"ID": "opaque", "Size": 5}))
        self.assertIsNone(object_identity({"ID": "opaque", "Size": 5, "Hashes": {"md5": ""}}))
        self.assertFalse(can_reuse({}, None, "a" * 64, 100, 10))

    def test_pinned_size_is_checked_against_stream_even_when_remote_stat_lies(self):
        payload = b"synthetic bytes"
        expected = hashlib.sha256(payload).hexdigest()
        false_size = len(payload) + 1
        stat = {"ID": "opaque", "Size": false_size, "Hashes": {"sha256": expected}}
        process = Mock(stdout=io.BytesIO(payload)); process.wait.return_value = 0
        with tempfile.TemporaryDirectory() as directory, \
                patch("scripts.offsite_health_state.subprocess.run", return_value=Mock(stdout=json.dumps(stat))), \
                patch("scripts.offsite_health_state.subprocess.Popen", return_value=process):
            with self.assertRaisesRegex(ValueError, "stream hash mismatch"):
                verify("synthetic:object", expected, "synthetic", Path(directory), "all", 10,
                       expected_size=false_size, policy="synthetic-policy")
            self.assertEqual(list(Path(directory).glob("*.json")), [])
