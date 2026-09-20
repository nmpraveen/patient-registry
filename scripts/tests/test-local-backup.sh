#!/usr/bin/env bash
set -Eeuo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf -- "$test_root"' EXIT
mkdir -p "$test_root/repo/scripts" "$test_root/repo/deploy" "$test_root/bin"
cp "$repo_root/scripts/backup.sh" "$test_root/repo/scripts/backup.sh"
printf 'UNSAFE=$(touch %s/should-not-exist)\n' "$test_root" > "$test_root/repo/.env"
printf 'synthetic\n' > "$test_root/repo/docker-compose.yml"
printf 'synthetic production\n' > "$test_root/repo/docker-compose.prod.yml"
printf 'synthetic edge\n' > "$test_root/repo/deploy/Caddyfile"
cat > "$test_root/bin/docker" <<'FAKE'
#!/usr/bin/env bash
[[ "${FAKE_DUMP_FAIL:-0}" == 0 ]] || exit 23
printf '%s\n' '-- synthetic SQL only'
FAKE
cat > "$test_root/bin/git" <<'FAKE'
#!/usr/bin/env bash
printf '%040d\n' 1
FAKE
chmod +x "$test_root/bin/docker" "$test_root/bin/git"
export PATH="$test_root/bin:$PATH"
umask 022
bash "$test_root/repo/scripts/backup.sh" "$test_root/success"
[[ "$(stat -c %a "$test_root/success")" == 700 ]]
[[ "$(stat -c %a "$test_root/success/database.sql")" == 600 ]]
[[ "$(stat -c %a "$test_root/success/.env.backup")" == 600 ]]
[[ -f "$test_root/success/COMPLETE" && -f "$test_root/success/deploy/Caddyfile.backup" ]]
test ! -e "$test_root/should-not-exist"
if bash "$test_root/repo/scripts/backup.sh" "$test_root/success" >/dev/null 2>&1; then exit 1; fi
if FAKE_DUMP_FAIL=1 bash "$test_root/repo/scripts/backup.sh" "$test_root/failed" >/dev/null 2>&1; then exit 1; fi
test ! -e "$test_root/failed/COMPLETE"
echo LOCAL_BACKUP_TEST_OK
