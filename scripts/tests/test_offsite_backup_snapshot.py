"""Exercise exporter advancement inside the existing fully fake backup harness."""

from pathlib import Path
import os
import subprocess
import unittest


@unittest.skipIf(os.name == "nt", "Run shell stubs with native Linux Python")
class BackupSnapshotTests(unittest.TestCase):
    def test_concurrent_export_cannot_change_full_or_checkpoint_snapshot_identity(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / "scripts/tests/test-offsite-backup.sh").read_text()
        harness = source.split("export FAKE_AUDIT_SCHEMA_PRESENT=0")[0]
        harness = harness.replace('repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"', 'repo_root="$(pwd)"')
        advance = r'''  previous_dir="$MEDTRACK_SECURITY_EVIDENCE_ROOT/segments/segment-00000001-20260829T120000Z"
  next_dir="$MEDTRACK_SECURITY_EVIDENCE_ROOT/segments/segment-00000002-20260829T130000Z"
  cp -R "$previous_dir" "$next_dir"
  previous_hash="$(sed -n 's/^chain_sha256=//p' "$previous_dir/chain.env" | tr -d '\r\n')"
  printf 'segment_format=medtrack-security-evidence-v1\nsequence=2\ncreated_utc=20260829T130000Z\nprevious_chain_sha256=%s\n' "$previous_hash" > "$next_dir/segment.meta"
  (cd "$next_dir" && sha256sum audit-events.jsonl caddy-access.jsonl gunicorn-access.jsonl segment.meta > manifest.sha256)
  next_manifest="$(sha256sum "$next_dir/manifest.sha256" | awk '{print $1}')"
  next_hash="$(printf '%s\n%s\n' "$previous_hash" "$next_manifest" | sha256sum | awk '{print $1}')"
  printf 'manifest_sha256=%s\nchain_sha256=%s\n' "$next_manifest" "$next_hash" > "$next_dir/chain.env"
  printf 'checkpoint_format=medtrack-security-evidence-checkpoint-v1\nsequence=2\nlast_audit_id=5\nchain_sha256=%s\ncompleted_epoch=%s\nlast_segment=segment-00000002-20260829T130000Z\n' "$next_hash" "$(date -u +%s)" > "$MEDTRACK_SECURITY_EVIDENCE_ROOT/state/checkpoint.env"
'''
        marker = "  printf 'PGDMP-test-database\\n'"
        self.assertIn(marker, harness)
        harness = harness.replace(marker, advance + marker)
        for tier, directory in (("weekly", "security-evidence"), ("canary", "security-evidence-checkpoint")):
            with self.subTest(tier=tier):
                run = harness + f'''MEDTRACK_BACKUP_TIMESTAMP=20260811T010000Z "$repo_root/scripts/backup-offsite.sh" --tier {tier}
archive="$backup_root/local/{tier}/medtrack-prod-{tier}-20260811T010000Z.tar.age"
runtime_chain="$(tar -xOzf "$archive" ./runtime.txt | sed -n 's/^security_evidence_chain_sha256=//p')"
embedded_chain="$(tar -xOzf "$archive" ./{directory}/state/checkpoint.env | sed -n 's/^chain_sha256=//p')"
[[ "$runtime_chain" == "$embedded_chain" && "$runtime_chain" == "$chain_hash" ]]
'''
                result = subprocess.run(["bash", "-s"], cwd=root, input=run, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
