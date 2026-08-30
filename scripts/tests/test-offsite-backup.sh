#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf -- "$test_root"' EXIT

fake_bin="$test_root/bin"
fake_remote="$test_root/remote"
backup_root="$test_root/backups"
mkdir -p "$fake_bin" "$fake_remote" "$backup_root"

cat > "$fake_bin/docker" <<'FAKE_DOCKER'
#!/usr/bin/env bash
set -Eeuo pipefail
joined="$*"
if [[ "$1" == "--version" ]]; then
  echo "Docker version test"
elif [[ "$1" == "image" && "$2" == "inspect" && "$joined" == *"org.opencontainers.image.revision"* ]]; then
  echo "${FAKE_SOURCE_COMMIT:?set FAKE_SOURCE_COMMIT}"
elif [[ "$1" == "image" && "$2" == "inspect" && "$joined" == *"medtrack.git-tree"* ]]; then
  echo "${FAKE_SOURCE_TREE:?set FAKE_SOURCE_TREE}"
elif [[ "$1" == "image" && "$2" == "inspect" && "$joined" == *"medtrack.build-context"* ]]; then
  echo "git-archive-allowlist-v1"
elif [[ "$1" == "image" && "$2" == "inspect" && "$joined" == *"medtrack.context-policy"* ]]; then
  echo "${FAKE_CONTEXT_POLICY:?set FAKE_CONTEXT_POLICY}"
elif [[ "$1" == "inspect" && "$joined" == *"{{.Image}}"* ]]; then
  echo "sha256:synthetic-live-source-image"
elif [[ "$joined" == *" ps -q web"* ]]; then
  echo "synthetic-live-web-container"
elif [[ "$joined" == *"pg_dump"* ]]; then
  printf 'PGDMP-test-database\n'
elif [[ "$joined" == *"pg_restore"* ]]; then
  cat >/dev/null
  printf '; Archive created for test\n1; 0 0 TABLE public.test postgres\n'
elif [[ "$joined" == *"SHOW server_version"* ]]; then
  echo "16.14"
elif [[ "$joined" == *"COPY (SELECT app"* ]]; then
  printf 'contenttypes.0001_initial\npatients.0001_initial\n'
elif [[ "$joined" == *" compose "* || "$1" == "compose" ]]; then
  if [[ "$joined" == *" version"* ]]; then
    echo "Docker Compose version test"
  elif [[ "$joined" == *" images"* ]]; then
    echo "test image identity"
  else
    echo "Unexpected fake docker invocation: $joined" >&2
    exit 1
  fi
else
  echo "Unexpected fake docker invocation: $joined" >&2
  exit 1
fi
FAKE_DOCKER

cat > "$fake_bin/age" <<'FAKE_AGE'
#!/usr/bin/env bash
set -Eeuo pipefail
output=""
input=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -r) shift 2 ;;
    -o) output="$2"; shift 2 ;;
    *) input="$1"; shift ;;
  esac
done
cp "$input" "$output"
FAKE_AGE

cat > "$fake_bin/flock" <<'FAKE_FLOCK'
#!/usr/bin/env bash
exit 0
FAKE_FLOCK

cat > "$fake_bin/install" <<'FAKE_INSTALL'
#!/usr/bin/env bash
set -Eeuo pipefail
directory_mode=0
create_parent=0
positional=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -d) directory_mode=1; shift ;;
    -D) create_parent=1; shift ;;
    -m) shift 2 ;;
    *) positional+=("$1"); shift ;;
  esac
done
if (( directory_mode )); then
  mkdir -p "${positional[@]}"
else
  source_file="${positional[0]}"
  destination="${positional[1]}"
  if (( create_parent )); then
    mkdir -p "$(dirname "$destination")"
  fi
  cp "$source_file" "$destination"
fi
FAKE_INSTALL

cat > "$fake_bin/rclone" <<'FAKE_RCLONE'
#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "$1" == "--config" ]]; then
  shift 2
fi
command_name="$1"
shift
remote_to_path() {
  local spec="$1"
  printf '%s/%s' "$FAKE_RCLONE_ROOT" "${spec#*:}"
}
case "$command_name" in
  listremotes)
    echo "medtrack-drive:"
    ;;
  mkdir)
    mkdir -p "$(remote_to_path "$1")"
    ;;
  copyto)
    source_file="$1"
    destination="$(remote_to_path "$2")"
    if [[ -e "$destination" ]]; then
      echo "immutable destination exists: $destination" >&2
      exit 1
    fi
    mkdir -p "$(dirname "$destination")"
    cp "$source_file" "$destination"
    ;;
  check)
    local_dir="$1"
    remote_dir="$(remote_to_path "$2")"
    shift 2
    while [[ $# -gt 0 ]]; do
      if [[ "$1" == "--include" ]]; then
        filename="${2#/}"
        cmp "$local_dir/$filename" "$remote_dir/$filename"
        shift 2
      else
        shift
      fi
    done
    ;;
  lsf)
    remote_dir="$(remote_to_path "$1")"
    if [[ -d "$remote_dir" ]]; then
      find "$remote_dir" -maxdepth 1 -type f -name '*.complete' -printf '%f\n'
    fi
    ;;
  deletefile)
    rm -f -- "$(remote_to_path "$1")"
    ;;
  about)
    printf '{"free":1000000000,"used":1}\n'
    ;;
  *)
    echo "Unexpected fake rclone command: $command_name" >&2
    exit 1
    ;;
esac
FAKE_RCLONE

chmod +x "$fake_bin/docker" "$fake_bin/age" "$fake_bin/flock" "$fake_bin/install" "$fake_bin/rclone"
printf '[medtrack-drive]\ntype = drive\n' > "$test_root/rclone.conf"
printf 'age1testrecipient\n' > "$test_root/recipient.txt"
printf 'POSTGRES_DB=test\n' > "$test_root/production.env"

export PATH="$fake_bin:$PATH"
export FAKE_RCLONE_ROOT="$fake_remote"
export MEDTRACK_BACKUP_CONFIG="$test_root/no-config"
export MEDTRACK_REPO_ROOT="$repo_root"
export MEDTRACK_ENV_FILE="$test_root/production.env"
export MEDTRACK_OFFSITE_ROOT="$backup_root"
export MEDTRACK_BACKUP_STATE_ROOT="$backup_root/state"
export RCLONE_CONFIG="$test_root/rclone.conf"
export RCLONE_REMOTE="medtrack-drive:medtrack/test"
export AGE_RECIPIENT_FILE="$test_root/recipient.txt"
export FAKE_SOURCE_COMMIT="$(git -C "$repo_root" rev-parse HEAD)"
export FAKE_SOURCE_TREE="$(git -C "$repo_root" rev-parse "$FAKE_SOURCE_COMMIT^{tree}")"
export FAKE_CONTEXT_POLICY="$(printf '%s\n%s\n' "$(git -C "$repo_root" rev-parse "$FAKE_SOURCE_COMMIT:Dockerfile")" "$(git -C "$repo_root" rev-parse "$FAKE_SOURCE_COMMIT:.dockerignore")" | sha256sum | awk '{print $1}')"

MEDTRACK_BACKUP_TIMESTAMP=20260811T010000Z "$repo_root/scripts/backup-offsite.sh" --tier canary
MEDTRACK_BACKUP_TIMESTAMP=20260811T020000Z "$repo_root/scripts/backup-offsite.sh" --tier canary

local_dir="$backup_root/local/canary"
remote_dir="$fake_remote/medtrack/test/canary"
[[ "$(find "$local_dir" -maxdepth 1 -type f | wc -l | tr -d '[:space:]')" == "3" ]]
[[ "$(find "$remote_dir" -maxdepth 1 -type f | wc -l | tr -d '[:space:]')" == "3" ]]
[[ -f "$local_dir/medtrack-prod-canary-20260811T020000Z.tar.age.complete" ]]
[[ -f "$remote_dir/medtrack-prod-canary-20260811T020000Z.tar.age.complete" ]]
[[ ! -e "$local_dir/medtrack-prod-canary-20260811T010000Z.tar.age" ]]
[[ -s "$backup_root/state/last-success-canary.epoch" ]]
[[ -s "$backup_root/state/latest-canary.receipt" ]]
grep -Fxq 'receipt_format=medtrack-offsite-receipt-v2' "$backup_root/state/latest-canary.receipt"
grep -Fxq 'tier=canary' "$backup_root/state/latest-canary.receipt"
grep -Fxq "source_commit=$FAKE_SOURCE_COMMIT" "$backup_root/state/latest-canary.receipt"
grep -Fxq "target_commit=$FAKE_SOURCE_COMMIT" "$backup_root/state/latest-canary.receipt"
grep -Fxq 'source_image_id=sha256:synthetic-live-source-image' "$backup_root/state/latest-canary.receipt"
[[ -z "$(find "$backup_root/staging" -mindepth 1 -print -quit)" ]]

echo "OFFSITE_BACKUP_TEST_OK"
