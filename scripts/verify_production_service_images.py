#!/usr/bin/env python3
"""Build/copy, scan, SBOM, and receipt every non-web production image."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

from build_canonical_image import (
    inspect_oci_archive,
    load_oci_archive,
    sha256_file,
)
from verify_container_build import extract_git_archive


TRIVY_IMAGE = "aquasec/trivy:0.74.0@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969"
SYFT_IMAGE = "anchore/syft:v1.51.1@sha256:95fe0835e5bebc6f8b1f8acef68d47d63d594ef4c0f25c097ff853b23cbac74c"
SERVICE_BUILDS = {
    "postgres": {
        "dockerfile": "Dockerfile.postgres",
        "tag": "medtrack-postgres:16.14-hardened",
        "policy": "security/postgres-vex.json",
    },
    "caddy": {
        "dockerfile": "deploy/Dockerfile.caddy",
        "tag": "medtrack-caddy:2.11.4-ratelimit",
        "policy": "security/caddy-vex.json",
    },
}


def build_service_image(
    context: Path,
    output: Path,
    builder: str,
    service: str,
    revision: str,
    artifact: Path,
) -> dict[str, str]:
    spec = SERVICE_BUILDS[service]
    dockerfile = str(spec["dockerfile"])
    metadata = output / f"{service}-buildkit-metadata.json"
    artifact.unlink(missing_ok=True)
    metadata.unlink(missing_ok=True)
    command = [
        "docker", "buildx", "build", "--builder", builder,
        "--platform", "linux/amd64", "--provenance=false", "--sbom=false",
        "--pull", "--file", str(context / dockerfile),
    ]
    if service == "caddy":
        command.extend(["--build-arg", f"VCS_REF={revision}"])
    command.extend(
        [
            "--tag", str(spec["tag"]),
            "--metadata-file", str(metadata),
            "--output", f"type=oci,dest={artifact},tar=true,oci-mediatypes=true",
            str(context),
        ]
    )
    subprocess.run(command, check=True)
    record = {
        "source": (
            "git+https://github.com/nmpraveen/patient-registry"
            f"@{revision}#{dockerfile}"
        ),
        "dockerfile": dockerfile,
        "dockerfile_sha256": sha256_file(context / dockerfile),
        "build_metadata": metadata.name,
        "build_metadata_sha256": sha256_file(metadata),
    }
    if service == "caddy":
        record.update(
            {
                "runtime_config": "deploy/Caddyfile",
                "runtime_config_sha256": sha256_file(context / "deploy" / "Caddyfile"),
            }
        )
    return record


def scan_and_sbom(
    repo_root: Path,
    service: str,
    artifact: Path,
    manifest_digest: str,
    policy: Path,
    policy_display: str,
) -> dict[str, str]:
    report = artifact.parent / f"{service}-trivy.json"
    sbom = artifact.parent / f"{service}-sbom.cdx.json"
    output_mount = f"{artifact.parent.resolve()}:/output"
    with tempfile.TemporaryDirectory(prefix="medtrack-service-oci-layout-") as layout_dir:
        layout = Path(layout_dir)
        with tarfile.open(artifact, mode="r:*") as archive:
            for member in archive.getmembers():
                target = (layout / member.name).resolve()
                if layout.resolve() not in target.parents and target != layout.resolve():
                    raise RuntimeError(f"unsafe OCI archive member: {member.name}")
                if not (member.isfile() or member.isdir()):
                    raise RuntimeError(f"unsupported OCI archive member type: {member.name}")
            archive.extractall(layout)
        for path in layout.rglob("*"):
            path.chmod(0o700 if path.is_dir() else 0o600)
        subprocess.run(
            [
                "docker", "run", "--rm", "--volume", output_mount,
                "--volume", f"{layout.resolve()}:/oci:ro",
                TRIVY_IMAGE, "image", "--input", "/oci",
                "--scanners", "vuln,secret", "--severity", "HIGH,CRITICAL",
                "--ignore-unfixed=false", "--exit-code", "0",
                "--format", "json", "--output", f"/output/{report.name}",
            ],
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
        "vex_policy": policy_display,
        "vex_policy_sha256": sha256_file(policy),
    }


def verify_findings(
    repo_root: Path, report: Path, policy: Path, manifest_digest: str
) -> None:
    subprocess.run(
        [
            sys.executable, str(repo_root / "scripts" / "verify_container_vulnerabilities.py"),
            "--report", str(report), "--policy", str(policy),
            "--image-digest", manifest_digest,
        ],
        cwd=repo_root,
        check=True,
    )


def write_service_receipt(output: Path, record: dict[str, object]) -> None:
    service = str(record["service"])
    (output / f"{service}-image-receipt.json").write_text(
        json.dumps({"schema": "medtrack.production-service-image/v1", **record}, indent=2) + "\n",
        encoding="utf-8",
    )


def write_set_receipt(
    output: Path,
    revision: str,
    records: list[dict[str, object]],
    gate: str,
) -> Path:
    receipt = {
        "schema": "medtrack.production-image-set/v1",
        "revision": revision,
        "platform": "linux/amd64",
        "gate": gate,
        "services": records,
    }
    receipt_path = output / "production-service-images.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt_path


def runtime_smoke(
    source_root: Path,
    service: str,
    artifact: Path,
    revision: str,
    expected_config_digest: str,
) -> dict[str, str]:
    image = f"medtrack-{service}-proof:{revision[:12]}"
    load_oci_archive(artifact, image)
    inspection = json.loads(
        subprocess.run(
            ["docker", "image", "inspect", image],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )[0]
    loaded_image_id = str(inspection.get("Id", ""))
    configured_user = str(inspection.get("Config", {}).get("User", ""))
    if loaded_image_id != expected_config_digest:
        raise RuntimeError(
            f"{service} loaded image ID does not match its OCI config digest: "
            f"loaded={loaded_image_id} config={expected_config_digest}"
        )
    if service == "postgres":
        command = [
            "docker", "run", "--rm", "--entrypoint", "sh", image, "-ceu",
            'test "$(id -u)" = 70; test "$(id -g)" = 70; '
            "! test -e /usr/local/bin/gosu; postgres --version; "
            "printf 'uid=%s gid=%s\\n' \"$(id -u)\" \"$(id -g)\"",
        ]
        runtime_uid = "70"
        runtime_gid = "70"
    else:
        labels = inspection.get("Config", {}).get("Labels") or {}
        if labels.get("org.opencontainers.image.revision") != revision:
            raise RuntimeError("Caddy runtime revision label does not match the exact Git revision")
        if configured_user != "10002:10001":
            raise RuntimeError(f"Caddy image has an unexpected runtime user: {configured_user!r}")
        command = [
            "docker", "run", "--rm", "--entrypoint", "sh",
            "--env", "MEDTRACK_DOMAIN=http://medtrack.invalid",
            "--cap-drop", "ALL", "--cap-add", "NET_BIND_SERVICE",
            "--security-opt", "no-new-privileges:true",
            "--tmpfs", "/var/log/medtrack:rw,noexec,nosuid,nodev,mode=0770,uid=10002,gid=10001",
            "--volume", f"{(source_root / 'deploy' / 'Caddyfile').resolve()}:/etc/caddy/Caddyfile:ro",
            image, "-ceu",
            'test "$(id -u)" = 10002; test "$(id -g)" = 10001; '
            "caddy list-modules | grep -Fxq http.handlers.rate_limit; "
            "caddy validate --config /etc/caddy/Caddyfile; "
            "caddy respond --listen :80 >/tmp/caddy-bind.log 2>&1 & caddy_pid=$!; "
            "caddy_ready=0; "
            "for attempt in 1 2 3 4 5 6 7 8 9 10; do "
            "if wget -q -O /dev/null http://127.0.0.1/; then caddy_ready=1; break; fi; "
            "kill -0 \"$caddy_pid\" 2>/dev/null || break; sleep 0.1; done; "
            "kill \"$caddy_pid\" 2>/dev/null || true; wait \"$caddy_pid\" || true; "
            "test \"$caddy_ready\" = 1; "
            "printf 'uid=%s gid=%s\\n' \"$(id -u)\" \"$(id -g)\"",
        ]
        subprocess.run(command, check=True)
        runtime_uid = "10002"
        runtime_gid = "10001"
    if service == "postgres":
        subprocess.run(command, check=True)
    return {
        "loaded_image": image,
        "loaded_image_id": loaded_image_id,
        "configured_user": configured_user,
        "runtime_uid": runtime_uid,
        "runtime_gid": runtime_gid,
    }


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

    with tempfile.TemporaryDirectory(prefix="medtrack-service-context-") as context_dir:
        context = Path(context_dir)
        extract_git_archive(repo_root, revision, context)
        for service in services:
            artifact = output / f"{service}-image.oci.tar"
            build = build_service_image(
                context, output, args.builder, service, revision, artifact
            )
            policy_display = str(SERVICE_BUILDS[service]["policy"])
            policy = context / policy_display
            identity = inspect_oci_archive(artifact)
            build_metadata_path = output / str(build["build_metadata"])
            build_metadata = json.loads(build_metadata_path.read_text(encoding="utf-8"))
            if build_metadata.get("containerimage.digest") != identity["manifest_digest"]:
                raise RuntimeError(
                    f"{service} BuildKit digest does not match its canonical OCI archive"
                )
            runtime = runtime_smoke(
                context, service, artifact, revision, identity["config_digest"]
            )
            evidence = scan_and_sbom(
                repo_root,
                service,
                artifact,
                identity["manifest_digest"],
                policy,
                policy_display,
            )
            record = {
                "service": service,
                "revision": revision,
                "artifact": artifact.name,
                "artifact_sha256": sha256_file(artifact),
                **build,
                **identity,
                **runtime,
                **evidence,
            }
            try:
                verify_findings(
                    repo_root,
                    output / str(evidence["trivy_report"]),
                    policy,
                    str(identity["manifest_digest"]),
                )
            except subprocess.CalledProcessError:
                record["gate"] = "fail"
                records.append(record)
                write_service_receipt(output, record)
                write_set_receipt(output, revision, records, "fail")
                raise
            record["gate"] = "pass"
            records.append(record)
            write_service_receipt(output, record)

    receipt_path = write_set_receipt(output, revision, records, "pass")
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
