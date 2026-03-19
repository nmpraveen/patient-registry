#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: scripts/restore.sh <backup_dir>" >&2
  exit 1
fi

BACKUP_DIR="$1"
SQL_FILE="$BACKUP_DIR/database.sql"
ENV_FILE="$BACKUP_DIR/.env.backup"
COMPOSE_FILE="$BACKUP_DIR/docker-compose.yml.backup"
DEV_COMPOSE_FILE="$BACKUP_DIR/docker-compose.dev.yml.backup"
OVERRIDE_COMPOSE_FILE="$BACKUP_DIR/docker-compose.override.yml.backup"

if [ ! -f "$SQL_FILE" ]; then
  echo "Missing $SQL_FILE" >&2
  exit 1
fi

if [ -f "$ENV_FILE" ]; then
  cp "$ENV_FILE" .env
  echo "Restored .env from backup"
fi
if [ -f "$COMPOSE_FILE" ]; then
  cp "$COMPOSE_FILE" docker-compose.yml
  echo "Restored docker-compose.yml from backup"
fi
if [ -f "$DEV_COMPOSE_FILE" ]; then
  cp "$DEV_COMPOSE_FILE" docker-compose.dev.yml
  echo "Restored docker-compose.dev.yml from backup"
fi
if [ -f "$OVERRIDE_COMPOSE_FILE" ]; then
  cp "$OVERRIDE_COMPOSE_FILE" docker-compose.override.yml
  echo "Restored docker-compose.override.yml from backup"
fi
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

echo "Recreating DB schema..."
docker compose exec -T db psql -U "${POSTGRES_USER:-patient_registry}" -d postgres -c "DROP DATABASE IF EXISTS ${POSTGRES_DB:-patient_registry};"
docker compose exec -T db psql -U "${POSTGRES_USER:-patient_registry}" -d postgres -c "CREATE DATABASE ${POSTGRES_DB:-patient_registry};"

echo "Restoring database..."
docker compose exec -T db psql -U "${POSTGRES_USER:-patient_registry}" "${POSTGRES_DB:-patient_registry}" < "$SQL_FILE"

echo "Restore complete."
