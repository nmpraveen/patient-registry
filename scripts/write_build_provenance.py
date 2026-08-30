#!/usr/bin/env python3
"""Write local provenance for the verified canonical OCI manifest digest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from build_context_receipt import create_receipt


MATERIALS = (
    ".dockerignore",
    "Dockerfile",
    "Dockerfile.postgres",
    "requirements.in",
    "requirements.txt",
    "docker-compose.yml",
    "docker-compose.prod.yml",
    "android/gradle/verification-metadata.xml",
    "scripts/build_context_receipt.py",
    "scripts/build_canonical_image.py",
    "scripts/verify_canonical_artifact.sh",
    "scripts/verify_container_vulnerabilities.py",
    "security/container-vex.json",
    "security/postgres-vex.json",
    "security/caddy-vex.json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-metadata", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    revision = subprocess.run(
        ["git", "rev-parse", args.revision],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    metadata_path = Path(args.canonical_metadata)
    artifact_path = Path(args.artifact)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("schema") != "medtrack.canonical-image/v1":
        raise RuntimeError("canonical image metadata has the wrong schema")
    if metadata.get("revision") != revision:
        raise RuntimeError("canonical image metadata revision does not match the requested revision")
    if metadata.get("artifact_sha256") != f"sha256:{sha256(artifact_path)}":
        raise RuntimeError("canonical OCI artifact hash does not match its metadata")
    context_receipt = create_receipt(repo_root, revision)
    if metadata.get("build_context_sha256") != context_receipt["build_context_sha256"]:
        raise RuntimeError("canonical image metadata build-context digest does not match Git")
    manifest_digest = str(metadata.get("manifest_digest", ""))
    if not manifest_digest.startswith("sha256:") or len(manifest_digest) != 71:
        raise RuntimeError("canonical image metadata has an invalid manifest digest")
    materials = []
    for relative in MATERIALS:
        path = repo_root / relative
        if path.is_file():
            materials.append(
                {
                    "uri": f"git+https://github.com/nmpraveen/patient-registry@{revision}#{relative}",
                    "digest": {"sha256": sha256(path)},
                }
            )
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [
            {
                "name": str(metadata["image_name"]),
                "digest": {"sha256": manifest_digest.removeprefix("sha256:")},
            }
        ],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://mobyproject.org/buildkit@v1",
                "externalParameters": {
                    "revision": revision,
                    "buildContext": {
                        "schema": context_receipt["schema"],
                        "digest": context_receipt["build_context_sha256"],
                        "fileCount": context_receipt["file_count"],
                    },
                },
                "internalParameters": {
                    "platform": "linux/amd64",
                    "artifactSha256": metadata["artifact_sha256"],
                    "platformManifestDigest": metadata["platform_manifest_digest"],
                    "configDigest": metadata["config_digest"],
                },
                "resolvedDependencies": materials,
            },
            "runDetails": {
                "builder": {
                    "id": "https://github.com/nmpraveen/patient-registry/.github/workflows/attest-release.yml"
                },
                "metadata": {"invocationId": "exact-git-revision"},
            },
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(statement, indent=2) + "\n", encoding="utf-8")
    print(f"BUILD_PROVENANCE_WRITTEN path={output} manifest_digest={manifest_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
