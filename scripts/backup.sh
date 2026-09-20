#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# Compatibility-only local snapshot; this never satisfies the encrypted
# pre-deployment receipt gate.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
out_dir="${1:-backups/$stamp}"
if [[ ! -f .env ]]; then echo "Missing .env in repo root" >&2; exit 1; fi
if [[ -e "$out_dir" || -L "$out_dir" ]]; then
  echo "Refusing to reuse an existing backup destination" >&2
  exit 1
fi
mkdir -p "$(dirname "$out_dir")"
mkdir -m 0700 "$out_dir"
trap 'echo "Local backup incomplete; no COMPLETE marker was written" >&2' ERR

echo "[1/3] Backing up Postgres database..."
docker compose exec -T db sh -ceu \
  'exec pg_dump --format=plain --no-owner --no-privileges --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
  > "$out_dir/database.sql.partial"
test -s "$out_dir/database.sql.partial"
mv "$out_dir/database.sql.partial" "$out_dir/database.sql"

echo "[2/3] Backing up env/config files..."
install -m 0600 .env "$out_dir/.env.backup"
for config in docker-compose.yml docker-compose.dev.yml docker-compose.prod.yml docker-compose.override.yml deploy/Caddyfile; do
  if [[ -f "$config" ]]; then install -D -m 0600 "$config" "$out_dir/$config.backup"; fi
done

echo "[3/3] Recording app commit..."
git rev-parse HEAD > "$out_dir/app_commit.txt"
(
  cd "$out_dir"
  find . -type f ! -name manifest.sha256 -print0 | sort -z | xargs -0 sha256sum > manifest.sha256
  sha256sum --check --strict manifest.sha256 >/dev/null
  printf 'medtrack-local-upgrade-backup-v2\n' > COMPLETE
)
trap - ERR
echo "Local backup complete at: $out_dir (encrypted offsite receipt still required for production deployment)"
