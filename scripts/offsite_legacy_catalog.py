#!/usr/bin/env python3
"""Pinned retained-byte exceptions; never restore authorization or provenance."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

POLICY = "medtrack-retained-integrity-v1"
CATALOG_FORMAT = "medtrack-retained-legacy-v1"
BASE_FIELDS = {"archive", "sha256", "completed_utc"}
V2_FIELDS = BASE_FIELDS | {"source_commit", "intended_target_commit"}
V3_FIELDS = V2_FIELDS | {"security_evidence_chain_sha256"}
MODERN_FIELDS = V3_FIELDS | {"drive_verified", "drive_verified_epoch"}
LEGACY_FIELDS = {"offsite-v1": BASE_FIELDS, "offsite-v2": V2_FIELDS, "offsite-v3": V3_FIELDS}
TIERS = {"rapid", "daily", "weekly", "monthly"}
ENTRY_FIELDS = {"tier", "archive", "format", "ciphertext_size", "ciphertext_sha256",
                "checksum_file_sha256", "marker_file_sha256"}
MAX_CATALOG_BYTES = 2 * 1024 * 1024


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def is_hash(value, length=64):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{%d}" % length, value) is not None


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate key")
        result[key] = value
    return result


def archive_stamp(tier, archive):
    require(tier in TIERS and isinstance(archive, str), "invalid tier/name")
    match = re.fullmatch(r"medtrack-prod-" + tier + r"-([0-9]{8}T[0-9]{6}Z)\.tar\.age", archive)
    require(match is not None, "invalid archive name")
    stamp = match[1]
    parsed = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    require(parsed.strftime("%Y%m%dT%H%M%SZ") == stamp, "invalid timestamp")
    return stamp


def validate_catalog(raw, expected_digest, namespace):
    require(is_hash(expected_digest) and sha256(raw) == expected_digest, "catalog digest mismatch")
    require(len(raw) <= MAX_CATALOG_BYTES, "catalog too large")
    catalog = json.loads(raw, object_pairs_hook=unique_pairs)
    require(isinstance(catalog, dict) and set(catalog) == {
        "catalog_format", "policy_version", "namespace", "entries"}, "invalid catalog fields")
    require(catalog["catalog_format"] == CATALOG_FORMAT and catalog["policy_version"] == POLICY,
            "unsupported catalog policy")
    require(isinstance(namespace, str) and re.fullmatch(r"[A-Za-z0-9_-]+:[A-Za-z0-9._/-]+", namespace)
            and all(part not in {"", ".", ".."} for part in namespace.split(":", 1)[1].split("/")),
            "invalid namespace")
    require(catalog["namespace"] == namespace, "catalog namespace mismatch")
    require(isinstance(catalog["entries"], list) and len(catalog["entries"]) <= 4096, "invalid entry list")
    entries = {}
    for entry in catalog["entries"]:
        require(isinstance(entry, dict) and set(entry) == ENTRY_FIELDS, "invalid entry fields")
        archive_stamp(entry["tier"], entry["archive"])
        require(entry["format"] in LEGACY_FIELDS, "unsupported legacy shape")
        require(type(entry["ciphertext_size"]) is int and entry["ciphertext_size"] > 0, "invalid size")
        for field in ("ciphertext_sha256", "checksum_file_sha256", "marker_file_sha256"):
            require(is_hash(entry[field]), "invalid pinned hash")
        key = entry["tier"] + "/" + entry["archive"]
        require(key not in entries, "duplicate entry")
        entries[key] = entry
    return entries


def create_snapshot(catalog_path, expected_digest, namespace, output):
    require(bool(catalog_path) == bool(expected_digest), "catalog path and independent digest are both required")
    entries = {}
    digest = "none"
    if catalog_path:
        require(Path(catalog_path).is_absolute(), "catalog path must be absolute")
        with Path(catalog_path).open("rb") as stream:
            raw = stream.read(MAX_CATALOG_BYTES + 1)
        entries = validate_catalog(raw, expected_digest, namespace)
        digest = expected_digest
    # Validate the source once. Every consumer verifies this private snapshot's
    # captured digest, never reopens the replaceable source catalog.
    raw = json.dumps({"policy_version": POLICY, "catalog_sha256": digest,
                      "namespace": namespace, "entries": entries}, sort_keys=True).encode("utf-8")
    with Path(output).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(output, 0o400)
    return POLICY, digest, sha256(raw)


def read_snapshot(path, digest, namespace):
    raw = Path(path).read_bytes()
    require(is_hash(digest) and sha256(raw) == digest, "snapshot changed")
    snapshot = json.loads(raw)
    require(snapshot["policy_version"] == POLICY and snapshot["namespace"] == namespace,
            "snapshot policy/namespace mismatch")
    return snapshot


def marker_fields(raw):
    require(raw.endswith(b"\n") and all(byte == 10 or 32 <= byte <= 126 for byte in raw),
            "invalid marker encoding")
    pairs = []
    for line in raw.decode("ascii").splitlines():
        require("=" in line, "invalid marker line")
        key, value = line.split("=", 1)
        require(re.fullmatch(r"[a-z][a-z0-9_]*", key) is not None and value and value.strip() == value,
                "invalid marker field")
        pairs.append((key, value))
    return unique_pairs(pairs)


def check_metadata(snapshot, tier, archive, marker_raw, checksum_raw, latest):
    stamp = archive_stamp(tier, archive)
    fields = marker_fields(marker_raw)
    entry = snapshot["entries"].get(tier + "/" + archive)
    required_fields = LEGACY_FIELDS[entry["format"]] if entry else MODERN_FIELDS
    require(set(fields) == required_fields, "unlisted or wrong marker shape")
    require(fields["archive"] == archive and fields["completed_utc"] == stamp, "marker name/time mismatch")
    require(is_hash(fields["sha256"]), "invalid ciphertext hash")
    require(checksum_raw == (fields["sha256"] + "  " + archive + "\n").encode("ascii"),
            "invalid checksum file")
    for key in ("source_commit", "intended_target_commit"):
        if key in fields:
            require(is_hash(fields[key], 40), "invalid historical commit")
    if "security_evidence_chain_sha256" in fields:
        require(is_hash(fields["security_evidence_chain_sha256"]), "invalid evidence chain hash")
    if "drive_verified" in fields:
        require(fields["drive_verified"] == "1" and re.fullmatch(r"[1-9][0-9]{0,10}", fields["drive_verified_epoch"]),
                "invalid Drive verification")
        completed_epoch = int(datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp())
        require(completed_epoch <= int(fields["drive_verified_epoch"]) <= int(datetime.now(timezone.utc).timestamp()),
                "invalid Drive verification time")
    size = None
    if entry:
        require(not latest, "newest backup must be modern")
        require(fields["sha256"] == entry["ciphertext_sha256"]
                and sha256(marker_raw) == entry["marker_file_sha256"]
                and sha256(checksum_raw) == entry["checksum_file_sha256"], "legacy triplet changed")
        size = entry["ciphertext_size"]
    return fields["sha256"], stamp, size


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("snapshot")
    init.add_argument("--catalog", default="")
    init.add_argument("--sha256", default="")
    init.add_argument("--namespace", required=True)
    init.add_argument("--output", required=True)
    for name in ("check", "verify-snapshot"):
        command = sub.add_parser(name)
        command.add_argument("--snapshot", required=True)
        command.add_argument("--snapshot-sha256", required=True)
        command.add_argument("--namespace", required=True)
        if name == "check":
            command.add_argument("--tier", required=True)
            command.add_argument("--archive", required=True)
            command.add_argument("--marker-file", type=Path, required=True)
            command.add_argument("--checksum-file", type=Path, required=True)
            command.add_argument("--latest", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "snapshot":
            print(*create_snapshot(args.catalog, args.sha256, args.namespace, args.output))
        else:
            snapshot = read_snapshot(args.snapshot, args.snapshot_sha256, args.namespace)
            if args.command == "check":
                digest, stamp, size = check_metadata(snapshot, args.tier, args.archive,
                    args.marker_file.read_bytes(), args.checksum_file.read_bytes(), args.latest)
                print(digest, stamp, size if size is not None else "-")
    except (ValueError, OSError, KeyError, TypeError, UnicodeError):
        print("OFFSITE_METADATA_INVALID", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
