import unittest

from scripts.offsite_health_state import can_reuse, object_identity


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
