#!/usr/bin/env python3
"""Match every container HIGH/CRITICAL finding to an exact, expiring waiver."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys


SCHEMA = "medtrack.container-vex/v1"
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
ALLOWED_STATUS = {"affected", "fix_deferred", "will_not_fix"}
REQUIRED_FIELDS = {
    "vulnerability_id",
    "package_name",
    "installed_version",
    "target",
    "image_digest",
    "status",
    "justification",
    "source",
    "owner",
    "created_at",
    "expires_at",
}


def timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} is not an ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone: {value!r}")
    return parsed.astimezone(timezone.utc)


def identity(item: dict[str, object]) -> tuple[str, str, str, str]:
    return (
        str(item["vulnerability_id"]),
        str(item["package_name"]),
        str(item["installed_version"]),
        str(item["target"]),
    )


def findings(report: dict[str, object]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for target in report.get("Results") or []:
        target_name = str(target.get("Target", ""))
        for vulnerability in target.get("Vulnerabilities") or []:
            severity = str(vulnerability.get("Severity", "")).upper()
            if severity not in {"HIGH", "CRITICAL"}:
                continue
            result.append(
                {
                    "vulnerability_id": str(vulnerability.get("VulnerabilityID", "")),
                    "package_name": str(vulnerability.get("PkgName", "")),
                    "installed_version": str(vulnerability.get("InstalledVersion", "")),
                    "target": target_name,
                    "severity": severity,
                    "fixed_version": str(vulnerability.get("FixedVersion", "")),
                    "status": str(vulnerability.get("Status", "")),
                }
            )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--image-digest", required=True)
    args = parser.parse_args()
    if not DIGEST.fullmatch(args.image_digest):
        raise ValueError("--image-digest must be sha256:<64 lowercase hex characters>")

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    if policy.get("schema") != SCHEMA:
        raise ValueError(f"VEX policy schema must be {SCHEMA}")
    entries = policy.get("entries")
    if not isinstance(entries, list):
        raise ValueError("VEX policy entries must be a list")

    now = datetime.now(timezone.utc)
    validated: dict[tuple[str, str, str, str], dict[str, object]] = {}
    errors: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entry {index} is not an object")
            continue
        missing = sorted(REQUIRED_FIELDS - entry.keys())
        extra = sorted(entry.keys() - REQUIRED_FIELDS)
        if missing or extra:
            errors.append(f"entry {index} fields mismatch missing={missing} extra={extra}")
            continue
        key = identity(entry)
        if key in validated:
            errors.append(f"duplicate waiver identity: {key}")
        if entry["image_digest"] != args.image_digest:
            errors.append(f"waiver image digest mismatch for {key}")
        if entry["status"] not in ALLOWED_STATUS:
            errors.append(f"unsupported waiver status for {key}: {entry['status']!r}")
        if not str(entry["justification"]).strip() or not str(entry["owner"]).strip():
            errors.append(f"waiver justification/owner is empty for {key}")
        if not str(entry["source"]).startswith("https://"):
            errors.append(f"waiver source must be HTTPS for {key}")
        try:
            created = timestamp(str(entry["created_at"]), "created_at")
            expires = timestamp(str(entry["expires_at"]), "expires_at")
            if created > now or expires <= now or expires <= created:
                errors.append(f"waiver time window is invalid or expired for {key}")
        except ValueError as exc:
            errors.append(str(exc))
        validated[key] = entry

    detected = findings(report)
    detected_keys = {identity(item) for item in detected}
    for target in report.get("Results") or []:
        for secret in target.get("Secrets") or []:
            errors.append(
                "secret finding "
                f"rule={secret.get('RuleID', 'unknown')} target={target.get('Target', 'unknown')} "
                f"start_line={secret.get('StartLine', 'unknown')}"
            )
    for item in detected:
        key = identity(item)
        waiver = validated.get(key)
        if waiver is None:
            errors.append(
                "unwaived finding "
                f"{item['severity']} {item['vulnerability_id']} "
                f"package={item['package_name']} version={item['installed_version']} "
                f"target={item['target']} fixed={item['fixed_version'] or 'none'} "
                f"scanner_status={item['status'] or 'unknown'}"
            )
        else:
            print(
                "CONTAINER_VEX_RESIDUAL "
                f"severity={item['severity']} vulnerability={item['vulnerability_id']} "
                f"package={item['package_name']} version={item['installed_version']} "
                f"status={waiver['status']} expires={waiver['expires_at']} owner={waiver['owner']}"
            )
    for key in sorted(set(validated) - detected_keys):
        errors.append(f"unused or stale waiver entry: {key}")

    if errors:
        for error in errors:
            print(f"CONTAINER_VEX_FAIL {error}", file=sys.stderr)
        return 1
    critical = sum(item["severity"] == "CRITICAL" for item in detected)
    high = sum(item["severity"] == "HIGH" for item in detected)
    print(
        "CONTAINER_VEX_OK "
        f"image_digest={args.image_digest} high={high} critical={critical} "
        f"waivers={len(entries)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
