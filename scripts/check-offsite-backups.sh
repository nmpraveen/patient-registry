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
hash_mode="${MEDTRACK_HEALTH_HASH_MODE:-all}"
scratch_restore_hook="${MEDTRACK_SCRATCH_RESTORE_HOOK:-}"
require_scratch_restore_hook="${MEDTRACK_REQUIRE_SCRATCH_RESTORE_HOOK:-0}"
production_mode="${MEDTRACK_HEALTH_PRODUCTION_MODE:-0}"
scratch_restore_receipt="${MEDTRACK_SCRATCH_RESTORE_RECEIPT:-}"
scratch_restore_max_age="${MEDTRACK_SCRATCH_RESTORE_MAX_AGE_SECONDS:-691200}"

if [[ ! -f "$rclone_config" ]]; then
  echo "Missing rclone configuration: $rclone_config" >&2
  exit 1
fi
if [[ "$hash_mode" != "latest" && "$hash_mode" != "all" ]]; then
  echo "MEDTRACK_HEALTH_HASH_MODE must be latest or all" >&2
  exit 1
fi
if [[ "$production_mode" == "1" && "$hash_mode" != "all" ]]; then
  echo "Production off-site health requires full hashing of every retained ciphertext" >&2
  exit 1
fi
if [[ "$production_mode" == "1" && ! "$scratch_restore_max_age" =~ ^[1-9][0-9]*$ ]]; then
  echo "MEDTRACK_SCRATCH_RESTORE_MAX_AGE_SECONDS must be a positive integer" >&2
  exit 1
fi

now_epoch="$(date -u +%s)"
failed=0

remote_cat() {
  rclone --config "$rclone_config" cat "$1"
}

receipt_value() {
  local content="$1"
  local key="$2"
  printf '%s\n' "$content" | sed -n "s/^${key}=//p" | tail -n 1 | tr -d '\r'
}

verify_remote_hash() {
  local remote_archive="$1"
  local expected_hash="$2"
  local actual_hash
  actual_hash="$(rclone --config "$rclone_config" cat "$remote_archive" | sha256sum | awk '{print $1}')"
  if [[ "$actual_hash" != "$expected_hash" ]]; then
    echo "OFFSITE_BACKUP_HEALTH_FAIL archive=${remote_archive##*/} reason=ciphertext-hash-mismatch" >&2
    return 1
  fi
}

check_tier() {
  local tier="$1"
  local maximum_age="$2"
  local maximum_count="$3"
  local success_epoch age marker_count remote_tier latest_marker marker listing remote_listing
  local marker_content checksum_content archive checksum expected_hash marker_hash checksum_hash checksum_file
  local completed_utc marker_stamp
  local -a remote_files=()
  local -a markers=()

  remote_tier="${rclone_remote%/}/$tier"
  if ! remote_listing="$(rclone --config "$rclone_config" lsf "$remote_tier" --files-only)"; then
    echo "OFFSITE_BACKUP_HEALTH_FAIL tier=$tier reason=remote-listing-failed" >&2
    failed=1
    return
  fi
  mapfile -t remote_files < <(printf '%s\n' "$remote_listing" | tr -d '\r' | sed '/^$/d' | sort)
  for listing in "${remote_files[@]}"; do
    if [[ "$listing" == medtrack-prod-"$tier"-*.tar.age.complete ]]; then
      markers+=("$listing")
    elif [[ "$listing" != medtrack-prod-"$tier"-*.tar.age && "$listing" != medtrack-prod-"$tier"-*.tar.age.sha256 ]]; then
      echo "OFFSITE_BACKUP_HEALTH_FAIL tier=$tier reason=unexpected-object object=$listing" >&2
      failed=1
      return
    fi
  done

  marker_count="${#markers[@]}"
  if (( marker_count < 1 || marker_count > maximum_count )); then
    echo "OFFSITE_BACKUP_HEALTH_FAIL tier=$tier remote_complete_markers=$marker_count expected=1..$maximum_count" >&2
    failed=1
    return
  fi
  if (( ${#remote_files[@]} != marker_count * 3 )); then
    echo "OFFSITE_BACKUP_HEALTH_FAIL tier=$tier reason=incomplete-or-orphaned-triplet objects=${#remote_files[@]} markers=$marker_count" >&2
    failed=1
    return
  fi

  latest_marker="${markers[$((marker_count - 1))]}"
  for marker in "${markers[@]}"; do
    if [[ ! "$marker" =~ ^medtrack-prod-${tier}-[0-9]{8}T[0-9]{6}Z\.tar\.age\.complete$ ]]; then
      echo "OFFSITE_BACKUP_HEALTH_FAIL tier=$tier reason=invalid-marker-name object=$marker" >&2
      failed=1
      return
    fi
    archive="${marker%.complete}"
    checksum="$archive.sha256"
    if ! printf '%s\n' "${remote_files[@]}" | grep -Fxq "$archive" ||
      ! printf '%s\n' "${remote_files[@]}" | grep -Fxq "$checksum"; then
      echo "OFFSITE_BACKUP_HEALTH_FAIL tier=$tier reason=missing-triplet-member marker=$marker" >&2
      failed=1
      return
    fi

    marker_content="$(remote_cat "$remote_tier/$marker")"
    checksum_content="$(remote_cat "$remote_tier/$checksum")"
    marker_hash="$(receipt_value "$marker_content" sha256)"
    completed_utc="$(receipt_value "$marker_content" completed_utc)"
    marker_stamp="${archive#medtrack-prod-${tier}-}"
    marker_stamp="${marker_stamp%.tar.age}"
    checksum_hash="$(printf '%s\n' "$checksum_content" | awk 'NR==1 {print $1}')"
    checksum_file="$(printf '%s\n' "$checksum_content" | awk 'NR==1 {print $2}')"
    if [[ "$(receipt_value "$marker_content" archive)" != "$archive" ||
      ! "$marker_hash" =~ ^[0-9a-f]{64}$ ||
      "$checksum_hash" != "$marker_hash" ||
      "$checksum_file" != "$archive" || "$completed_utc" != "$marker_stamp" ]]; then
      echo "OFFSITE_BACKUP_HEALTH_FAIL tier=$tier reason=invalid-marker-or-checksum marker=$marker" >&2
      failed=1
      return
    fi

    if [[ "$hash_mode" == "all" || "$marker" == "$latest_marker" ]]; then
      expected_hash="$marker_hash"
      if ! verify_remote_hash "$remote_tier/$archive" "$expected_hash"; then
        failed=1
        return
      fi
    fi

    if [[ "$marker" == "$latest_marker" ]]; then
      completed_iso="${completed_utc:0:4}-${completed_utc:4:2}-${completed_utc:6:2}T${completed_utc:9:2}:${completed_utc:11:2}:${completed_utc:13:2}Z"
      if ! success_epoch="$(date -u -d "$completed_iso" +%s 2>/dev/null)" || [[ ! "$success_epoch" =~ ^[0-9]+$ ]]; then
        echo "OFFSITE_BACKUP_HEALTH_FAIL tier=$tier reason=invalid-remote-completion-time marker=$marker" >&2
        failed=1
        return
      fi
      age=$((now_epoch - success_epoch))
      if (( age < 0 || age > maximum_age )); then
        echo "OFFSITE_BACKUP_HEALTH_FAIL tier=$tier age_seconds=$age maximum_seconds=$maximum_age source=remote-marker" >&2
        failed=1
        return
      fi
    fi
  done
  echo "OFFSITE_BACKUP_HEALTH tier=$tier age_seconds=$age freshness_source=remote-marker triplets=$marker_count ciphertext_hash_mode=$hash_mode"
}

check_tier rapid 28800 28
check_tier daily 129600 30
check_tier weekly 691200 12
check_tier monthly 3024000 12

if [[ "$production_mode" == "1" ]]; then
  if [[ -z "$scratch_restore_receipt" || "$scratch_restore_receipt" != /* || ! -f "$scratch_restore_receipt" ]]; then
    echo "OFFSITE_BACKUP_HEALTH_FAIL reason=missing-independent-scratch-restore-receipt" >&2
    failed=1
  else
    scratch_receipt_format="$(sed -n 's/^receipt_format=//p' "$scratch_restore_receipt" | tail -n 1)"
    scratch_completed_epoch="$(sed -n 's/^completed_epoch=//p' "$scratch_restore_receipt" | tail -n 1)"
    scratch_alert_contract="$(sed -n 's/^alert_contract=//p' "$scratch_restore_receipt" | tail -n 1)"
    if [[ "$scratch_receipt_format" != "medtrack-independent-scratch-restore-v1" ||
      "$scratch_alert_contract" != "required" || ! "$scratch_completed_epoch" =~ ^[0-9]+$ ||
      $((now_epoch - scratch_completed_epoch)) -lt 0 || $((now_epoch - scratch_completed_epoch)) -gt scratch_restore_max_age ]]; then
      echo "OFFSITE_BACKUP_HEALTH_FAIL reason=stale-or-invalid-independent-scratch-restore-receipt" >&2
      failed=1
    else
      echo "OFFSITE_BACKUP_INDEPENDENT_SCRATCH_RESTORE_OK age_seconds=$((now_epoch - scratch_completed_epoch))"
    fi
  fi
elif [[ -n "$scratch_restore_hook" ]]; then
  if [[ "$scratch_restore_hook" != /* || ! -x "$scratch_restore_hook" ]]; then
    echo "OFFSITE_BACKUP_HEALTH_FAIL reason=invalid-scratch-restore-hook" >&2
    failed=1
  elif ! "$scratch_restore_hook"; then
    echo "OFFSITE_BACKUP_HEALTH_FAIL reason=scratch-restore-hook-failed" >&2
    failed=1
  else
    echo "OFFSITE_BACKUP_SCRATCH_RESTORE_HOOK_OK"
  fi
elif [[ "$require_scratch_restore_hook" == "1" ]]; then
  echo "OFFSITE_BACKUP_HEALTH_FAIL reason=required-scratch-restore-hook-missing" >&2
  failed=1
fi

if (( failed != 0 )); then
  exit 1
fi

rclone --config "$rclone_config" about "${rclone_remote%%:*}:" --json
echo "OFFSITE_BACKUP_HEALTH_OK"
