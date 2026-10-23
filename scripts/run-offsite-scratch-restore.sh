#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# Install the finalizer before loading private config: preflight is an attempt too.
started_epoch="$(date -u +%s)"
attempt_id="${started_epoch}-$$-${RANDOM}"
receipt_hash=none
stage=config
write_attempt() {
  local status="$1" alert="$2" target tmp
  target="${MEDTRACK_SCRATCH_RESTORE_ATTEMPT:-${MEDTRACK_SCRATCH_RESTORE_RECEIPT:-}.attempt}"
  [[ "$target" == /* && ! -L "$target" && "$target" != "${MEDTRACK_SCRATCH_RESTORE_RECEIPT:-}" ]] || return 1
  install -d -m 0700 "$(dirname "$target")" || return 1
  tmp="$(mktemp "$(dirname "$target")/.scratch-attempt.XXXXXX")" || return 1
  {
    printf 'attempt_format=medtrack-independent-scratch-attempt-v1\n'
    printf 'attempt_id=%s\nstatus=%s\nstarted_epoch=%s\nupdated_epoch=%s\n' "$attempt_id" "$status" "$started_epoch" "$(date -u +%s)"
    printf 'stage=%s\nalert_delivery=%s\nreceipt_sha256=%s\n' "$stage" "$alert" "$receipt_hash"
  } > "$tmp" && chmod 0600 "$tmp" && mv -f -- "$tmp" "$target"
}
finish() {
  local code=$? delivery=failed alert_hook="${MEDTRACK_SCRATCH_RESTORE_ALERT_HOOK:-}"
  trap - EXIT
  if (( code != 0 )); then
    write_attempt failure pending || echo 'OFFSITE_SCRATCH_RESTORE_FAIL attempt_write=failed' >&2
    if [[ "$alert_hook" == /* && -x "$alert_hook" ]] &&
      "$alert_hook" "MEDTRACK independent encrypted-backup scratch restore failed stage=$stage" >/dev/null 2>&1; then
      delivery=delivered
    fi
    write_attempt failure "$delivery" || echo 'OFFSITE_SCRATCH_RESTORE_FAIL attempt_write=failed' >&2
    echo "OFFSITE_SCRATCH_RESTORE_FAIL stage=$stage alert_delivery=$delivery" >&2
    [[ "$delivery" == delivered ]] || code=2
  fi
  exit "$code"
}
trap finish EXIT
config_file="${MEDTRACK_BACKUP_CONFIG:-/etc/medtrack-backup/backup.env}"
if [[ -r "$config_file" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$config_file"
  set +a
fi
stage=preflight
write_attempt running not-needed
scratch_restore_hook="${MEDTRACK_SCRATCH_RESTORE_HOOK:-}"
alert_hook="${MEDTRACK_SCRATCH_RESTORE_ALERT_HOOK:-}"
receipt="${MEDTRACK_SCRATCH_RESTORE_RECEIPT:-}"
if [[ "$scratch_restore_hook" != /* || ! -x "$scratch_restore_hook" ||
  "$alert_hook" != /* || ! -x "$alert_hook" || "$receipt" != /* || -L "$receipt" ||
  "${MEDTRACK_SCRATCH_RESTORE_ATTEMPT:-$receipt.attempt}" == "$receipt" ]]; then
  echo 'Independent scratch restore requires separate absolute state paths and executable restore/alert hooks' >&2
  exit 1
fi
install -d -m 0700 "$(dirname "$receipt")"
stage=restore
"$scratch_restore_hook"
stage=receipt
completed_epoch="$(date -u +%s)"
receipt_tmp="$(mktemp "$(dirname "$receipt")/.scratch-restore.XXXXXX")"
{
  printf 'receipt_format=medtrack-independent-scratch-restore-v1\n'
  printf 'completed_epoch=%s\nattempt_id=%s\nalert_contract=required\n' "$completed_epoch" "$attempt_id"
} > "$receipt_tmp"
chmod 0600 "$receipt_tmp"
mv -f -- "$receipt_tmp" "$receipt"
receipt_hash="$(sha256sum "$receipt" | awk '{print $1}')"
stage=complete
write_attempt success not-needed
echo "OFFSITE_SCRATCH_RESTORE_OK receipt=$receipt"
