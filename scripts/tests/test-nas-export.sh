#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf -- "$test_root"' EXIT

source_root="$test_root/source"
export_root="$test_root/export"
state_file="$test_root/state/last-success.epoch"
fake_bin="$test_root/bin"
mkdir -p "$source_root/rapid" "$export_root" "$fake_bin"
cat > "$fake_bin/getent" <<'FAKE_GETENT'
#!/usr/bin/env bash
exit 0
FAKE_GETENT
cat > "$fake_bin/install" <<'FAKE_INSTALL'
#!/usr/bin/env bash
set -Eeuo pipefail
directory_mode=0
positional=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -d) directory_mode=1; shift ;;
    -o|-g|-m) shift 2 ;;
    *) positional+=("$1"); shift ;;
  esac
done
if (( directory_mode )); then
  mkdir -p "${positional[@]}"
else
  cp "${positional[0]}" "${positional[1]}"
fi
FAKE_INSTALL
cat > "$fake_bin/chown" <<'FAKE_CHOWN'
#!/usr/bin/env bash
exit 0
FAKE_CHOWN
chmod +x "$fake_bin/getent" "$fake_bin/install" "$fake_bin/chown"
export PATH="$fake_bin:$PATH"

create_triplet() {
  local stamp="$1"
  local archive="medtrack-prod-rapid-${stamp}.tar.age"
  printf 'encrypted-%s\n' "$stamp" > "$source_root/rapid/$archive"
  (
    cd "$source_root/rapid"
    sha256sum "$archive" > "$archive.sha256"
  )
  printf 'archive=%s\ncompleted_utc=%s\n' "$archive" "$stamp" > "$source_root/rapid/$archive.complete"
}

create_triplet 20260912T120000Z
create_triplet 20260912T180000Z

common_env=(
  SOURCE_ROOT="$source_root"
  EXPORT_ROOT="$export_root"
  EXPORT_OWNER="$(id -u)"
  EXPORT_GROUP="$(id -g)"
  STATE_FILE="$state_file"
)
env "${common_env[@]}" "$repo_root/deploy/nas-export/export-encrypted-backups.sh"
test "$(find "$export_root/rapid" -maxdepth 1 -type f | wc -l)" -eq 6

rm -- "$source_root/rapid/medtrack-prod-rapid-20260912T120000Z.tar.age"{,.sha256,.complete}
create_triplet 20260913T000000Z
env "${common_env[@]}" "$repo_root/deploy/nas-export/export-encrypted-backups.sh"

test ! -e "$export_root/rapid/medtrack-prod-rapid-20260912T120000Z.tar.age"
test -f "$export_root/rapid/medtrack-prod-rapid-20260912T180000Z.tar.age.complete"
test -f "$export_root/rapid/medtrack-prod-rapid-20260913T000000Z.tar.age.complete"
test "$(find "$export_root/rapid" -maxdepth 1 -type f | wc -l)" -eq 6
test -s "$state_file"

echo "NAS_EXPORT_TEST_OK"
