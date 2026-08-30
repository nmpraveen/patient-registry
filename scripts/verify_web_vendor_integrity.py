#!/usr/bin/env python3
"""Write or verify the pinned web-vendor byte manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
VENDOR_ROOT = BASE_DIR / "patients" / "static" / "patients" / "vendor"
MANIFEST_PATH = BASE_DIR / "WEB_VENDOR_INTEGRITY.json"
MANIFEST_VENDOR_ROOT = "patients/static/patients/vendor"

PACKAGES = [
    {
        "name": "bootstrap",
        "version": "5.3.3",
        "source": "https://registry.npmjs.org/bootstrap/-/bootstrap-5.3.3.tgz",
        "archive_integrity": "sha512-8HLCdWgyoMguSO9o+aH+iuZ+aht+mzW0u3HIMzVu7Srrpv7EBBxTnrFlSCskwdY1+EOFQSm7uMJhNQHkdPcmjg==",
        "license": "MIT",
        "license_file": "bootstrap/5.3.3/LICENSE",
    },
    {
        "name": "@freshworks/crayons",
        "version": "4.1.0",
        "source": "https://registry.npmjs.org/@freshworks/crayons/-/crayons-4.1.0.tgz",
        "archive_integrity": "sha512-xcTYf4xHnVZtabNviAg2+IIzJRmf/lkOxxzXBb/iYEErooIxV530YjnQ/A9Ukor1Q1Nc0wnFuAeKb5Gb0BQ8Jg==",
        "license": "MIT",
        "license_file": "crayons/4.1.0/LICENSE.md",
    },
    {
        "name": "@freshworks/crayons-icon",
        "version": "4.2.0-beta.0",
        "source": "https://registry.npmjs.org/@freshworks/crayons-icon/-/crayons-icon-4.2.0-beta.0.tgz",
        "archive_integrity": "sha512-adxpT1rGfPovAt0Zk8iUR0vdKi4Jk0Y6uK/FWhH1LlFtpSgoSjmqOImzKzoYGAhkR4mtXFOEedxHovz5g6OvsA==",
        "license": "MIT",
        "license_file": "crayons-icons/4.2.0-beta.0/LICENSE.md",
    },
    {
        "name": "htmx.org",
        "version": "1.9.12",
        "source": "https://registry.npmjs.org/htmx.org/-/htmx.org-1.9.12.tgz",
        "archive_integrity": "sha512-VZAohXyF7xPGS52IM8d1T1283y+X4D+Owf3qY1NZ9RuBypyu9l8cGsxUMAG5fEAb/DhT7rDoJ9Hpu5/HxFD3cw==",
        "license": "BSD-2-Clause",
        "license_file": "htmx/1.9.12/LICENSE",
    },
    {
        "name": "chart.js",
        "version": "4.4.4",
        "source": "https://registry.npmjs.org/chart.js/-/chart.js-4.4.4.tgz",
        "archive_integrity": "sha512-emICKGBABnxhMjUjlYRR12PmOXhJ2eJjEHL2/dZlWjxRAZT1D8xplLFq5M0tMQK8ja+wBS/tuVEJB5C6r7VxJA==",
        "license": "MIT",
        "license_file": "chartjs/4.4.4/LICENSE.md",
    },
    {
        "name": "@fontsource/inter",
        "version": "5.2.8",
        "source": "https://registry.npmjs.org/@fontsource/inter/-/inter-5.2.8.tgz",
        "archive_integrity": "sha512-P6r5WnJoKiNVV+zvW2xM13gNdFhAEpQ9dQJHt3naLvfg+LkF2ldgSLiF4T41lf1SQCM9QmkqPTn4TH568IRagg==",
        "license": "OFL-1.1",
        "license_file": "inter/5.2.8/LICENSE",
    },
]

INTENTIONAL_CRAYONS_CHANGES = [
    {
        "file": "crayons/4.1.0/dist/crayons/p-2e817ac9.js",
        "change": "ES module icon resolver points to the pinned local crayons-icon directory.",
    },
    {
        "file": "crayons/4.1.0/dist/crayons/p-92bb9b78.system.js",
        "change": "SystemJS icon resolver points to the pinned local crayons-icon directory.",
    },
    {
        "file": "crayons/4.1.0/dist/crayons/crayons-csp-loader.js",
        "change": "MEDTRACK-authored adapter supplies native import() before upstream eval/blob fallbacks.",
    },
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_files() -> dict[str, str]:
    return {
        path.relative_to(VENDOR_ROOT).as_posix(): sha256_file(path)
        for path in sorted(VENDOR_ROOT.rglob("*"))
        if path.is_file()
    }


def write_manifest() -> None:
    payload = {
        "schema_version": 1,
        "hash_algorithm": "sha256",
        "vendor_root": MANIFEST_VENDOR_ROOT,
        "packages": PACKAGES,
        "intentional_crayons_changes": INTENTIONAL_CRAYONS_CHANGES,
        "files": current_files(),
    }
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_manifest() -> list[str]:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected = payload.get("files", {})
    actual = current_files()
    errors = []
    if payload.get("schema_version") != 1:
        errors.append("unsupported schema_version")
    if payload.get("hash_algorithm") != "sha256":
        errors.append("hash_algorithm must be sha256")
    if payload.get("vendor_root") != MANIFEST_VENDOR_ROOT:
        errors.append("vendor_root does not match the reviewed location")
    if payload.get("packages") != PACKAGES:
        errors.append("package provenance metadata differs from the reviewed pins")
    if payload.get("intentional_crayons_changes") != INTENTIONAL_CRAYONS_CHANGES:
        errors.append("intentional Crayons change metadata differs from the reviewed list")
    if not isinstance(expected, dict):
        return errors + ["files must be an object of relative paths to SHA-256 hashes"]
    for path, digest in expected.items():
        if not isinstance(path, str) or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            errors.append(f"invalid SHA-256 entry: {path!r}")
    for package in PACKAGES:
        if package["license_file"] not in expected:
            errors.append(f"license is not covered by the manifest: {package['name']}")
    for change in INTENTIONAL_CRAYONS_CHANGES:
        if change["file"] not in expected:
            errors.append(f"intentional change is not covered by the manifest: {change['file']}")
    for path in sorted(set(expected) - set(actual)):
        errors.append(f"missing: {path}")
    for path in sorted(set(actual) - set(expected)):
        errors.append(f"unmanifested: {path}")
    for path in sorted(set(expected) & set(actual)):
        if expected[path] != actual[path]:
            errors.append(f"hash mismatch: {path}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Regenerate the reviewed manifest.")
    args = parser.parse_args()
    if args.write:
        write_manifest()
        print(f"Wrote {MANIFEST_PATH}")
        return 0
    errors = verify_manifest()
    if errors:
        print("Web vendor integrity verification failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Verified {len(current_files())} vendored web files against {MANIFEST_PATH.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
