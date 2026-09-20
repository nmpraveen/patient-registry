#!/usr/bin/env bash
set -Eeuo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf -- "$test_root"' EXIT
export MEDTRACK_OPERATION_LOCK="$test_root/operation.lock"
# shellcheck source=scripts/operation-lock.sh
source "$repo_root/scripts/operation-lock.sh"
acquire_medtrack_operation_lock
for entrypoint in deploy-production.sh restore.sh; do
  set +e
  result="$(7>&- bash "$repo_root/scripts/$entrypoint" rollback --confirm synthetic 2>&1)"
  status=$?
  set -e
  [[ "$status" == 75 && "$result" == *"owns the operation lock"* ]]
done
flock -u 7
exec 7>&-
echo OPERATION_LOCK_TEST_OK
