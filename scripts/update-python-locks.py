#!/usr/bin/env python3
"""Regenerate reviewed, hash-locked Python requirements in the runtime image."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


PYTHON_LOCK_IMAGE = (
    "python:3.12.13-slim-bookworm@"
    "sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2"
)
PIP_TOOLS_VERSION = "7.6.1"


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    mount = f"type=bind,source={repo_root},target=/workspace"
    command = ["docker", "run", "--rm", "--mount", mount, "--workdir", "/workspace"]
    if os.name != "nt" and hasattr(os, "getuid"):
        command.extend(["--user", f"{os.getuid()}:{os.getgid()}"])
    command.extend(
        [
            "--env",
            "HOME=/tmp/medtrack-lock-home",
            "--env",
            "CUSTOM_COMPILE_COMMAND=python scripts/update-python-locks.py",
            PYTHON_LOCK_IMAGE,
            "sh",
            "-euc",
            f"""
mkdir -p "$HOME"
python -m venv /tmp/medtrack-lock-venv
/tmp/medtrack-lock-venv/bin/python -m pip install --quiet --disable-pip-version-check --no-cache-dir pip-tools=={PIP_TOOLS_VERSION}
for source in requirements.in requirements-ci.in; do
  output="${{source%.in}}.txt"
  /tmp/medtrack-lock-venv/bin/pip-compile \
    --quiet \
    --generate-hashes \
    --allow-unsafe \
    --resolver=backtracking \
    --strip-extras \
    --no-emit-index-url \
    --output-file="$output" \
    "$source"
done
""",
        ]
    )
    try:
        subprocess.run(command, cwd=repo_root, check=True)
    except FileNotFoundError:
        print("Docker is required to regenerate Python lock files.", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        return exc.returncode
    print(f"PYTHON_LOCKS_UPDATED image={PYTHON_LOCK_IMAGE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
