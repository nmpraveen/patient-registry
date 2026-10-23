#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# Install the finalizer before loading private config: preflight is an attempt too.
started_epoch="$(date -u +%s)"
attempt_id="${started_epoch}-$$-${RANDOM}"
attempt_claimed=0
state_writer="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scratch_restore_state.py"
stage=config
write_attempt() {
  local status="$1" alert="$2" target
  local -a claim=()
  target="${MEDTRACK_SCRATCH_RESTORE_ATTEMPT:-${MEDTRACK_SCRATCH_RESTORE_RECEIPT:-}.attempt}"
  [[ "$target" == /* && ! -L "$target" && "$target" != "${MEDTRACK_SCRATCH_RESTORE_RECEIPT:-}" ]] || return 1
  if (( attempt_claimed == 0 )); then claim=(--claim); attempt_claimed=1; fi
  "${PYTHON_COMMAND:-python3}" "$state_writer" --attempt "$target" \
    --receipt "${MEDTRACK_SCRATCH_RESTORE_RECEIPT:-}" --attempt-id "$attempt_id" \
    --started-epoch "$started_epoch" --stage "$stage" --status "$status" --alert "$alert" "${claim[@]}"
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
stage=restore
"$scratch_restore_hook"
stage=complete
write_attempt success not-needed
echo "OFFSITE_SCRATCH_RESTORE_OK receipt=$receipt"
