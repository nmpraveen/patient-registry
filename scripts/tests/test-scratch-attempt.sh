#!/usr/bin/env bash
set -Eeuo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf -- "$test_root"' EXIT
export MEDTRACK_BACKUP_CONFIG="$test_root/no-config"
export MEDTRACK_SCRATCH_RESTORE_RECEIPT="$test_root/restore.receipt"
export MEDTRACK_SCRATCH_RESTORE_ATTEMPT="$test_root/custom.attempt"
export MEDTRACK_SCRATCH_RESTORE_HOOK="$test_root/restore"
export MEDTRACK_SCRATCH_RESTORE_ALERT_HOOK="$test_root/alert"
export TEST_ALERT_LOG="$test_root/alerts"
printf '#!/usr/bin/env bash\nexit 0\n' > "$test_root/restore"
printf '#!/usr/bin/env bash\nprintf "alert\\n" >> "$TEST_ALERT_LOG"\n' > "$test_root/alert"
chmod +x "$test_root/restore" "$test_root/alert"
runner="$repo_root/scripts/run-offsite-scratch-restore.sh"
valid() { python "$repo_root/scripts/verify_scratch_attempt.py" "$MEDTRACK_SCRATCH_RESTORE_ATTEMPT" "$MEDTRACK_SCRATCH_RESTORE_RECEIPT" "$(date -u +%s)"; }
fail_run() {
  local expected="$1" code=0
  "$runner" > "$test_root/output" 2>&1 || code=$?
  [[ "$code" == "$expected" ]] || { cat "$test_root/output"; exit 1; }
  grep -qx 'status=failure' "$MEDTRACK_SCRATCH_RESTORE_ATTEMPT"
  if valid >/dev/null 2>&1; then echo 'Failure concealed by stale receipt' >&2; exit 1; fi
}
"$runner"
valid
cp "$MEDTRACK_SCRATCH_RESTORE_RECEIPT" "$test_root/old.receipt"
# An interrupted attempt cannot reuse a previous success, even in the same second.
sed -i 's/status=success/status=running/' "$MEDTRACK_SCRATCH_RESTORE_ATTEMPT"
if valid >/dev/null 2>&1; then exit 1; fi
"$runner"
# A preflight failure must alert and invalidate old success, preserving the receipt for diagnosis.
MEDTRACK_SCRATCH_RESTORE_HOOK="$test_root/missing" fail_run 1
grep -qx 'alert_delivery=delivered' "$MEDTRACK_SCRATCH_RESTORE_ATTEMPT"
[[ -s "$TEST_ALERT_LOG" ]]
printf '#!/usr/bin/env bash\nexit 9\n' > "$test_root/restore"
fail_run 9
# Delivery failure is distinct, explicit, and nonzero.
printf '#!/usr/bin/env bash\nexit 5\n' > "$test_root/alert"
fail_run 2
grep -qx 'alert_delivery=failed' "$MEDTRACK_SCRATCH_RESTORE_ATTEMPT"
grep -q 'alert_delivery=failed' "$test_root/output"
# A successful retry repairs state; a modified or replaced receipt is rejected.
printf '#!/usr/bin/env bash\nexit 0\n' > "$test_root/restore"
"$runner"
valid
cp "$MEDTRACK_SCRATCH_RESTORE_RECEIPT" "$test_root/good.receipt"
printf 'extra=changed\n' >> "$MEDTRACK_SCRATCH_RESTORE_RECEIPT"
if valid >/dev/null 2>&1; then exit 1; fi
cp "$test_root/old.receipt" "$MEDTRACK_SCRATCH_RESTORE_RECEIPT"
if valid >/dev/null 2>&1; then exit 1; fi
cp "$test_root/good.receipt" "$MEDTRACK_SCRATCH_RESTORE_RECEIPT"
# Config loading errors are covered by the finalizer too.
printf 'return 8\n' > "$test_root/bad-config"
MEDTRACK_BACKUP_CONFIG="$test_root/bad-config" fail_run 2
# Missing attempt and duplicate state keys fail closed.
"$runner"
printf 'status=success\n' >> "$MEDTRACK_SCRATCH_RESTORE_ATTEMPT"
if valid >/dev/null 2>&1; then exit 1; fi
rm "$MEDTRACK_SCRATCH_RESTORE_ATTEMPT"
if valid >/dev/null 2>&1; then exit 1; fi
echo SCRATCH_ATTEMPT_TEST_OK
