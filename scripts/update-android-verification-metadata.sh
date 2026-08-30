#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
android_root="$repo_root/android"

if (($#)); then
  tasks=("$@")
else
  tasks=(testDebugUnitTest lintRelease assembleRelease)
fi

gradle_home="$(mktemp -d "${TMPDIR:-/tmp}/medtrack-gradle-verification.XXXXXX")"
cleanup() {
  if [[ -n "${gradle_home:-}" && -d "$gradle_home" ]]; then
    rm -rf -- "$gradle_home"
  fi
}
trap cleanup EXIT

cd "$android_root"
GRADLE_USER_HOME="$gradle_home" bash ./gradlew \
  --no-daemon \
  --max-workers=1 \
  --write-verification-metadata sha256 \
  "${tasks[@]}"

echo "ANDROID_VERIFICATION_METADATA_UPDATED tasks=${tasks[*]}"
