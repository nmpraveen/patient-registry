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
for command_name in docker git grep mktemp realpath sha256sum tar; do
  command -v "$command_name" >/dev/null 2>&1 || { echo "Missing required command: $command_name" >&2; exit 1; }
done
git -C "$repo_root" cat-file -e "$commit^{commit}"
git_tree="$(git -C "$repo_root" rev-parse "$commit^{tree}")"
context_root="$(mktemp -d)"
cleanup() { rm -rf -- "$context_root"; }
trap cleanup EXIT
git -C "$repo_root" archive --format=tar "$commit" | tar -xf - -C "$context_root"

if grep -Eq '^[[:space:]]*(COPY|ADD)[[:space:]]+\.[[:space:]]' "$context_root/Dockerfile"; then
  echo "The committed Dockerfile contains a broad context copy" >&2
  exit 1
fi
context_policy="$(
  printf '%s\n%s\n' \
    "$(git -C "$repo_root" rev-parse "$commit:Dockerfile")" \
    "$(git -C "$repo_root" rev-parse "$commit:.dockerignore")" |
    sha256sum | awk '{print $1}'
)"
image_ref="medtrack-app:$commit"
docker build --pull \
  --build-arg "VCS_REF=$commit" \
  --build-arg "MEDTRACK_GIT_TREE=$git_tree" \
  --build-arg "MEDTRACK_CONTEXT_POLICY=$context_policy" \
  --tag "$image_ref" "$context_root"
image_id="$(docker image inspect --format '{{.Id}}' "$image_ref")"
revision_label="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$image_ref")"
tree_label="$(docker image inspect --format '{{ index .Config.Labels "net.naveenhospital.medtrack.git-tree" }}' "$image_ref")"
context_label="$(docker image inspect --format '{{ index .Config.Labels "net.naveenhospital.medtrack.build-context" }}' "$image_ref")"
policy_label="$(docker image inspect --format '{{ index .Config.Labels "net.naveenhospital.medtrack.context-policy" }}' "$image_ref")"
if [[ -z "$image_id" || "$revision_label" != "$commit" || "$tree_label" != "$git_tree" ||
  "$context_label" != "git-archive-allowlist-v1" || "$policy_label" != "$context_policy" ]]; then
  echo "Built image labels do not match the committed allowlisted context" >&2
  exit 1
fi

mkdir -p -m 0700 "$(dirname "$attestation")"
attestation="$(realpath "$(dirname "$attestation")")/$(basename "$attestation")"
attestation_tmp="$(mktemp "$(dirname "$attestation")/.image-attestation.XXXXXX")"
{
  printf 'attestation_format=medtrack-committed-image-v1\n'
  printf 'build_context=git-archive-allowlist-v1\n'
  printf 'git_commit=%s\n' "$commit"
  printf 'git_tree=%s\n' "$git_tree"
  printf 'context_policy_sha256=%s\n' "$context_policy"
  printf 'image_ref=%s\n' "$image_ref"
  printf 'image_id=%s\n' "$image_id"
} > "$attestation_tmp"
chmod 0600 "$attestation_tmp"
mv "$attestation_tmp" "$attestation"
echo "ATTESTED_IMAGE_BUILD_OK commit=$commit tree=$git_tree image=$image_id attestation=$attestation"
