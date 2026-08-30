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
  rapid) keep_count=28 ;;
  daily) keep_count=30 ;;
  weekly) keep_count=12 ;;
  monthly) keep_count=12 ;;
  pre-deployment) keep_count=14 ;;
  canary) keep_count=1 ;;
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

for command_name in age docker flock git install mktemp rclone sha256sum tar; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 1
  fi
done

if [[ "$repo_root" != /* || "$backup_root" != /* || "$state_root" != /* ]]; then
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
source_git_tree="$(docker image inspect --format '{{ index .Config.Labels "net.naveenhospital.medtrack.git-tree" }}' "$source_image_id")"
source_build_context="$(docker image inspect --format '{{ index .Config.Labels "net.naveenhospital.medtrack.build-context" }}' "$source_image_id")"
source_context_policy="$(docker image inspect --format '{{ index .Config.Labels "net.naveenhospital.medtrack.context-policy" }}' "$source_image_id")"
if [[ ! "$source_commit" =~ ^[0-9a-f]{40}$ || ! "$source_git_tree" =~ ^[0-9a-f]{40}$ ||
  "$source_build_context" != "git-archive-allowlist-v1" || ! "$source_context_policy" =~ ^[0-9a-f]{64}$ ]]; then
  echo "The running web image lacks committed allowlisted-context attestation" >&2
  exit 1
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

echo "[3/8] Collecting recovery configuration and runtime identity"
"${compose[@]}" exec -T db sh -ceu \
  'exec psql --tuples-only --no-align --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --command="COPY (SELECT app || '\''.'\'' || name FROM django_migrations ORDER BY app, name) TO STDOUT"' \
  > "$payload_dir/schema-migrations.txt"
if [[ ! -s "$payload_dir/schema-migrations.txt" ]]; then
  echo "Could not capture the live migration schema identity" >&2
  exit 1
fi
schema_migration_sha256="$(sha256sum "$payload_dir/schema-migrations.txt" | awk '{print $1}')"
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
  printf 'backup_format=medtrack-offsite-v2\n'
  printf 'created_utc=%s\n' "$stamp"
  printf 'tier=%s\n' "$tier"
  printf 'source_commit=%s\n' "$source_commit"
  printf 'source_image_id=%s\n' "$source_image_id"
  printf 'source_git_tree=%s\n' "$source_git_tree"
  printf 'source_build_context=%s\n' "$source_build_context"
  printf 'source_context_policy_sha256=%s\n' "$source_context_policy"
  printf 'source_schema_migration_sha256=%s\n' "$schema_migration_sha256"
  printf 'intended_target_commit=%s\n' "$target_commit"
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
  done < <(find . -type f ! -name manifest.sha256 -print0 | sort -z)
) > "$payload_dir/manifest.sha256"

echo "[5/8] Encrypting the complete recovery archive"
tar --format=posix -C "$payload_dir" -cf "$plaintext_tar" .
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
  excess=$((${#markers[@]} - keep_count))
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
    for target in "$base_name" "$base_name.sha256" "$marker"; do
      rm -f -- "$local_tier_dir/$target"
    done
  done
}

prune_remote() {
  local -a markers=()
  local marker base_name remote_target index excess
  mapfile -t markers < <(rclone --config "$rclone_config" lsf "$remote_tier" --files-only --include "medtrack-prod-${tier}-*.tar.age.complete" | sort)
  excess=$((${#markers[@]} - keep_count))
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
prune_remote
prune_local

completed_epoch="$(date -u +%s)"
state_tmp="$(mktemp "$state_root/.last-success-${tier}.XXXXXX")"
printf '%s\n' "$completed_epoch" > "$state_tmp"
mv "$state_tmp" "$state_root/last-success-$tier.epoch"

receipt_path="$state_root/receipt-${tier}-${stamp}.env"
receipt_tmp="$(mktemp "$state_root/.receipt-${tier}-${stamp}.XXXXXX")"
{
  printf 'receipt_format=medtrack-offsite-receipt-v2\n'
  printf 'tier=%s\n' "$tier"
  printf 'archive=%s\n' "$archive_name"
  printf 'sha256=%s\n' "$(cut -d ' ' -f 1 "$local_tier_dir/$checksum_name")"
  printf 'source_commit=%s\n' "$source_commit"
  printf 'source_image_id=%s\n' "$source_image_id"
  printf 'source_git_tree=%s\n' "$source_git_tree"
  printf 'source_build_context=%s\n' "$source_build_context"
  printf 'source_context_policy_sha256=%s\n' "$source_context_policy"
  printf 'source_schema_migration_sha256=%s\n' "$schema_migration_sha256"
  printf 'target_commit=%s\n' "$target_commit"
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

printf 'OFFSITE_BACKUP_OK tier=%s archive=%s keep=%s receipt=%s\n' \
  "$tier" "$archive_name" "$keep_count" "$receipt_path"
