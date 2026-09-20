#!/usr/bin/env bash
# Sourced by deployment/recovery entrypoints; FD 7 stays open for the operation.
acquire_medtrack_operation_lock() {
  local lock_file="${MEDTRACK_OPERATION_LOCK:-/run/medtrack-operations.lock}"
  if [[ "$lock_file" != /* || -L "$lock_file" || ! -d "$(dirname "$lock_file")" ]]; then
    echo "Operation lock must use an absolute file in a trusted existing directory" >&2
    return 1
  fi
  command -v flock >/dev/null || { echo "flock is required for production mutations" >&2; return 1; }
  exec 7>"$lock_file"
  if ! flock -n 7; then
    echo "Another MEDTRACK deployment or recovery mutation owns the operation lock" >&2
    return 75
  fi
}
