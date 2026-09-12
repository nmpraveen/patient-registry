#!/usr/bin/env bash
set -Eeuo pipefail

checkpoint_root="${MEDTRACK_SECURITY_EVIDENCE_CHECKPOINT_ROOT:-}"
if [[ -z "$checkpoint_root" || "$checkpoint_root" != /* || ! -d "$checkpoint_root" || -L "$checkpoint_root" ]]; then
  echo "Security-evidence checkpoint root must be an absolute non-symlinked directory" >&2
  exit 1
fi

for command_name in awk cmp find grep sed sha256sum sort tr; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "Missing required command: $command_name" >&2
    exit 1
  }
done

checkpoint="$checkpoint_root/state/checkpoint.env"
if [[ ! -f "$checkpoint" || -L "$checkpoint" ]]; then
  echo "Security-evidence checkpoint file is missing or unsafe" >&2
  exit 1
fi
if find "$checkpoint_root" ! -type f ! -type d -print -quit | grep -q .; then
  echo "Security-evidence checkpoint contains a link or special file" >&2
  exit 1
fi

value_from() {
  local file="$1"
  local key="$2"
  sed -n "s/^${key}=//p" "$file" | tail -n 1 | tr -d '\r'
}

format="$(value_from "$checkpoint" checkpoint_format)"
sequence="$(value_from "$checkpoint" sequence)"
last_audit_id="$(value_from "$checkpoint" last_audit_id)"
chain_sha256="$(value_from "$checkpoint" chain_sha256)"
completed_epoch="$(value_from "$checkpoint" completed_epoch)"
last_segment="$(value_from "$checkpoint" last_segment)"
if [[ "$format" != "medtrack-security-evidence-checkpoint-v1" ||
  ! "$sequence" =~ ^[1-9][0-9]*$ || ! "$last_audit_id" =~ ^[0-9]+$ ||
  ! "$chain_sha256" =~ ^[0-9a-f]{64}$ || ! "$completed_epoch" =~ ^[0-9]+$ ||
  ! "$last_segment" =~ ^segment-[0-9]{8}-[0-9]{8}T[0-9]{6}Z$ ]]; then
  echo "Security-evidence checkpoint metadata is invalid" >&2
  exit 1
fi

segment_dir="$checkpoint_root/segments/$last_segment"
if [[ ! -d "$segment_dir" || -L "$segment_dir" ]]; then
  echo "Security-evidence checkpoint segment is missing or unsafe" >&2
  exit 1
fi
mapfile -t segment_dirs < <(find "$checkpoint_root/segments" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)
if (( ${#segment_dirs[@]} != 1 )) || [[ "${segment_dirs[0]}" != "$last_segment" ]]; then
  echo "Security-evidence checkpoint must contain exactly its referenced latest segment" >&2
  exit 1
fi

for required in audit-events.jsonl caddy-access.jsonl gunicorn-access.jsonl segment.meta manifest.sha256 chain.env; do
  if [[ ! -f "$segment_dir/$required" || -L "$segment_dir/$required" ]]; then
    echo "Security-evidence checkpoint segment is missing $required" >&2
    exit 1
  fi
done
find "$segment_dir" -maxdepth 1 -type f -printf '%f\n' | sort > "$checkpoint_root/.actual-files"
printf '%s\n' audit-events.jsonl caddy-access.jsonl chain.env gunicorn-access.jsonl manifest.sha256 segment.meta | sort > "$checkpoint_root/.expected-files"
if ! cmp -s "$checkpoint_root/.actual-files" "$checkpoint_root/.expected-files"; then
  rm -f "$checkpoint_root/.actual-files" "$checkpoint_root/.expected-files"
  echo "Security-evidence checkpoint segment contains unexpected files" >&2
  exit 1
fi
rm -f "$checkpoint_root/.actual-files" "$checkpoint_root/.expected-files"

while IFS= read -r manifest_line; do
  if [[ ! "$manifest_line" =~ ^[0-9a-f]{64}[[:space:]][\ \*](audit-events\.jsonl|caddy-access\.jsonl|gunicorn-access\.jsonl|segment\.meta)$ ]]; then
    echo "Security-evidence segment manifest is unsafe or incomplete" >&2
    exit 1
  fi
done < "$segment_dir/manifest.sha256"
(
  cd "$segment_dir"
  sha256sum --check --strict manifest.sha256 >/dev/null
)

segment_sequence="$(value_from "$segment_dir/segment.meta" sequence)"
previous_chain="$(value_from "$segment_dir/segment.meta" previous_chain_sha256)"
manifest_sha256="$(sha256sum "$segment_dir/manifest.sha256" | awk '{print $1}')"
recorded_manifest_sha256="$(value_from "$segment_dir/chain.env" manifest_sha256)"
recorded_chain_sha256="$(value_from "$segment_dir/chain.env" chain_sha256)"
calculated_chain_sha256="$(printf '%s\n%s\n' "$previous_chain" "$manifest_sha256" | sha256sum | awk '{print $1}')"
if [[ "$segment_sequence" != "$sequence" || ! "$previous_chain" =~ ^[0-9a-f]{64}$ ||
  "$manifest_sha256" != "$recorded_manifest_sha256" ||
  "$recorded_chain_sha256" != "$chain_sha256" || "$calculated_chain_sha256" != "$chain_sha256" ]]; then
  echo "Security-evidence checkpoint segment chain is invalid" >&2
  exit 1
fi

printf 'SECURITY_EVIDENCE_CHECKPOINT_OK sequence=%s chain_sha256=%s last_segment=%s\n' \
  "$sequence" "$chain_sha256" "$last_segment"
