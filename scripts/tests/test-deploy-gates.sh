#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf -- "$test_root"' EXIT

fake_bin="$test_root/bin"
triplet_dir="$test_root/pre-deployment"
evidence_dir="$test_root/evidence"
mkdir -p "$fake_bin" "$triplet_dir"

cat > "$fake_bin/docker" <<'FAKE_DOCKER'
#!/usr/bin/env bash
set -Eeuo pipefail
joined="$*"
if [[ -n "${FAKE_DOCKER_LOG:-}" ]]; then
  printf '%s\n' "$joined" >> "$FAKE_DOCKER_LOG"
fi
if [[ "${FAKE_FAIL_TERMINATE:-0}" == "1" && "$joined" == *"pg_terminate_backend"* ]]; then
  exit 42
elif [[ "${FAKE_FAIL_ROLLBACK_CREATEDB:-0}" == "1" && "$joined" == *"createdb"* && "$joined" == *"--template=patient_registry"* ]]; then
  exit 43
elif [[ "$1" == "build" ]]; then
  exit 0
elif [[ "$1" == "image" && "$2" == "inspect" && "$joined" == *"{{.Id}}"* ]]; then
  echo "sha256:synthetic-planned-image"
elif [[ "$1" == "image" && "$2" == "inspect" && "$joined" == *"org.opencontainers.image.revision"* ]]; then
  echo "${FAKE_IMAGE_REVISION:?set FAKE_IMAGE_REVISION}"
elif [[ "$1" == "image" && "$2" == "inspect" && "$joined" == *"medtrack.git-tree"* ]]; then
  echo "${FAKE_GIT_TREE:?set FAKE_GIT_TREE}"
elif [[ "$1" == "image" && "$2" == "inspect" && "$joined" == *"medtrack.build-context"* ]]; then
  echo "git-archive-allowlist-v1"
elif [[ "$1" == "image" && "$2" == "inspect" && "$joined" == *"medtrack.context-policy"* ]]; then
  echo "${FAKE_CONTEXT_POLICY:?set FAKE_CONTEXT_POLICY}"
elif [[ "$1" == "inspect" && "$joined" == *"{{.Image}}"* ]]; then
  echo "sha256:synthetic-previous-image"
elif [[ "$1" == "inspect" && "$joined" == *"{{.Config.Image}}"* ]]; then
  echo "patient-registry-web:synthetic-previous"
elif [[ "$1" == "inspect" ]]; then
  echo "healthy"
elif [[ "$1" == "tag" ]]; then
  exit 0
elif [[ "$joined" == *" ps -q db"* ]]; then
  echo "synthetic-db-container"
elif [[ "$joined" == *" ps -q web"* ]]; then
  echo "synthetic-web-container"
elif [[ "$joined" == *" ps -q caddy"* ]]; then
  echo "synthetic-caddy-container"
elif [[ "$joined" == *" images -q web"* ]]; then
  echo "sha256:synthetic-planned-image"
elif [[ "$joined" == *" images -q migrate"* ]]; then
  echo "sha256:synthetic-planned-image"
elif [[ "$joined" == *"pg_dump"* ]]; then
  printf 'PGDMP-synthetic-deploy-rollback\n'
elif [[ "$joined" == *"pg_restore --list"* ]]; then
  cat >/dev/null
  printf '; Archive created for test\n1; 0 0 TABLE public.test postgres\n'
elif [[ "$joined" == *"pg_restore"* ]]; then
  cat >/dev/null
elif [[ "$joined" == *"FROM pg_tables"* ]]; then
  echo "5"
elif [[ "$joined" == *"FROM django_migrations"* ]]; then
  echo "10"
elif [[ "$joined" == *"SELECT oid::text FROM pg_database"* && "$joined" == *"deploy_rollback"* ]]; then
  echo "222"
elif [[ "$joined" == *"SELECT oid::text FROM pg_database"* ]]; then
  echo "111"
elif [[ "$joined" == *"FROM pg_database"* ]]; then
  echo "1"
elif [[ "$joined" == *"migrate --plan"* ]]; then
  printf 'Planned operations:\n  patients.9999_synthetic\n'
elif [[ "$joined" == *" compose "* || "$1" == "compose" ]]; then
  exit 0
else
  echo "Unexpected fake docker invocation: $joined" >&2
  exit 1
fi
FAKE_DOCKER
cat > "$fake_bin/curl" <<'FAKE_CURL'
#!/usr/bin/env bash
exit 0
FAKE_CURL
chmod +x "$fake_bin/docker" "$fake_bin/curl"

commit="$(git -C "$repo_root" rev-parse HEAD)"
context_policy="$(printf '%s\n%s\n' "$(git -C "$repo_root" rev-parse "$commit:Dockerfile")" "$(git -C "$repo_root" rev-parse "$commit:.dockerignore")" | sha256sum | awk '{print $1}')"
archive="medtrack-prod-pre-deployment-20260829T120000Z.tar.age"
printf 'synthetic-encrypted-predeployment\n' > "$triplet_dir/$archive"
hash="$(sha256sum "$triplet_dir/$archive" | awk '{print $1}')"
printf '%s  %s\n' "$hash" "$archive" > "$triplet_dir/$archive.sha256"
{
  printf 'archive=%s\n' "$archive"
  printf 'sha256=%s\n' "$hash"
  printf 'completed_utc=20260829T120000Z\n'
  printf 'source_commit=%s\n' "$commit"
  printf 'intended_target_commit=%s\n' "$commit"
} > "$triplet_dir/$archive.complete"
receipt="$test_root/predeployment.receipt"
{
  printf 'receipt_format=medtrack-offsite-receipt-v2\n'
  printf 'tier=pre-deployment\n'
  printf 'archive=%s\n' "$archive"
  printf 'sha256=%s\n' "$hash"
  printf 'source_commit=%s\n' "$commit"
  printf 'source_image_id=sha256:synthetic-previous-image\n'
  printf 'source_git_tree=%s\n' "$(git -C "$repo_root" rev-parse "$commit^{tree}")"
  printf 'source_build_context=git-archive-allowlist-v1\n'
  printf 'source_context_policy_sha256=%s\n' "$context_policy"
  printf 'source_schema_migration_sha256=%064d\n' 1
  printf 'target_commit=%s\n' "$commit"
  printf 'completed_epoch=%s\n' "$(date -u +%s)"
  printf 'local_archive=%s\n' "$triplet_dir/$archive"
  printf 'local_checksum=%s\n' "$triplet_dir/$archive.sha256"
  printf 'local_marker=%s\n' "$triplet_dir/$archive.complete"
  printf 'remote_tier=medtrack-drive:synthetic/pre-deployment\n'
} > "$receipt"
{
  printf 'POSTGRES_DB=patient_registry\n'
  printf 'POSTGRES_USER=patient_registry\n'
  printf 'POSTGRES_PASSWORD=synthetic-not-a-secret\n'
  printf 'MEDTRACK_DOMAIN=book.example.invalid\n'
} > "$test_root/test.env"

export PATH="$fake_bin:$PATH"
export MEDTRACK_ENV_FILE="$test_root/test.env"
export FAKE_IMAGE_REVISION="$commit"
export FAKE_GIT_TREE="$(git -C "$repo_root" rev-parse "$commit^{tree}")"
export FAKE_CONTEXT_POLICY="$context_policy"
plan_log="$test_root/plan-docker.log"
export FAKE_DOCKER_LOG="$plan_log"

"$repo_root/scripts/deploy-production.sh" plan "$commit" \
  --backup-receipt "$receipt" \
  --evidence-dir "$evidence_dir"

grep -Fxq 'receipt_format=medtrack-deployment-plan-v1' "$evidence_dir/plan.receipt"
test -s "$evidence_dir/migration-plan.txt"
plan_hash="$(sha256sum "$evidence_dir/migration-plan.txt" | awk '{print $1}')"
grep -Fxq "migration_plan_sha256=$plan_hash" "$evidence_dir/plan.receipt"
if grep -Eq '(^| )compose( |$).*( pull| up| stop| start| restart| down)( |$)' "$plan_log"; then
  echo "Plan phase unexpectedly attempted to mutate a live service" >&2
  cat "$plan_log" >&2
  exit 1
fi

cat > "$test_root/failing-login-smoke" <<'FAKE_LOGIN'
#!/usr/bin/env bash
exit 1
FAKE_LOGIN
chmod +x "$test_root/failing-login-smoke"

assert_preclone_failure_recovers() {
  local failure_flag="$1" case_name="$2" case_evidence="$test_root/evidence-$2"
  mkdir -p "$case_evidence"
  cp "$evidence_dir/plan.receipt" "$case_evidence/plan.receipt"
  cp "$evidence_dir/image.attestation" "$case_evidence/image.attestation"
  export FAKE_DOCKER_LOG="$test_root/$case_name-docker.log"
  export "$failure_flag=1"
  set +e
  case_output="$("$repo_root/scripts/deploy-production.sh" apply "$commit" \
    --backup-receipt "$receipt" \
    --evidence-dir "$case_evidence" \
    --approve-plan-sha256 "$plan_hash" \
    --login-smoke-hook "$test_root/failing-login-smoke" 2>&1)"
  case_exit=$?
  set -e
  unset "$failure_flag"
  if (( case_exit == 0 )) || [[ "$case_output" != *"restarting the prior release"* ]]; then
    echo "$case_name failure did not trigger automatic restart of the prior release" >&2
    printf '%s\n' "$case_output" >&2
    exit 1
  fi
  grep -Fq 'stop caddy web' "$FAKE_DOCKER_LOG"
  grep -Fq 'up -d --no-build db web caddy' "$FAKE_DOCKER_LOG"
}

assert_preclone_failure_recovers FAKE_FAIL_TERMINATE terminate-connections
assert_preclone_failure_recovers FAKE_FAIL_ROLLBACK_CREATEDB rollback-createdb

export FAKE_DOCKER_LOG="$test_root/login-failure-docker.log"
set +e
apply_output="$("$repo_root/scripts/deploy-production.sh" apply "$commit" \
  --backup-receipt "$receipt" \
  --evidence-dir "$evidence_dir" \
  --approve-plan-sha256 "$plan_hash" \
  --login-smoke-hook "$test_root/failing-login-smoke" 2>&1)"
apply_exit=$?
set -e
if (( apply_exit == 0 )) || [[ "$apply_output" != *"restoring the retained database and image"* ]]; then
  echo "Post-migration smoke failure did not trigger automatic rollback" >&2
  printf '%s\n' "$apply_output" >&2
  exit 1
fi

if "$repo_root/scripts/deploy-production.sh" "$commit" >/dev/null 2>&1; then
  echo "Legacy one-step deployment unexpectedly bypassed the plan gate" >&2
  exit 1
fi

stale_receipt="$test_root/stale-deployment.receipt"
{
  printf 'receipt_format=medtrack-deployment-v1\n'
  printf 'git_commit=%s\n' "$commit"
  printf 'rollback_database=patient_registry_deploy_rollback_synthetic\n'
  printf 'rollback_database_oid=222\n'
  printf 'deployed_database_oid=111\n'
  printf 'previous_image_id=sha256:synthetic-previous-image\n'
  printf 'previous_image_ref=patient-registry-web:synthetic-previous\n'
  printf 'deployed_image_id=sha256:synthetic-planned-image\n'
} > "$stale_receipt"
export FAKE_DOCKER_LOG="$test_root/stale-rollback-docker.log"
if "$repo_root/scripts/deploy-production.sh" rollback \
  --deployment-receipt "$stale_receipt" \
  --confirm ROLLBACK_MEDTRACK_DEPLOYMENT >/dev/null 2>&1; then
  echo "Manual rollback unexpectedly accepted a stale deployment receipt" >&2
  exit 1
fi
if grep -Fq 'stop caddy web' "$FAKE_DOCKER_LOG"; then
  echo "Stale rollback receipt changed service state before rejection" >&2
  exit 1
fi

echo "DEPLOY_GATES_TEST_OK"
