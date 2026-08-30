#!/usr/bin/env python3
"""Write an unsigned local in-toto/SLSA provenance statement for CI artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from build_context_receipt import create_receipt, verify_image


MATERIALS = (
    ".dockerignore",
    "Dockerfile",
    "requirements.in",
    "requirements.txt",
    "docker-compose.yml",
    "docker-compose.prod.yml",
    "android/gradle/verification-metadata.xml",
    "scripts/build_context_receipt.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
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
    inspection = json.loads(
        subprocess.run(
            ["docker", "image", "inspect", args.image],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )[0]
    context_receipt = create_receipt(repo_root, revision)
    verify_image(args.image, context_receipt)
    image_id = inspection["Id"].removeprefix("sha256:")
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
        "subject": [{"name": args.image, "digest": {"sha256": image_id}}],
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
                "internalParameters": {"platform": inspection.get("Os") + "/" + inspection.get("Architecture")},
                "resolvedDependencies": materials,
            },
            "runDetails": {
                "builder": {
                    "id": os.environ.get(
                        "GITHUB_WORKFLOW_REF",
                        "local://scripts/verify_container_build.py",
                    )
                },
                "metadata": {
                    "invocationId": os.environ.get("GITHUB_RUN_ID", "local"),
                },
            },
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(statement, indent=2) + "\n", encoding="utf-8")
    print(f"BUILD_PROVENANCE_WRITTEN path={output} image_sha256={image_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
