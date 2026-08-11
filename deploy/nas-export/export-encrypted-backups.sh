#!/usr/bin/env bash
set -Eeuo pipefail

umask 027

source_root="${SOURCE_ROOT:-/srv/medtrack/offsite-backups/local}"
export_root="${EXPORT_ROOT:-/srv/medtrack/nas-export/data}"
export_owner="${EXPORT_OWNER:-root}"
export_group="${EXPORT_GROUP:-medtrack-nas-readers}"
state_file="${STATE_FILE:-/srv/medtrack/nas-export/.last-success.epoch}"
tiers=(rapid daily weekly monthly pre-deployment canary)

for command_name in cmp find getent install ln mktemp sha256sum stat; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 1
  fi
done

if [[ "$source_root" != /* || "$export_root" != /* || "$state_file" != /* ]]; then
  echo "Source, export, and state paths must be absolute" >&2
  exit 1
fi
if [[ ! -d "$source_root" || -L "$source_root" ]]; then
  echo "Encrypted source root is missing or symlinked: $source_root" >&2
  exit 1
fi
if ! getent group "$export_group" >/dev/null 2>&1; then
  echo "Export group does not exist: $export_group" >&2
  exit 1
fi

install -d -o "$export_owner" -g "$export_group" -m 0750 "$export_root"
if [[ -L "$export_root" ]]; then
  echo "Refusing a symlinked export root" >&2
  exit 1
fi

publish_immutable() {
  local source_file="$1"
  local destination_dir="$2"
  local name destination_file temp_file
  name="${source_file##*/}"
  destination_file="$destination_dir/$name"

  if [[ -e "$destination_file" ]]; then
    if [[ ! -f "$destination_file" || -L "$destination_file" ]]; then
      echo "Existing export target is not a regular file: $destination_file" >&2
      return 1
    fi
    if ! cmp -s "$source_file" "$destination_file"; then
      echo "Immutable export conflict: $destination_file" >&2
      return 1
    fi
    return 0
  fi

  temp_file="$(mktemp "$destination_dir/.${name}.XXXXXX")"
  install -o "$export_owner" -g "$export_group" -m 0640 "$source_file" "$temp_file"
  if ln "$temp_file" "$destination_file" 2>/dev/null; then
    rm -f -- "$temp_file"
    return 0
  fi
  rm -f -- "$temp_file"
  if [[ -f "$destination_file" && ! -L "$destination_file" ]] && cmp -s "$source_file" "$destination_file"; then
    return 0
  fi
  echo "Failed to publish immutable export target: $destination_file" >&2
  return 1
}

published_sets=0
for tier in "${tiers[@]}"; do
  source_tier="$source_root/$tier"
  [[ -d "$source_tier" ]] || continue
  destination_tier="$export_root/$tier"
  install -d -o "$export_owner" -g "$export_group" -m 0750 "$destination_tier"

  while IFS= read -r -d '' marker; do
    marker_name="${marker##*/}"
    if [[ ! "$marker_name" =~ ^medtrack-prod-${tier}-[0-9]{8}T[0-9]{6}Z\.tar\.age\.complete$ ]]; then
      echo "Refusing unexpected completion marker: $marker_name" >&2
      exit 1
    fi
    archive="${marker%.complete}"
    checksum="$archive.sha256"
    for source_file in "$archive" "$checksum" "$marker"; do
      if [[ ! -s "$source_file" || -L "$source_file" ]]; then
        echo "Incomplete or symlinked backup triplet: $source_file" >&2
        exit 1
      fi
    done
    (
      cd "$source_tier"
      sha256sum -c "${checksum##*/}" >/dev/null
    )

    publish_immutable "$archive" "$destination_tier"
    publish_immutable "$checksum" "$destination_tier"
    publish_immutable "$marker" "$destination_tier"
    published_sets=$((published_sets + 1))
  done < <(find "$source_tier" -maxdepth 1 -type f -name "medtrack-prod-${tier}-*.tar.age.complete" -print0 | sort -z)
done

state_dir="${state_file%/*}"
install -d -o "$export_owner" -g "$export_group" -m 0750 "$state_dir"
state_temp="$(mktemp "$state_dir/.last-success.XXXXXX")"
date -u +%s > "$state_temp"
chown "$export_owner:$export_group" "$state_temp"
chmod 0640 "$state_temp"
mv -f -- "$state_temp" "$state_file"

printf 'MEDTRACK_NAS_EXPORT_OK sets=%s export_root=%s\n' "$published_sets" "$export_root"
