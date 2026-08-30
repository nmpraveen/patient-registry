#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
test_root="$(mktemp -d "$repo_root/.edge-auth-test.XXXXXX")"
docker_repo_root="$repo_root"
docker_test_root="$test_root"
if command -v cygpath >/dev/null 2>&1; then
  docker_repo_root="$(cygpath -w "$repo_root")"
  docker_test_root="$(cygpath -w "$test_root")"
fi
container_name="medtrack-edge-throttle-test-$$"
backend_name="medtrack-edge-backend-test-$$"
network_name="medtrack-edge-network-test-$$"
cleanup() {
  docker rm -f "$container_name" >/dev/null 2>&1 || true
  docker rm -f "$backend_name" >/dev/null 2>&1 || true
  docker network rm "$network_name" >/dev/null 2>&1 || true
  rm -rf -- "$test_root"
}
trap cleanup EXIT

image_ref="medtrack-caddy:auth-throttle-test"
MSYS_NO_PATHCONV=1 docker build --quiet -f "$docker_repo_root/deploy/Dockerfile.caddy" \
  -t "$image_ref" "$docker_repo_root" >/dev/null
MSYS_NO_PATHCONV=1 docker run --rm --entrypoint sh -e MEDTRACK_DOMAIN=http://medtrack.invalid \
  -v "$docker_repo_root/deploy/Caddyfile:/etc/caddy/Caddyfile:ro" "$image_ref" -ceu \
  'caddy list-modules | grep -Fxq http.handlers.rate_limit && caddy validate --config /etc/caddy/Caddyfile' >/dev/null
adapted_config="$(MSYS_NO_PATHCONV=1 docker run --rm --entrypoint caddy -e MEDTRACK_DOMAIN=http://medtrack.invalid \
  -v "$docker_repo_root/deploy/Caddyfile:/etc/caddy/Caddyfile:ro" "$image_ref" \
  adapt --config /etc/caddy/Caddyfile)"
grep -Fq '"delete":["X-Medtrack-Client-IP"]' <<<"$adapted_config"
grep -Fq '"X-Medtrack-Client-Ip":["{http.request.remote.host}"]' <<<"$adapted_config"
if env SECRET_KEY=synthetic-test-key POSTGRES_PASSWORD=synthetic \
  MEDTRACK_REQUIRE_TRUSTED_PROXY=True MEDTRACK_EXPECTED_PROXY_IP=172.30.0.10 \
  MEDTRACK_TRUSTED_PROXY_CIDRS=172.30.0.11/32 \
  python "$repo_root/manage.py" check >/dev/null 2>&1; then
  echo "Production startup accepted an inconsistent trusted-proxy allowlist" >&2
  exit 1
fi
if docker run --rm --entrypoint sh caddy:2.11.4-alpine@sha256:5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648 \
  -ceu 'caddy list-modules | grep -Fxq http.handlers.rate_limit'; then
  echo "Stock Caddy unexpectedly satisfied the required edge rate-limit module gate" >&2
  exit 1
fi

mkdir -p "$test_root/logs"
docker network create "$network_name" >/dev/null
docker run -d --name "$backend_name" --network "$network_name" --network-alias web \
  --entrypoint caddy "$image_ref" respond --listen :8000 --body OK >/dev/null
for _ in $(seq 1 20); do
  docker exec "$backend_name" wget -qO- http://127.0.0.1:8000/ >/dev/null 2>&1 && break
  sleep 1
done
MSYS_NO_PATHCONV=1 docker run -d --name "$container_name" --network "$network_name" -e MEDTRACK_DOMAIN=http://medtrack.invalid \
  -p 127.0.0.1::80 \
  -v "$docker_repo_root/deploy/Caddyfile:/etc/caddy/Caddyfile:ro" \
  -v "$docker_test_root/logs:/var/log/medtrack" "$image_ref" >/dev/null
port="$(docker inspect --format '{{(index (index .NetworkSettings.Ports "80/tcp") 0).HostPort}}' "$container_name")"
for _ in $(seq 1 30); do
  ready_status="$(curl --silent --header 'Host: medtrack.invalid' --output /dev/null --write-out '%{http_code}' \
    "http://127.0.0.1:$port/" || true)"
  [[ "$ready_status" == 200 ]] && break
  sleep 1
done
[[ "${ready_status:-}" == 200 ]]

assert_429_after() {
  local path="$1" allowed="$2" response_headers="$test_root/headers.txt" response_body="$test_root/body.txt" status=""
  for _ in $(seq 1 "$((allowed + 1))"); do
    status="$(curl --silent --dump-header "$response_headers" --output "$response_body" \
      --write-out '%{http_code}' --header 'Host: medtrack.invalid' --request POST \
      "http://127.0.0.1:$port$path")"
    [[ "$status" == 429 ]] && break
  done
  if [[ "$status" != 429 ]]; then
    echo "Expected 429 for $path, got $status" >&2
    cat "$response_headers" "$response_body" >&2
    docker inspect --format '{{json .Mounts}}' "$container_name" >&2
    docker logs "$container_name" >&2
    return 1
  fi
  grep -Eqi '^Retry-After:' "$response_headers"
  grep -Fq 'Too many authentication attempts. Retry later.' "$response_body"
}

assert_429_after /login/ 12
assert_429_after /api/auth/token/ 12
assert_429_after /api/auth/token/refresh/ 30
assert_429_after /login/device/authenticate/verify/ 15
status="$(curl --silent --header 'Host: medtrack.invalid' --output /dev/null --write-out '%{http_code}' --request POST "http://127.0.0.1:$port/admin/login/")"
[[ "$status" == 429 ]]

docker stop "$container_name" >/dev/null
if rg -i 'authorization|cookie|query_string|request_body|patient[_ -]?search|clinical_payload|"uri"|"path"|remote_ip|client_ip' "$test_root/logs"; then
  echo "PHI-safe edge log retained a forbidden request field" >&2
  exit 1
fi
rg -q '"status":429' "$test_root/logs/caddy-access.json"

echo "EDGE_AUTH_THROTTLE_TEST_OK"
