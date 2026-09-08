#!/usr/bin/env python3
"""Fail closed when sensitive paths or secret signatures occur in image layers."""

from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import PurePosixPath
import re
import subprocess
import tarfile
import tempfile


FORBIDDEN_PATH = re.compile(
    r"(^|/)(\.env($|\.)|LOCAL_CREDENTIALS\.md$|google-services\.json$|"
    r"[^/]*(firebase-adminsdk|firebase-service-account|service-account|credential)[^/]*\.json$|"
    r"backups?($|/)|backup\.env$|[^/]+\.age(key)?$|rclone\.conf$|"
    r"outputs?($|/)|node_modules($|/)|docker-compose\.override\.yml$|"
    r"[^/]+\.(sql|dump|pgdump|zip)$|patient_data\.json$)",
    re.IGNORECASE,
)
SECRET_SIGNATURES = (
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----",
    b"-----BEGIN EC PRIVATE KEY-----",
    b"-----BEGIN OPENSSH PRIVATE KEY-----",
    # Split cloud-credential markers so source scanners do not mistake this
    # detector for a credential; Python joins adjacent byte literals at load.
    b'"type": "service_' b'account"',
    b'"private_' b'key_id":',
)
RUNTIME_ROOT_ALLOWLIST = {
    "CHANGELOG.md",
    "VERSION",
    "api",
    "backups",
    "manage.py",
    "patient_registry",
    "patients",
    "staff_directory",
    "staff_announcements",
    "staff_reminders",
    "requirements.txt",
    "staticfiles",
    "templates",
}


def normalize(name: str) -> str:
    return str(PurePosixPath(name.lstrip("./")))


def forbidden_path(path: str, *, is_directory: bool) -> bool:
    # The exact empty runtime mountpoint is safe. Any file or child below it is
    # still forbidden by the same backup/PHI path expression.
    if is_directory and path == "app/backups":
        return False
    return FORBIDDEN_PATH.search(path) is not None


def scan_tar_stream(
    fileobj: BytesIO,
    *,
    canary: bytes | None,
    findings: list[str],
    source: str,
) -> None:
    with tarfile.open(fileobj=fileobj, mode="r:*") as layer:
        for member in layer:
            path = normalize(member.name)
            application_path = path.startswith(("app/", "context/"))
            if application_path and forbidden_path(path, is_directory=member.isdir()):
                findings.append(f"forbidden path in {source}: {path}")
            if not member.isfile():
                continue
            extracted = layer.extractfile(member)
            if extracted is None:
                continue
            content = extracted.read()
            if application_path and canary and canary in content:
                findings.append(f"canary content in {source}: {path}")
            if application_path:
                for signature in SECRET_SIGNATURES:
                    if signature in content:
                        findings.append(
                            f"secret signature {signature.decode('ascii')} in {source}: {path}"
                        )


def scan_layers(image: str, canary: bytes | None) -> list[str]:
    findings: list[str] = []
    with tempfile.TemporaryDirectory(prefix="medtrack-image-scan-") as temp_dir:
        archive = f"{temp_dir}/image.tar"
        subprocess.run(["docker", "image", "save", "--output", archive, image], check=True)
        with tarfile.open(archive, mode="r:") as outer:
            manifest_file = outer.extractfile("manifest.json")
            if manifest_file is None:
                return ["docker image archive is missing manifest.json"]
            manifests = json.load(manifest_file)
            if len(manifests) != 1:
                return [f"expected one image manifest, found {len(manifests)}"]
            for layer_path in manifests[0].get("Layers", []):
                layer_file = outer.extractfile(layer_path)
                if layer_file is None:
                    findings.append(f"missing image layer: {layer_path}")
                    continue
                scan_tar_stream(
                    BytesIO(layer_file.read()),
                    canary=canary,
                    findings=findings,
                    source=layer_path,
                )
    return findings


def scan_final_filesystem(image: str, mode: str, canary: bytes | None) -> list[str]:
    findings: list[str] = []
    container = subprocess.run(
        ["docker", "create", image], check=True, capture_output=True, text=True
    ).stdout.strip()
    try:
        with tempfile.TemporaryDirectory(prefix="medtrack-container-scan-") as temp_dir:
            archive = f"{temp_dir}/filesystem.tar"
            subprocess.run(["docker", "export", "--output", archive, container], check=True)
            with tarfile.open(archive, mode="r:") as filesystem:
                app_roots: set[str] = set()
                for member in filesystem:
                    path = normalize(member.name)
                    application_path = path.startswith(("app/", "context/"))
                    if application_path and forbidden_path(path, is_directory=member.isdir()):
                        findings.append(f"forbidden final path: {path}")
                    if mode == "runtime" and path.startswith("app/"):
                        parts = PurePosixPath(path).parts
                        if len(parts) >= 2:
                            app_roots.add(parts[1])
                    if application_path and canary and member.isfile():
                        extracted = filesystem.extractfile(member)
                        if extracted is not None and canary in extracted.read():
                            findings.append(f"canary content in final filesystem: {path}")
                if mode == "runtime":
                    unexpected = sorted(app_roots - RUNTIME_ROOT_ALLOWLIST)
                    missing = sorted(RUNTIME_ROOT_ALLOWLIST - app_roots)
                    if unexpected:
                        findings.append(f"unexpected /app roots: {', '.join(unexpected)}")
                    if missing:
                        findings.append(f"missing /app roots: {', '.join(missing)}")
    finally:
        subprocess.run(
            ["docker", "rm", "--force", container],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("--mode", choices=("runtime", "context"), default="runtime")
    parser.add_argument("--canary")
    args = parser.parse_args()
    canary = args.canary.encode("utf-8") if args.canary else None
    findings = scan_layers(args.image, canary)
    findings.extend(scan_final_filesystem(args.image, args.mode, canary))
    if findings:
        for finding in sorted(set(findings)):
            print(f"IMAGE_SCAN_FAIL {finding}")
        return 1
    print(f"IMAGE_SCAN_OK image={args.image} mode={args.mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
