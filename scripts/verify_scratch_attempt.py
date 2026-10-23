#!/usr/bin/env python3
"""Validate the latest independent attempt against the exact restore receipt."""
import hashlib
import re
import sys
from pathlib import Path


def fields(raw):
    result = {}
    for line in raw.decode("ascii").splitlines():
        key, value = line.split("=", 1)
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def require(condition):
    if not condition:
        raise ValueError("invalid attempt")


def verify(attempt_path, receipt_path, now):
    attempt = fields(Path(attempt_path).read_bytes())
    raw = Path(receipt_path).read_bytes()
    receipt = fields(raw)
    require(attempt["attempt_format"] == "medtrack-independent-scratch-attempt-v1")
    require(attempt["status"] == "success")
    require(attempt["stage"] == "complete")
    require(attempt["alert_delivery"] == "not-needed")
    require(re.fullmatch(r"[0-9]+-[0-9]+-[0-9]+", attempt["attempt_id"]))
    require(attempt["attempt_id"] == receipt["attempt_id"])
    require(attempt["receipt_sha256"] == hashlib.sha256(raw).hexdigest())
    require(0 < int(attempt["started_epoch"]) <= int(receipt["completed_epoch"]) <= int(attempt["updated_epoch"]) <= now)


if __name__ == "__main__":
    try:
        verify(sys.argv[1], sys.argv[2], int(sys.argv[3]))
    except (AssertionError, KeyError, ValueError, OSError, UnicodeError, IndexError):
        print("SCRATCH_ATTEMPT_INVALID", file=sys.stderr)
        sys.exit(1)
