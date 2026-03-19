#!/usr/bin/env bash
set -euo pipefail

STAMP=$(date +"%Y%m%d-%H%M%S")
OUT_DIR=${1:-backups/$STAMP}
mkdir -p "$OUT_DIR"

if [ ! -f .env ]; then
  echo "Missing .env in repo root" >&2
  exit 1
fi
set -a
source .env
set +a

echo "[1/3] Backing up Postgres database..."
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-patient_registry}" "${POSTGRES_DB:-patient_registry}" > "$OUT_DIR/database.sql"

echo "[2/3] Backing up env/config files..."
cp .env "$OUT_DIR/.env.backup"
cp docker-compose.yml "$OUT_DIR/docker-compose.yml.backup"
if [ -f docker-compose.dev.yml ]; then
  cp docker-compose.dev.yml "$OUT_DIR/docker-compose.dev.yml.backup"
fi
if [ -f docker-compose.override.yml ]; then
  cp docker-compose.override.yml "$OUT_DIR/docker-compose.override.yml.backup"
fi

echo "[3/3] Recording app commit..."
git rev-parse --short HEAD > "$OUT_DIR/app_commit.txt"

echo "Backup complete at: $OUT_DIR"
