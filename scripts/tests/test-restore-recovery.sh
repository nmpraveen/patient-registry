#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf -- "$test_root"' EXIT

fake_bin="$test_root/bin"
payload_dir="$test_root/payload"
mkdir -p "$fake_bin" "$payload_dir"

cat > "$fake_bin/age" <<'FAKE_AGE'
#!/usr/bin/env bash
set -Eeuo pipefail
output=""
input=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --decrypt) shift ;;
    -i) shift 2 ;;
    -o) output="$2"; shift 2 ;;
    *) input="$1"; shift ;;
  esac
done
cp "$input" "$output"
FAKE_AGE

cat > "$fake_bin/docker" <<'FAKE_DOCKER'
#!/usr/bin/env bash
set -Eeuo pipefail
joined="$*"
if [[ -n "${FAKE_DOCKER_LOG:-}" ]]; then
  printf '%s\n' "$joined" >> "$FAKE_DOCKER_LOG"
fi
if [[ "${FAKE_FAIL_SCRATCH_RENAME:-0}" == "1" && "$joined" == *'ALTER DATABASE "medtrack_restore_'* && "$joined" == *'RENAME TO "patient_registry"'* ]]; then
  exit 44
elif [[ "$1" == "image" && "$2" == "inspect" && "$joined" == *"{{.Id}}"* ]]; then
  echo "sha256:synthetic-restore-web-image"
elif [[ "$1" == "run" ]]; then
  exit 0
elif [[ "$1" == "image" && "$2" == "inspect" && "$joined" == *"org.opencontainers.image.revision"* ]]; then
  echo "${FAKE_IMAGE_REVISION:?set FAKE_IMAGE_REVISION}"
elif [[ "$1" == "image" && "$2" == "inspect" && "$joined" == *"build-context.schema"* ]]; then
  echo "medtrack.build-context/v1"
elif [[ "$1" == "image" && "$2" == "inspect" && "$joined" == *"build-context.digest"* ]]; then
  echo "sha256:$(printf '%064d' 1)"
elif [[ "$1" == "inspect" && "$joined" == *"{{.Image}}"* ]]; then
  echo "sha256:synthetic-restore-web-image"
elif [[ "$1" == "inspect" ]]; then
  echo "healthy"
elif [[ "$1" == "tag" ]]; then
  exit 0
elif [[ "$joined" == *" ps -q "* ]]; then
  echo "synthetic-container"
elif [[ "$joined" == *" images -q web"* ]]; then
  echo "sha256:synthetic-restore-web-image"
elif [[ "$joined" == *" images -q migrate"* ]]; then
  echo "sha256:synthetic-restore-migrate-image"
elif [[ "$joined" == *" images -q caddy"* ]]; then
  echo "sha256:synthetic-caddy-image"
elif [[ "$joined" == *"pg_dump"* ]]; then
  printf 'PGDMP-synthetic-rollback\n'
elif [[ "$joined" == *"pg_restore --list"* ]]; then
  cat >/dev/null
  printf '; Archive created for test\n1; 0 0 SCHEMA public postgres\n2; 0 0 TABLE public.test postgres\n3; 0 0 TABLE DATA public patients_auditevent postgres\n'
elif [[ "$joined" == *"pg_restore"* ]]; then
  cat >/dev/null
elif [[ "$joined" == *"SHOW server_version"* ]]; then
  echo "16.14"
elif [[ "$joined" == *"FROM pg_tables"* ]]; then
  echo "5"
elif [[ "$joined" == *"COPY (SELECT app"* ]]; then
  printf 'contenttypes.0001_initial\npatients.0001_initial\npatients.0037_backend_auth_clinical_security\n'
elif [[ "$joined" == *"to_regclass('public.patients_patientidentityallocator')"* ]]; then
  echo 0
elif [[ "$joined" == *"to_regclass"* ]]; then
  echo 1
elif [[ "$joined" == *"pg_trigger"* ]]; then
  echo 1
elif [[ "$joined" == *"count(*) FROM public.patients_auditevent"* ]]; then
  echo 5
elif [[ "$joined" == *"max(id)"* ]]; then
  echo 5
elif [[ "$joined" == *"FROM django_migrations"* ]]; then
  echo "10"
elif [[ "$joined" == *"FROM pg_database"* ]]; then
  echo "1"
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
chmod +x "$fake_bin/age" "$fake_bin/docker" "$fake_bin/curl"
cat > "$test_root/build-context-verifier.py" <<'PY'
#!/usr/bin/env python3
import sys
if "--format" in sys.argv:
    print("sha256:" + "0" * 63 + "1")
else:
    print("BUILD_CONTEXT_IMAGE_VERIFIED schema=medtrack.build-context/v1")
PY

commit="$(git -C "$repo_root" rev-parse HEAD)"
context_policy="$(printf '%s\n%s\n' "$(git -C "$repo_root" rev-parse "$commit:Dockerfile")" "$(git -C "$repo_root" rev-parse "$commit:.dockerignore")" | sha256sum | awk '{print $1}')"
printf 'PGDMP-synthetic-source\n' > "$payload_dir/database.dump"
printf '; Archive created for test\n1; 0 0 TABLE public.test postgres\n2; 0 0 TABLE DATA public patients_auditevent postgres\n' > "$payload_dir/database.list"
printf 'contenttypes.0001_initial\npatients.0001_initial\npatients.0037_backend_auth_clinical_security\n' > "$payload_dir/schema-migrations.txt"
schema_hash="$(sha256sum "$payload_dir/schema-migrations.txt" | awk '{print $1}')"
{
  printf 'backup_format=medtrack-offsite-v3\n'
  printf 'source_commit=%s\n' "$commit"
  printf 'source_image_id=sha256:synthetic-restore-web-image\n'
  printf 'source_build_context_schema=medtrack.build-context/v1\n'
  printf 'source_build_context_sha256=sha256:%064d\n' 1
  printf 'source_schema_migration_sha256=%s\n' "$schema_hash"
  printf 'intended_target_commit=%s\n' "$commit"
  printf 'postgres_server_version=16.14\n'
  printf 'audit_table_present=1\n'
  printf 'security_evidence_sequence=1\n'
} > "$payload_dir/runtime.txt"
printf 'checkpoint_format=medtrack-audit-backup-checkpoint-v1\naudit_table_present=1\naudit_trigger_present=1\nminimum_row_count=5\nminimum_max_id=5\nmaximum_occurred_at=2026-08-29T12:00:00Z\n' > "$payload_dir/audit-checkpoint.env"
evidence_root="$payload_dir/security-evidence"
segment_dir="$evidence_root/segments/segment-00000001-20260829T120000Z"
mkdir -p "$segment_dir" "$evidence_root/state"
genesis="$(printf 'MEDTRACK_SECURITY_EVIDENCE_CHAIN_V1\n' | sha256sum | awk '{print $1}')"
printf '{}\n' > "$segment_dir/audit-events.jsonl"
: > "$segment_dir/caddy-access.jsonl"
: > "$segment_dir/gunicorn-access.jsonl"
printf 'segment_format=medtrack-security-evidence-v1\nsequence=1\ncreated_utc=20260829T120000Z\nprevious_chain_sha256=%s\n' "$genesis" > "$segment_dir/segment.meta"
(cd "$segment_dir" && sha256sum audit-events.jsonl caddy-access.jsonl gunicorn-access.jsonl segment.meta > manifest.sha256)
manifest_hash="$(sha256sum "$segment_dir/manifest.sha256" | awk '{print $1}')"
chain_hash="$(printf '%s\n%s\n' "$genesis" "$manifest_hash" | sha256sum | awk '{print $1}')"
printf 'manifest_sha256=%s\nchain_sha256=%s\n' "$manifest_hash" "$chain_hash" > "$segment_dir/chain.env"
printf 'checkpoint_format=medtrack-security-evidence-checkpoint-v1\nsequence=1\nlast_audit_id=5\nchain_sha256=%s\ncompleted_epoch=%s\nlast_segment=%s\n' \
  "$chain_hash" "$(date -u +%s)" "${segment_dir##*/}" > "$evidence_root/state/checkpoint.env"
printf 'security_evidence_chain_sha256=%s\n' "$chain_hash" >> "$payload_dir/runtime.txt"
(
  cd "$payload_dir"
  find . -type f ! -path './manifest.sha256' -print0 | sort -z | while IFS= read -r -d '' payload_file; do
    sha256sum "$payload_file"
  done > manifest.sha256
)
archive="$test_root/medtrack-prod-canary-20260829T120000Z.tar.age"
tar --format=posix -C "$payload_dir" -cf "$archive" .
(
  cd "$test_root"
  sha256sum "$(basename "$archive")" > "$(basename "$archive").sha256"
)
printf 'AGE-SECRET-KEY-TEST\n' > "$test_root/identity.txt"
{
  printf 'POSTGRES_DB=patient_registry\n'
  printf 'POSTGRES_USER=patient_registry\n'
  printf 'MEDTRACK_DOMAIN=book.example.invalid\n'
  printf 'DATABASE_URL=postgresql://patient_registry:synthetic@db:5432/live_database\n'
} > "$test_root/test.env"

export PATH="$fake_bin:$PATH"
export MEDTRACK_ENV_FILE="$test_root/test.env"
export MEDTRACK_BUILD_CONTEXT_VERIFIER="$test_root/build-context-verifier.py"
export PYTHON_COMMAND=python
export MEDTRACK_RESTORE_SCRATCH_ROOT="$test_root"
export FAKE_IMAGE_REVISION="$commit"
FAKE_GIT_TREE="$(git -C "$repo_root" rev-parse "$commit^{tree}")"
export FAKE_GIT_TREE
export FAKE_CONTEXT_POLICY="$context_policy"
export FAKE_DOCKER_LOG="$test_root/restore-docker.log"

image_attestation="$test_root/source-image.attestation"
{
  printf 'attestation_format=medtrack-build-receipt-v1\n'
  printf 'build_context_schema=medtrack.build-context/v1\n'
  printf 'build_context_sha256=sha256:%064d\n' 1
  printf 'revision=%s\n' "$commit"
  printf 'image_ref=medtrack-app:%s\n' "$commit"
  printf 'image_id=sha256:synthetic-restore-web-image\n'
} > "$image_attestation"

cat > "$test_root/success-login-smoke" <<'SUCCESS_LOGIN'
#!/usr/bin/env bash
test "$MEDTRACK_SMOKE_BASE_URL" = "https://book.example.invalid"
SUCCESS_LOGIN
cat > "$test_root/failing-login-smoke" <<'FAILING_LOGIN'
#!/usr/bin/env bash
exit 1
FAILING_LOGIN
chmod +x "$test_root/success-login-smoke" "$test_root/failing-login-smoke"

verify_receipts="$test_root/verify-receipts"
"$repo_root/scripts/restore.sh" verify \
  --archive "$archive" \
  --checksum "$archive.sha256" \
  --identity "$test_root/identity.txt" \
  --expected-commit "$commit" \
  --image-attestation "$image_attestation" \
  --receipt-dir "$verify_receipts"
grep -Fxq 'receipt_format=medtrack-restore-verification-v1' "$verify_receipts/verification.receipt"
grep -Eq -- '-e DATABASE_URL= -e POSTGRES_DB=medtrack_restore_' "$FAKE_DOCKER_LOG"

activation_receipts="$test_root/activation-receipts"
rollback_dir="$test_root/rollback-artifacts"
MEDTRACK_ALLOW_PRODUCTION_RESTORE=1 "$repo_root/scripts/restore.sh" activate \
  --archive "$archive" \
  --checksum "$archive.sha256" \
  --identity "$test_root/identity.txt" \
  --expected-commit "$commit" \
  --image-attestation "$image_attestation" \
  --receipt-dir "$activation_receipts" \
  --rollback-dir "$rollback_dir" \
  --login-smoke-hook "$test_root/success-login-smoke" \
  --confirm ACTIVATE_VERIFIED_MEDTRACK_RESTORE
grep -Fxq 'receipt_format=medtrack-restore-activation-v1' "$activation_receipts/activation.receipt"
test -s "$rollback_dir/database.dump"
test -s "$rollback_dir/manifest.sha256"

MEDTRACK_ALLOW_PRODUCTION_RESTORE=1 "$repo_root/scripts/restore.sh" rollback \
  --receipt-dir "$activation_receipts" \
  --confirm ROLLBACK_MEDTRACK_RESTORE

set +e
failed_smoke_output="$(MEDTRACK_ALLOW_PRODUCTION_RESTORE=1 "$repo_root/scripts/restore.sh" activate \
  --archive "$archive" \
  --checksum "$archive.sha256" \
  --identity "$test_root/identity.txt" \
  --expected-commit "$commit" \
  --image-attestation "$image_attestation" \
  --receipt-dir "$test_root/failed-smoke-receipts" \
  --rollback-dir "$test_root/failed-smoke-rollback" \
  --login-smoke-hook "$test_root/failing-login-smoke" \
  --confirm ACTIVATE_VERIFIED_MEDTRACK_RESTORE 2>&1)"
failed_smoke_exit=$?
set -e
if (( failed_smoke_exit == 0 )) || [[ "$failed_smoke_output" != *"reverting to the verified rollback database"* ]]; then
  echo "Restore activation smoke failure did not trigger rollback" >&2
  printf '%s\n' "$failed_smoke_output" >&2
  exit 1
fi

export FAKE_FAIL_SCRATCH_RENAME=1
set +e
second_rename_output="$(MEDTRACK_ALLOW_PRODUCTION_RESTORE=1 "$repo_root/scripts/restore.sh" activate \
  --archive "$archive" \
  --checksum "$archive.sha256" \
  --identity "$test_root/identity.txt" \
  --expected-commit "$commit" \
  --image-attestation "$image_attestation" \
  --receipt-dir "$test_root/second-rename-receipts" \
  --rollback-dir "$test_root/second-rename-rollback" \
  --login-smoke-hook "$test_root/success-login-smoke" \
  --confirm ACTIVATE_VERIFIED_MEDTRACK_RESTORE 2>&1)"
second_rename_exit=$?
set -e
unset FAKE_FAIL_SCRATCH_RENAME
if (( second_rename_exit == 0 )) || [[ "$second_rename_output" != *"restoring its original database name"* ]]; then
  echo "Second restore rename failure did not compensate the canonical database name" >&2
  printf '%s\n' "$second_rename_output" >&2
  exit 1
fi
grep -Fq 'ALTER DATABASE "patient_registry_rollback_' "$FAKE_DOCKER_LOG"
grep -Fq 'RENAME TO "patient_registry"' "$FAKE_DOCKER_LOG"

export FAKE_IMAGE_REVISION="0000000000000000000000000000000000000000"
if "$repo_root/scripts/restore.sh" verify \
  --archive "$archive" \
  --checksum "$archive.sha256" \
  --identity "$test_root/identity.txt" \
  --expected-commit "$commit" \
  --image-attestation "$image_attestation" \
  --receipt-dir "$test_root/stale-image-receipt" >/dev/null 2>&1; then
  echo "Restore verification unexpectedly accepted a stale application image" >&2
  exit 1
fi
export FAKE_IMAGE_REVISION="$commit"

special_archive="$test_root/medtrack-prod-canary-20260829T120001Z.tar.age"
cp "$archive" "$special_archive"
python - "$special_archive" <<'PY'
import sys
import tarfile

with tarfile.open(sys.argv[1], "a") as bundle:
    member = tarfile.TarInfo("./unexpected.pipe")
    member.type = tarfile.FIFOTYPE
    member.mode = 0o600
    bundle.addfile(member)
PY
(
  cd "$test_root"
  sha256sum "$(basename "$special_archive")" > "$(basename "$special_archive").sha256"
)
if "$repo_root/scripts/restore.sh" verify \
  --archive "$special_archive" \
  --checksum "$special_archive.sha256" \
  --identity "$test_root/identity.txt" \
  --expected-commit "$commit" \
  --image-attestation "$image_attestation" \
  --receipt-dir "$test_root/special-entry-receipt" >/dev/null 2>&1; then
  echo "Restore verification unexpectedly accepted a FIFO archive member" >&2
  exit 1
fi

printf '%064d  %s\n' 0 "$(basename "$archive")" > "$test_root/bad.sha256"
if "$repo_root/scripts/restore.sh" verify \
  --archive "$archive" \
  --checksum "$test_root/bad.sha256" \
  --identity "$test_root/identity.txt" \
  --expected-commit "$commit" \
  --image-attestation "$image_attestation" \
  --receipt-dir "$test_root/bad-receipt" >/dev/null 2>&1; then
  echo "Restore verification unexpectedly accepted a corrupt checksum" >&2
  exit 1
fi

echo "RESTORE_RECOVERY_TEST_OK"
