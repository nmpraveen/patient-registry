"""Exercise actual OS state locks, including native Windows byte-range locks."""
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

from scripts.scratch_restore_state import fields, state_lock, write


class ScratchStateTests(unittest.TestCase):
    def args(self, root, attempt_id, status="running", claim=False):
        return SimpleNamespace(
            attempt=str(root / "latest.attempt"), receipt=str(root / "restore.receipt"),
            attempt_id=attempt_id, status=status, claim=claim, started_epoch="1",
            stage="complete" if status == "success" else "preflight", alert="not-needed",
        )

    def test_older_finalizers_cannot_replace_newer_state_or_receipt(self):
        for status in ("running", "failure", "success"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                write(self.args(root, "1-1-1", claim=True))
                write(self.args(root, "1-1-1", status="success"))
                write(self.args(root, "1-2-2", claim=True))
                if status != "running":
                    write(self.args(root, "1-2-2", status=status))
                attempt = root / "latest.attempt"
                receipt = root / "restore.receipt"
                before = (attempt.read_bytes(), receipt.read_bytes())
                for old_status in ("success", "failure"):
                    with self.assertRaises(ValueError):
                        write(self.args(root, "1-1-1", status=old_status))
                    self.assertEqual(before, (attempt.read_bytes(), receipt.read_bytes()))

    def test_new_claim_waits_for_atomic_ownership_transaction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(self.args(root, "1-1-1", claim=True))
            attempt = root / "latest.attempt"
            script = Path(__file__).resolve().parents[1] / "scratch_restore_state.py"
            args = self.args(root, "1-2-2", claim=True)
            command = [sys.executable, str(script), "--claim"]
            for field, value in vars(args).items():
                if field != "claim":
                    command.extend(["--" + field.replace("_", "-"), value])
            process = None
            try:
                with state_lock(attempt):
                    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    with self.assertRaises(subprocess.TimeoutExpired):
                        process.communicate(timeout=0.3)
                    self.assertEqual(fields(attempt.read_bytes())["attempt_id"], "1-1-1")
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, (stdout, stderr))
                self.assertEqual(fields(attempt.read_bytes())["attempt_id"], "1-2-2")
            finally:
                if process is not None and process.poll() is None:
                    process.kill()
                    process.communicate()


if __name__ == "__main__":
    unittest.main()
