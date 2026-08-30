#!/usr/bin/env bash
set -Eeuo pipefail

config_file="${MEDTRACK_BACKUP_CONFIG:-/etc/medtrack-backup/backup.env}"
if [[ -r "$config_file" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$config_file"
  set +a
fi

evidence_root="${MEDTRACK_SECURITY_EVIDENCE_ROOT:-/srv/medtrack/security-evidence}"
maximum_age="${MEDTRACK_SECURITY_EVIDENCE_MAX_AGE_SECONDS:-7200}"
allow_stale="${MEDTRACK_SECURITY_EVIDENCE_ALLOW_STALE:-0}"
state_file="$evidence_root/state/checkpoint.env"
segments_root="$evidence_root/segments"
anchor_file="$evidence_root/state/anchor.env"
if [[ ! "$maximum_age" =~ ^[1-9][0-9]*$ || ! "$allow_stale" =~ ^[01]$ ||
  ! -f "$state_file" || ! -d "$segments_root" ]]; then
  echo "SECURITY_EVIDENCE_HEALTH_FAIL reason=missing-or-invalid-state" >&2
  exit 1
fi

value() { sed -n "s/^$2=//p" "$1" | tail -n 1 | tr -d '\r'; }
expected_sequence=1
expected_previous="$(printf 'MEDTRACK_SECURITY_EVIDENCE_CHAIN_V1\n' | sha256sum | awk '{print $1}')"
if [[ -f "$anchor_file" ]]; then
  anchor_format="$(value "$anchor_file" anchor_format)"
  expected_sequence="$(value "$anchor_file" next_sequence)"
  expected_previous="$(value "$anchor_file" previous_chain_sha256)"
  if [[ "$anchor_format" != "medtrack-security-evidence-anchor-v1" ||
    ! "$expected_sequence" =~ ^[1-9][0-9]*$ || ! "$expected_previous" =~ ^[0-9a-f]{64}$ ]]; then
    echo "SECURITY_EVIDENCE_HEALTH_FAIL reason=invalid-retention-anchor" >&2
    exit 1
  fi
fi
first_sequence="$expected_sequence"
segment_count=0
segment_list="$(find "$segments_root" -mindepth 1 -maxdepth 1 -type d -name 'segment-*' -print)" || {
  echo "SECURITY_EVIDENCE_HEALTH_FAIL reason=segment-enumeration-failed" >&2
  exit 1
}
while IFS= read -r segment_dir; do
  [[ -z "$segment_dir" ]] && continue
  segment_count=$((segment_count + 1))
  sequence="$(value "$segment_dir/segment.meta" sequence)"
  previous="$(value "$segment_dir/segment.meta" previous_chain_sha256)"
  manifest_hash="$(sha256sum "$segment_dir/manifest.sha256" | awk '{print $1}')"
  recorded_manifest="$(value "$segment_dir/chain.env" manifest_sha256)"
  recorded_chain="$(value "$segment_dir/chain.env" chain_sha256)"
  calculated_chain="$(printf '%s\n%s\n' "$previous" "$manifest_hash" | sha256sum | awk '{print $1}')"
  if [[ "$sequence" != "$expected_sequence" || "$previous" != "$expected_previous" ||
    "$recorded_manifest" != "$manifest_hash" || "$recorded_chain" != "$calculated_chain" ]]; then
    echo "SECURITY_EVIDENCE_HEALTH_FAIL reason=chain-discontinuity segment=${segment_dir##*/}" >&2
    exit 1
  fi
  (
    cd "$segment_dir"
    sha256sum --check --strict manifest.sha256 >/dev/null
  )
  expected_previous="$recorded_chain"
  expected_sequence=$((expected_sequence + 1))
done < <(printf '%s\n' "$segment_list" | sed '/^$/d' | sort)

state_sequence="$(value "$state_file" sequence)"
state_chain="$(value "$state_file" chain_sha256)"
completed_epoch="$(value "$state_file" completed_epoch)"
last_sequence=$((first_sequence + segment_count - 1))
if (( segment_count < 1 )) || [[ "$state_sequence" != "$last_sequence" || "$state_chain" != "$expected_previous" ||
  ! "$completed_epoch" =~ ^[0-9]+$ ]]; then
  echo "SECURITY_EVIDENCE_HEALTH_FAIL reason=checkpoint-mismatch" >&2
  exit 1
fi
age=$(($(date -u +%s) - completed_epoch))
if (( age < 0 || (allow_stale == 0 && age > maximum_age) )); then
  echo "SECURITY_EVIDENCE_HEALTH_FAIL reason=export-lag age_seconds=$age maximum_seconds=$maximum_age" >&2
  exit 1
fi
echo "SECURITY_EVIDENCE_HEALTH_OK segments=$segment_count chain_sha256=$state_chain age_seconds=$age"
