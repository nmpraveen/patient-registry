#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

if [[ $# -ne 2 ]]; then
  echo "Usage: scripts/build-attested-image.sh <full-git-commit> <absolute-attestation-path>" >&2
  exit 2
fi

commit="$1"
attestation="$2"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! "$commit" =~ ^[0-9a-f]{40}$ || "$attestation" != /* ]]; then
  echo "Build attestation requires a full commit and absolute output path" >&2
  exit 1
fi
python_command="${PYTHON_COMMAND:-python3}"
for command_name in docker git mktemp "$python_command" realpath tar; do
  command -v "$command_name" >/dev/null 2>&1 || { echo "Missing required command: $command_name" >&2; exit 1; }
done
git -C "$repo_root" cat-file -e "$commit^{commit}"
verifier="${MEDTRACK_BUILD_CONTEXT_VERIFIER:-$repo_root/scripts/build_context_receipt.py}"
if [[ ! -f "$verifier" ]]; then
  echo "Canonical medtrack.build-context/v1 verifier is missing: $verifier (requires build PR #100)" >&2
  exit 1
fi
context_root="$(mktemp -d)"
cleanup() { rm -rf -- "$context_root"; }
trap cleanup EXIT
git -C "$repo_root" archive --format=tar "$commit" | tar -xf - -C "$context_root"

context_digest="$("$python_command" "$verifier" --revision "$commit" --format digest)"
[[ "$context_digest" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo "Canonical build-context digest is invalid" >&2; exit 1; }
image_ref="medtrack-app:$commit"
docker build --pull \
  --build-arg "VCS_REF=$commit" \
  --build-arg "BUILD_CONTEXT_SHA256=$context_digest" \
  --tag "$image_ref" "$context_root"
image_id="$(docker image inspect --format '{{.Id}}' "$image_ref")"
"$python_command" "$verifier" --revision "$commit" --verify-image "$image_id"

mkdir -p -m 0700 "$(dirname "$attestation")"
attestation="$(realpath "$(dirname "$attestation")")/$(basename "$attestation")"
attestation_tmp="$(mktemp "$(dirname "$attestation")/.image-attestation.XXXXXX")"
{
  printf 'attestation_format=medtrack-build-receipt-v1\n'
  printf 'build_context_schema=medtrack.build-context/v1\n'
  printf 'build_context_sha256=%s\n' "$context_digest"
  printf 'revision=%s\n' "$commit"
  printf 'image_ref=%s\n' "$image_ref"
  printf 'image_id=%s\n' "$image_id"
} > "$attestation_tmp"
chmod 0600 "$attestation_tmp"
mv "$attestation_tmp" "$attestation"
echo "MEDTRACK_BUILD_RECEIPT revision=$commit build_context_sha256=$context_digest image=$image_id" | tee -a "$attestation"
echo "ATTESTED_IMAGE_BUILD_OK commit=$commit image=$image_id attestation=$attestation"
