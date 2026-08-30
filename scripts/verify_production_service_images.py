#!/usr/bin/env python3
"""Build/copy, scan, SBOM, and receipt every non-web production image."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from build_canonical_image import (
    SKOPEO_IMAGE,
    inspect_oci_archive,
    load_oci_archive,
    sha256_file,
)
from verify_container_build import extract_git_archive


TRIVY_IMAGE = "aquasec/trivy:0.74.0@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969"
SYFT_IMAGE = "anchore/syft:v1.51.1@sha256:95fe0835e5bebc6f8b1f8acef68d47d63d594ef4c0f25c097ff853b23cbac74c"
DIGEST_PIN = re.compile(r"^\S+@sha256:[0-9a-f]{64}$")


def compose_image(path: Path, service: str) -> str:
    current_service: str | None = None
    in_services = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if line == "services:":
            in_services = True
            continue
        if not in_services or not line:
            continue
        if not line.startswith(" "):
            break
        service_match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if service_match:
            current_service = service_match.group(1)
            continue
        image_match = re.match(r"^    image:\s*([^\s]+)\s*$", line)
        if current_service == service and image_match:
            reference = image_match.group(1).strip("'\"")
            if not DIGEST_PIN.fullmatch(reference):
                raise RuntimeError(f"production {service} image is not digest-pinned: {reference}")
            return reference
    raise RuntimeError(f"production Compose has no image reference for service {service}")


def copy_registry_image(reference: str, artifact: Path) -> None:
    artifact.unlink(missing_ok=True)
    subprocess.run(
        [
            "docker", "run", "--rm",
            "--volume", f"{artifact.parent.resolve()}:/output",
            SKOPEO_IMAGE,
            "copy", "--override-os", "linux", "--override-arch", "amd64",
            f"docker://{reference}", f"oci-archive:/output/{artifact.name}",
        ],
        check=True,
    )


def scan_and_sbom(
    repo_root: Path,
    service: str,
    artifact: Path,
    manifest_digest: str,
    policy: Path,
    cache: Path,
) -> dict[str, str]:
    report = artifact.parent / f"{service}-trivy.json"
    sbom = artifact.parent / f"{service}-sbom.cdx.json"
    output_mount = f"{artifact.parent.resolve()}:/output"
    cache_mount = f"{cache.resolve()}:/root/.cache/trivy"
    subprocess.run(
        [
            "docker", "run", "--rm", "--volume", output_mount,
            "--volume", cache_mount, TRIVY_IMAGE,
            "image", "--input", f"/output/{artifact.name}",
            "--scanners", "vuln,secret", "--severity", "HIGH,CRITICAL",
            "--ignore-unfixed=false", "--exit-code", "0",
            "--format", "json", "--output", f"/output/{report.name}",
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable, str(repo_root / "scripts" / "verify_container_vulnerabilities.py"),
            "--report", str(report), "--policy", str(policy),
            "--image-digest", manifest_digest,
        ],
        cwd=repo_root,
        check=True,
    )
    subprocess.run(
        [
            "docker", "run", "--rm", "--volume", output_mount, SYFT_IMAGE,
            "scan", f"oci-archive:/output/{artifact.name}",
            "--output", f"cyclonedx-json=/output/{sbom.name}",
        ],
        check=True,
    )
    return {
        "trivy_report": report.name,
        "trivy_report_sha256": sha256_file(report),
        "sbom": sbom.name,
        "sbom_sha256": sha256_file(sbom),
        "vex_policy": policy.relative_to(repo_root).as_posix(),
        "vex_policy_sha256": sha256_file(policy),
    }


def runtime_smoke(service: str, artifact: Path, revision: str) -> str:
    image = f"medtrack-{service}-proof:{revision[:12]}"
    load_oci_archive(artifact, image)
    if service == "postgres":
        command = [
            "docker", "run", "--rm", "--entrypoint", "sh", image, "-ceu",
            'test "$(id -u)" = 70; test "$(id -g)" = 70; '
            "! test -e /usr/local/bin/gosu; postgres --version",
        ]
    else:
        command = ["docker", "run", "--rm", "--entrypoint", "caddy", image, "version"]
    subprocess.run(command, check=True)
    return image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--builder", required=True)
    parser.add_argument("--output", default="output/production-images")
    parser.add_argument("--service", action="append", choices=("postgres", "caddy"))
    args = parser.parse_args()
    services = args.service or ["postgres", "caddy"]
    repo_root = Path(__file__).resolve().parent.parent
    revision = subprocess.run(
        ["git", "rev-parse", args.revision], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    output = (repo_root / args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []

    with tempfile.TemporaryDirectory(prefix="medtrack-service-context-") as context_dir, tempfile.TemporaryDirectory(prefix="medtrack-trivy-cache-") as cache_dir:
        context = Path(context_dir)
        extract_git_archive(repo_root, revision, context)
        cache = Path(cache_dir)
        for service in services:
            artifact = output / f"{service}-image.oci.tar"
            build_metadata_path: Path | None = None
            if service == "postgres":
                artifact.unlink(missing_ok=True)
                build_metadata_path = output / "postgres-buildkit-metadata.json"
                subprocess.run(
                    [
                        "docker", "buildx", "build", "--builder", args.builder,
                        "--platform", "linux/amd64", "--provenance=false", "--sbom=false",
                        "--pull", "--file", str(context / "Dockerfile.postgres"),
                        "--tag", "medtrack-postgres:16.14-hardened",
                        "--metadata-file", str(build_metadata_path),
                        "--output", f"type=oci,dest={artifact},tar=true,oci-mediatypes=true",
                        str(context),
                    ],
                    check=True,
                )
                source = "git+https://github.com/nmpraveen/patient-registry#Dockerfile.postgres"
                policy = repo_root / "security" / "postgres-vex.json"
            else:
                reference = compose_image(repo_root / "docker-compose.prod.yml", "caddy")
                copy_registry_image(reference, artifact)
                source = reference
                policy = repo_root / "security" / "caddy-vex.json"
            identity = inspect_oci_archive(artifact)
            if build_metadata_path is not None:
                build_metadata = json.loads(build_metadata_path.read_text(encoding="utf-8"))
                if build_metadata.get("containerimage.digest") != identity["manifest_digest"]:
                    raise RuntimeError("PostgreSQL BuildKit digest does not match its OCI archive")
            loaded_image = runtime_smoke(service, artifact, revision)
            evidence = scan_and_sbom(
                repo_root, service, artifact, identity["manifest_digest"], policy, cache
            )
            record = {
                "service": service,
                "source": source,
                "revision": revision,
                "loaded_image": loaded_image,
                "artifact": artifact.name,
                "artifact_sha256": sha256_file(artifact),
                **identity,
                **evidence,
            }
            (output / f"{service}-image-receipt.json").write_text(
                json.dumps({"schema": "medtrack.production-service-image/v1", **record}, indent=2) + "\n",
                encoding="utf-8",
            )
            records.append(record)

    receipt = {
        "schema": "medtrack.production-image-set/v1",
        "revision": revision,
        "platform": "linux/amd64",
        "services": records,
    }
    receipt_path = output / "production-service-images.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(
        "PRODUCTION_SERVICE_IMAGES_OK "
        f"revision={revision} services={','.join(services)} receipt={receipt_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"PRODUCTION_SERVICE_IMAGES_FAIL {exc}", file=sys.stderr)
        raise
