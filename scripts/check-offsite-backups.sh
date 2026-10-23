#!/usr/bin/env bash
set -Eeuo pipefail

config_file="${MEDTRACK_BACKUP_CONFIG:-/etc/medtrack-backup/backup.env}"
if [[ -r "$config_file" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$config_file"
  set +a
fi

rclone_config="${RCLONE_CONFIG:-/srv/medtrack/backup-secrets/rclone.conf}"
rclone_remote="${RCLONE_REMOTE:-medtrack-drive:Naveen-Hospital-Backups/MEDTRACK/production}"
hash_mode="${MEDTRACK_HEALTH_HASH_MODE:-all}"
scratch_restore_hook="${MEDTRACK_SCRATCH_RESTORE_HOOK:-}"
require_scratch_restore_hook="${MEDTRACK_REQUIRE_SCRATCH_RESTORE_HOOK:-0}"
production_mode="${MEDTRACK_HEALTH_PRODUCTION_MODE:-0}"
scratch_restore_receipt="${MEDTRACK_SCRATCH_RESTORE_RECEIPT:-}"
scratch_restore_attempt="${MEDTRACK_SCRATCH_RESTORE_ATTEMPT:-$scratch_restore_receipt.attempt}"
scratch_restore_max_age="${MEDTRACK_SCRATCH_RESTORE_MAX_AGE_SECONDS:-691200}"
security_evidence_health_hook="${MEDTRACK_SECURITY_EVIDENCE_HEALTH_HOOK:-}"
health_state_root="${MEDTRACK_HEALTH_STATE_ROOT:-/var/lib/medtrack-backup-health}"
scrub_maximum_age="${MEDTRACK_FULL_SCRUB_MAX_AGE_SECONDS:-691200}"
python_command="${PYTHON_COMMAND:-python3}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --hash-mode) [[ $# -ge 2 ]] || exit 2; hash_mode="$2"; shift 2 ;;
    --production) production_mode=1; shift ;;
    *) echo "Usage: check-offsite-backups.sh [--hash-mode all|incremental|latest] [--production]" >&2; exit 2 ;;
  esac
done

if [[ ! -f "$rclone_config" ]]; then
  echo "Missing rclone configuration: $rclone_config" >&2
  exit 1
fi
if [[ "$hash_mode" != "latest" && "$hash_mode" != "all" && "$hash_mode" != "incremental" ]]; then
  echo "MEDTRACK_HEALTH_HASH_MODE must be latest, incremental, or all" >&2
  exit 1
fi
if [[ "$production_mode" == "1" && "$hash_mode" == "latest" ]]; then
  echo "Production health requires all objects to be checked, with periodic full stream hashing" >&2
  exit 1
fi
if [[ "$production_mode" == "1" && ! "$scratch_restore_max_age" =~ ^[1-9][0-9]*$ ]]; then
  echo "MEDTRACK_SCRATCH_RESTORE_MAX_AGE_SECONDS must be a positive integer" >&2
  exit 1
fi

now_epoch="$(date -u +%s)"
failed=0
if [[ "$health_state_root" != /* || -L "$health_state_root" || ! "$scrub_maximum_age" =~ ^[1-9][0-9]*$ ]]; then
  echo "Invalid health state directory or scrub interval" >&2; exit 1
fi
umask 077
install -d -m 0700 "$health_state_root"
run_state="$(mktemp -d "$health_state_root/.metadata.XXXXXX")"
trap 'chmod u+w "$run_state/catalog.json" 2>/dev/null || true; rm -rf -- "$run_state"' EXIT
catalog_snapshot="$run_state/catalog.json"
catalog_binding="$("$python_command" "$repo_root/scripts/offsite_legacy_catalog.py" snapshot \
  --catalog "${MEDTRACK_LEGACY_CATALOG:-}" --sha256 "${MEDTRACK_LEGACY_CATALOG_SHA256:-}" \
  --namespace "$rclone_remote" --output "$catalog_snapshot")"
read -r metadata_policy catalog_sha256 snapshot_sha256 <<< "$catalog_binding"
remote_identity="$(printf '%s' "$rclone_remote" | sha256sum | awk '{print $1}')"
scrub_receipt="$health_state_root/full-scrub-$remote_identity.receipt"
if [[ "$production_mode" == "1" && "$hash_mode" == "incremental" ]]; then
  scrub_epoch="$(sed -n 's/^completed_epoch=//p' "$scrub_receipt" 2>/dev/null || true)"
  scrub_format="$(sed -n 's/^receipt_format=//p' "$scrub_receipt" 2>/dev/null || true)"
  scrub_policy="$(sed -n 's/^metadata_policy=//p' "$scrub_receipt" 2>/dev/null || true)"
  scrub_catalog="$(sed -n 's/^legacy_catalog_sha256=//p' "$scrub_receipt" 2>/dev/null || true)"
  if [[ "$scrub_format" != "medtrack-full-ciphertext-scrub-v2" || "$scrub_policy" != "$metadata_policy" ||
    "$scrub_catalog" != "$catalog_sha256" || ! "$scrub_epoch" =~ ^[0-9]+$ ]] || (( now_epoch - scrub_epoch < 0 || now_epoch - scrub_epoch > scrub_maximum_age )); then
    echo "OFFSITE_BACKUP_HEALTH_FAIL reason=missing-or-stale-full-scrub" >&2; exit 1
  fi
fi

remote_cat() {
  rclone --config "$rclone_config" cat "$1"
}

verify_remote_hash() {
  local remote_archive="$1"
  local expected_hash="$2"
  local expected_size="$3"
  local actual_hash
  local -a size_arguments=()
  [[ "$expected_size" == "-" ]] || size_arguments=(--size "$expected_size")
  if [[ "$hash_mode" == "incremental" || "$hash_mode" == "all" || "$expected_size" != "-" ]]; then
    local object_mode="$hash_mode"
    [[ "$object_mode" != "latest" ]] || object_mode=all
    "$python_command" "$repo_root/scripts/offsite_health_state.py" \
      --remote "$remote_archive" --sha256 "$expected_hash" --config "$rclone_config" \
      --cache-root "$health_state_root/objects" --mode "$object_mode" --maximum-age "$scrub_maximum_age" \
      --policy "$metadata_policy:$catalog_sha256" "${size_arguments[@]}" >/dev/null
    return
  fi
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
  local archive checksum marker_hash metadata expected_size completed_utc completed_iso
  local -a latest_arguments=()
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

    # Preserve raw bytes: shell command substitution strips trailing newlines.
    if ! remote_cat "$remote_tier/$marker" > "$run_state/marker" ||
      ! remote_cat "$remote_tier/$checksum" > "$run_state/checksum"; then
      echo "OFFSITE_BACKUP_HEALTH_FAIL tier=$tier reason=metadata-read-failed" >&2
      failed=1
      return
    fi
    latest_arguments=()
    [[ "$marker" != "$latest_marker" ]] || latest_arguments=(--latest)
    if ! metadata="$("$python_command" "$repo_root/scripts/offsite_legacy_catalog.py" check \
      --snapshot "$catalog_snapshot" --snapshot-sha256 "$snapshot_sha256" --namespace "$rclone_remote" \
      --tier "$tier" --archive "$archive" --marker-file "$run_state/marker" \
      --checksum-file "$run_state/checksum" "${latest_arguments[@]}")"; then
      echo "OFFSITE_BACKUP_HEALTH_FAIL tier=$tier reason=invalid-marker-or-checksum marker=$marker" >&2
      failed=1
      return
    fi
    read -r marker_hash completed_utc expected_size <<< "$metadata"

    if [[ "$hash_mode" == "all" || "$hash_mode" == "incremental" || "$marker" == "$latest_marker" || "$expected_size" != "-" ]]; then
      if ! verify_remote_hash "$remote_tier/$archive" "$marker_hash" "$expected_size"; then
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
  if [[ -z "$security_evidence_health_hook" || "$security_evidence_health_hook" != /* ||
    ! -x "$security_evidence_health_hook" ]]; then
    echo "OFFSITE_BACKUP_HEALTH_FAIL reason=missing-security-evidence-health-hook" >&2
    failed=1
  elif ! "$security_evidence_health_hook"; then
    echo "OFFSITE_BACKUP_HEALTH_FAIL reason=security-evidence-chain-or-lag" >&2
    failed=1
  else
    echo "OFFSITE_BACKUP_SECURITY_EVIDENCE_OK"
  fi
fi

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
    elif ! "$python_command" "$repo_root/scripts/verify_scratch_attempt.py" \
      "$scratch_restore_attempt" "$scratch_restore_receipt" "$now_epoch"; then
      echo "OFFSITE_BACKUP_HEALTH_FAIL reason=invalid-or-unsuccessful-scratch-attempt" >&2
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
"$python_command" "$repo_root/scripts/offsite_legacy_catalog.py" verify-snapshot \
  --snapshot "$catalog_snapshot" --snapshot-sha256 "$snapshot_sha256" --namespace "$rclone_remote"
if [[ "$hash_mode" == "all" ]]; then
  receipt_tmp="$(mktemp "$health_state_root/.full-scrub.XXXXXX")"
  printf 'receipt_format=medtrack-full-ciphertext-scrub-v2\ncompleted_epoch=%s\nmetadata_policy=%s\nlegacy_catalog_sha256=%s\n' \
    "$(date -u +%s)" "$metadata_policy" "$catalog_sha256" > "$receipt_tmp"
  mv "$receipt_tmp" "$scrub_receipt"
fi
echo "OFFSITE_BACKUP_HEALTH_OK"
