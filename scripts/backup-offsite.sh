#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

usage() {
  echo "Usage: scripts/backup-offsite.sh --tier rapid|daily|weekly|monthly|pre-deployment|canary [--target-commit <full-sha>]" >&2
}

tier=""
target_commit=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tier) tier="${2:-}"; shift 2 ;;
    --target-commit) target_commit="${2:-}"; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done
case "$tier" in
  rapid) remote_keep_count=28; local_keep_count=4; evidence_mode=checkpoint ;;
  daily) remote_keep_count=30; local_keep_count=2; evidence_mode=checkpoint ;;
  weekly) remote_keep_count=12; local_keep_count=2; evidence_mode=full ;;
  monthly) remote_keep_count=12; local_keep_count=1; evidence_mode=full ;;
  pre-deployment) remote_keep_count=14; local_keep_count=2; evidence_mode=full ;;
  canary) remote_keep_count=1; local_keep_count=1; evidence_mode=checkpoint ;;
  *)
    usage
    exit 2
    ;;
esac

config_file="${MEDTRACK_BACKUP_CONFIG:-/etc/medtrack-backup/backup.env}"
if [[ -r "$config_file" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$config_file"
  set +a
fi

repo_root="${MEDTRACK_REPO_ROOT:-/srv/medtrack/app}"
backup_root="${MEDTRACK_OFFSITE_ROOT:-/srv/medtrack/offsite-backups}"
state_root="${MEDTRACK_BACKUP_STATE_ROOT:-$backup_root/state}"
rclone_config="${RCLONE_CONFIG:-/srv/medtrack/backup-secrets/rclone.conf}"
rclone_remote="${RCLONE_REMOTE:-medtrack-drive:Naveen-Hospital-Backups/MEDTRACK/production}"
recipient_file="${AGE_RECIPIENT_FILE:-/srv/medtrack/backup-secrets/age-recipient.txt}"
production_env="${MEDTRACK_ENV_FILE:-$repo_root/.env}"
evidence_root="${MEDTRACK_SECURITY_EVIDENCE_ROOT:-/srv/medtrack/security-evidence}"
require_audit_schema="${MEDTRACK_REQUIRE_AUDIT_EVENT_SCHEMA:-1}"
build_context_verifier="${MEDTRACK_BUILD_CONTEXT_VERIFIER:-$repo_root/scripts/build_context_receipt.py}"
evidence_checkpoint_verifier="${MEDTRACK_SECURITY_EVIDENCE_CHECKPOINT_VERIFIER:-$repo_root/scripts/verify-security-evidence-checkpoint.sh}"

python_command="${PYTHON_COMMAND:-python3}"
for command_name in age docker flock git install mktemp "$python_command" rclone sha256sum tar; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 1
  fi
done

if [[ "$repo_root" != /* || "$backup_root" != /* || "$state_root" != /* || "$evidence_root" != /* ||
  ! "$require_audit_schema" =~ ^[01]$ ]]; then
  echo "Repository, backup, and state paths must be absolute" >&2
  exit 1
fi
if [[ ! -d "$repo_root/.git" && ! -f "$repo_root/.git" ]]; then
  echo "MEDTRACK repository not found at $repo_root" >&2
  exit 1
fi
if [[ ! -f "$production_env" ]]; then
  echo "Production environment file not found at $production_env" >&2
  exit 1
fi
if [[ ! -f "$rclone_config" ]]; then
  echo "rclone configuration not found at $rclone_config" >&2
  exit 1
fi
if [[ ! -f "$recipient_file" ]]; then
  echo "age recipient file not found at $recipient_file" >&2
  exit 1
fi
if [[ ! -f "$build_context_verifier" ]]; then
  echo "Canonical medtrack.build-context/v1 verifier is missing (requires build PR #100)" >&2
  exit 1
fi
if [[ ! -x "$evidence_checkpoint_verifier" ]]; then
  echo "Security-evidence checkpoint verifier is missing or not executable" >&2
  exit 1
fi

recipient="$(tr -d '[:space:]' < "$recipient_file")"
if [[ ! "$recipient" =~ ^age1[0-9a-z]+$ ]]; then
  echo "Invalid age recipient in $recipient_file" >&2
  exit 1
fi
remote_name="${rclone_remote%%:*}:"
if [[ "$rclone_remote" != *:* || "$remote_name" == ":" ]]; then
  echo "RCLONE_REMOTE must use rclone remote:path syntax" >&2
  exit 1
fi
if ! rclone --config "$rclone_config" listremotes | grep -Fxq "$remote_name"; then
  echo "Configured rclone remote $remote_name is unavailable" >&2
  exit 1
fi

install -d -m 0700 "$backup_root" "$backup_root/staging" "$backup_root/local" "$state_root"
local_tier_dir="$backup_root/local/$tier"
install -d -m 0700 "$local_tier_dir"

exec 9>"$backup_root/backup.lock"
if ! flock -n 9; then
  echo "Another MEDTRACK offsite backup is already running" >&2
  exit 75
fi

stamp="${MEDTRACK_BACKUP_TIMESTAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
if [[ ! "$stamp" =~ ^[0-9]{8}T[0-9]{6}Z$ ]]; then
  echo "Backup timestamp must use YYYYMMDDTHHMMSSZ" >&2
  exit 1
fi

archive_name="medtrack-prod-${tier}-${stamp}.tar.age"
checksum_name="$archive_name.sha256"
marker_name="$archive_name.complete"
remote_tier="${rclone_remote%/}/$tier"

if [[ -e "$local_tier_dir/$archive_name" || -e "$local_tier_dir/$marker_name" ]]; then
  echo "Refusing to overwrite existing backup $archive_name" >&2
  exit 1
fi

stage_dir="$(mktemp -d "$backup_root/staging/${tier}-${stamp}.XXXXXX")"
payload_dir="$stage_dir/payload"
plaintext_tar="$stage_dir/medtrack-backup.tar"
encrypted_partial="$stage_dir/$archive_name.partial"
install -d -m 0700 "$payload_dir/config"

cleanup() {
  if [[ -n "${stage_dir:-}" && -d "$stage_dir" ]]; then
    rm -rf -- "$stage_dir"
  fi
}
trap cleanup EXIT

compose=(docker compose -f "$repo_root/docker-compose.yml" -f "$repo_root/docker-compose.prod.yml")

web_container_id="$("${compose[@]}" ps -q web)"
if [[ -z "$web_container_id" ]]; then
  echo "A running web container is required to bind backup provenance" >&2
  exit 1
fi
source_image_id="$(docker inspect --format '{{.Image}}' "$web_container_id")"
source_commit="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$source_image_id")"
source_build_context_schema="$(docker image inspect --format '{{ index .Config.Labels "org.medtrack.build-context.schema" }}' "$source_image_id")"
source_build_context_sha256="$(docker image inspect --format '{{ index .Config.Labels "org.medtrack.build-context.digest" }}' "$source_image_id")"
if [[ ! "$source_commit" =~ ^[0-9a-f]{40}$ || "$source_build_context_schema" != "medtrack.build-context/v1" ||
  ! "$source_build_context_sha256" =~ ^sha256:[0-9a-f]{64}$ ]] ||
  ! "$python_command" "$build_context_verifier" --revision "$source_commit" --verify-image "$source_image_id"; then
  echo "The running web image lacks committed allowlisted-context attestation" >&2
  exit 1
fi

query_live_scalar() {
  "${compose[@]}" exec -T db sh -ceu \
    'exec psql --tuples-only --no-align --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --command="$1"' sh "$1" |
    tr -d '[:space:]'
}
audit_table_present="$(query_live_scalar "SELECT CASE WHEN to_regclass('public.patients_auditevent') IS NOT NULL THEN 1 ELSE 0 END")"
audit_trigger_present="$(query_live_scalar "SELECT count(*) FROM pg_trigger WHERE tgname='patients_auditevent_append_only' AND NOT tgisinternal")"
if [[ "$require_audit_schema" == "1" && ( "$audit_table_present" != "1" || "$audit_trigger_present" != "1" ) ]]; then
  echo "AuditEvent table or append-only trigger is absent; refusing production backup promotion" >&2
  exit 1
fi
audit_row_count=0
audit_max_id=0
audit_max_occurred_at=none
if [[ "$audit_table_present" == "1" ]]; then
  audit_row_count="$(query_live_scalar 'SELECT count(*) FROM public.patients_auditevent')"
  audit_max_id="$(query_live_scalar 'SELECT COALESCE(max(id),0) FROM public.patients_auditevent')"
  audit_max_occurred_at="$(query_live_scalar "SELECT COALESCE(to_char(max(occurred_at) AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"'),'none') FROM public.patients_auditevent")"
fi
if [[ ! "$audit_row_count" =~ ^[0-9]+$ || ! "$audit_max_id" =~ ^[0-9]+$ ]]; then
  echo "Could not capture a safe AuditEvent backup checkpoint" >&2
  exit 1
fi

if [[ "$require_audit_schema" == "1" ]]; then
  MEDTRACK_SECURITY_EVIDENCE_ALLOW_STALE=1 "$repo_root/scripts/verify-security-evidence.sh"
  evidence_chain_sha256="$(sed -n 's/^chain_sha256=//p' "$evidence_root/state/checkpoint.env" | tail -n 1)"
  evidence_sequence="$(sed -n 's/^sequence=//p' "$evidence_root/state/checkpoint.env" | tail -n 1)"
  if [[ ! "$evidence_chain_sha256" =~ ^[0-9a-f]{64}$ || ! "$evidence_sequence" =~ ^[1-9][0-9]*$ ]]; then
    echo "Security evidence checkpoint is invalid" >&2
    exit 1
  fi
  evidence_last_segment="$(sed -n 's/^last_segment=//p' "$evidence_root/state/checkpoint.env" | tail -n 1)"
  if [[ ! "$evidence_last_segment" =~ ^segment-[0-9]{8}-[0-9]{8}T[0-9]{6}Z$ ||
    ! -d "$evidence_root/segments/$evidence_last_segment" || -L "$evidence_root/segments/$evidence_last_segment" ]]; then
    echo "Security evidence checkpoint does not identify a safe latest segment" >&2
    exit 1
  fi
else
  evidence_chain_sha256=none
  evidence_sequence=0
  evidence_last_segment=none
fi
if [[ -z "$target_commit" ]]; then
  if [[ "$tier" == "pre-deployment" ]]; then
    echo "Pre-deployment backups require --target-commit for the intended deployment" >&2
    exit 1
  fi
  target_commit="$source_commit"
fi
if [[ ! "$target_commit" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Target commit must be a full lowercase Git SHA" >&2
  exit 1
fi
if [[ "$tier" == "pre-deployment" && ( "$(git -C "$repo_root" rev-parse HEAD)" != "$target_commit" ||
  -n "$(git -C "$repo_root" status --porcelain --untracked-files=no)" ) ]]; then
  echo "Pre-deployment target checkout must be clean and match --target-commit" >&2
  exit 1
fi

echo "[1/8] Creating PostgreSQL custom-format dump"
"${compose[@]}" exec -T db sh -ceu 'exec pg_dump --format=custom --compress=6 --no-owner --no-privileges --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' > "$payload_dir/database.dump"
if [[ ! -s "$payload_dir/database.dump" ]]; then
  echo "PostgreSQL dump is empty" >&2
  exit 1
fi

echo "[2/8] Validating PostgreSQL dump structure"
"${compose[@]}" exec -T db sh -ceu 'exec pg_restore --list' < "$payload_dir/database.dump" > "$payload_dir/database.list"
if [[ ! -s "$payload_dir/database.list" ]]; then
  echo "pg_restore did not produce a dump catalog" >&2
  exit 1
fi
if [[ "$audit_table_present" == "1" ]] && ! grep -Eq 'TABLE DATA[[:space:]]+public[[:space:]]+patients_auditevent' "$payload_dir/database.list"; then
  echo "PostgreSQL dump catalog does not contain AuditEvent application data" >&2
  exit 1
fi

echo "[3/8] Collecting recovery configuration and runtime identity"
"${compose[@]}" exec -T db sh -ceu \
  'exec psql --tuples-only --no-align --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --command="COPY (SELECT app || '\''.'\'' || name FROM django_migrations ORDER BY app, name) TO STDOUT"' \
  > "$payload_dir/schema-migrations.txt"
if [[ ! -s "$payload_dir/schema-migrations.txt" ]]; then
  echo "Could not capture the live migration schema identity" >&2
  exit 1
fi
if [[ "$require_audit_schema" == "1" ]] && ! grep -Fxq 'patients.0037_backend_auth_clinical_security' "$payload_dir/schema-migrations.txt"; then
  echo "AuditEvent schema migration from PR #103 is not applied" >&2
  exit 1
fi
schema_migration_sha256="$(sha256sum "$payload_dir/schema-migrations.txt" | awk '{print $1}')"
{
  printf 'checkpoint_format=medtrack-audit-backup-checkpoint-v1\n'
  printf 'audit_table_present=%s\n' "$audit_table_present"
  printf 'audit_trigger_present=%s\n' "$audit_trigger_present"
  printf 'minimum_row_count=%s\n' "$audit_row_count"
  printf 'minimum_max_id=%s\n' "$audit_max_id"
  printf 'maximum_occurred_at=%s\n' "$audit_max_occurred_at"
} > "$payload_dir/audit-checkpoint.env"
if [[ "$require_audit_schema" == "1" ]]; then
  if find "$evidence_root/state" "$evidence_root/segments" ! -type f ! -type d -print -quit | grep -q .; then
    echo "Security evidence contains a link or special file" >&2
    exit 1
  fi
  if [[ "$evidence_mode" == "full" ]]; then
    install -d -m 0700 "$payload_dir/security-evidence"
    (cd "$evidence_root" && tar -cf - state segments) |
      tar -xf - -C "$payload_dir/security-evidence" --no-same-owner --no-same-permissions
    MEDTRACK_SECURITY_EVIDENCE_ROOT="$payload_dir/security-evidence" \
      MEDTRACK_SECURITY_EVIDENCE_ALLOW_STALE=1 "$repo_root/scripts/verify-security-evidence.sh"
  else
    checkpoint_root="$payload_dir/security-evidence-checkpoint"
    install -d -m 0700 "$checkpoint_root/state" "$checkpoint_root/segments"
    install -m 0600 "$evidence_root/state/checkpoint.env" "$checkpoint_root/state/checkpoint.env"
    (cd "$evidence_root/segments" && tar -cf - "$evidence_last_segment") |
      tar -xf - -C "$checkpoint_root/segments" --no-same-owner --no-same-permissions
    MEDTRACK_SECURITY_EVIDENCE_CHECKPOINT_ROOT="$checkpoint_root" \
      "$evidence_checkpoint_verifier"
  fi
fi
install -m 0600 "$production_env" "$payload_dir/config/environment.env"
for relative_path in docker-compose.yml docker-compose.prod.yml deploy/Caddyfile; do
  if [[ -f "$repo_root/$relative_path" ]]; then
    install -D -m 0600 "$repo_root/$relative_path" "$payload_dir/config/$relative_path"
  fi
done
if [[ -f /etc/docker/daemon.json ]]; then
  install -m 0600 /etc/docker/daemon.json "$payload_dir/config/docker-daemon.json"
fi
if [[ -f /etc/audit/rules.d/medtrack-app.rules ]]; then
  install -m 0600 /etc/audit/rules.d/medtrack-app.rules "$payload_dir/config/medtrack-app.rules"
fi

{
  printf 'backup_format=medtrack-offsite-v4\n'
  printf 'created_utc=%s\n' "$stamp"
  printf 'tier=%s\n' "$tier"
  printf 'source_commit=%s\n' "$source_commit"
  printf 'source_image_id=%s\n' "$source_image_id"
  printf 'source_build_context_schema=%s\n' "$source_build_context_schema"
  printf 'source_build_context_sha256=%s\n' "$source_build_context_sha256"
  printf 'source_schema_migration_sha256=%s\n' "$schema_migration_sha256"
  printf 'intended_target_commit=%s\n' "$target_commit"
  printf 'audit_table_present=%s\n' "$audit_table_present"
  printf 'audit_minimum_row_count=%s\n' "$audit_row_count"
  printf 'audit_minimum_max_id=%s\n' "$audit_max_id"
  printf 'security_evidence_sequence=%s\n' "$evidence_sequence"
  printf 'security_evidence_chain_sha256=%s\n' "$evidence_chain_sha256"
  printf 'security_evidence_mode=%s\n' "$evidence_mode"
  printf 'security_evidence_last_segment=%s\n' "$evidence_last_segment"
  printf 'postgres_server_version=%s\n' "$("${compose[@]}" exec -T db sh -ceu 'exec psql --tuples-only --no-align --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --command="SHOW server_version"')"
  docker --version
  docker compose version
  "${compose[@]}" images
} > "$payload_dir/runtime.txt"

echo "[4/8] Building the recovery-content integrity manifest"
(
  cd "$payload_dir"
  while IFS= read -r -d '' payload_file; do
    sha256sum "$payload_file"
  done < <(find . -type f ! -path './manifest.sha256' -print0 | sort -z)
) > "$payload_dir/manifest.sha256"

echo "[5/8] Compressing and encrypting the complete recovery archive"
tar --format=posix -C "$payload_dir" -czf "$plaintext_tar" .
age -r "$recipient" -o "$encrypted_partial" "$plaintext_tar"
if [[ ! -s "$encrypted_partial" ]]; then
  echo "Encrypted archive is empty" >&2
  exit 1
fi
mv "$encrypted_partial" "$local_tier_dir/$archive_name"
(
  cd "$local_tier_dir"
  sha256sum "$archive_name" > "$checksum_name.tmp"
  mv "$checksum_name.tmp" "$checksum_name"
)

echo "[6/8] Uploading uniquely named ciphertext to Google Drive"
rclone --config "$rclone_config" mkdir "$remote_tier"
rclone --config "$rclone_config" copyto "$local_tier_dir/$archive_name" "$remote_tier/$archive_name" --immutable
rclone --config "$rclone_config" copyto "$local_tier_dir/$checksum_name" "$remote_tier/$checksum_name" --immutable

echo "[7/8] Verifying the uploaded ciphertext"
rclone --config "$rclone_config" check "$local_tier_dir" "$remote_tier" \
  --one-way \
  --include "/$archive_name" \
  --include "/$checksum_name"

{
  printf 'archive=%s\n' "$archive_name"
  printf 'sha256=%s\n' "$(cut -d ' ' -f 1 "$local_tier_dir/$checksum_name")"
  printf 'completed_utc=%s\n' "$stamp"
  printf 'source_commit=%s\n' "$source_commit"
  printf 'intended_target_commit=%s\n' "$target_commit"
  printf 'security_evidence_chain_sha256=%s\n' "$evidence_chain_sha256"
} > "$local_tier_dir/$marker_name.tmp"
mv "$local_tier_dir/$marker_name.tmp" "$local_tier_dir/$marker_name"
rclone --config "$rclone_config" copyto "$local_tier_dir/$marker_name" "$remote_tier/$marker_name" --immutable
rclone --config "$rclone_config" check "$local_tier_dir" "$remote_tier" \
  --one-way \
  --include "/$marker_name"

prune_local() {
  local -a markers=()
  local marker base_name target index excess
  mapfile -t markers < <(find "$local_tier_dir" -maxdepth 1 -type f -name "medtrack-prod-${tier}-*.tar.age.complete" -printf '%f\n' | sort)
  excess=$((${#markers[@]} - local_keep_count))
  if (( excess <= 0 )); then
    return
  fi
  for ((index = 0; index < excess; index++)); do
    marker="${markers[$index]}"
    if [[ ! "$marker" =~ ^medtrack-prod-${tier}-[0-9]{8}T[0-9]{6}Z\.tar\.age\.complete$ ]]; then
      echo "Refusing local retention cleanup for unexpected marker: $marker" >&2
      exit 1
    fi
    base_name="${marker%.complete}"
    rclone --config "$rclone_config" check "$local_tier_dir" "$remote_tier" \
      --one-way \
      --include "/$base_name" \
      --include "/$base_name.sha256" \
      --include "/$marker"
    for target in "$base_name" "$base_name.sha256" "$marker"; do
      rm -f -- "$local_tier_dir/$target"
    done
  done
}

prune_remote() {
  local -a markers=()
  local marker base_name remote_target index excess
  mapfile -t markers < <(rclone --config "$rclone_config" lsf "$remote_tier" --files-only --include "medtrack-prod-${tier}-*.tar.age.complete" | sort)
  excess=$((${#markers[@]} - remote_keep_count))
  if (( excess <= 0 )); then
    return
  fi
  for ((index = 0; index < excess; index++)); do
    marker="${markers[$index]}"
    if [[ ! "$marker" =~ ^medtrack-prod-${tier}-[0-9]{8}T[0-9]{6}Z\.tar\.age\.complete$ ]]; then
      echo "Refusing remote retention cleanup for unexpected marker: $marker" >&2
      exit 1
    fi
    base_name="${marker%.complete}"
    for remote_target in "$base_name" "$base_name.sha256" "$marker"; do
      rclone --config "$rclone_config" deletefile "$remote_tier/$remote_target"
    done
  done
}

echo "[8/8] Applying exact tier retention (Drive deletions use Trash)"
prune_local
prune_remote

completed_epoch="$(date -u +%s)"
state_tmp="$(mktemp "$state_root/.last-success-${tier}.XXXXXX")"
printf '%s\n' "$completed_epoch" > "$state_tmp"
mv "$state_tmp" "$state_root/last-success-$tier.epoch"

receipt_path="$state_root/receipt-${tier}-${stamp}.env"
receipt_tmp="$(mktemp "$state_root/.receipt-${tier}-${stamp}.XXXXXX")"
{
  printf 'receipt_format=medtrack-offsite-receipt-v4\n'
  printf 'tier=%s\n' "$tier"
  printf 'archive=%s\n' "$archive_name"
  printf 'sha256=%s\n' "$(cut -d ' ' -f 1 "$local_tier_dir/$checksum_name")"
  printf 'source_commit=%s\n' "$source_commit"
  printf 'source_image_id=%s\n' "$source_image_id"
  printf 'source_build_context_schema=%s\n' "$source_build_context_schema"
  printf 'source_build_context_sha256=%s\n' "$source_build_context_sha256"
  printf 'source_schema_migration_sha256=%s\n' "$schema_migration_sha256"
  printf 'target_commit=%s\n' "$target_commit"
  printf 'audit_minimum_row_count=%s\n' "$audit_row_count"
  printf 'audit_minimum_max_id=%s\n' "$audit_max_id"
  printf 'security_evidence_sequence=%s\n' "$evidence_sequence"
  printf 'security_evidence_chain_sha256=%s\n' "$evidence_chain_sha256"
  printf 'security_evidence_mode=%s\n' "$evidence_mode"
  printf 'completed_epoch=%s\n' "$completed_epoch"
  printf 'local_archive=%s\n' "$local_tier_dir/$archive_name"
  printf 'local_checksum=%s\n' "$local_tier_dir/$checksum_name"
  printf 'local_marker=%s\n' "$local_tier_dir/$marker_name"
  printf 'remote_tier=%s\n' "$remote_tier"
} > "$receipt_tmp"
chmod 0600 "$receipt_tmp"
mv "$receipt_tmp" "$receipt_path"
latest_receipt_tmp="$(mktemp "$state_root/.latest-${tier}.XXXXXX")"
cp "$receipt_path" "$latest_receipt_tmp"
chmod 0600 "$latest_receipt_tmp"
mv "$latest_receipt_tmp" "$state_root/latest-${tier}.receipt"

printf 'OFFSITE_BACKUP_OK tier=%s archive=%s local_keep=%s remote_keep=%s evidence=%s receipt=%s\n' \
  "$tier" "$archive_name" "$local_keep_count" "$remote_keep_count" "$evidence_mode" "$receipt_path"
