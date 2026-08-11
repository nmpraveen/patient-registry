#!/usr/bin/env bash
set -Eeuo pipefail

config_file="${MEDTRACK_BACKUP_CONFIG:-/etc/medtrack-backup/backup.env}"
if [[ -r "$config_file" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$config_file"
  set +a
fi

backup_root="${MEDTRACK_OFFSITE_ROOT:-/srv/medtrack/offsite-backups}"
state_root="${MEDTRACK_BACKUP_STATE_ROOT:-$backup_root/state}"
rclone_config="${RCLONE_CONFIG:-/srv/medtrack/backup-secrets/rclone.conf}"
rclone_remote="${RCLONE_REMOTE:-medtrack-drive:Naveen-Hospital-Backups/MEDTRACK/production}"

if [[ ! -f "$rclone_config" ]]; then
  echo "Missing rclone configuration: $rclone_config" >&2
  exit 1
fi

now_epoch="$(date -u +%s)"
failed=0

check_tier() {
  local tier="$1"
  local maximum_age="$2"
  local maximum_count="$3"
  local state_file="$state_root/last-success-$tier.epoch"
  local success_epoch age marker_count remote_tier

  if [[ ! -f "$state_file" ]]; then
    echo "OFFSITE_BACKUP_HEALTH_FAIL tier=$tier reason=missing-success-state" >&2
    failed=1
    return
  fi
  success_epoch="$(tr -d '[:space:]' < "$state_file")"
  if [[ ! "$success_epoch" =~ ^[0-9]+$ ]]; then
    echo "OFFSITE_BACKUP_HEALTH_FAIL tier=$tier reason=invalid-success-state" >&2
    failed=1
    return
  fi
  age=$((now_epoch - success_epoch))
  if (( age < 0 || age > maximum_age )); then
    echo "OFFSITE_BACKUP_HEALTH_FAIL tier=$tier age_seconds=$age maximum_seconds=$maximum_age" >&2
    failed=1
    return
  fi

  remote_tier="${rclone_remote%/}/$tier"
  marker_count="$(rclone --config "$rclone_config" lsf "$remote_tier" --files-only --include "medtrack-prod-${tier}-*.tar.age.complete" | wc -l)"
  marker_count="${marker_count//[[:space:]]/}"
  if [[ ! "$marker_count" =~ ^[0-9]+$ || "$marker_count" -lt 1 || "$marker_count" -gt "$maximum_count" ]]; then
    echo "OFFSITE_BACKUP_HEALTH_FAIL tier=$tier remote_complete_markers=$marker_count expected=1..$maximum_count" >&2
    failed=1
    return
  fi
  echo "OFFSITE_BACKUP_HEALTH tier=$tier age_seconds=$age remote_complete_markers=$marker_count"
}

check_tier rapid 28800 28
check_tier daily 129600 30
check_tier weekly 691200 12
check_tier monthly 3024000 12

if (( failed != 0 )); then
  exit 1
fi

rclone --config "$rclone_config" about "${rclone_remote%%:*}:" --json
echo "OFFSITE_BACKUP_HEALTH_OK"
