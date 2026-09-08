#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf -- "$test_root"' EXIT
export IDENTITY_TEST_LOG="$test_root/calls"
export IDENTITY_SOURCE_SCHEMA=1 IDENTITY_TARGET_SCHEMA=1 IDENTITY_EXPORT_FAIL=0 IDENTITY_APPLY_FAIL=0
sed -n '/^identity_schema_present()/,/^db_exists()/p' "$repo_root/scripts/restore.sh" | sed '$d' > "$test_root/functions.sh"
# shellcheck source=/dev/null
source "$test_root/functions.sh"
database_user=synthetic
identity_fenced_database=""

fake_compose() {
  printf '%s\n' "$*" >> "$IDENTITY_TEST_LOG"
  if [[ "$*" == *"to_regclass"* ]]; then
    if [[ "$*" == *"--dbname=source"* ]]; then echo "$IDENTITY_SOURCE_SCHEMA"; else echo "$IDENTITY_TARGET_SCHEMA"; fi
  elif [[ "$*" == *"patient_identity_checkpoint export"* ]]; then
    [[ "$IDENTITY_EXPORT_FAIL" == 0 ]] || return 1
    printf '{"synthetic":"checkpoint"}\n'
  elif [[ "$*" == *"patient_identity_checkpoint apply"* ]]; then
    cat >/dev/null
    [[ "$IDENTITY_APPLY_FAIL" == 0 ]] || return 1
  fi
}
compose=(fake_compose)
declare -p compose database_user >/dev/null

carry_forward_identity source target "$test_root/valid.json"
test "$identity_fenced_database" = source
grep -Fq 'SET default_transaction_read_only = on' "$IDENTITY_TEST_LOG"
grep -Fq 'pg_terminate_backend' "$IDENTITY_TEST_LOG"
grep -Fq 'PGOPTIONS=-c default_transaction_read_only=off' "$IDENTITY_TEST_LOG"
grep -Fq 'verify_patient_identity' "$IDENTITY_TEST_LOG"
fence_line="$(grep -n 'SET default_transaction_read_only' "$IDENTITY_TEST_LOG" | head -1 | cut -d: -f1)"
export_line="$(grep -n 'checkpoint export' "$IDENTITY_TEST_LOG" | head -1 | cut -d: -f1)"
apply_line="$(grep -n 'checkpoint apply' "$IDENTITY_TEST_LOG" | head -1 | cut -d: -f1)"
test "$fence_line" -lt "$export_line"
test "$export_line" -lt "$apply_line"
release_identity_fence
test -z "$identity_fenced_database"

IDENTITY_SOURCE_SCHEMA=0
if carry_forward_identity source target "$test_root/missing.json"; then echo "Missing outgoing ledger accepted" >&2; exit 1; fi
IDENTITY_TARGET_SCHEMA=0
carry_forward_identity source target "$test_root/old-schema.json"
test ! -e "$test_root/old-schema.json"
IDENTITY_SOURCE_SCHEMA=1
if carry_forward_identity source target "$test_root/old-target.json"; then echo "Old target discarded issuance" >&2; exit 1; fi
IDENTITY_TARGET_SCHEMA=1 IDENTITY_EXPORT_FAIL=1
if carry_forward_identity source target "$test_root/failed-export.json"; then echo "Failed capture accepted" >&2; exit 1; fi
IDENTITY_EXPORT_FAIL=0 IDENTITY_APPLY_FAIL=1
if carry_forward_identity source target "$test_root/failed-apply.json"; then echo "Failed reconciliation accepted" >&2; exit 1; fi
if carry_forward_identity source target "$test_root/valid.json"; then echo "Surviving checkpoint overwritten" >&2; exit 1; fi
echo IDENTITY_RESTORE_GATE_TEST_OK
