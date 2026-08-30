#!/usr/bin/env python3
"""Build an exact Git revision from a safe context and prove canaries stay out."""

from __future__ import annotations

import argparse
from pathlib import Path
import secrets
import subprocess
import sys
import tarfile
import tempfile


CANARY_PATHS = (
    ".env",
    "LOCAL_CREDENTIALS.md",
    "firebase-service-account-canary.json",
    "backups/canary-patient-export.zip",
    "identity.agekey",
    "rclone.conf",
    "output/canary-phi.txt",
    "node_modules/canary.js",
    "docker-compose.override.yml",
    "patients/backups/nested-canary.zip",
    "patients/output/nested-canary-phi.txt",
    "patients/node_modules/nested-canary.js",
    "api/google-services.json",
)


def extract_git_archive(repo_root: Path, revision: str, destination: Path) -> None:
    archive = subprocess.run(
        ["git", "archive", "--format=tar", revision],
        cwd=repo_root,
        check=True,
        capture_output=True,
    ).stdout
    with tarfile.open(fileobj=__import__("io").BytesIO(archive), mode="r:") as source:
        for member in source.getmembers():
            target = (destination / member.name).resolve()
            if destination.resolve() not in target.parents and target != destination.resolve():
                raise RuntimeError(f"unsafe archive member: {member.name}")
        source.extractall(destination)


def run_scan(repo_root: Path, image: str, mode: str, canary: str) -> None:
    subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "scan_container_image.py"),
            image,
            "--mode",
            mode,
            "--canary",
            canary,
        ],
        cwd=repo_root,
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--image")
    parser.add_argument("--no-pull", action="store_true")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    revision = subprocess.run(
        ["git", "rev-parse", args.revision],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    image = args.image or f"medtrack-build-proof:{revision[:12]}"
    context_image = f"medtrack-context-proof:{revision[:12]}"
    canary = f"MEDTRACK_FAKE_SECRET_PHI_CANARY_{secrets.token_hex(16)}"

    try:
        with tempfile.TemporaryDirectory(prefix="medtrack-safe-context-") as temp_dir:
            temp_root = Path(temp_dir)
            context = temp_root / "context"
            context.mkdir()
            extract_git_archive(repo_root, revision, context)
            for relative in CANARY_PATHS:
                path = context / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"synthetic test data only\n{canary}\n", encoding="utf-8")

            audit_dockerfile = temp_root / "Dockerfile.context-audit"
            audit_dockerfile.write_text(
                'FROM scratch\nCOPY . /context\nCMD ["/non-running-audit-image"]\n',
                encoding="utf-8",
            )
            subprocess.run(
                [
                    "docker",
                    "build",
                    "--no-cache",
                    "--file",
                    str(audit_dockerfile),
                    "--tag",
                    context_image,
                    str(context),
                ],
                check=True,
            )
            run_scan(repo_root, context_image, "context", canary)

            build = ["docker", "build", "--no-cache"]
            if not args.no_pull:
                build.append("--pull")
            build.extend(
                [
                    "--build-arg",
                    f"VCS_REF={revision}",
                    "--tag",
                    image,
                    str(context),
                ]
            )
            subprocess.run(build, check=True)
            run_scan(repo_root, image, "runtime", canary)
    finally:
        subprocess.run(
            ["docker", "image", "rm", "--force", context_image],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    print(
        f"SAFE_CONTEXT_BUILD_OK revision={revision} image={image} "
        f"canaries={len(CANARY_PATHS)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
