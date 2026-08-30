#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

config_file="${MEDTRACK_BACKUP_CONFIG:-/etc/medtrack-backup/backup.env}"
if [[ -r "$config_file" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$config_file"
  set +a
fi

scratch_restore_hook="${MEDTRACK_SCRATCH_RESTORE_HOOK:-}"
alert_hook="${MEDTRACK_SCRATCH_RESTORE_ALERT_HOOK:-}"
receipt="${MEDTRACK_SCRATCH_RESTORE_RECEIPT:-}"

if [[ -z "$scratch_restore_hook" || "$scratch_restore_hook" != /* || ! -x "$scratch_restore_hook" ||
  -z "$alert_hook" || "$alert_hook" != /* || ! -x "$alert_hook" ||
  -z "$receipt" || "$receipt" != /* ]]; then
  echo "Independent scratch restore requires absolute executable restore/alert hooks and an absolute receipt path" >&2
  exit 1
fi

receipt_dir="$(dirname "$receipt")"
if [[ ! -d "$receipt_dir" ]]; then
  install -d -m 0700 "$receipt_dir"
fi
rm -f -- "$receipt"
if ! "$scratch_restore_hook"; then
  "$alert_hook" "MEDTRACK independent encrypted-backup scratch restore failed" || true
  echo "OFFSITE_SCRATCH_RESTORE_FAIL alert_attempted=true" >&2
  exit 1
fi

receipt_tmp="$(mktemp "$(dirname "$receipt")/.scratch-restore.XXXXXX")"
{
  printf 'receipt_format=medtrack-independent-scratch-restore-v1\n'
  printf 'completed_epoch=%s\n' "$(date -u +%s)"
  printf 'alert_contract=required\n'
} > "$receipt_tmp"
chmod 0600 "$receipt_tmp"
mv "$receipt_tmp" "$receipt"
echo "OFFSITE_SCRATCH_RESTORE_OK receipt=$receipt"
