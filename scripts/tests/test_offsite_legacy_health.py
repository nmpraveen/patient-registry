"""Exercise the real shell verifier against a local synthetic rclone remote."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.offsite_legacy_catalog import POLICY, sha256
from scripts.tests.test_offsite_legacy_catalog import document, triplet, NAMESPACE

REPO = Path(__file__).resolve().parents[2]
FAKE_RCLONE = r'''#!/usr/bin/env python3
import hashlib, json, os, pathlib, sys
args = sys.argv[1:]
if args[0] == "--config": args = args[2:]
command, remote = args[:2]
root = pathlib.Path(os.environ["FAKE_REMOTE"])
path = root / remote.split(":", 1)[1]
if command == "lsf":
    # Replace the external catalog after the shell has snapshotted it.
    replacement = os.environ.get("REPLACE_CATALOG")
    if replacement: pathlib.Path(replacement).write_bytes(b"replaced mid-run")
    print("\n".join(sorted(p.name for p in path.iterdir() if p.is_file())))
elif command == "cat":
    with open(os.environ["FAKE_DOWNLOADS"], "a") as log: log.write(remote + "\n")
    sys.stdout.buffer.write(path.read_bytes())
elif command == "lsjson":
    raw = path.read_bytes()
    print(json.dumps({"ID": str(path), "Size": len(raw), "ModTime": "fixed",
                      "Hashes": {"sha256": hashlib.sha256(raw).hexdigest()}}))
elif command == "about": print('{"free": 1000000}')
else: raise SystemExit(2)
'''


@unittest.skipIf(os.name == "nt", "Shell orchestration runs in Linux CI; parser/lock tests also run natively")
class LegacyHealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        binary = self.root / "bin"; binary.mkdir()
        rclone = binary / "rclone"; rclone.write_text(FAKE_RCLONE); rclone.chmod(0o700)
        config = self.root / "rclone.conf"; config.write_text("synthetic")
        hook = self.root / "hook"; hook.write_text("#!/bin/sh\nexit 0\n"); hook.chmod(0o700)
        self.downloads = self.root / "downloads"
        self.remote = self.root / "remote" / "backup" / "production"
        self.state = self.root / "state"
        self.catalog_path = self.root / "private-catalog.json"
        self.env = os.environ | {
            "PATH": str(binary) + os.pathsep + os.environ["PATH"],
            "FAKE_REMOTE": str(self.root / "remote"), "FAKE_DOWNLOADS": str(self.downloads),
            "MEDTRACK_BACKUP_CONFIG": str(self.root / "absent-config"), "RCLONE_CONFIG": str(config),
            "RCLONE_REMOTE": NAMESPACE, "MEDTRACK_HEALTH_STATE_ROOT": str(self.state),
            "MEDTRACK_HEALTH_HASH_MODE": "all", "PYTHON_COMMAND": "python3",
            "MEDTRACK_HEALTH_PRODUCTION_MODE": "1", "MEDTRACK_FULL_SCRUB_MAX_AGE_SECONDS": "691200",
            "MEDTRACK_SCRATCH_RESTORE_RECEIPT": str(self.root / "restore.receipt"),
            "MEDTRACK_SCRATCH_RESTORE_HOOK": str(hook), "MEDTRACK_SCRATCH_RESTORE_ALERT_HOOK": str(hook),
            "MEDTRACK_SECURITY_EVIDENCE_HEALTH_HOOK": str(hook),
            "MEDTRACK_LEGACY_CATALOG": "", "MEDTRACK_LEGACY_CATALOG_SHA256": "",
        }
        self.stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.current = {}
        for tier in ("rapid", "daily", "weekly", "monthly"):
            entry, marker, checksum = triplet(tier=tier, stamp=self.stamp, shape="current")
            self.publish(entry, marker, checksum)
            self.current[tier] = entry
        self.entries = []
        for shape, stamp in (("offsite-v1", "20200101T000000Z"), ("offsite-v2", "20200102T000000Z"),
                             ("offsite-v3", "20200103T000000Z")):
            entry, marker, checksum = triplet(stamp=stamp, shape=shape)
            self.publish(entry, marker, checksum); self.entries.append(entry)
        restore = subprocess.run(["bash", str(REPO / "scripts/run-offsite-scratch-restore.sh")],
                                 env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(restore.returncode, 0, restore.stdout + restore.stderr)
        self.pin()

    def publish(self, entry, marker, checksum):
        directory = self.remote / entry["tier"]; directory.mkdir(parents=True, exist_ok=True)
        path = directory / entry["archive"]
        path.write_bytes(b"synthetic encrypted bytes only\n")
        Path(str(path) + ".complete").write_bytes(marker)
        Path(str(path) + ".sha256").write_bytes(checksum)

    def pin(self):
        raw = json.dumps(document(self.entries)).encode()
        self.catalog_path.write_bytes(raw)
        self.env.update(MEDTRACK_LEGACY_CATALOG=str(self.catalog_path), MEDTRACK_LEGACY_CATALOG_SHA256=sha256(raw))

    def run_health(self, success=True, **env):
        result = subprocess.run(["bash", str(REPO / "scripts/check-offsite-backups.sh")],
                                env=self.env | env, capture_output=True, text=True, timeout=45)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("OFFSITE_BACKUP_HEALTH_OK", result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("OFFSITE_BACKUP_HEALTH_OK", result.stdout)
        return result

    def receipt(self):
        return next(self.state.glob("full-scrub-*.receipt"))

    def test_full_then_incremental_preserves_triplets_and_reuses_verified_hashes(self):
        before = {str(path): path.read_bytes() for path in self.remote.rglob("*") if path.is_file()}
        self.run_health()
        receipt = self.receipt().read_text()
        self.assertIn("metadata_policy=" + POLICY, receipt)
        self.assertIn("legacy_catalog_sha256=" + self.env["MEDTRACK_LEGACY_CATALOG_SHA256"], receipt)
        self.downloads.write_text("")
        self.run_health(MEDTRACK_HEALTH_HASH_MODE="incremental")
        self.assertFalse(any(line.endswith(".tar.age") for line in self.downloads.read_text().splitlines()))
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.remote.rglob("*") if path.is_file()})

    def test_catalog_policy_or_catalog_digest_change_requires_new_scrub_and_cache_acceptance(self):
        self.run_health()
        receipt = self.receipt(); good = receipt.read_text()
        for changed in (good.replace(POLICY, "other-policy"), good.replace("scrub-v2", "scrub-v1"),
                        good.replace("completed_epoch=", "completed_epoch=0\nignored=")):
            receipt.write_text(changed)
            self.run_health(False, MEDTRACK_HEALTH_HASH_MODE="incremental")
        receipt.write_text(good)
        # A byte-only catalog edit still changes its independent pin and acceptance scope.
        raw = self.catalog_path.read_bytes() + b"\n"; self.catalog_path.write_bytes(raw)
        self.env["MEDTRACK_LEGACY_CATALOG_SHA256"] = sha256(raw)
        self.run_health(False, MEDTRACK_HEALTH_HASH_MODE="incremental")
        self.downloads.write_text("")
        # Nonproduction incremental still cannot reuse old policy-scoped object acceptance.
        self.run_health(MEDTRACK_HEALTH_PRODUCTION_MODE="0", MEDTRACK_HEALTH_HASH_MODE="incremental")
        self.assertEqual(sum(line.endswith(".tar.age") for line in self.downloads.read_text().splitlines()), 7)
        self.run_health()
        self.run_health(MEDTRACK_HEALTH_HASH_MODE="incremental")

    def test_unlisted_wrong_namespace_size_and_changed_triplet_fail_without_receipt(self):
        for overrides in ({"MEDTRACK_LEGACY_CATALOG": "", "MEDTRACK_LEGACY_CATALOG_SHA256": ""},
                          {"MEDTRACK_LEGACY_CATALOG_SHA256": "0" * 64},
                          {"RCLONE_REMOTE": "synthetic:wrong/root"}):
            self.run_health(False, **overrides)
        self.entries[0]["ciphertext_size"] += 1; self.pin()
        self.run_health(False)
        self.entries[0]["ciphertext_size"] -= 1; self.pin()
        for suffix in ("", ".sha256", ".complete"):
            path = self.remote / "weekly" / (self.entries[0]["archive"] + suffix)
            original = path.read_bytes(); path.write_bytes(original + b"changed\n")
            self.run_health(False)
            path.write_bytes(original)
        self.assertFalse(list(self.state.glob("full-scrub-*.receipt")))

    def test_retired_entries_allowed_but_legacy_newest_or_stale_modern_fails(self):
        retired = self.entries[0]
        for suffix in ("", ".sha256", ".complete"):
            (self.remote / "weekly" / (retired["archive"] + suffix)).unlink()
        self.run_health()
        modern = self.current["weekly"]
        for suffix in ("", ".sha256", ".complete"):
            (self.remote / "weekly" / (modern["archive"] + suffix)).unlink()
        self.run_health(False)
        entry, marker, checksum = triplet(stamp="20200104T000000Z", shape="current")
        self.publish(entry, marker, checksum)
        result = self.run_health(False)
        self.assertIn("freshness_source", result.stdout)  # other tiers still checked
        self.assertIn("maximum_seconds=691200", result.stderr)

    def test_restore_attempt_evidence_or_orphan_failure_cannot_publish_scrub(self):
        attempt = Path(self.env["MEDTRACK_SCRATCH_RESTORE_RECEIPT"] + ".attempt")
        good = attempt.read_text(); attempt.write_text(good.replace("status=success", "status=failure"))
        self.run_health(False)
        attempt.write_text(good)
        self.run_health(False, MEDTRACK_SECURITY_EVIDENCE_HEALTH_HOOK=str(self.root / "missing"))
        orphan = self.remote / "weekly" / "orphan.tar.age"; orphan.write_bytes(b"orphan")
        self.run_health(False)
        self.assertFalse(list(self.state.glob("full-scrub-*.receipt")))

    def test_midrun_catalog_replacement_uses_only_initial_snapshot(self):
        digest = self.env["MEDTRACK_LEGACY_CATALOG_SHA256"]
        self.run_health(REPLACE_CATALOG=str(self.catalog_path))
        self.assertEqual(self.catalog_path.read_bytes(), b"replaced mid-run")
        self.assertIn("legacy_catalog_sha256=" + digest, self.receipt().read_text())
        self.run_health(False)

    def test_legacy_entries_still_count_toward_tier_retention_limit(self):
        for day in range(4, 13):
            entry, marker, checksum = triplet(stamp=f"202001{day:02d}T000000Z")
            self.publish(entry, marker, checksum); self.entries.append(entry)
        self.pin()
        result = self.run_health(False)
        self.assertIn("remote_complete_markers=13 expected=1..12", result.stderr)
        self.assertFalse(list(self.state.glob("full-scrub-*.receipt")))


if __name__ == "__main__":
    unittest.main()
