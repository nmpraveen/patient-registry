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

repo_root="${MEDTRACK_REPO_ROOT:-/srv/medtrack/app}"
evidence_root="${MEDTRACK_SECURITY_EVIDENCE_ROOT:-/srv/medtrack/security-evidence}"
log_root="${MEDTRACK_SECURITY_LOG_DIR:-/srv/medtrack/security-logs}"
alert_hook="${MEDTRACK_SECURITY_EVIDENCE_ALERT_HOOK:-}"
maximum_rows="${MEDTRACK_AUDIT_EXPORT_MAX_ROWS:-10000}"
maximum_log_bytes="${MEDTRACK_SECURITY_LOG_EXPORT_MAX_BYTES:-10485760}"
maximum_lag="${MEDTRACK_SECURITY_EVIDENCE_MAX_LAG_SECONDS:-7200}"
keep_segments="${MEDTRACK_SECURITY_EVIDENCE_KEEP_SEGMENTS:-720}"
failure_alert_threshold="${MEDTRACK_SECURITY_FAILURE_ALERT_THRESHOLD:-25}"
audit_schema_head="f01f9311882c24b865f4ccd48dd32bc9933e6b7f"

if [[ "$repo_root" != /* || "$evidence_root" != /* || "$log_root" != /* ||
  ! "$maximum_rows" =~ ^[1-9][0-9]*$ || ! "$maximum_log_bytes" =~ ^[1-9][0-9]*$ ||
  ! "$maximum_lag" =~ ^[1-9][0-9]*$ || ! "$keep_segments" =~ ^[1-9][0-9]*$ ||
  ! "$failure_alert_threshold" =~ ^[1-9][0-9]*$ ||
  -z "$alert_hook" || "$alert_hook" != /* || ! -x "$alert_hook" ]]; then
  echo "Security evidence export requires absolute roots, bounded limits, and an executable alert hook" >&2
  exit 1
fi

alert_on_failure() {
  local exit_code=$?
  trap - ERR
  "$alert_hook" "MEDTRACK audit/security evidence export failed" || true
  exit "$exit_code"
}
trap alert_on_failure ERR

for command_name in docker find flock git install mktemp sha256sum sort tail; do
  command -v "$command_name" >/dev/null 2>&1 || { echo "Missing required command: $command_name" >&2; false; }
done
for private_dir in "$evidence_root" "$evidence_root/state" "$evidence_root/segments"; do
  if [[ ! -d "$private_dir" ]]; then install -d -m 0700 "$private_dir"; fi
done
exec 9>"$evidence_root/export.lock"
flock -n 9 || { echo "Another security evidence export owns the lock" >&2; exit 75; }

compose=(docker compose -f "$repo_root/docker-compose.yml" -f "$repo_root/docker-compose.prod.yml")
env_file="${MEDTRACK_ENV_FILE:-$repo_root/.env}"
if [[ -r "$env_file" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
fi
db_name="${POSTGRES_DB:-patient_registry}"
db_user="${POSTGRES_USER:-patient_registry}"
query_scalar() {
  "${compose[@]}" exec -T db psql --tuples-only --no-align --username="$db_user" --dbname="$db_name" --command="$1" | tr -d '[:space:]'
}

schema_present="$(query_scalar "SELECT CASE WHEN to_regclass('public.patients_auditevent') IS NOT NULL THEN 1 ELSE 0 END")"
trigger_present="$(query_scalar "SELECT count(*) FROM pg_trigger WHERE tgname='patients_auditevent_append_only' AND NOT tgisinternal")"
if [[ "$schema_present" != "1" || "$trigger_present" != "1" ]]; then
  echo "AuditEvent table or PostgreSQL append-only trigger is missing (contract PR #103 $audit_schema_head)" >&2
  false
fi

state_file="$evidence_root/state/checkpoint.env"
value() { sed -n "s/^$2=//p" "$1" | tail -n 1 | tr -d '\r'; }
if [[ -f "$state_file" ]]; then
  last_id="$(value "$state_file" last_audit_id)"
  previous_chain="$(value "$state_file" chain_sha256)"
  previous_sequence="$(value "$state_file" sequence)"
  [[ "$last_id" =~ ^[0-9]+$ && "$previous_chain" =~ ^[0-9a-f]{64}$ && "$previous_sequence" =~ ^[0-9]+$ ]] || false
  MEDTRACK_SECURITY_EVIDENCE_ALLOW_STALE=1 "$repo_root/scripts/verify-security-evidence.sh"
else
  last_id=0
  previous_sequence=0
  previous_chain="$(printf 'MEDTRACK_SECURITY_EVIDENCE_CHAIN_V1\n' | sha256sum | awk '{print $1}')"
fi

sequence=$((previous_sequence + 1))
created_utc="$(date -u +%Y%m%dT%H%M%SZ)"
export_max_id="$(query_scalar "SELECT COALESCE(max(id), $last_id) FROM (SELECT id FROM patients_auditevent WHERE id > $last_id ORDER BY id LIMIT $maximum_rows) bounded")"
[[ "$export_max_id" =~ ^[0-9]+$ && "$export_max_id" -ge "$last_id" ]] || false
stage_dir="$(mktemp -d "$evidence_root/.segment-${sequence}.XXXXXX")"
cleanup() { [[ -z "$stage_dir" ]] || rm -rf -- "$stage_dir"; }
trap cleanup EXIT

"${compose[@]}" exec -T db psql --tuples-only --no-align --username="$db_user" --dbname="$db_name" \
  --command="COPY (SELECT json_build_object('id',id,'event_id',event_id,'occurred_at',occurred_at,'category',category,'action',action,'outcome',outcome,'source',source)::text FROM patients_auditevent WHERE id > $last_id AND id <= $export_max_id ORDER BY id) TO STDOUT" \
  > "$stage_dir/audit-events.jsonl"
for safe_log in caddy-access.json gunicorn-access.log; do
  output_name="${safe_log%.*}.jsonl"
  if [[ -f "$log_root/$safe_log" ]]; then
    tail -c "$maximum_log_bytes" "$log_root/$safe_log" > "$stage_dir/$output_name"
  else
    : > "$stage_dir/$output_name"
  fi
done
if grep -Eqi 'authorization|cookie|query_string|request_body|patient[_ -]?search|clinical_payload|"uri"|"path"' \
  "$stage_dir/caddy-access.jsonl" "$stage_dir/gunicorn-access.jsonl"; then
  echo "Security request log contained a forbidden sensitive field" >&2
  false
fi
edge_429_count="$(grep -Ehc '"status"[[:space:]]*:[[:space:]]*429' \
  "$stage_dir/caddy-access.jsonl" "$stage_dir/gunicorn-access.jsonl" | awk '{total += $1} END {print total + 0}')"
audit_failure_count="$(grep -Eic '"outcome"[[:space:]]*:[[:space:]]*"(failure|denied|locked|lockout)"' \
  "$stage_dir/audit-events.jsonl" || true)"
if (( edge_429_count >= failure_alert_threshold || audit_failure_count >= failure_alert_threshold )); then
  "$alert_hook" "MEDTRACK sustained authentication failures detected edge_429=$edge_429_count audit_failures=$audit_failure_count" || true
fi
source_container="$("${compose[@]}" ps -q web)"
source_image="$(docker inspect --format '{{.Image}}' "$source_container")"
source_commit="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$source_image")"
{
  printf 'segment_format=medtrack-security-evidence-v1\n'
  printf 'sequence=%s\n' "$sequence"
  printf 'created_utc=%s\n' "$created_utc"
  printf 'source_commit=%s\n' "$source_commit"
  printf 'audit_schema_pr_head=%s\n' "$audit_schema_head"
  printf 'audit_start_id=%s\n' "$((last_id + 1))"
  printf 'audit_end_id=%s\n' "$export_max_id"
  printf 'previous_chain_sha256=%s\n' "$previous_chain"
  printf 'log_export_max_bytes=%s\n' "$maximum_log_bytes"
  printf 'privacy_contract=no-uri-query-headers-ip-body-cookie-auth-search-or-clinical-payload\n'
  printf 'edge_429_count=%s\n' "$edge_429_count"
  printf 'audit_failure_count=%s\n' "$audit_failure_count"
} > "$stage_dir/segment.meta"
(
  cd "$stage_dir"
  sha256sum audit-events.jsonl caddy-access.jsonl gunicorn-access.jsonl segment.meta > manifest.sha256
)
manifest_hash="$(sha256sum "$stage_dir/manifest.sha256" | awk '{print $1}')"
chain_hash="$(printf '%s\n%s\n' "$previous_chain" "$manifest_hash" | sha256sum | awk '{print $1}')"
{
  printf 'manifest_sha256=%s\n' "$manifest_hash"
  printf 'chain_sha256=%s\n' "$chain_hash"
} > "$stage_dir/chain.env"
segment_name="segment-$(printf '%08d' "$sequence")-$created_utc"
mv "$stage_dir" "$evidence_root/segments/$segment_name"
stage_dir=""

state_tmp="$(mktemp "$evidence_root/state/.checkpoint.XXXXXX")"
{
  printf 'checkpoint_format=medtrack-security-evidence-checkpoint-v1\n'
  printf 'sequence=%s\n' "$sequence"
  printf 'last_audit_id=%s\n' "$export_max_id"
  printf 'chain_sha256=%s\n' "$chain_hash"
  printf 'completed_epoch=%s\n' "$(date -u +%s)"
  printf 'last_segment=%s\n' "$segment_name"
} > "$state_tmp"
chmod 0600 "$state_tmp"
mv "$state_tmp" "$state_file"

segment_list="$(find "$evidence_root/segments" -mindepth 1 -maxdepth 1 -type d -name 'segment-*' -print)"
mapfile -t retained_segments < <(printf '%s\n' "$segment_list" | sed '/^$/d' | sort)
while (( ${#retained_segments[@]} > keep_segments )); do
  expired_segment="${retained_segments[0]}"
  expired_sequence="$(value "$expired_segment/segment.meta" sequence)"
  expired_chain="$(value "$expired_segment/chain.env" chain_sha256)"
  [[ "$expired_sequence" =~ ^[1-9][0-9]*$ && "$expired_chain" =~ ^[0-9a-f]{64}$ ]] || false
  anchor_tmp="$(mktemp "$evidence_root/state/.anchor.XXXXXX")"
  {
    printf 'anchor_format=medtrack-security-evidence-anchor-v1\n'
    printf 'next_sequence=%s\n' "$((expired_sequence + 1))"
    printf 'previous_chain_sha256=%s\n' "$expired_chain"
  } > "$anchor_tmp"
  chmod 0600 "$anchor_tmp"
  mv "$anchor_tmp" "$evidence_root/state/anchor.env"
  find "$expired_segment" -mindepth 1 -maxdepth 1 -type f -delete
  rmdir "$expired_segment"
  retained_segments=("${retained_segments[@]:1}")
done

remaining_oldest="$(query_scalar "SELECT COALESCE(EXTRACT(EPOCH FROM (now() - min(occurred_at)))::bigint, 0) FROM patients_auditevent WHERE id > $export_max_id")"
if [[ ! "$remaining_oldest" =~ ^[0-9]+$ || "$remaining_oldest" -gt "$maximum_lag" ]]; then
  echo "AuditEvent export remains beyond the allowed lag: age_seconds=$remaining_oldest" >&2
  false
fi
trap - ERR
trap - EXIT
"$repo_root/scripts/verify-security-evidence.sh"
echo "SECURITY_EVIDENCE_EXPORT_OK segment=$segment_name audit_end_id=$export_max_id chain_sha256=$chain_hash"
