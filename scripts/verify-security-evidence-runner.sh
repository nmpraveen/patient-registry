#!/usr/bin/env bash
set -Eeuo pipefail

# Read-only rollout gate: a systemd drop-in may still select a copied old runner.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
command_text="$(systemctl show medtrack-security-evidence-export.service --property=ExecStart --value)"
runner="$(sed -n 's/^{ path=\([^ ;]*\) ; argv\[\]=\1 ; [^{}]* }$/\1/p' <<<"$command_text")"
if [[ "$runner" != /* || "$runner" == *$'\n'* || ! -f "$runner" || ! -x "$runner" ]]; then
  echo "SECURITY_EVIDENCE_RUNNER_FAIL reason=unsupported-effective-command" >&2
  exit 1
fi
if ! cmp -s -- "$repo_root/scripts/export-security-evidence.sh" "$runner"; then
  echo "SECURITY_EVIDENCE_RUNNER_FAIL reason=installed-runner-differs-from-reviewed-source" >&2
  exit 1
fi
echo "SECURITY_EVIDENCE_RUNNER_OK"
