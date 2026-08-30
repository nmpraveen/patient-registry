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

artifact="$output_path/medtrack-image.oci.tar"
metadata="$output_path/medtrack-canonical-image.json"
report="$output_path/medtrack-trivy.json"
sbom="$output_path/medtrack-sbom.cdx.json"
provenance="$output_path/medtrack-provenance.intoto.json"
manifest_digest="$(jq -er '.manifest_digest | select(test("^sha256:[0-9a-f]{64}$"))' "$metadata")"

docker run --rm \
  --volume "$output_path:/output" \
  aquasec/trivy:0.74.0@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969 \
  image --input /output/medtrack-image.oci.tar \
  --scanners vuln,secret --severity HIGH,CRITICAL \
  --ignore-unfixed=false --exit-code 0 \
  --format json --output /output/medtrack-trivy.json

python scripts/verify_container_vulnerabilities.py \
  --report "$report" \
  --policy security/container-vex.json \
  --image-digest "$manifest_digest"

docker run --rm \
  --volume "$output_path:/output" \
  anchore/syft:v1.51.1@sha256:95fe0835e5bebc6f8b1f8acef68d47d63d594ef4c0f25c097ff853b23cbac74c \
  scan oci-archive:/output/medtrack-image.oci.tar \
  --output cyclonedx-json=/output/medtrack-sbom.cdx.json

python scripts/write_build_provenance.py \
  --canonical-metadata "$metadata" \
  --artifact "$artifact" \
  --revision "$revision" \
  --output "$provenance"

echo "CANONICAL_ARTIFACT_VERIFIED revision=$revision manifest_digest=$manifest_digest high=0 critical=0 secrets=0 sbom=$sbom provenance=$provenance"
