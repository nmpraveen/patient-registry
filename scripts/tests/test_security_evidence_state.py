import gzip
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.security_evidence_state import capture_log, ordered_logs


class SecurityLogCursorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "gunicorn-access.log"

    def test_unchanged_file_has_no_new_records(self):
        self.path.write_bytes(b'{"status":429}\n')
        first, cursor = capture_log(self.path, None, 100)
        second, _ = capture_log(self.path, cursor, 100)
        self.assertTrue(first)
        self.assertEqual(second, b"")

    def test_partial_line_and_bounded_backlog_are_not_discarded(self):
        self.path.write_bytes(b'a\nb\npartial')
        first, cursor = capture_log(self.path, None, 3)
        second, cursor = capture_log(self.path, cursor, 100)
        self.assertEqual(first + second, b'a\nb\n')
        with self.path.open("ab") as stream:
            stream.write(b'\n')
        third, _ = capture_log(self.path, cursor, 100)
        self.assertEqual(third, b'partial\n')

    def test_rotation_drains_old_tail_then_new_file(self):
        self.path.write_bytes(b'old1\nold2\n')
        first, cursor = capture_log(self.path, None, 5)
        self.path.rename(str(self.path) + '.1')
        self.path.write_bytes(b'new\n')
        second, _ = capture_log(self.path, cursor, 100)
        self.assertEqual(first + second, b'old1\nold2\nnew\n')

    def test_empty_cursor_uses_inode_after_append_and_rotation(self):
        self.path.write_bytes(b'')
        _, cursor = capture_log(self.path, None, 100)
        self.path.write_bytes(b'old-after-empty\n')
        self.path.rename(str(self.path) + '.1')
        self.path.write_bytes(b'new\n')
        content, _ = capture_log(self.path, cursor, 100)
        self.assertEqual(content, b'old-after-empty\nnew\n')

    def test_empty_cursor_copytruncate_ambiguity_fails_closed(self):
        self.path.write_bytes(b'')
        _, cursor = capture_log(self.path, None, 100)
        self.path.write_bytes(b'old-after-empty\n')
        Path(str(self.path) + '.1').write_bytes(self.path.read_bytes())
        self.path.write_bytes(b'new\n')
        with self.assertRaises(ValueError):
            capture_log(self.path, cursor, 100)

    def test_matching_prefix_in_new_file_does_not_override_original_inode(self):
        self.path.write_bytes(b'same\nold-tail\n')
        _, cursor = capture_log(self.path, None, 5)
        self.path.rename(str(self.path) + '.1')
        self.path.write_bytes(b'same\nnew-tail\n')
        content, _ = capture_log(self.path, cursor, 100)
        self.assertEqual(content, b'old-tail\nsame\nnew-tail\n')

    def test_all_intermediate_rotations_are_drained(self):
        self.path.write_bytes(b'old1\nold2\n')
        _, cursor = capture_log(self.path, None, 5)
        self.path.rename(str(self.path) + '.2')
        Path(str(self.path) + '.1').write_bytes(b'middle\n')
        self.path.write_bytes(b'new\n')
        content, _ = capture_log(self.path, cursor, 100)
        self.assertEqual(content, b'old2\nmiddle\nnew\n')

    def test_missing_intermediate_rotation_fails(self):
        self.path.write_bytes(b'old\n')
        _, cursor = capture_log(self.path, None, 100)
        self.path.rename(str(self.path) + '.2')
        self.path.write_bytes(b'new\n')
        with self.assertRaises(ValueError):
            capture_log(self.path, cursor, 100)

    def test_incomplete_closed_rotation_fails_instead_of_stalling(self):
        self.path.write_bytes(b'old\npartial')
        _, cursor = capture_log(self.path, None, 100)
        self.path.rename(str(self.path) + '.1')
        self.path.write_bytes(b'new\n')
        with self.assertRaisesRegex(ValueError, 'incomplete final line'):
            capture_log(self.path, cursor, 100)

    def test_copytruncate_uses_retained_copy(self):
        self.path.write_bytes(b'old1\nold2\n')
        first, cursor = capture_log(self.path, None, 5)
        Path(str(self.path) + '.1').write_bytes(self.path.read_bytes())
        self.path.write_bytes(b'new-record-longer-than-previous-offset\n')
        second, _ = capture_log(self.path, cursor, 100)
        self.assertEqual(first + second, b'old1\nold2\nnew-record-longer-than-previous-offset\n')

    def test_lost_rotation_and_oversized_line_fail_closed(self):
        self.path.write_bytes(b'old\n')
        _, cursor = capture_log(self.path, None, 100)
        self.path.write_bytes(b'new\n')
        with self.assertRaises(ValueError):
            capture_log(self.path, cursor, 100)
        with self.assertRaises(ValueError):
            capture_log(self.path, None, 2)

    def test_shorter_file_with_same_prefix_cannot_hide_lost_copytruncate(self):
        self.path.write_bytes(b'a\n' * 2500)
        _, cursor = capture_log(self.path, None, 10000)
        self.path.write_bytes(b'a\n' * 2200)
        with self.assertRaises(ValueError):
            capture_log(self.path, cursor, 1000)


class CaddyLogCursorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "caddy-access.json"

    def rotate_compressed(self, name):
        rotated = self.path.with_name(name)
        with gzip.open(rotated, "wb") as stream:
            stream.write(self.path.read_bytes())
        self.path.unlink()

    def test_compressed_size_rotation_drains_tail_and_current_with_bounds(self):
        self.path.write_bytes(b"old1\nold2\n")
        first, cursor = capture_log(self.path, None, 5)
        self.rotate_compressed("caddy-access-2026-09-20T04-05-56.762-size.json.gz")
        self.path.write_bytes(b"new1\nnew2\n")
        second, cursor = capture_log(self.path, cursor, 5)
        third, cursor = capture_log(self.path, cursor, 5)
        fourth, cursor = capture_log(self.path, cursor, 100)
        unchanged, _ = capture_log(self.path, cursor, 100)
        self.assertEqual((first, second, third, fourth, unchanged),
                         (b"old1\n", b"old2\n", b"new1\n", b"new2\n", b""))

    def test_legacy_time_and_size_rotations_are_drained_in_timestamp_order(self):
        self.path.write_bytes(b"first\ntail\n")
        _, cursor = capture_log(self.path, None, 6)
        self.rotate_compressed("caddy-access-2026-09-20T04-05-56.760.json.gz")
        self.path.with_name("caddy-access-2026-09-20T04-05-56.762-size.json").write_bytes(b"size\n")
        with gzip.open(self.path.with_name("caddy-access-2026-09-20T04-05-56.761-time.json.gz"), "wb") as stream:
            stream.write(b"time\n")
        self.path.write_bytes(b"current\n")
        content, _ = capture_log(self.path, cursor, 100)
        self.assertEqual(content, b"tail\ntime\nsize\ncurrent\n")

    def test_supported_default_names_and_compression_variants(self):
        for reason in ("", "-size", "-time"):
            for compression in ("", ".gz"):
                with self.subTest(reason=reason, compression=compression):
                    rotated = self.path.with_name(f"caddy-access-2026-09-20T04-05-56.762{reason}.json{compression}")
                    rotated.touch()
                    self.assertEqual(ordered_logs(self.path), [rotated])
                    rotated.unlink()

    def test_same_timestamp_variants_remain_ambiguous(self):
        first = self.path.with_name("caddy-access-2026-09-20T04-05-56.762-size.json")
        first.touch()
        for name in ("caddy-access-2026-09-20T04-05-56.762-size.json.gz",
                     "caddy-access-2026-09-20T04-05-56.762-time.json",
                     "caddy-access-2026-09-20T04-05-56.762.json"):
            with self.subTest(name=name):
                duplicate = self.path.with_name(name)
                duplicate.touch()
                with self.assertRaisesRegex(ValueError, "Ambiguous"):
                    ordered_logs(self.path)
                duplicate.unlink()

    def test_invalid_names_and_dates_fail_closed(self):
        for suffix in ("2026-09-20T04-05-56.762-other.json.gz",
                       "\uff12\uff10\uff12\uff16-09-20T04-05-56.762-size.json",
                       "2026-09-20T04-05-56.762-size.json.zst",
                       "2026-09-20T04-05-56.762-size.json.gz.tmp",
                       "2026-09-20T04-05-56-size.json.gz",
                       "2026-02-30T04-05-56.762-size.json.gz",
                       "2026-09-20T25-05-56.762-time.json.gz"):
            with self.subTest(suffix=suffix):
                invalid = self.path.with_name("caddy-access-" + suffix)
                invalid.touch()
                with self.assertRaises(ValueError):
                    ordered_logs(self.path)
                invalid.unlink()

    def test_compressed_inode_reuse_cannot_disambiguate_repeated_prefix(self):
        self.path.write_bytes(b"old\ntail\n")
        _, cursor = capture_log(self.path, None, 4)
        self.rotate_compressed("caddy-access-2026-09-20T04-05-56.762-size.json.gz")
        ambiguous = self.path.with_name("caddy-access-2026-09-20T04-05-57.762-size.json.gz")
        with gzip.open(ambiguous, "wb") as stream:
            stream.write(b"old\nanother-tail\n")
        # Linux can recycle the deleted raw inode for this compressed file.
        # Make that observed allocation deterministic on every test platform.
        cursor["inode"] = ambiguous.stat().st_ino
        self.path.write_bytes(b"new\n")
        with self.assertRaisesRegex(ValueError, "continuity missing"):
            capture_log(self.path, cursor, 100)

    def test_lost_compressed_tail_cannot_match_reused_current_inode(self):
        self.path.write_bytes(b"old1\nold2\ntail\n")
        _, cursor = capture_log(self.path, None, 5)
        name = "caddy-access-2026-09-20T04-05-56.762-size.json.gz"
        self.rotate_compressed(name)
        self.path.write_bytes(b"new\n")
        _, cursor = capture_log(self.path, cursor, 5)
        rotated = self.path.with_name(name)
        old_inode = rotated.stat().st_ino
        rotated.unlink()
        self.path.write_bytes(b"old1\nold2\nreplacement\n")
        original_stat = Path.stat

        def reused_inode(path, *args, **kwargs):
            result = list(original_stat(path, *args, **kwargs))
            if path == self.path:
                result[1] = old_inode
            return os.stat_result(result)

        with patch.object(Path, "stat", reused_inode):
            with self.assertRaisesRegex(ValueError, "continuity missing"):
                capture_log(self.path, cursor, 100)


if __name__ == "__main__":
    unittest.main()
