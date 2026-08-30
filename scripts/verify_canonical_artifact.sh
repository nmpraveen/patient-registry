#!/usr/bin/env bash
set -euo pipefail

revision="${1:?usage: verify_canonical_artifact.sh <40-character-revision> [output-directory]}"
output_directory="${2:-output}"
if [[ ! "$revision" =~ ^[0-9a-f]{40}$ ]]; then
  echo "revision must be a full lowercase Git SHA" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
output_path="$(realpath "$output_directory")"
case "$output_path" in
  "$repo_root"/*) ;;
  *) echo "output directory must be inside the repository" >&2; exit 2 ;;
esac
host_output_path="$output_path"
if command -v cygpath >/dev/null 2>&1; then
  host_output_path="$(cygpath -w "$output_path")"
  export MSYS_NO_PATHCONV=1
fi

artifact="$host_output_path/medtrack-image.oci.tar"
metadata="$host_output_path/medtrack-canonical-image.json"
report="$host_output_path/medtrack-trivy.json"
sbom="$host_output_path/medtrack-sbom.cdx.json"
provenance="$host_output_path/medtrack-provenance.intoto.json"
manifest_digest="$(python - "$metadata" <<'PY'
import json
from pathlib import Path
import re
import sys

digest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["manifest_digest"]
if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
    raise SystemExit("invalid canonical manifest digest")
print(digest)
PY
)"
layout_path="$(python - "$artifact" <<'PY'
from pathlib import Path
import tarfile
import tempfile
import sys

destination = Path(tempfile.mkdtemp(prefix="medtrack-oci-layout-"))
with tarfile.open(sys.argv[1], mode="r:*") as archive:
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if destination.resolve() not in target.parents and target != destination.resolve():
            raise SystemExit(f"unsafe OCI archive member: {member.name}")
        if not (member.isfile() or member.isdir()):
            raise SystemExit(f"unsupported OCI archive member type: {member.name}")
    archive.extractall(destination)
for path in destination.rglob("*"):
    path.chmod(0o700 if path.is_dir() else 0o600)
print(destination)
PY
)"
cleanup_layout() {
  python - "$layout_path" <<'PY'
from pathlib import Path
import shutil
import sys

path = Path(sys.argv[1]).resolve()
if path.name.startswith("medtrack-oci-layout-"):
    shutil.rmtree(path)
PY
}
trap cleanup_layout EXIT

docker run --rm \
  --volume "$host_output_path:/output" \
  --volume "$layout_path:/oci:ro" \
  aquasec/trivy:0.74.0@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969 \
  image --input /oci \
  --scanners vuln,secret --severity HIGH,CRITICAL \
  --ignore-unfixed=false --exit-code 0 \
  --format json --output /output/medtrack-trivy.json

python scripts/verify_container_vulnerabilities.py \
  --report "$report" \
  --policy security/container-vex.json \
  --image-digest "$manifest_digest"

docker run --rm \
  --volume "$host_output_path:/output" \
  anchore/syft:v1.51.1@sha256:95fe0835e5bebc6f8b1f8acef68d47d63d594ef4c0f25c097ff853b23cbac74c \
  scan oci-archive:/output/medtrack-image.oci.tar \
  --output cyclonedx-json=/output/medtrack-sbom.cdx.json

python scripts/write_build_provenance.py \
  --canonical-metadata "$metadata" \
  --artifact "$artifact" \
  --revision "$revision" \
  --output "$provenance"

echo "CANONICAL_ARTIFACT_VERIFIED revision=$revision manifest_digest=$manifest_digest high=0 critical=0 secrets=0 sbom=$sbom provenance=$provenance"
