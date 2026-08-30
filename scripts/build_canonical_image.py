#!/usr/bin/env python3
"""Build, load, and verify one canonical OCI image for an exact Git revision."""

from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import secrets
import subprocess
import sys
import tarfile
import tempfile

from build_context_receipt import create_receipt, verify_image
from verify_container_build import CANARY_PATHS, extract_git_archive, run_scan


SCHEMA = "medtrack.canonical-image/v1"
SKOPEO_IMAGE = "quay.io/skopeo/stable:v1.21.0@sha256:a585e4a3b8a045baa87c7f1b2f940d6d299ebede85ab3f2419d52d2264eefc93"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def verified_blob(archive: tarfile.TarFile, digest: str) -> bytes:
    algorithm, hexadecimal = digest.split(":", 1)
    if algorithm != "sha256" or len(hexadecimal) != 64:
        raise RuntimeError(f"unsupported OCI digest: {digest}")
    member = archive.extractfile(f"blobs/sha256/{hexadecimal}")
    if member is None:
        raise RuntimeError(f"OCI archive is missing blob {digest}")
    content = member.read()
    if hashlib.sha256(content).hexdigest() != hexadecimal:
        raise RuntimeError(f"OCI blob checksum mismatch: {digest}")
    return content


def inspect_oci_archive(path: Path) -> dict[str, str]:
    with tarfile.open(path, mode="r:*") as archive:
        index_file = archive.extractfile("index.json")
        layout_file = archive.extractfile("oci-layout")
        if index_file is None or layout_file is None:
            raise RuntimeError("canonical artifact is not an OCI image-layout archive")
        layout = json.load(layout_file)
        if layout.get("imageLayoutVersion") != "1.0.0":
            raise RuntimeError(f"unsupported OCI layout version: {layout!r}")
        index = json.load(index_file)
        descriptors = index.get("manifests") or []
        if len(descriptors) != 1:
            raise RuntimeError(f"expected one OCI entrypoint descriptor, found {len(descriptors)}")
        descriptor = descriptors[0]
        manifest_digest = str(descriptor.get("digest", ""))
        manifest_bytes = verified_blob(archive, manifest_digest)
        manifest = json.loads(manifest_bytes)
        media_type = str(descriptor.get("mediaType", ""))
        if "image.index" in media_type:
            children = manifest.get("manifests") or []
            platform_children = [
                child
                for child in children
                if child.get("platform", {}).get("os") == "linux"
                and child.get("platform", {}).get("architecture") == "amd64"
            ]
            if len(platform_children) != 1:
                raise RuntimeError(
                    f"expected one linux/amd64 platform manifest, found {len(platform_children)}"
                )
            platform_digest = str(platform_children[0].get("digest", ""))
            manifest = json.loads(verified_blob(archive, platform_digest))
        else:
            platform_digest = manifest_digest
        config_digest = str(manifest.get("config", {}).get("digest", ""))
        verified_blob(archive, config_digest)
        return {
            "manifest_digest": manifest_digest,
            "platform_manifest_digest": platform_digest,
            "config_digest": config_digest,
        }


def load_oci_archive(artifact: Path, image: str) -> None:
    subprocess.run(
        ["docker", "image", "rm", "--force", image],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    mount = f"{artifact.parent.resolve()}:/artifacts:ro"
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--volume",
            "/var/run/docker.sock:/var/run/docker.sock",
            "--volume",
            mount,
            SKOPEO_IMAGE,
            "copy",
            "--override-os",
            "linux",
            "--override-arch",
            "amd64",
            f"oci-archive:/artifacts/{artifact.name}",
            f"docker-daemon:{image}",
        ],
        check=True,
    )


def verify_runtime_execution(image: str) -> None:
    program = """
import os
from pathlib import Path

assert os.getuid() == 10001, os.getuid()
assert os.getgid() == 10001, os.getgid()
for directory in (Path('/tmp'), Path('/app/staticfiles'), Path('/app/backups')):
    probe = directory / '.medtrack-write-probe'
    probe.write_text('synthetic runtime write probe', encoding='utf-8')
    probe.unlink()
try:
    with Path('/app/manage.py').open('a', encoding='utf-8'):
        pass
except PermissionError:
    pass
else:
    raise AssertionError('/app/manage.py is writable by the runtime identity')
print('CANONICAL_RUNTIME_OK uid=10001 gid=10001 writable=/tmp,/app/staticfiles,/app/backups code_readonly=true')
"""
    subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "python", image, "-c", program],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--image")
    parser.add_argument("--artifact", default="output/medtrack-image.oci.tar")
    parser.add_argument("--metadata", default="output/medtrack-canonical-image.json")
    parser.add_argument("--builder")
    parser.add_argument("--no-pull", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    revision = subprocess.run(
        ["git", "rev-parse", args.revision],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    receipt = create_receipt(repo_root, revision)
    image = args.image or f"medtrack-canonical:{revision[:12]}"
    context_image = f"medtrack-context-proof:{revision[:12]}"
    artifact = (repo_root / args.artifact).resolve()
    metadata_path = (repo_root / args.metadata).resolve()
    artifact.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    artifact.unlink(missing_ok=True)
    buildkit_metadata = artifact.with_suffix(artifact.suffix + ".buildkit.json")
    buildkit_metadata.unlink(missing_ok=True)
    canary = f"MEDTRACK_FAKE_SECRET_PHI_CANARY_{secrets.token_hex(16)}"

    try:
        with tempfile.TemporaryDirectory(prefix="medtrack-canonical-context-") as temp_dir:
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

            command = ["docker", "buildx", "build"]
            if args.builder:
                command.extend(["--builder", args.builder])
            command.extend(["--platform", "linux/amd64", "--provenance=false", "--sbom=false"])
            if not args.no_pull:
                command.append("--pull")
            if args.no_cache:
                command.append("--no-cache")
            command.extend(
                [
                    "--build-arg",
                    f"VCS_REF={revision}",
                    "--build-arg",
                    f"BUILD_CONTEXT_SHA256={receipt['build_context_sha256']}",
                    "--tag",
                    image,
                    "--metadata-file",
                    str(buildkit_metadata),
                    "--output",
                    f"type=oci,dest={artifact},tar=true,oci-mediatypes=true",
                    str(context),
                ]
            )
            subprocess.run(command, cwd=repo_root, check=True)

        oci = inspect_oci_archive(artifact)
        build_metadata = json.loads(buildkit_metadata.read_text(encoding="utf-8"))
        buildkit_digest = str(build_metadata.get("containerimage.digest", ""))
        if buildkit_digest != oci["manifest_digest"]:
            raise RuntimeError(
                "BuildKit digest does not match the canonical OCI entrypoint: "
                f"buildkit={buildkit_digest} archive={oci['manifest_digest']}"
            )
        load_oci_archive(artifact, image)
        run_scan(repo_root, image, "runtime", canary)
        verify_image(image, receipt)
        verify_runtime_execution(image)
        inspection = json.loads(
            subprocess.run(
                ["docker", "image", "inspect", image],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        )[0]
        metadata = {
            "schema": SCHEMA,
            "source": "https://github.com/nmpraveen/patient-registry",
            "revision": revision,
            "image_name": image,
            "manifest_digest": oci["manifest_digest"],
            "platform_manifest_digest": oci["platform_manifest_digest"],
            "config_digest": oci["config_digest"],
            "loaded_image_id": inspection["Id"],
            "artifact": artifact.name,
            "artifact_sha256": sha256_file(artifact),
            "build_context_schema": receipt["schema"],
            "build_context_sha256": receipt["build_context_sha256"],
            "canary_count": len(CANARY_PATHS),
        }
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    finally:
        subprocess.run(
            ["docker", "image", "rm", "--force", context_image],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    print(
        "CANONICAL_IMAGE_OK "
        f"revision={revision} manifest_digest={metadata['manifest_digest']} "
        f"artifact_sha256={metadata['artifact_sha256']} "
        f"build_context_sha256={receipt['build_context_sha256']} "
        f"canaries={len(CANARY_PATHS)} image={image}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"CANONICAL_IMAGE_FAIL {exc}", file=sys.stderr)
        raise
