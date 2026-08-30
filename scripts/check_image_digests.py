#!/usr/bin/env python3
"""Validate or intentionally refresh the digest pins for production images."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


IMAGE_REFS = (
    ("Dockerfile", "python:3.12.13-alpine3.23"),
    ("Dockerfile.postgres", "postgres:16.14-alpine3.24"),
    ("deploy/Dockerfile.caddy", "caddy:2.11.4-builder-alpine"),
    ("deploy/Dockerfile.caddy", "alpine:3.24"),
    ("scripts/build_canonical_image.py", "quay.io/skopeo/stable:v1.21.0"),
    ("scripts/update-python-locks.py", "python:3.12.13-alpine3.23"),
    ("scripts/update-python-locks.py", "python:3.12.13-slim-bookworm"),
    ("scripts/verify_canonical_artifact.sh", "aquasec/trivy:0.74.0"),
    ("scripts/verify_canonical_artifact.sh", "anchore/syft:v1.51.1"),
    ("scripts/verify_production_service_images.py", "aquasec/trivy:0.74.0"),
    ("scripts/verify_production_service_images.py", "anchore/syft:v1.51.1"),
)
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


def remote_digest(tag: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            tag,
            "--format",
            "{{json .Manifest}}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    manifest = json.loads(result.stdout)
    digest = manifest.get("digest", "")
    if not DIGEST_PATTERN.fullmatch(digest):
        raise RuntimeError(f"Registry returned an invalid digest for {tag}: {digest!r}")
    return digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--remote",
        action="store_true",
        help="verify each immutable pin against the current digest behind its reviewed tag",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="replace moved digests after reviewing the upstream tag (implies --remote)",
    )
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    failures: list[str] = []

    for relative_path, tag in IMAGE_REFS:
        path = repo_root / relative_path
        text = path.read_text(encoding="utf-8")
        match = re.search(re.escape(tag) + r"@(sha256:[0-9a-f]{64})", text)
        if not match:
            failures.append(f"{relative_path}: missing digest pin for {tag}")
            continue
        pinned = match.group(1)
        current = remote_digest(tag) if args.remote or args.update else pinned
        if args.update and current != pinned:
            path.write_text(
                text[: match.start(1)] + current + text[match.end(1) :],
                encoding="utf-8",
                newline="\n",
            )
            print(f"UPDATED {relative_path} {tag}@{current}")
        elif current != pinned:
            failures.append(
                f"{relative_path}: {tag} moved from {pinned} to {current}; "
                "review upstream and run with --update"
            )
        else:
            print(f"IMAGE_DIGEST_OK {relative_path} {tag}@{pinned}")

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
