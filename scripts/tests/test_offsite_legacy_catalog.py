"""Only synthetic triplets; historical exceptions cannot downgrade current markers."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts import offsite_legacy_catalog as catalog

NAMESPACE = "synthetic:backup/production"


def triplet(tier="weekly", stamp="20200101T000000Z", shape="offsite-v1"):
    archive = f"medtrack-prod-{tier}-{stamp}.tar.age"
    ciphertext = b"synthetic encrypted bytes only\n"
    digest = hashlib.sha256(ciphertext).hexdigest()
    fields = {"archive": archive, "sha256": digest, "completed_utc": stamp}
    if shape != "offsite-v1":
        fields.update(source_commit="a" * 40, intended_target_commit="b" * 40)
    if shape in {"offsite-v3", "current"}:
        fields["security_evidence_chain_sha256"] = "c" * 64
    if shape == "current":
        fields.update(drive_verified="1", drive_verified_epoch=str(int(
            datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp())))
    marker = "".join(f"{key}={value}\n" for key, value in fields.items()).encode()
    checksum = f"{digest}  {archive}\n".encode()
    entry = {"tier": tier, "archive": archive, "format": shape, "ciphertext_size": len(ciphertext),
             "ciphertext_sha256": digest, "checksum_file_sha256": catalog.sha256(checksum),
             "marker_file_sha256": catalog.sha256(marker)}
    return entry, marker, checksum


def document(entries):
    return {"catalog_format": catalog.CATALOG_FORMAT, "policy_version": catalog.POLICY,
            "namespace": NAMESPACE, "entries": entries}


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.entry, self.marker, self.checksum = triplet()

    def validate(self, doc, namespace=NAMESPACE):
        raw = json.dumps(doc).encode()
        return catalog.validate_catalog(raw, catalog.sha256(raw), namespace)

    def snapshot(self, entry=None):
        return {"entries": self.validate(document([entry or self.entry]))}

    def check(self, snapshot=None, marker=None, checksum=None, tier="weekly", archive=None, latest=False):
        return catalog.check_metadata(snapshot or self.snapshot(), tier, archive or self.entry["archive"],
                                      self.marker if marker is None else marker,
                                      self.checksum if checksum is None else checksum, latest)

    def test_exact_historical_shapes_preserve_bytes_and_never_qualify_as_newest(self):
        for shape in catalog.LEGACY_FIELDS:
            with self.subTest(shape=shape):
                entry, marker, checksum = triplet(shape=shape)
                snapshot = self.snapshot(entry)
                self.assertEqual(self.check(snapshot, marker, checksum),
                                 (entry["ciphertext_sha256"], "20200101T000000Z", entry["ciphertext_size"]))
                with self.assertRaisesRegex(ValueError, "newest"):
                    self.check(snapshot, marker, checksum, latest=True)

    def test_current_eight_field_marker_needs_no_catalog_but_all_fields_are_required(self):
        entry, marker, checksum = triplet(shape="current")
        self.assertEqual(self.check({"entries": {}}, marker, checksum, latest=True)[2], None)
        for line in marker.splitlines(keepends=True):
            with self.subTest(stripped=line.split(b"=")[0]), self.assertRaises(ValueError):
                self.check({"entries": {}}, marker.replace(line, b""), checksum)
        # Dropping both Drive fields must not silently become historical v3.
        stripped = b"".join(line for line in marker.splitlines(keepends=True) if not line.startswith(b"drive_"))
        with self.assertRaises(ValueError):
            self.check({"entries": {}}, stripped, checksum)
        with self.assertRaisesRegex(ValueError, "encoding"):
            self.check({"entries": {}}, marker.replace(b"\n", b"\v", 1), checksum)

    def test_catalog_is_exact_versioned_finite_and_namespace_bound(self):
        for field, value in (("catalog_format", "next"), ("policy_version", "next"),
                             ("namespace", "synthetic:elsewhere"), ("entries", {})):
            doc = document([self.entry]); doc[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.validate(doc)
        for extra in ({"unexpected": 1},):
            with self.assertRaises(ValueError):
                self.validate(document([self.entry]) | extra)
        with self.assertRaises(ValueError):
            self.validate(document([self.entry] * 4097))
        for namespace in ("synthetic:../x", "synthetic:a//b", "synthetic:a/./b"):
            with self.subTest(namespace=namespace), self.assertRaises(ValueError):
                self.validate(document([self.entry]) | {"namespace": namespace}, namespace)

    def test_catalog_rejects_duplicate_entries_and_duplicate_keys_at_every_level(self):
        with self.assertRaisesRegex(ValueError, "duplicate entry"):
            self.validate(document([self.entry, self.entry]))
        raw = json.dumps(document([self.entry])).encode()
        for key in (b'"namespace"', b'"tier"', b'"ciphertext_size"'):
            modified = raw.replace(key + b":", key + b': null, ' + key + b":", 1)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "duplicate key"):
                catalog.validate_catalog(modified, catalog.sha256(modified), NAMESPACE)

    def test_catalog_rejects_invalid_shapes_sizes_hashes_names_and_times(self):
        mutations = [("format", "unknown"), ("format", "current"), ("ciphertext_size", True),
                     ("ciphertext_size", 0), ("ciphertext_size", "1"), ("ciphertext_sha256", "A" * 64),
                     ("marker_file_sha256", "x"), ("checksum_file_sha256", "x"), ("tier", "canary"),
                     ("archive", "../" + self.entry["archive"]), ("tier", "daily"),
                     ("archive", "medtrack-prod-weekly-20200231T000000Z.tar.age")]
        for key, value in mutations:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.validate(document([self.entry | {key: value}]))
        for doc in (document([self.entry | {"extra": "x"}]), document([{"tier": "weekly"}])):
            with self.assertRaises(ValueError):
                self.validate(doc)

    def test_no_auto_enrollment_wrong_tier_name_backdate_or_coordinated_replacement(self):
        with self.assertRaises(ValueError):
            self.check({"entries": {}})
        for tier, stamp in (("monthly", "20200101T000000Z"), ("weekly", "19990101T000000Z")):
            entry, marker, checksum = triplet(tier=tier, stamp=stamp)
            with self.subTest(tier=tier, stamp=stamp), self.assertRaises(ValueError):
                self.check(marker=marker, checksum=checksum, tier=tier, archive=entry["archive"])
        digest = self.entry["ciphertext_sha256"].encode()
        with self.assertRaisesRegex(ValueError, "triplet changed"):
            self.check(marker=self.marker.replace(digest, b"d" * 64),
                       checksum=self.checksum.replace(digest, b"d" * 64))

    def test_changed_raw_bytes_duplicate_fields_and_checksum_variants_reject(self):
        for marker in (self.marker + b"\n", self.marker + b"sha256=" + b"d" * 64 + b"\n",
                       self.marker.replace(b"\n", b"\r\n"), self.marker.rstrip(b"\n"),
                       self.marker.replace(b"completed_utc=2020", b"completed_utc=2019"),
                       self.marker + b"unknown=x\n", b"\x00" + self.marker):
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                self.check(marker=marker)
        for checksum in (self.checksum + b"\n", self.checksum.replace(b"  ", b" "),
                         self.checksum + self.checksum, self.checksum.rstrip(b"\n")):
            with self.subTest(checksum=checksum), self.assertRaises(ValueError):
                self.check(checksum=checksum)
        # Same parsed fields in another order are still changed pinned bytes.
        with self.assertRaisesRegex(ValueError, "triplet changed"):
            self.check(marker=b"".join(reversed(self.marker.splitlines(keepends=True))))

    def test_historical_fields_are_validated_even_when_catalog_digest_pins_them(self):
        for shape, key in (("offsite-v2", "source_commit"), ("offsite-v2", "intended_target_commit"),
                           ("offsite-v3", "security_evidence_chain_sha256")):
            entry, marker, checksum = triplet(shape=shape)
            fields = catalog.marker_fields(marker); fields[key] = "invalid"
            marker = "".join(f"{k}={v}\n" for k, v in fields.items()).encode()
            entry["marker_file_sha256"] = catalog.sha256(marker)
            with self.subTest(shape=shape, key=key), self.assertRaises(ValueError):
                self.check(self.snapshot(entry), marker, checksum)

    def test_drive_fields_must_be_paired_successful_and_time_valid(self):
        _, marker, checksum = triplet(shape="current")
        for key, value in (("drive_verified", "0"), ("drive_verified_epoch", "0"),
                           ("drive_verified_epoch", "99999999999"), ("drive_verified_epoch", "1")):
            fields = catalog.marker_fields(marker); fields[key] = value
            changed = "".join(f"{k}={v}\n" for k, v in fields.items()).encode()
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.check({"entries": {}}, changed, checksum)

    def test_snapshot_ignores_replaced_source_and_rejects_snapshot_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / "source.json"; target = root / "snapshot.json"
            raw = json.dumps(document([self.entry])).encode(); source.write_bytes(raw)
            policy, digest, snapshot_digest = catalog.create_snapshot(source, catalog.sha256(raw), NAMESPACE, target)
            self.assertEqual((policy, digest), (catalog.POLICY, catalog.sha256(raw)))
            source.write_bytes(b"changed source")
            snapshot = catalog.read_snapshot(target, snapshot_digest, NAMESPACE)
            self.check(snapshot)
            target.chmod(0o600); target.write_bytes(target.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "snapshot changed"):
                catalog.read_snapshot(target, snapshot_digest, NAMESPACE)

    def test_digest_pairing_and_retired_entries(self):
        raw = json.dumps(document([self.entry])).encode()
        with self.assertRaisesRegex(ValueError, "digest"):
            catalog.validate_catalog(raw, "0" * 64, NAMESPACE)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "snapshot.json"
            for path, digest in (("", "a" * 64), ("file.json", "")):
                with self.assertRaises(ValueError):
                    catalog.create_snapshot(path, digest, NAMESPACE, target)
            # A retired catalog entry imposes no presence/count requirement.
            _, modern, checksum = triplet(tier="daily", shape="current")
            catalog.check_metadata(self.snapshot(), "daily", "medtrack-prod-daily-20200101T000000Z.tar.age",
                                   modern, checksum, True)
            _, digest, snapshot_digest = catalog.create_snapshot("", "", NAMESPACE, target)
            self.assertEqual(digest, "none")
            self.assertEqual(catalog.read_snapshot(target, snapshot_digest, NAMESPACE)["entries"], {})
            target.chmod(0o600)


if __name__ == "__main__":
    unittest.main()
