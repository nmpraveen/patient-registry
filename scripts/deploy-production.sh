#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: scripts/deploy-production.sh <expected-full-git-commit>" >&2
  exit 2
fi

expected_commit="$1"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ ! -f .env ]]; then
  echo "Missing $repo_root/.env" >&2
  exit 1
fi

actual_commit="$(git rev-parse HEAD)"
if [[ "$actual_commit" != "$expected_commit" ]]; then
  echo "Refusing deployment: expected $expected_commit but found $actual_commit" >&2
  exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Refusing deployment from a modified tracked worktree" >&2
  exit 1
fi

compose=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

echo "[1/6] Validating production Compose configuration"
"${compose[@]}" config --quiet

echo "[2/6] Pulling pinned service images"
"${compose[@]}" pull db caddy

echo "[3/6] Building the pinned MEDTRACK commit"
"${compose[@]}" build --pull web

echo "[4/6] Starting MEDTRACK"
"${compose[@]}" up -d --remove-orphans

echo "[5/6] Waiting for the web healthcheck"
for attempt in $(seq 1 24); do
  container_id="$("${compose[@]}" ps -q web)"
  status=""
  if [[ -n "$container_id" ]]; then
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$container_id")"
  fi
  if [[ "$status" == "healthy" ]]; then
    break
  fi
  if [[ "$attempt" -eq 24 ]]; then
    "${compose[@]}" ps
    "${compose[@]}" logs --tail 200 web
    echo "Web healthcheck did not become healthy" >&2
    exit 1
  fi
  sleep 5
done

echo "[6/6] Running Django deployment checks"
"${compose[@]}" exec -T web python manage.py check --deploy
"${compose[@]}" ps

echo "DEPLOY_PRODUCTION_OK commit=$actual_commit"
