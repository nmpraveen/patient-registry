#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf -- "$test_root"' EXIT

fake_bin="$test_root/bin"
fake_remote="$test_root/remote"
state_root="$test_root/state"
mkdir -p "$fake_bin" "$fake_remote/medtrack/test" "$state_root"

cat > "$fake_bin/rclone" <<'FAKE_RCLONE'
#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "$1" == "--config" ]]; then shift 2; fi
command_name="$1"
shift
remote_to_path() { printf '%s/%s' "$FAKE_RCLONE_ROOT" "${1#*:}"; }
case "$command_name" in
  lsf)
    if [[ "${FAKE_RCLONE_FAIL_LSF:-0}" == "1" ]]; then exit 55; fi
    find "$(remote_to_path "$1")" -maxdepth 1 -type f -printf '%f\n' | sort
    ;;
  cat)
    cat "$(remote_to_path "$1")"
    ;;
  about)
    printf '{"free":1000000000,"used":1}\n'
    ;;
  *)
    echo "Unexpected fake rclone command: $command_name" >&2
    exit 1
    ;;
esac
FAKE_RCLONE
chmod +x "$fake_bin/rclone"

remote_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
for tier in rapid daily weekly monthly; do
  tier_dir="$fake_remote/medtrack/test/$tier"
  mkdir -p "$tier_dir"
  archive="medtrack-prod-${tier}-${remote_stamp}.tar.age"
  printf 'ciphertext-%s\n' "$tier" > "$tier_dir/$archive"
  hash="$(sha256sum "$tier_dir/$archive" | awk '{print $1}')"
  printf '%s  %s\n' "$hash" "$archive" > "$tier_dir/$archive.sha256"
  {
    printf 'archive=%s\n' "$archive"
    printf 'sha256=%s\n' "$hash"
    printf 'completed_utc=%s\n' "$remote_stamp"
  } > "$tier_dir/$archive.complete"
  printf '0\n' > "$state_root/last-success-$tier.epoch"
done

cat > "$test_root/scratch-hook" <<'HOOK'
#!/usr/bin/env bash
echo "synthetic scratch restore hook passed"
HOOK
chmod +x "$test_root/scratch-hook"
printf '[medtrack-drive]\ntype = drive\n' > "$test_root/rclone.conf"

export PATH="$fake_bin:$PATH"
export FAKE_RCLONE_ROOT="$fake_remote"
export MEDTRACK_BACKUP_CONFIG="$test_root/no-config"
export MEDTRACK_OFFSITE_ROOT="$test_root"
export MEDTRACK_BACKUP_STATE_ROOT="$state_root"
export RCLONE_CONFIG="$test_root/rclone.conf"
export RCLONE_REMOTE="medtrack-drive:medtrack/test"
export MEDTRACK_HEALTH_HASH_MODE=all
export MEDTRACK_SCRATCH_RESTORE_HOOK="$test_root/scratch-hook"
export MEDTRACK_REQUIRE_SCRATCH_RESTORE_HOOK=1

"$repo_root/scripts/check-offsite-backups.sh"

export FAKE_RCLONE_FAIL_LSF=1
if "$repo_root/scripts/check-offsite-backups.sh" >/dev/null 2>&1; then
  echo "Health check unexpectedly hid a remote listing failure" >&2
  exit 1
fi
unset FAKE_RCLONE_FAIL_LSF

rapid_marker="$fake_remote/medtrack/test/rapid/medtrack-prod-rapid-${remote_stamp}.tar.age.complete"
cp "$rapid_marker" "$test_root/rapid-marker.original"
sed 's/^completed_utc=.*/completed_utc=20000101T000000Z/' "$rapid_marker" > "$rapid_marker.tmp"
mv "$rapid_marker.tmp" "$rapid_marker"
if "$repo_root/scripts/check-offsite-backups.sh" >/dev/null 2>&1; then
  echo "Health check unexpectedly accepted stale remote completion metadata" >&2
  exit 1
fi
cp "$test_root/rapid-marker.original" "$rapid_marker"

if MEDTRACK_HEALTH_PRODUCTION_MODE=1 MEDTRACK_HEALTH_HASH_MODE=latest \
  "$repo_root/scripts/check-offsite-backups.sh" >/dev/null 2>&1; then
  echo "Production health unexpectedly accepted partial ciphertext hashing" >&2
  exit 1
fi

scratch_receipt="$test_root/independent-scratch.receipt"
{
  printf 'receipt_format=medtrack-independent-scratch-restore-v1\n'
  printf 'completed_epoch=%s\n' "$(date -u +%s)"
  printf 'alert_contract=required\n'
} > "$scratch_receipt"
MEDTRACK_HEALTH_PRODUCTION_MODE=1 MEDTRACK_HEALTH_HASH_MODE=all \
  MEDTRACK_SCRATCH_RESTORE_RECEIPT="$scratch_receipt" \
  "$repo_root/scripts/check-offsite-backups.sh"

printf '0\n' > "$scratch_receipt"
if MEDTRACK_HEALTH_PRODUCTION_MODE=1 MEDTRACK_HEALTH_HASH_MODE=all \
  MEDTRACK_SCRATCH_RESTORE_RECEIPT="$scratch_receipt" \
  "$repo_root/scripts/check-offsite-backups.sh" >/dev/null 2>&1; then
  echo "Production health unexpectedly accepted a stale/invalid independent restore receipt" >&2
  exit 1
fi

cat > "$test_root/alert-hook" <<'ALERT'
#!/usr/bin/env bash
printf '%s\n' "$1" >> "$FAKE_ALERT_LOG"
ALERT
cat > "$test_root/failing-scratch-hook" <<'FAIL_SCRATCH'
#!/usr/bin/env bash
exit 1
FAIL_SCRATCH
chmod +x "$test_root/alert-hook" "$test_root/failing-scratch-hook"
export FAKE_ALERT_LOG="$test_root/alerts.log"
set +e
runner_output="$(MEDTRACK_SCRATCH_RESTORE_HOOK="$test_root/failing-scratch-hook" \
  MEDTRACK_SCRATCH_RESTORE_ALERT_HOOK="$test_root/alert-hook" \
  MEDTRACK_SCRATCH_RESTORE_RECEIPT="$test_root/runner.receipt" \
  "$repo_root/scripts/run-offsite-scratch-restore.sh" 2>&1)"
runner_exit=$?
set -e
if (( runner_exit == 0 )); then
  echo "Independent scratch runner unexpectedly hid restore failure" >&2
  exit 1
fi
if [[ ! -f "$FAKE_ALERT_LOG" ]]; then
  echo "Independent scratch runner did not invoke its required alert hook" >&2
  printf '%s\n' "$runner_output" >&2
  exit 1
fi
grep -Fq 'scratch restore failed' "$FAKE_ALERT_LOG"

printf 'corrupt-ciphertext\n' >> "$fake_remote/medtrack/test/daily/medtrack-prod-daily-${remote_stamp}.tar.age"
if "$repo_root/scripts/check-offsite-backups.sh" >/dev/null 2>&1; then
  echo "Health check unexpectedly accepted corrupt ciphertext" >&2
  exit 1
fi

echo "OFFSITE_HEALTH_TEST_OK"
