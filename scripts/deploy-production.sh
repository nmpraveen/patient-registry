#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

usage() {
  cat >&2 <<'EOF'
Usage:
  scripts/deploy-production.sh plan <expected-full-git-commit> \
    --backup-receipt <fresh-pre-deployment-receipt> --evidence-dir <absolute-dir>
  scripts/deploy-production.sh apply <expected-full-git-commit> \
    --backup-receipt <fresh-pre-deployment-receipt> --evidence-dir <absolute-dir> \
    --approve-plan-sha256 <sha256> --login-smoke-hook <absolute-executable>
  scripts/deploy-production.sh rollback --deployment-receipt <file> \
    --confirm ROLLBACK_MEDTRACK_DEPLOYMENT

The plan phase is read-only against the database. Apply refuses to run until the exact generated
migration-plan hash is explicitly supplied, then creates and scratch-restores fresh rollback artifacts.
Plan requires the existing database service to already be healthy and never pulls, starts, stops, or
recreates a live service.
EOF
}

if [[ $# -lt 1 ]]; then usage; exit 2; fi
mode="$1"
shift
case "$mode" in plan|apply|rollback) ;; *) usage; exit 2 ;; esac

expected_commit=""
if [[ "$mode" != "rollback" ]]; then
  expected_commit="${1:-}"
  shift || true
fi
backup_receipt=""
evidence_dir=""
approved_plan_hash=""
login_smoke_hook=""
deployment_receipt=""
confirmation=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup-receipt) backup_receipt="${2:-}"; shift 2 ;;
    --evidence-dir) evidence_dir="${2:-}"; shift 2 ;;
    --approve-plan-sha256) approved_plan_hash="${2:-}"; shift 2 ;;
    --login-smoke-hook) login_smoke_hook="${2:-}"; shift 2 ;;
    --deployment-receipt) deployment_receipt="${2:-}"; shift 2 ;;
    --confirm) confirmation="${2:-}"; shift 2 ;;
    *) echo "Unknown deployment option: $1" >&2; usage; exit 2 ;;
  esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
environment_file="${MEDTRACK_ENV_FILE:-$repo_root/.env}"
if [[ ! -f "$environment_file" ]]; then echo "Missing deployment environment file: $environment_file" >&2; exit 1; fi
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
compose=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

receipt_value() {
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
    if [[ "$status" == "healthy" || "$status" == "running" ]]; then return 0; fi
    sleep 5
  done
  "${compose[@]}" ps >&2
  return 1
}

require_existing_healthy_database() {
  local container_id status
  container_id="$("${compose[@]}" ps -q db)"
  if [[ -z "$container_id" ]]; then
    echo "The database service must already be running; this mode will not start or recreate it" >&2
    return 1
  fi
  status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
  if [[ "$status" != "healthy" ]]; then
    echo "The existing database service is not healthy: status=$status" >&2
    return 1
  fi
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
  local attestation_file="$1" expected="$2"
  local expected_tree expected_policy inspected_id
  if [[ ! -f "$attestation_file" || "$(receipt_value "$attestation_file" attestation_format)" != "medtrack-committed-image-v1" ]]; then
    echo "Missing or invalid committed-image attestation" >&2
    return 1
  fi
  attested_commit="$(receipt_value "$attestation_file" git_commit)"
  attested_tree="$(receipt_value "$attestation_file" git_tree)"
  attested_context="$(receipt_value "$attestation_file" build_context)"
  attested_policy="$(receipt_value "$attestation_file" context_policy_sha256)"
  attested_image_ref="$(receipt_value "$attestation_file" image_ref)"
  attested_image_id="$(receipt_value "$attestation_file" image_id)"
  expected_tree="$(git rev-parse "$expected^{tree}")"
  expected_policy="$(printf '%s\n%s\n' "$(git rev-parse "$expected:Dockerfile")" "$(git rev-parse "$expected:.dockerignore")" | sha256sum | awk '{print $1}')"
  inspected_id="$(docker image inspect --format '{{.Id}}' "$attested_image_ref")"
  if [[ "$attested_commit" != "$expected" || "$attested_tree" != "$expected_tree" ||
    "$attested_context" != "git-archive-allowlist-v1" || "$attested_policy" != "$expected_policy" ||
    -z "$attested_image_id" || "$inspected_id" != "$attested_image_id" ||
    "$(image_revision "$attested_image_id")" != "$expected" ||
    "$(image_label "$attested_image_id" net.naveenhospital.medtrack.git-tree)" != "$expected_tree" ||
    "$(image_label "$attested_image_id" net.naveenhospital.medtrack.build-context)" != "$attested_context" ||
    "$(image_label "$attested_image_id" net.naveenhospital.medtrack.context-policy)" != "$attested_policy" ]]; then
    echo "Image attestation does not match the committed allowlisted context or local image" >&2
    return 1
  fi
}

rename_database() {
  local source_db="$1" target_db="$2"
  "${compose[@]}" exec -T db psql -v ON_ERROR_STOP=1 --username="$database_user" --dbname=postgres \
    --command="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$source_db' AND pid <> pg_backend_pid();" \
    --command="ALTER DATABASE \"$source_db\" RENAME TO \"$target_db\";" >/dev/null
}

database_exists() {
  local target_db="$1"
  "${compose[@]}" exec -T db psql --tuples-only --no-align --username="$database_user" --dbname=postgres \
    --command="SELECT 1 FROM pg_database WHERE datname = '$target_db'" | tr -d '[:space:]'
}

database_oid() {
  local target_db="$1"
  "${compose[@]}" exec -T db psql --tuples-only --no-align --username="$database_user" --dbname=postgres \
    --command="SELECT oid::text FROM pg_database WHERE datname = '$target_db'" | tr -d '[:space:]'
}

rollback_release() {
  local rollback_database="$1" failed_database="$2" previous_image_id="$3" previous_image_ref="$4"
  local recovery_status=0 existing_database=""
  echo "Deployment gate failed; restoring the retained database and image" >&2
  "${compose[@]}" stop caddy web >/dev/null 2>&1 || true
  existing_database="$(database_exists "$database_name")" || recovery_status=1
  if [[ "$existing_database" == "1" ]]; then
    rename_database "$database_name" "$failed_database" || recovery_status=1
  fi
  rename_database "$rollback_database" "$database_name" || recovery_status=1
  docker tag "$previous_image_id" "$previous_image_ref" || recovery_status=1
  "${compose[@]}" up -d --no-build db web caddy || recovery_status=1
  wait_for_service_health db || recovery_status=1
  wait_for_service_health web || recovery_status=1
  wait_for_service_health caddy || recovery_status=1
  return "$recovery_status"
}

restart_previous_release_without_database_rollback() {
  local previous_image_id="$1" previous_image_ref="$2"
  local recovery_status=0
  echo "Deployment gate failed before the rollback database was ready; restarting the prior release" >&2
  docker tag "$previous_image_id" "$previous_image_ref" || recovery_status=1
  "${compose[@]}" up -d --no-build db web caddy || recovery_status=1
  wait_for_service_health db || recovery_status=1
  wait_for_service_health web || recovery_status=1
  wait_for_service_health caddy || recovery_status=1
  return "$recovery_status"
}

recover_post_quiesce_failure() {
  local original_exit="$1"
  trap - ERR
  set +e
  if (( rollback_database_ready )); then
    rollback_release "$rollback_database" "$failed_database" "$previous_image_id" "$previous_image_ref"
    recovery_exit=$?
  else
    restart_previous_release_without_database_rollback "$previous_image_id" "$previous_image_ref"
    recovery_exit=$?
  fi
  if (( recovery_exit != 0 )); then
    echo "CRITICAL: automatic post-quiesce recovery was attempted but did not complete" >&2
  fi
  exit "$original_exit"
}

if [[ "$mode" == "rollback" ]]; then
  if [[ "$confirmation" != "ROLLBACK_MEDTRACK_DEPLOYMENT" || -z "$deployment_receipt" || ! -f "$deployment_receipt" ]]; then
    echo "Rollback requires the deployment receipt and exact confirmation token" >&2
    exit 1
  fi
  if [[ "$(receipt_value "$deployment_receipt" receipt_format)" != "medtrack-deployment-v1" ]]; then
    echo "Invalid deployment receipt" >&2
    exit 1
  fi
  rollback_database="$(receipt_value "$deployment_receipt" rollback_database)"
  previous_image_id="$(receipt_value "$deployment_receipt" previous_image_id)"
  previous_image_ref="$(receipt_value "$deployment_receipt" previous_image_ref)"
  deployed_commit="$(receipt_value "$deployment_receipt" git_commit)"
  deployed_image_id="$(receipt_value "$deployment_receipt" deployed_image_id)"
  deployed_database_oid="$(receipt_value "$deployment_receipt" deployed_database_oid)"
  rollback_database_oid="$(receipt_value "$deployment_receipt" rollback_database_oid)"
  current_web_container="$("${compose[@]}" ps -q web)"
  current_web_image=""
  current_web_revision=""
  if [[ -n "$current_web_container" ]]; then
    current_web_image="$(docker inspect --format '{{.Image}}' "$current_web_container")"
    current_web_revision="$(image_revision "$current_web_image")"
  fi
  if [[ ! "$rollback_database" =~ ^[A-Za-z_][A-Za-z0-9_]*$ || -z "$previous_image_id" || -z "$previous_image_ref" ||
    ! "$deployed_commit" =~ ^[0-9a-f]{40}$ || -z "$deployed_image_id" ||
    ! "$deployed_database_oid" =~ ^[0-9]+$ || ! "$rollback_database_oid" =~ ^[0-9]+$ ||
    "$(git rev-parse HEAD)" != "$deployed_commit" || "$current_web_image" != "$deployed_image_id" ||
    "$current_web_revision" != "$deployed_commit" || "$(database_oid "$database_name")" != "$deployed_database_oid" ||
    "$(database_oid "$rollback_database")" != "$rollback_database_oid" ]]; then
    echo "Deployment receipt has invalid rollback identity" >&2
    exit 1
  fi
  failed_database="${database_name}_failed_$(date -u +%Y%m%d%H%M%S)"
  rollback_release "$rollback_database" "$failed_database" "$previous_image_id" "$previous_image_ref"
  echo "DEPLOYMENT_ROLLBACK_OK rollback_database=$rollback_database failed_database=$failed_database"
  exit 0
fi

if [[ ! "$expected_commit" =~ ^[0-9a-f]{40}$ ]]; then echo "Expected commit must be a full lowercase SHA" >&2; exit 1; fi
if [[ "$(git rev-parse HEAD)" != "$expected_commit" ]]; then echo "Refusing deployment from a different commit" >&2; exit 1; fi
if ! git diff --quiet || ! git diff --cached --quiet; then echo "Refusing deployment from a modified tracked worktree" >&2; exit 1; fi
if [[ -z "$backup_receipt" || ! -f "$backup_receipt" || -z "$evidence_dir" || "$evidence_dir" != /* ]]; then
  echo "A backup receipt and absolute evidence directory are required" >&2
  exit 1
fi
mkdir -p -m 0700 "$evidence_dir"
backup_receipt="$(realpath -e "$backup_receipt")"
evidence_dir="$(realpath "$evidence_dir")"

receipt_format="$(receipt_value "$backup_receipt" receipt_format)"
receipt_tier="$(receipt_value "$backup_receipt" tier)"
receipt_source_commit="$(receipt_value "$backup_receipt" source_commit)"
receipt_source_image_id="$(receipt_value "$backup_receipt" source_image_id)"
receipt_source_tree="$(receipt_value "$backup_receipt" source_git_tree)"
receipt_source_context="$(receipt_value "$backup_receipt" source_build_context)"
receipt_source_policy="$(receipt_value "$backup_receipt" source_context_policy_sha256)"
receipt_schema_hash="$(receipt_value "$backup_receipt" source_schema_migration_sha256)"
receipt_target_commit="$(receipt_value "$backup_receipt" target_commit)"
receipt_epoch="$(receipt_value "$backup_receipt" completed_epoch)"
receipt_archive="$(receipt_value "$backup_receipt" archive)"
receipt_hash="$(receipt_value "$backup_receipt" sha256)"
local_archive="$(receipt_value "$backup_receipt" local_archive)"
local_checksum="$(receipt_value "$backup_receipt" local_checksum)"
local_marker="$(receipt_value "$backup_receipt" local_marker)"
if [[ "$receipt_format" != "medtrack-offsite-receipt-v2" || "$receipt_tier" != "pre-deployment" ||
  ! "$receipt_source_commit" =~ ^[0-9a-f]{40}$ || -z "$receipt_source_image_id" ||
  ! "$receipt_source_tree" =~ ^[0-9a-f]{40}$ || "$receipt_source_context" != "git-archive-allowlist-v1" ||
  ! "$receipt_source_policy" =~ ^[0-9a-f]{64}$ ||
  ! "$receipt_schema_hash" =~ ^[0-9a-f]{64}$ || "$receipt_target_commit" != "$expected_commit" || ! "$receipt_epoch" =~ ^[0-9]+$ ||
  ! "$receipt_hash" =~ ^[0-9a-f]{64}$ || ! -f "$local_archive" || ! -f "$local_checksum" || ! -f "$local_marker" ]]; then
  echo "Pre-deployment backup receipt is incomplete or does not match the exact commit" >&2
  exit 1
fi
receipt_age=$(($(date -u +%s) - receipt_epoch))
maximum_receipt_age="${MEDTRACK_PREDEPLOY_MAX_AGE_SECONDS:-7200}"
if (( receipt_age < 0 || receipt_age > maximum_receipt_age )); then
  echo "Pre-deployment backup receipt is stale: age_seconds=$receipt_age" >&2
  exit 1
fi
checksum_filename="$(awk 'NR==1 {print $2}' "$local_checksum")"
checksum_filename="${checksum_filename#\*}"
if [[ "$(basename "$local_archive")" != "$receipt_archive" || "$(sha256sum "$local_archive" | awk '{print $1}')" != "$receipt_hash" ||
  "$(awk 'NR==1 {print $1}' "$local_checksum")" != "$receipt_hash" || "$checksum_filename" != "$receipt_archive" ||
  "$(sed -n 's/^archive=//p' "$local_marker")" != "$receipt_archive" ||
  "$(sed -n 's/^sha256=//p' "$local_marker")" != "$receipt_hash" ||
  "$(sed -n 's/^source_commit=//p' "$local_marker")" != "$receipt_source_commit" ||
  "$(sed -n 's/^intended_target_commit=//p' "$local_marker")" != "$receipt_target_commit" ]]; then
  echo "Pre-deployment ciphertext triplet no longer matches its receipt" >&2
  exit 1
fi

echo "[1/5] Validating production Compose and exact backup receipt"
"${compose[@]}" config --quiet
echo "[2/5] Requiring the existing healthy database and preparing the exact application image"
require_existing_healthy_database
source_web_container="$("${compose[@]}" ps -q web)"
if [[ -z "$source_web_container" || "$(docker inspect --format '{{.Image}}' "$source_web_container")" != "$receipt_source_image_id" ||
  "$(image_revision "$receipt_source_image_id")" != "$receipt_source_commit" ||
  "$(image_label "$receipt_source_image_id" net.naveenhospital.medtrack.git-tree)" != "$receipt_source_tree" ||
  "$(image_label "$receipt_source_image_id" net.naveenhospital.medtrack.build-context)" != "$receipt_source_context" ||
  "$(image_label "$receipt_source_image_id" net.naveenhospital.medtrack.context-policy)" != "$receipt_source_policy" ]]; then
  echo "The running source release does not match the pre-deployment backup provenance" >&2
  exit 1
fi
image_attestation="$evidence_dir/image.attestation"
if [[ "$mode" == "plan" ]]; then
  "$repo_root/scripts/build-attested-image.sh" "$expected_commit" "$image_attestation"
fi
verify_image_attestation "$image_attestation" "$expected_commit"
export MEDTRACK_APP_IMAGE="$attested_image_ref"
export MEDTRACK_BUILD_REVISION="$attested_commit"
export MEDTRACK_BUILD_GIT_TREE="$attested_tree"
export MEDTRACK_CONTEXT_POLICY="$attested_policy"

plan_receipt="$evidence_dir/plan.receipt"
if [[ "$mode" == "apply" ]]; then
  if [[ ! -f "$plan_receipt" || "$(receipt_value "$plan_receipt" receipt_format)" != "medtrack-deployment-plan-v1" ]]; then
    echo "Apply requires the retained receipt from a prior plan phase" >&2
    exit 1
  fi
  reviewed_plan_hash="$(receipt_value "$plan_receipt" migration_plan_sha256)"
  reviewed_image_id="$(receipt_value "$plan_receipt" planned_image_id)"
  reviewed_migrate_image_id="$(receipt_value "$plan_receipt" planned_migrate_image_id)"
  reviewed_commit="$(receipt_value "$plan_receipt" git_commit)"
  reviewed_backup_archive="$(receipt_value "$plan_receipt" backup_archive)"
  reviewed_backup_hash="$(receipt_value "$plan_receipt" backup_sha256)"
  reviewed_source_commit="$(receipt_value "$plan_receipt" source_commit)"
  reviewed_source_image_id="$(receipt_value "$plan_receipt" source_image_id)"
  reviewed_attestation_hash="$(receipt_value "$plan_receipt" image_attestation_sha256)"
  if [[ "$reviewed_plan_hash" != "$approved_plan_hash" || "$reviewed_commit" != "$expected_commit" ||
    "$reviewed_backup_archive" != "$receipt_archive" || "$reviewed_backup_hash" != "$receipt_hash" ||
    "$reviewed_source_commit" != "$receipt_source_commit" || "$reviewed_source_image_id" != "$receipt_source_image_id" ||
    "$reviewed_attestation_hash" != "$(sha256sum "$image_attestation" | awk '{print $1}')" ]]; then
    echo "Approved migration hash, backup, or exact commit does not match the retained plan receipt" >&2
    exit 1
  fi
  plan_file="$evidence_dir/migration-plan.apply.txt"
else
  plan_file="$evidence_dir/migration-plan.txt"
fi
prepared_image_id="$attested_image_id"
prepared_migrate_image_id="$attested_image_id"
if [[ "$mode" == "apply" && ( "$prepared_image_id" != "$reviewed_image_id" ||
  "$prepared_migrate_image_id" != "$reviewed_migrate_image_id" ) ]]; then
  echo "Apply image identity changed after the reviewed plan" >&2
  exit 1
fi
echo "[3/5] Generating the controlled one-shot migration plan"
"${compose[@]}" run --rm --no-deps web python manage.py makemigrations --check --dry-run
"${compose[@]}" run --rm --no-deps web python manage.py migrate --plan | tee "$plan_file"
plan_hash="$(sha256sum "$plan_file" | awk '{print $1}')"
planned_image_id="$attested_image_id"
planned_migrate_image_id="$attested_image_id"
if [[ "$planned_image_id" != "$prepared_image_id" || "$planned_migrate_image_id" != "$prepared_migrate_image_id" ]]; then
  echo "Application image identity changed while generating the migration plan" >&2
  exit 1
fi

if [[ "$mode" == "plan" ]]; then
  {
    printf 'receipt_format=medtrack-deployment-plan-v1\n'
    printf 'git_commit=%s\n' "$expected_commit"
    printf 'migration_plan_sha256=%s\n' "$plan_hash"
    printf 'planned_image_id=%s\n' "$planned_image_id"
    printf 'planned_migrate_image_id=%s\n' "$planned_migrate_image_id"
    printf 'backup_archive=%s\n' "$receipt_archive"
    printf 'backup_sha256=%s\n' "$receipt_hash"
    printf 'source_commit=%s\n' "$receipt_source_commit"
    printf 'source_image_id=%s\n' "$receipt_source_image_id"
    printf 'source_schema_migration_sha256=%s\n' "$receipt_schema_hash"
    printf 'image_attestation_sha256=%s\n' "$(sha256sum "$image_attestation" | awk '{print $1}')"
    printf 'created_epoch=%s\n' "$(date -u +%s)"
  } > "$plan_receipt"
  chmod 0600 "$plan_receipt"
  echo "[4/5] Plan retained for operator review"
  echo "[5/5] No migration or production switch was performed"
  printf 'DEPLOY_PLAN_OK receipt=%s migration_plan=%s migration_plan_sha256=%s\n' "$plan_receipt" "$plan_file" "$plan_hash"
  exit 0
fi

if [[ ! "$approved_plan_hash" =~ ^[0-9a-f]{64}$ || "$approved_plan_hash" != "$plan_hash" ||
  "$planned_image_id" != "$reviewed_image_id" || "$planned_migrate_image_id" != "$reviewed_migrate_image_id" ]]; then
  echo "Apply requires the exact reviewed migration-plan SHA-256 and built image ID" >&2
  exit 1
fi
if [[ -z "$login_smoke_hook" || "$login_smoke_hook" != /* || ! -x "$login_smoke_hook" ]]; then
  echo "Apply requires an absolute executable authenticated login smoke hook" >&2
  exit 1
fi
if [[ -z "$domain" ]]; then echo "MEDTRACK_DOMAIN is required for origin and public TLS smoke" >&2; exit 1; fi

previous_container_id="$("${compose[@]}" ps -q web)"
if [[ -z "$previous_container_id" ]]; then echo "A running prior web container is required for rollback" >&2; exit 1; fi
previous_image_id="$(docker inspect --format '{{.Image}}' "$previous_container_id")"
previous_image_ref="$(docker inspect --format '{{.Config.Image}}' "$previous_container_id")"
stamp="$(date -u +%Y%m%d%H%M%S)"
rollback_database="${database_name}_deploy_rollback_${stamp}"
rollback_database="${rollback_database:0:63}"
failed_database="${database_name}_deploy_failed_${stamp}"
failed_database="${failed_database:0:63}"
scratch_database="medtrack_deploy_verify_${stamp}_$$"
scratch_database="${scratch_database:0:63}"
rollback_dir="$evidence_dir/rollback-$stamp"
mkdir -m 0700 "$rollback_dir"

echo "[4/5] Creating and scratch-restoring fresh rollback artifacts"
"${compose[@]}" exec -T db pg_dump --format=custom --compress=6 --no-owner --no-privileges \
  --username="$database_user" --dbname="$database_name" > "$rollback_dir/database.dump"
"${compose[@]}" exec -T db pg_restore --list < "$rollback_dir/database.dump" > "$rollback_dir/database.list"
(
  cd "$rollback_dir"
  sha256sum database.dump database.list > manifest.sha256
)
"${compose[@]}" exec -T db createdb --username="$database_user" --template=template0 "$scratch_database"
scratch_cleanup() {
  "${compose[@]}" exec -T db dropdb --if-exists --username="$database_user" "$scratch_database" >/dev/null 2>&1 || true
}
trap scratch_cleanup EXIT
"${compose[@]}" exec -T db pg_restore --exit-on-error --no-owner --no-privileges \
  --username="$database_user" --dbname="$scratch_database" < "$rollback_dir/database.dump"
scratch_tables="$("${compose[@]}" exec -T db psql --tuples-only --no-align --username="$database_user" --dbname="$scratch_database" \
  --command="SELECT count(*) FROM pg_tables WHERE schemaname='public'" | tr -d '[:space:]')"
scratch_migrations="$("${compose[@]}" exec -T db psql --tuples-only --no-align --username="$database_user" --dbname="$scratch_database" \
  --command='SELECT count(*) FROM django_migrations' | tr -d '[:space:]')"
if [[ ! "$scratch_tables" =~ ^[1-9][0-9]*$ || ! "$scratch_migrations" =~ ^[1-9][0-9]*$ ]]; then
  echo "Rollback scratch restore did not contain application schema" >&2
  exit 1
fi
scratch_cleanup
trap - EXIT

echo "[5/5] Quiescing writes, snapshotting the rollback database, and running one-shot migration"
rollback_database_ready=0
trap 'recover_post_quiesce_failure $?' ERR
"${compose[@]}" stop caddy web
"${compose[@]}" exec -T db psql -v ON_ERROR_STOP=1 --username="$database_user" --dbname=postgres \
  --command="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$database_name' AND pid <> pg_backend_pid();" >/dev/null
"${compose[@]}" exec -T db createdb --username="$database_user" --template="$database_name" "$rollback_database"
rollback_database_ready=1

"${compose[@]}" --profile deploy run --rm migrate
"${compose[@]}" up -d --no-build --remove-orphans db web caddy
wait_for_service_health db
wait_for_service_health web
wait_for_service_health caddy
"${compose[@]}" exec -T web python manage.py migrate --check
"${compose[@]}" exec -T web python manage.py check --deploy --fail-level ERROR
curl --fail --silent --show-error --resolve "$domain:443:127.0.0.1" "https://$domain/login/" >/dev/null
curl --fail --silent --show-error "https://$domain/login/" >/dev/null
MEDTRACK_SMOKE_BASE_URL="https://$domain" "$login_smoke_hook"

deployed_database_oid="$(database_oid "$database_name")"
rollback_database_oid="$(database_oid "$rollback_database")"
if [[ ! "$deployed_database_oid" =~ ^[0-9]+$ || ! "$rollback_database_oid" =~ ^[0-9]+$ ]]; then
  echo "Could not bind the deployment receipt to exact database identities" >&2
  false
fi

deployment_receipt="$evidence_dir/deployment.receipt"
{
  printf 'receipt_format=medtrack-deployment-v1\n'
  printf 'git_commit=%s\n' "$expected_commit"
  printf 'source_commit=%s\n' "$receipt_source_commit"
  printf 'migration_plan_sha256=%s\n' "$plan_hash"
  printf 'backup_archive=%s\n' "$receipt_archive"
  printf 'backup_sha256=%s\n' "$receipt_hash"
  printf 'rollback_database=%s\n' "$rollback_database"
  printf 'rollback_database_oid=%s\n' "$rollback_database_oid"
  printf 'rollback_dump=%s\n' "$rollback_dir/database.dump"
  printf 'rollback_manifest=%s\n' "$rollback_dir/manifest.sha256"
  printf 'rollback_public_tables=%s\n' "$scratch_tables"
  printf 'rollback_migration_rows=%s\n' "$scratch_migrations"
  printf 'previous_image_id=%s\n' "$previous_image_id"
  printf 'previous_image_ref=%s\n' "$previous_image_ref"
  printf 'deployed_image_id=%s\n' "$planned_image_id"
  printf 'deployed_database_oid=%s\n' "$deployed_database_oid"
  printf 'migration_image_id=%s\n' "$planned_migrate_image_id"
  printf 'deployed_epoch=%s\n' "$(date -u +%s)"
} > "$deployment_receipt"
chmod 0600 "$deployment_receipt"
"${compose[@]}" ps
trap - ERR
printf 'DEPLOY_PRODUCTION_OK commit=%s receipt=%s rollback_database=%s\n' \
  "$expected_commit" "$deployment_receipt" "$rollback_database"
