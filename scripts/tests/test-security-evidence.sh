#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf -- "$test_root"' EXIT
fake_bin="$test_root/bin"
evidence_root="$test_root/evidence"
log_root="$test_root/logs"
mkdir -p "$fake_bin" "$log_root"

cat > "$fake_bin/docker" <<'FAKE_DOCKER'
#!/usr/bin/env bash
set -Eeuo pipefail
joined="$*"
if [[ "$joined" == *"to_regclass"* || "$joined" == *"pg_trigger"* ]]; then
  echo 1
elif [[ "$joined" == *"DELETE FROM patients_auditevidenceexportack"* || "$joined" == *"INSERT INTO patients_auditevidenceexportack"* ]]; then
  exit 0
elif [[ "$joined" == *"SELECT segment_sequence ||"* ]]; then
  exit 0
elif [[ "$joined" == *"psql"* && "$joined" != *"--command="* ]]; then
  cat >/dev/null
  exit 0
elif [[ "$joined" == *"COPY (SELECT json_build_object"* ]]; then
  if [[ ! -f "$MEDTRACK_SECURITY_EVIDENCE_ROOT/state/checkpoint.env" ]]; then
    printf '{"id":1,"event_id":"00000000-0000-0000-0000-000000000001","occurred_at":"2026-08-29T12:00:00Z","category":"auth","action":"login","outcome":"failure","source":"web"}\n'
    printf '{"id":2,"event_id":"00000000-0000-0000-0000-000000000002","occurred_at":"2026-08-29T12:00:01Z","category":"auth","action":"login","outcome":"success","source":"web"}\n'
  else
    printf '{"id":3,"event_id":"00000000-0000-0000-0000-000000000003","occurred_at":"2026-08-29T12:00:02Z","category":"auth","action":"login","outcome":"success","source":"web"}\n'
  fi
elif [[ "$joined" == *"now() - min(occurred_at)"* ]]; then
  echo "${FAKE_AUDIT_LAG:-0}"
elif [[ "$joined" == *" ps -q web"* ]]; then
  echo synthetic-web-container
elif [[ "$1" == "inspect" && "$joined" == *"{{.Image}}"* ]]; then
  echo sha256:synthetic-image
elif [[ "$1" == "image" && "$2" == "inspect" ]]; then
  echo f01f9311882c24b865f4ccd48dd32bc9933e6b7f
else
  echo "Unexpected fake docker invocation: $joined" >&2
  exit 1
fi
FAKE_DOCKER
cat > "$test_root/alert-hook" <<'ALERT'
#!/usr/bin/env bash
printf '%s\n' "$1" >> "$FAKE_ALERT_LOG"
ALERT
cat > "$fake_bin/flock" <<'FAKE_FLOCK'
#!/usr/bin/env bash
exit 0
FAKE_FLOCK
cat > "$fake_bin/install" <<'FAKE_INSTALL'
#!/usr/bin/env bash
set -Eeuo pipefail
paths=()
while [[ $# -gt 0 ]]; do
  case "$1" in -d) shift ;; -m) shift 2 ;; *) paths+=("$1"); shift ;; esac
done
mkdir -p "${paths[@]}"
FAKE_INSTALL
chmod +x "$fake_bin/docker" "$fake_bin/flock" "$fake_bin/install" "$test_root/alert-hook"

printf '{"timestamp":"now","method":"POST","status":429,"duration_us":12,"bytes":0}\n' > "$log_root/caddy-access.json"
printf '{"timestamp":"now","method":"POST","status":429,"duration_us":10,"bytes":0}\n' > "$log_root/gunicorn-access.log"
export PATH="$fake_bin:$PATH"
export MEDTRACK_BACKUP_CONFIG="$test_root/no-config"
export MEDTRACK_REPO_ROOT="$repo_root"
export MEDTRACK_ENV_FILE="$test_root/no-env"
export MEDTRACK_SECURITY_EVIDENCE_ROOT="$evidence_root"
export MEDTRACK_SECURITY_LOG_DIR="$log_root"
export MEDTRACK_SECURITY_EVIDENCE_ALERT_HOOK="$test_root/alert-hook"
export MEDTRACK_SECURITY_FAILURE_ALERT_THRESHOLD=1
export MEDTRACK_SECURITY_EVIDENCE_KEEP_SEGMENTS=1
export FAKE_ALERT_LOG="$test_root/alerts.log"
export PYTHON_COMMAND=python

"$repo_root/scripts/export-security-evidence.sh"
"$repo_root/scripts/export-security-evidence.sh"
"$repo_root/scripts/verify-security-evidence.sh"
test -s "$evidence_root/state/anchor.env"
[[ "$(find "$evidence_root/segments" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d '[:space:]')" == 1 ]]
grep -Fq 'sustained authentication failures' "$FAKE_ALERT_LOG"
[[ "$(grep -c 'sustained authentication failures' "$FAKE_ALERT_LOG")" == 1 ]]
if grep -Ei 'authorization|cookie|query_string|request_body|patient[_ -]?search|clinical_payload|"uri"|"path"' \
  "$evidence_root"/segments/segment-*/*.jsonl; then
  echo "Security evidence retained a forbidden sensitive field" >&2
  exit 1
else
  scan_status=$?
  if [[ "$scan_status" != 1 ]]; then
    echo "Could not inspect exported security evidence" >&2
    exit 1
  fi
fi

printf '{"timestamp":"now","method":"GET","status":200,"duration_us":12,"bytes":0}\n' >> "$log_root/caddy-access.json"
printf '{"timestamp":"now","method":"GET","status":200,"duration_us":10,"bytes":0}\n' >> "$log_root/gunicorn-access.log"
: > "$FAKE_ALERT_LOG"
"$repo_root/scripts/export-security-evidence.sh"
"$repo_root/scripts/verify-security-evidence.sh"
test ! -s "$FAKE_ALERT_LOG"

snapshot_root="$test_root/verification-snapshot"
cp -a "$evidence_root" "$snapshot_root"
printf 'MEDTRACK_SECURITY_EVIDENCE_ROOT=%q\nMEDTRACK_SECURITY_EVIDENCE_ALLOW_STALE=0\n' \
  "$evidence_root" > "$test_root/live-config"
snapshot_segment="$(find "$snapshot_root/segments" -mindepth 1 -maxdepth 1 -type d -print -quit)"
printf 'tamper\n' >> "$snapshot_segment/audit-events.jsonl"
if MEDTRACK_BACKUP_CONFIG="$test_root/live-config" "$repo_root/scripts/verify-security-evidence.sh" \
  --root "$snapshot_root" --allow-stale >/dev/null 2>&1; then
  echo "Configured live evidence hid a corrupted explicit snapshot" >&2
  exit 1
fi
cp "$evidence_root/segments/${snapshot_segment##*/}/audit-events.jsonl" "$snapshot_segment/audit-events.jsonl"
sed -i 's/^completed_epoch=.*/completed_epoch=0/' "$snapshot_root/state/checkpoint.env"
MEDTRACK_BACKUP_CONFIG="$test_root/live-config" "$repo_root/scripts/verify-security-evidence.sh" \
  --root "$snapshot_root" --allow-stale
if MEDTRACK_BACKUP_CONFIG="$test_root/live-config" "$repo_root/scripts/verify-security-evidence.sh" \
  --root "$snapshot_root" >/dev/null 2>&1; then
  echo "Explicit snapshot root unexpectedly disabled the freshness check" >&2
  exit 1
fi

cp "$evidence_root/state/checkpoint.env" "$test_root/checkpoint.saved"
sed -i 's/^completed_epoch=.*/completed_epoch=0/' "$evidence_root/state/checkpoint.env"
if "$repo_root/scripts/verify-security-evidence.sh" >/dev/null 2>&1; then
  echo "Security evidence verifier accepted a stale checkpoint" >&2
  exit 1
fi
mv "$test_root/checkpoint.saved" "$evidence_root/state/checkpoint.env"

: > "$FAKE_ALERT_LOG"
export FAKE_AUDIT_LAG=99999
if "$repo_root/scripts/export-security-evidence.sh" >/dev/null 2>&1; then
  echo "Security evidence exporter accepted an excessive AuditEvent lag" >&2
  exit 1
fi
unset FAKE_AUDIT_LAG
grep -Fq 'audit/security evidence export failed' "$FAKE_ALERT_LOG"
"$repo_root/scripts/verify-security-evidence.sh"

segment_dir="$(find "$evidence_root/segments" -mindepth 1 -maxdepth 1 -type d -print -quit)"
printf 'tamper\n' >> "$segment_dir/audit-events.jsonl"
if "$repo_root/scripts/verify-security-evidence.sh" >/dev/null 2>&1; then
  echo "Security evidence verifier accepted a modified segment" >&2
  exit 1
fi
: > "$FAKE_ALERT_LOG"
if "$repo_root/scripts/export-security-evidence.sh" >/dev/null 2>&1; then
  echo "Security evidence exporter accepted a broken evidence chain" >&2
  exit 1
fi
grep -Fq 'audit/security evidence export failed' "$FAKE_ALERT_LOG"

cat > "$fake_bin/systemctl" <<'FAKE_SYSTEMCTL'
#!/usr/bin/env bash
set -Eeuo pipefail
[[ "$*" == 'show medtrack-security-evidence-export.service --property=ExecStart --value' ]]
printf '%s\n' "$FAKE_EXEC_START"
FAKE_SYSTEMCTL
chmod +x "$fake_bin/systemctl"
export FAKE_EXEC_START="{ path=$repo_root/scripts/export-security-evidence.sh ; argv[]=$repo_root/scripts/export-security-evidence.sh ; ignore_errors=no ; }"
"$repo_root/scripts/verify-security-evidence-runner.sh"
installed_runner="$test_root/installed-exporter"
cp "$repo_root/scripts/export-security-evidence.sh" "$installed_runner"
chmod +x "$installed_runner"
export FAKE_EXEC_START="{ path=$installed_runner ; argv[]=$installed_runner ; ignore_errors=no ; }"
"$repo_root/scripts/verify-security-evidence-runner.sh"
printf '\n# stale installed exporter\n' >> "$installed_runner"
if "$repo_root/scripts/verify-security-evidence-runner.sh" >/dev/null 2>&1; then
  echo "Runner verification accepted a stale installed exporter" >&2
  exit 1
fi
for command_text in '' "{ path=/bin/sh ; argv[]=/bin/sh -c exporter ; ignore_errors=no ; }" \
  "{ path=$repo_root/scripts/export-security-evidence.sh ; argv[]=$repo_root/scripts/export-security-evidence.sh ; ignore_errors=no ; } { path=$installed_runner ; argv[]=$installed_runner ; ignore_errors=no ; }"; do
  if FAKE_EXEC_START="$command_text" "$repo_root/scripts/verify-security-evidence-runner.sh" >/dev/null 2>&1; then
    echo "Runner verification accepted an unsupported or multiple command" >&2
    exit 1
  fi
done

echo "SECURITY_EVIDENCE_TEST_OK"
