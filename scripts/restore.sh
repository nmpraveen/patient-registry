#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

usage() {
  cat >&2 <<'EOF'
Usage:
  scripts/restore.sh verify --archive <ciphertext.tar.age> --checksum <ciphertext.sha256> \
    --identity <age-identity> --expected-commit <full-sha> --image-attestation <file> \
    --receipt-dir <absolute-dir>
  MEDTRACK_ALLOW_PRODUCTION_RESTORE=1 scripts/restore.sh activate <same verification options> \
    --rollback-dir <absolute-empty-dir> --login-smoke-hook <absolute-executable> \
    --confirm ACTIVATE_VERIFIED_MEDTRACK_RESTORE
  MEDTRACK_ALLOW_PRODUCTION_RESTORE=1 scripts/restore.sh rollback --receipt-dir <activation-receipt-dir> \
    --confirm ROLLBACK_MEDTRACK_RESTORE

Verification is always performed in a new scratch database. Production activation is disabled unless
the explicit environment gate and confirmation token are both supplied.
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

mode="$1"
shift
case "$mode" in
  verify|activate|rollback) ;;
  *) usage; exit 2 ;;
esac

archive=""
checksum=""
identity=""
expected_commit=""
image_attestation=""
receipt_dir=""
rollback_dir=""
login_smoke_hook=""
confirmation=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --archive) archive="${2:-}"; shift 2 ;;
    --checksum) checksum="${2:-}"; shift 2 ;;
    --identity) identity="${2:-}"; shift 2 ;;
    --expected-commit) expected_commit="${2:-}"; shift 2 ;;
    --image-attestation) image_attestation="${2:-}"; shift 2 ;;
    --receipt-dir) receipt_dir="${2:-}"; shift 2 ;;
    --rollback-dir) rollback_dir="${2:-}"; shift 2 ;;
    --login-smoke-hook) login_smoke_hook="${2:-}"; shift 2 ;;
    --confirm) confirmation="${2:-}"; shift 2 ;;
    *) echo "Unknown restore option: $1" >&2; usage; exit 2 ;;
  esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

for command_name in comm docker git mktemp realpath sha256sum sort tar; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 1
  fi
done
environment_file="${MEDTRACK_ENV_FILE:-$repo_root/.env}"
if [[ ! -f "$environment_file" ]]; then
  echo "Missing restore environment file: $environment_file" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$environment_file"
set +a

database_name="${POSTGRES_DB:-patient_registry}"
database_user="${POSTGRES_USER:-patient_registry}"
domain="${MEDTRACK_DOMAIN:-}"
if [[ ! "$database_name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ || ! "$database_user" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "POSTGRES_DB and POSTGRES_USER must be simple PostgreSQL identifiers" >&2
  exit 1
fi

compose=(docker compose -f "$repo_root/docker-compose.yml" -f "$repo_root/docker-compose.prod.yml")
stage_dir=""
scratch_db=""
rollback_verify_db=""
production_switched=0

db_exists() {
  local target_db="$1"
  "${compose[@]}" exec -T db psql --tuples-only --no-align --username="$database_user" --dbname=postgres \
    --command="SELECT 1 FROM pg_database WHERE datname = '$target_db'" | tr -d '[:space:]'
}

drop_database() {
  local target_db="$1"
  [[ -z "$target_db" ]] && return
  if [[ ! "$target_db" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    echo "Refusing invalid scratch database name: $target_db" >&2
    return 1
  fi
  "${compose[@]}" exec -T db psql -v ON_ERROR_STOP=1 --username="$database_user" --dbname=postgres \
    --command="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$target_db' AND pid <> pg_backend_pid();" \
    --command="DROP DATABASE IF EXISTS \"$target_db\";" >/dev/null
}

cleanup() {
  local exit_code=$?
  set +e
  if (( production_switched == 0 )); then
    drop_database "$scratch_db" >/dev/null 2>&1
  fi
  drop_database "$rollback_verify_db" >/dev/null 2>&1
  if [[ -n "$stage_dir" && -d "$stage_dir" ]]; then
    rm -rf -- "$stage_dir"
  fi
  exit "$exit_code"
}
trap cleanup EXIT

receipt_value_from_file() {
  local receipt_file="$1"
  local key="$2"
  sed -n "s/^${key}=//p" "$receipt_file" | tail -n 1 | tr -d '\r'
}

wait_for_service_health() {
  local service="$1"
  local container_id status attempt
  for attempt in $(seq 1 24); do
    container_id="$("${compose[@]}" ps -q "$service")"
    status=""
    if [[ -n "$container_id" ]]; then
      status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
    fi
    if [[ "$status" == "healthy" || "$status" == "running" ]]; then
      return 0
    fi
    sleep 5
  done
  "${compose[@]}" ps >&2
  return 1
}

image_revision() {
  local image_id="$1"
  docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$image_id"
}

image_label() {
  local image_id="$1" label="$2"
  docker image inspect --format "{{ index .Config.Labels \"$label\" }}" "$image_id"
}

verify_image_attestation() {
  local expected_tree expected_policy inspected_id
  if [[ ! -f "$image_attestation" || "$(receipt_value_from_file "$image_attestation" attestation_format)" != "medtrack-committed-image-v1" ]]; then
    echo "Restore requires a committed allowlisted-context image attestation" >&2
    return 1
  fi
  attested_commit="$(receipt_value_from_file "$image_attestation" git_commit)"
  attested_tree="$(receipt_value_from_file "$image_attestation" git_tree)"
  attested_context="$(receipt_value_from_file "$image_attestation" build_context)"
  attested_policy="$(receipt_value_from_file "$image_attestation" context_policy_sha256)"
  attested_image_ref="$(receipt_value_from_file "$image_attestation" image_ref)"
  attested_image_id="$(receipt_value_from_file "$image_attestation" image_id)"
  expected_tree="$(git rev-parse "$expected_commit^{tree}")"
  expected_policy="$(printf '%s\n%s\n' "$(git rev-parse "$expected_commit:Dockerfile")" "$(git rev-parse "$expected_commit:.dockerignore")" | sha256sum | awk '{print $1}')"
  inspected_id="$(docker image inspect --format '{{.Id}}' "$attested_image_ref")"
  if [[ "$attested_commit" != "$expected_commit" || "$attested_tree" != "$expected_tree" ||
    "$attested_context" != "git-archive-allowlist-v1" || "$attested_policy" != "$expected_policy" ||
    -z "$attested_image_id" || "$inspected_id" != "$attested_image_id" ||
    "$(image_revision "$attested_image_id")" != "$expected_commit" ||
    "$(image_label "$attested_image_id" net.naveenhospital.medtrack.git-tree)" != "$expected_tree" ||
    "$(image_label "$attested_image_id" net.naveenhospital.medtrack.build-context)" != "$attested_context" ||
    "$(image_label "$attested_image_id" net.naveenhospital.medtrack.context-policy)" != "$attested_policy" ]]; then
    echo "Restore image attestation does not match the committed allowlisted context" >&2
    return 1
  fi
  verified_web_image_id="$attested_image_id"
  verified_migrate_image_id="$attested_image_id"
  export MEDTRACK_APP_IMAGE="$attested_image_ref"
  export MEDTRACK_BUILD_REVISION="$attested_commit"
  export MEDTRACK_BUILD_GIT_TREE="$attested_tree"
  export MEDTRACK_CONTEXT_POLICY="$attested_policy"
}

verify_application_images() {
  local web_container_id running_web_image_id
  web_container_id="$("${compose[@]}" ps -q web)"
  if [[ -z "$verified_web_image_id" || -z "$verified_migrate_image_id" || -z "$web_container_id" ]]; then
    echo "Restore requires built web/migrate images and a running web container" >&2
    return 1
  fi
  running_web_image_id="$(docker inspect --format '{{.Image}}' "$web_container_id")"
  if [[ "$running_web_image_id" != "$verified_web_image_id" || "$(image_revision "$running_web_image_id")" != "$expected_commit" ]]; then
    echo "Restore application image identity does not match the exact expected commit" >&2
    return 1
  fi
}

rename_database() {
  local source_db="$1"
  local target_db="$2"
  "${compose[@]}" exec -T db psql -v ON_ERROR_STOP=1 --username="$database_user" --dbname=postgres \
    --command="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$source_db' AND pid <> pg_backend_pid();" \
    --command="ALTER DATABASE \"$source_db\" RENAME TO \"$target_db\";" >/dev/null
}

perform_database_rollback() {
  local rollback_database="$1"
  local failed_database="$2"
  local recovery_status=0 existing_database=""
  echo "Restore activation failed; reverting to the verified rollback database" >&2
  "${compose[@]}" stop caddy web >/dev/null 2>&1 || true
  existing_database="$(db_exists "$database_name")" || recovery_status=1
  if [[ "$existing_database" == "1" ]]; then
    rename_database "$database_name" "$failed_database" || recovery_status=1
  fi
  rename_database "$rollback_database" "$database_name" || recovery_status=1
  "${compose[@]}" up -d --no-build db web caddy || recovery_status=1
  wait_for_service_health db || recovery_status=1
  wait_for_service_health web || recovery_status=1
  wait_for_service_health caddy || recovery_status=1
  return "$recovery_status"
}

recover_restore_switch_failure() {
  local original_exit="$1" recovery_exit=0
  trap - ERR
  set +e
  if (( restore_switch_state == 1 )); then
    echo "Restore switch failed after retaining production; restoring its original database name" >&2
    rename_database "$rollback_database" "$database_name"
    recovery_exit=$?
  else
    echo "Restore switch failed while quiescing; restarting the prior release" >&2
  fi
  "${compose[@]}" up -d --no-build db web caddy || recovery_exit=1
  wait_for_service_health db || recovery_exit=1
  wait_for_service_health web || recovery_exit=1
  wait_for_service_health caddy || recovery_exit=1
  if (( recovery_exit != 0 )); then
    echo "CRITICAL: automatic restore-switch recovery was attempted but did not complete" >&2
  fi
  exit "$original_exit"
}

if [[ "$mode" == "rollback" ]]; then
  if [[ "${MEDTRACK_ALLOW_PRODUCTION_RESTORE:-0}" != "1" || "$confirmation" != "ROLLBACK_MEDTRACK_RESTORE" ]]; then
    echo "Rollback requires MEDTRACK_ALLOW_PRODUCTION_RESTORE=1 and the exact confirmation token" >&2
    exit 1
  fi
  if [[ -z "$receipt_dir" || ! -d "$receipt_dir" ]]; then
    echo "Rollback requires an existing --receipt-dir" >&2
    exit 1
  fi
  activation_receipt="$receipt_dir/activation.receipt"
  if [[ ! -f "$activation_receipt" || "$(receipt_value_from_file "$activation_receipt" receipt_format)" != "medtrack-restore-activation-v1" ]]; then
    echo "Missing or invalid activation receipt" >&2
    exit 1
  fi
  receipt_commit="$(receipt_value_from_file "$activation_receipt" git_commit)"
  rollback_database="$(receipt_value_from_file "$activation_receipt" rollback_database)"
  if [[ ! "$receipt_commit" =~ ^[0-9a-f]{40}$ || ! "$rollback_database" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    echo "Activation receipt contains invalid rollback identity" >&2
    exit 1
  fi
  if [[ "$(git rev-parse HEAD)" != "$receipt_commit" || "$(db_exists "$rollback_database")" != "1" ]]; then
    echo "Rollback commit or retained rollback database does not match the activation receipt" >&2
    exit 1
  fi
  failed_database="${database_name}_failed_$(date -u +%Y%m%d%H%M%S)"
  perform_database_rollback "$rollback_database" "$failed_database"
  printf 'RESTORE_ROLLBACK_OK rollback_database=%s failed_database=%s\n' "$rollback_database" "$failed_database"
  exit 0
fi

if [[ -z "$archive" || -z "$checksum" || -z "$identity" || -z "$expected_commit" || -z "$image_attestation" || -z "$receipt_dir" ]]; then
  usage
  exit 2
fi
if [[ ! "$expected_commit" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Expected commit must be a full lowercase Git SHA" >&2
  exit 1
fi
image_attestation="$(realpath -e "$image_attestation")"
verify_image_attestation
actual_commit="$(git rev-parse HEAD)"
if [[ "$actual_commit" != "$expected_commit" ]]; then
  echo "Refusing restore: expected commit $expected_commit but found $actual_commit" >&2
  exit 1
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Refusing restore from a modified tracked worktree" >&2
  exit 1
fi
for input_file in "$archive" "$checksum" "$identity"; do
  if [[ ! -f "$input_file" ]]; then
    echo "Missing restore input: $input_file" >&2
    exit 1
  fi
done
archive="$(realpath -e "$archive")"
checksum="$(realpath -e "$checksum")"
identity="$(realpath -e "$identity")"
mkdir -p "$receipt_dir"
receipt_dir="$(realpath "$receipt_dir")"

archive_name="$(basename "$archive")"
checksum_hash="$(awk 'NR==1 {print $1}' "$checksum")"
checksum_filename="$(awk 'NR==1 {print $2}' "$checksum")"
checksum_filename="${checksum_filename#\*}"
if [[ ! "$archive_name" =~ ^medtrack-prod-[a-z-]+-[0-9]{8}T[0-9]{6}Z\.tar\.age$ ||
  ! "$checksum_hash" =~ ^[0-9a-f]{64}$ || "$checksum_filename" != "$archive_name" ]]; then
  echo "Ciphertext name or external checksum format is invalid" >&2
  exit 1
fi
actual_archive_hash="$(sha256sum "$archive" | awk '{print $1}')"
if [[ "$actual_archive_hash" != "$checksum_hash" ]]; then
  echo "Ciphertext SHA-256 verification failed" >&2
  exit 1
fi

stage_parent="${MEDTRACK_RESTORE_SCRATCH_ROOT:-/var/tmp}"
if [[ ! -d "$stage_parent" ]]; then
  echo "Restore scratch root does not exist: $stage_parent" >&2
  exit 1
fi
stage_dir="$(mktemp -d "$stage_parent/medtrack-restore.XXXXXX")"
plaintext_tar="$stage_dir/recovery.tar"
payload_dir="$stage_dir/payload"
mkdir -m 0700 "$payload_dir"

echo "[1/7] Decrypting verified ciphertext into disposable scratch storage"
verify_application_images
age --decrypt -i "$identity" -o "$plaintext_tar" "$archive"
if [[ ! -s "$plaintext_tar" ]]; then
  echo "Decrypted recovery archive is empty" >&2
  exit 1
fi

echo "[2/7] Rejecting unsafe archive paths and non-file archive entries"
while IFS= read -r member; do
  normalized="${member#./}"
  if [[ -z "$normalized" ]]; then
    continue
  fi
  if [[ "$normalized" == /* || "$normalized" == ".." || "$normalized" == ../* || "$normalized" == */../* ]]; then
    echo "Unsafe recovery archive member: $member" >&2
    exit 1
  fi
done < <(tar -tf "$plaintext_tar")
if tar -tvf "$plaintext_tar" | awk 'substr($1, 1, 1) !~ /^[-d]$/ {found=1} END {exit found ? 0 : 1}'; then
  echo "Recovery archive may contain only regular files and directories" >&2
  exit 1
fi
tar --extract --file "$plaintext_tar" --directory "$payload_dir" --no-same-owner --no-same-permissions
if find "$payload_dir" -type l -print -quit | grep -q .; then
  echo "Recovery archive extracted an unexpected symbolic link" >&2
  exit 1
fi

for required_file in database.dump database.list manifest.sha256 runtime.txt schema-migrations.txt; do
  if [[ ! -s "$payload_dir/$required_file" ]]; then
    echo "Recovery archive is missing $required_file" >&2
    exit 1
  fi
done

echo "[3/7] Verifying every internal manifest entry"
while IFS= read -r manifest_line; do
  if [[ ! "$manifest_line" =~ ^[0-9a-f]{64}[[:space:]][[:space:]]\./[A-Za-z0-9._/-]+$ || "$manifest_line" == *"../"* ]]; then
    echo "Internal manifest contains an unsafe or invalid entry" >&2
    exit 1
  fi
done < "$payload_dir/manifest.sha256"
(
  cd "$payload_dir"
  sha256sum --check --strict manifest.sha256
  awk '{print $2}' manifest.sha256 | sort > "$stage_dir/manifest-files.txt"
  find . -type f ! -name manifest.sha256 -print | sort > "$stage_dir/extracted-files.txt"
)
if [[ -n "$(comm -3 "$stage_dir/manifest-files.txt" "$stage_dir/extracted-files.txt")" ]]; then
  echo "Internal manifest does not cover the exact extracted recovery payload" >&2
  exit 1
fi

runtime_value() {
  local key="$1"
  sed -n "s/^${key}=//p" "$payload_dir/runtime.txt" | head -n 1 | tr -d '\r'
}
source_schema_migration_sha256="$(runtime_value source_schema_migration_sha256)"
intended_target_commit="$(runtime_value intended_target_commit)"
if [[ "$(runtime_value backup_format)" != "medtrack-offsite-v2" ||
  "$(runtime_value source_commit)" != "$expected_commit" ||
  "$(runtime_value source_image_id)" != "$verified_web_image_id" ||
  "$(runtime_value source_git_tree)" != "$attested_tree" ||
  "$(runtime_value source_build_context)" != "$attested_context" ||
  "$(runtime_value source_context_policy_sha256)" != "$attested_policy" ||
  ! "$source_schema_migration_sha256" =~ ^[0-9a-f]{64}$ ||
  "$(sha256sum "$payload_dir/schema-migrations.txt" | awk '{print $1}')" != "$source_schema_migration_sha256" ||
  ! "$intended_target_commit" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Backup source commit, image, schema identity, or intended target provenance does not match" >&2
  exit 1
fi

echo "[4/7] Inspecting the PostgreSQL dump catalog"
catalog_file="$stage_dir/current-catalog.txt"
"${compose[@]}" exec -T db pg_restore --list < "$payload_dir/database.dump" > "$catalog_file"
if [[ ! -s "$catalog_file" ]] || ! grep -Eq 'TABLE|TABLE DATA|SCHEMA' "$catalog_file"; then
  echo "PostgreSQL dump catalog validation failed" >&2
  exit 1
fi
recorded_postgres_version="$(runtime_value postgres_server_version)"
current_postgres_version="$("${compose[@]}" exec -T db psql --tuples-only --no-align --username="$database_user" --dbname="$database_name" --command='SHOW server_version' | tr -d '[:space:]')"
if [[ -z "$recorded_postgres_version" || "$current_postgres_version" != "$recorded_postgres_version" ]]; then
  echo "PostgreSQL version mismatch: backup=$recorded_postgres_version current=$current_postgres_version" >&2
  exit 1
fi

create_empty_database() {
  local target_db="$1"
  "${compose[@]}" exec -T db createdb --username="$database_user" --template=template0 "$target_db"
}

verify_dump_in_scratch() {
  local dump_file="$1"
  local target_db="$2"
  create_empty_database "$target_db"
  "${compose[@]}" exec -T db pg_restore --exit-on-error --no-owner --no-privileges \
    --username="$database_user" --dbname="$target_db" < "$dump_file"
  restored_table_count="$("${compose[@]}" exec -T db psql --tuples-only --no-align --username="$database_user" --dbname="$target_db" \
    --command="SELECT count(*) FROM pg_tables WHERE schemaname='public'" | tr -d '[:space:]')"
  restored_migration_count="$("${compose[@]}" exec -T db psql --tuples-only --no-align --username="$database_user" --dbname="$target_db" \
    --command='SELECT count(*) FROM django_migrations' | tr -d '[:space:]')"
  if [[ ! "$restored_table_count" =~ ^[1-9][0-9]*$ || ! "$restored_migration_count" =~ ^[1-9][0-9]*$ ]]; then
    echo "Scratch restore did not contain application tables and migration history" >&2
    return 1
  fi
  scratch_schema_file="$stage_dir/schema-$target_db.txt"
  "${compose[@]}" exec -T db psql --tuples-only --no-align --username="$database_user" --dbname="$target_db" \
    --command="COPY (SELECT app || '.' || name FROM django_migrations ORDER BY app, name) TO STDOUT" > "$scratch_schema_file"
  if [[ "$(sha256sum "$scratch_schema_file" | awk '{print $1}')" != "$source_schema_migration_sha256" ||
    -n "$(comm -3 "$payload_dir/schema-migrations.txt" "$scratch_schema_file")" ]]; then
    echo "Scratch restore migration schema identity does not match the backup" >&2
    return 1
  fi
  "${compose[@]}" run --rm --no-deps -e DATABASE_URL= -e POSTGRES_DB="$target_db" web python manage.py migrate --check
  "${compose[@]}" run --rm --no-deps -e DATABASE_URL= -e POSTGRES_DB="$target_db" web python manage.py check --deploy --fail-level ERROR
  "${compose[@]}" run --rm --no-deps -e DATABASE_URL= -e POSTGRES_DB="$target_db" web python -c \
    "import os; assert os.environ.get('MEDTRACK_IMAGE_REVISION') == '$expected_commit'"
  "${compose[@]}" run --rm --no-deps -e DATABASE_URL= -e POSTGRES_DB="$target_db" web python manage.py shell -c \
    "from django.test import Client; response=Client(HTTP_HOST='localhost').get('/login/'); assert response.status_code == 200, response.status_code"
}

stamp="$(date -u +%Y%m%d%H%M%S)"
scratch_db="medtrack_restore_${stamp}_$$"
scratch_db="${scratch_db:0:63}"
echo "[5/7] Restoring into isolated database $scratch_db"
verify_dump_in_scratch "$payload_dir/database.dump" "$scratch_db"

catalog_sha256="$(sha256sum "$catalog_file" | awk '{print $1}')"
verification_receipt="$receipt_dir/verification.receipt"
{
  printf 'receipt_format=medtrack-restore-verification-v1\n'
  printf 'archive=%s\n' "$archive_name"
  printf 'ciphertext_sha256=%s\n' "$actual_archive_hash"
  printf 'git_commit=%s\n' "$expected_commit"
  printf 'intended_target_commit=%s\n' "$intended_target_commit"
  printf 'source_schema_migration_sha256=%s\n' "$source_schema_migration_sha256"
  printf 'web_image_id=%s\n' "$verified_web_image_id"
  printf 'migrate_image_id=%s\n' "$verified_migrate_image_id"
  printf 'postgres_server_version=%s\n' "$current_postgres_version"
  printf 'catalog_sha256=%s\n' "$catalog_sha256"
  printf 'restored_public_tables=%s\n' "$restored_table_count"
  printf 'restored_migration_rows=%s\n' "$restored_migration_count"
  printf 'verified_epoch=%s\n' "$(date -u +%s)"
} > "$verification_receipt"
chmod 0600 "$verification_receipt"

if [[ "$mode" == "verify" ]]; then
  echo "[6/7] Dropping the verified scratch database"
  drop_database "$scratch_db"
  scratch_db=""
  echo "[7/7] Verification complete; production was not modified"
  printf 'RESTORE_VERIFY_OK receipt=%s tables=%s migrations=%s\n' \
    "$verification_receipt" "$restored_table_count" "$restored_migration_count"
  exit 0
fi

if [[ "${MEDTRACK_ALLOW_PRODUCTION_RESTORE:-0}" != "1" || "$confirmation" != "ACTIVATE_VERIFIED_MEDTRACK_RESTORE" ]]; then
  echo "Activation requires MEDTRACK_ALLOW_PRODUCTION_RESTORE=1 and the exact confirmation token" >&2
  exit 1
fi
if [[ -z "$rollback_dir" || "$rollback_dir" != /* ]]; then
  echo "Activation requires an absolute --rollback-dir" >&2
  exit 1
fi
if [[ -z "$domain" || -z "$login_smoke_hook" || "$login_smoke_hook" != /* || ! -x "$login_smoke_hook" ]]; then
  echo "Activation requires MEDTRACK_DOMAIN and an absolute executable authenticated login smoke hook" >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "Activation requires curl for origin and public TLS smoke checks" >&2
  exit 1
fi
if [[ -e "$rollback_dir" && -n "$(find "$rollback_dir" -mindepth 1 -print -quit 2>/dev/null)" ]]; then
  echo "Rollback directory must be absent or empty" >&2
  exit 1
fi
mkdir -p -m 0700 "$rollback_dir"
rollback_dir="$(realpath "$rollback_dir")"

echo "[6/7] Creating and scratch-restoring a fresh production rollback snapshot"
rollback_dump="$rollback_dir/database.dump"
"${compose[@]}" exec -T db pg_dump --format=custom --compress=6 --no-owner --no-privileges \
  --username="$database_user" --dbname="$database_name" > "$rollback_dump"
"${compose[@]}" exec -T db pg_restore --list < "$rollback_dump" > "$rollback_dir/database.list"
(
  cd "$rollback_dir"
  sha256sum database.dump database.list > manifest.sha256
)
rollback_verify_db="medtrack_rollback_verify_${stamp}_$$"
rollback_verify_db="${rollback_verify_db:0:63}"
verify_dump_in_scratch "$rollback_dump" "$rollback_verify_db"
drop_database "$rollback_verify_db"
rollback_verify_db=""

rollback_database="${database_name}_rollback_${stamp}"
rollback_database="${rollback_database:0:63}"
failed_database="${database_name}_failed_${stamp}"
failed_database="${failed_database:0:63}"

echo "[7/7] Quiescing writes and atomically switching verified databases"
verify_application_images
restore_switch_state=0
trap 'recover_restore_switch_failure $?' ERR
"${compose[@]}" stop caddy web
rename_database "$database_name" "$rollback_database"
restore_switch_state=1
rename_database "$scratch_db" "$database_name"
production_switched=1
scratch_db=""
trap - ERR

activation_ok=1
"${compose[@]}" up -d db web caddy || activation_ok=0
if (( activation_ok )); then wait_for_service_health db || activation_ok=0; fi
if (( activation_ok )); then wait_for_service_health web || activation_ok=0; fi
if (( activation_ok )); then wait_for_service_health caddy || activation_ok=0; fi
if (( activation_ok )); then "${compose[@]}" exec -T web python manage.py migrate --check || activation_ok=0; fi
if (( activation_ok )); then "${compose[@]}" exec -T web python manage.py check --deploy --fail-level ERROR || activation_ok=0; fi
if (( activation_ok )); then verify_application_images || activation_ok=0; fi
if (( activation_ok )); then curl --fail --silent --show-error --resolve "$domain:443:127.0.0.1" "https://$domain/login/" >/dev/null || activation_ok=0; fi
if (( activation_ok )); then curl --fail --silent --show-error "https://$domain/login/" >/dev/null || activation_ok=0; fi
if (( activation_ok )); then MEDTRACK_SMOKE_BASE_URL="https://$domain" "$login_smoke_hook" || activation_ok=0; fi

if (( ! activation_ok )); then
  perform_database_rollback "$rollback_database" "$failed_database"
  exit 1
fi

activation_receipt="$receipt_dir/activation.receipt"
{
  printf 'receipt_format=medtrack-restore-activation-v1\n'
  printf 'git_commit=%s\n' "$expected_commit"
  printf 'web_image_id=%s\n' "$verified_web_image_id"
  printf 'migrate_image_id=%s\n' "$verified_migrate_image_id"
  printf 'archive=%s\n' "$archive_name"
  printf 'ciphertext_sha256=%s\n' "$actual_archive_hash"
  printf 'rollback_database=%s\n' "$rollback_database"
  printf 'rollback_dump=%s\n' "$rollback_dump"
  printf 'rollback_manifest=%s\n' "$rollback_dir/manifest.sha256"
  printf 'activated_epoch=%s\n' "$(date -u +%s)"
} > "$activation_receipt"
chmod 0600 "$activation_receipt"
printf 'RESTORE_ACTIVATE_OK receipt=%s rollback_database=%s rollback_dump=%s\n' \
  "$activation_receipt" "$rollback_database" "$rollback_dump"
