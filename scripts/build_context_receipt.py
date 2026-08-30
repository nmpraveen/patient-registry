#!/usr/bin/env python3
"""Create and verify the versioned receipt for MEDTRACK's committed build context."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys


RECEIPT_SCHEMA = "medtrack.build-context/v1"
REVISION_LABEL = "org.opencontainers.image.revision"
CONTEXT_LABEL = "org.medtrack.build-context.digest"
CONTEXT_SCHEMA_LABEL = "org.medtrack.build-context.schema"
TOP_LEVEL_INPUTS = {
    ".dockerignore",
    "CHANGELOG.md",
    "Dockerfile",
    "VERSION",
    "manage.py",
    "requirements.txt",
}
RUNTIME_ROOTS = ("api/", "patient_registry/", "patients/", "templates/")
FORBIDDEN_COMPONENTS = {
    ".git",
    ".mypy_cache",
    ".playwright-mcp",
    ".pytest_cache",
    "__pycache__",
    "backup",
    "backups",
    "media",
    "node_modules",
    "output",
    "outputs",
    "tests",
}
FORBIDDEN_SUFFIXES = (
    ".age",
    ".agekey",
    ".dump",
    ".jks",
    ".key",
    ".keystore",
    ".local",
    ".p12",
    ".pem",
    ".pfx",
    ".pgdump",
    ".pyc",
    ".pyo",
    ".sql",
    ".sqlite3",
    ".tar",
    ".tar.gz",
    ".vps.bak",
    ".zip",
)


def is_forbidden(path: str) -> bool:
    pure_path = PurePosixPath(path)
    components = tuple(part.lower() for part in pure_path.parts)
    basename = components[-1]
    if any(component in FORBIDDEN_COMPONENTS for component in components):
        return True
    if basename == ".env" or basename.startswith(".env."):
        return True
    if basename in {
        "backup.env",
        "docker-compose.override.yml",
        "google-services.json",
        "local_credentials.md",
        "patient_data.json",
        "tests.py",
    }:
        return True
    if basename.startswith("rclone") and basename.endswith(".conf"):
        return True
    if basename.endswith(".json") and any(
        marker in basename
        for marker in ("credential", "firebase-adminsdk", "firebase-service-account", "service-account")
    ):
        return True
    if basename.startswith("docker-compose.") and "override" in basename:
        return True
    return basename.endswith(FORBIDDEN_SUFFIXES)


def is_allowlisted(path: str) -> bool:
    return (path in TOP_LEVEL_INPUTS or path.startswith(RUNTIME_ROOTS)) and not is_forbidden(path)


def git(repo_root: Path, *arguments: str, text: bool = False) -> bytes | str:
    return subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=text,
    ).stdout


def create_receipt(repo_root: Path, revision_name: str) -> dict[str, object]:
    revision = str(git(repo_root, "rev-parse", revision_name, text=True)).strip()
    if len(revision) != 40:
        raise RuntimeError(f"expected a full Git revision, got {revision!r}")
    tree = bytes(git(repo_root, "ls-tree", "-r", "-z", "--full-tree", revision))
    entries: list[tuple[str, str, str]] = []
    for record in tree.split(b"\0"):
        if not record:
            continue
        metadata, encoded_path = record.split(b"\t", 1)
        mode, object_type, object_id = metadata.decode("ascii").split()
        path = encoded_path.decode("utf-8")
        if is_allowlisted(path):
            if object_type != "blob":
                raise RuntimeError(f"unsupported Git object in build context: {path} ({object_type})")
            entries.append((path, mode, object_id))

    included_paths = {path for path, _, _ in entries}
    missing = sorted(TOP_LEVEL_INPUTS - included_paths)
    missing_roots = sorted(
        root for root in RUNTIME_ROOTS if not any(path.startswith(root) for path in included_paths)
    )
    if missing or missing_roots:
        raise RuntimeError(
            "committed build context is incomplete: "
            f"missing_files={missing} missing_roots={missing_roots}"
        )

    digest = hashlib.sha256()
    digest.update(RECEIPT_SCHEMA.encode("ascii") + b"\0")
    for path, mode, object_id in sorted(entries):
        content = bytes(git(repo_root, "cat-file", "blob", object_id))
        encoded_path = path.encode("utf-8")
        digest.update(mode.encode("ascii") + b"\0")
        digest.update(str(len(encoded_path)).encode("ascii") + b"\0" + encoded_path + b"\0")
        digest.update(str(len(content)).encode("ascii") + b"\0" + content + b"\0")

    return {
        "schema": RECEIPT_SCHEMA,
        "source": "https://github.com/nmpraveen/patient-registry",
        "revision": revision,
        "build_context_sha256": f"sha256:{digest.hexdigest()}",
        "file_count": len(entries),
    }


def inspect_labels(image: str) -> dict[str, str]:
    inspection = json.loads(
        subprocess.run(
            ["docker", "image", "inspect", image],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )[0]
    return inspection.get("Config", {}).get("Labels") or {}


def verify_image(image: str, receipt: dict[str, object]) -> None:
    labels = inspect_labels(image)
    expected = {
        REVISION_LABEL: receipt["revision"],
        CONTEXT_LABEL: receipt["build_context_sha256"],
        CONTEXT_SCHEMA_LABEL: receipt["schema"],
    }
    mismatches = [
        f"{name}: expected {value!r}, got {labels.get(name)!r}"
        for name, value in expected.items()
        if labels.get(name) != value
    ]
    if mismatches:
        raise RuntimeError("image receipt mismatch: " + "; ".join(mismatches))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--format", choices=("json", "digest"), default="json")
    parser.add_argument("--output")
    parser.add_argument("--verify-image")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    try:
        receipt = create_receipt(repo_root, args.revision)
        encoded = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(encoded, encoding="utf-8", newline="\n")
        if args.verify_image:
            verify_image(args.verify_image, receipt)
            print(
                "BUILD_CONTEXT_IMAGE_VERIFIED "
                f"image={args.verify_image} revision={receipt['revision']} "
                f"build_context_sha256={receipt['build_context_sha256']} "
                f"schema={receipt['schema']} files={receipt['file_count']}"
            )
        elif args.format == "digest":
            print(receipt["build_context_sha256"])
        else:
            sys.stdout.write(encoded)
    except (RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"BUILD_CONTEXT_RECEIPT_FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
