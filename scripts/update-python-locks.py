#!/usr/bin/env python3
"""Regenerate reviewed, hash-locked Python requirements in the runtime image."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


RUNTIME_LOCK_IMAGE = "python:3.12.13-alpine3.23@sha256:601d3d3797e90e2534782e69c85fafb7971b43f24c7b1b079b7e48dd435e458d"
CI_LOCK_IMAGE = "python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2"
LOCK_TARGETS = (
    ("requirements.in", "requirements.txt", RUNTIME_LOCK_IMAGE),
    ("requirements-ci.in", "requirements-ci.txt", CI_LOCK_IMAGE),
)
PIP_TOOLS_VERSION = "7.6.1"


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    mount = f"type=bind,source={repo_root},target=/workspace"
    try:
        for source, output, image in LOCK_TARGETS:
            command = ["docker", "run", "--rm", "--mount", mount, "--workdir", "/workspace"]
            if os.name != "nt" and hasattr(os, "getuid"):
                command.extend(["--user", f"{os.getuid()}:{os.getgid()}"])
            command.extend(
                [
                    "--env",
                    "HOME=/tmp/medtrack-lock-home",
                    "--env",
                    "CUSTOM_COMPILE_COMMAND=python scripts/update-python-locks.py",
                    image,
                    "sh",
                    "-euc",
                    f"""
mkdir -p "$HOME"
python -m venv /tmp/medtrack-lock-venv
/tmp/medtrack-lock-venv/bin/python -m pip install --quiet --disable-pip-version-check --no-cache-dir pip-tools=={PIP_TOOLS_VERSION}
/tmp/medtrack-lock-venv/bin/pip-compile \
  --quiet \
  --generate-hashes \
  --allow-unsafe \
  --resolver=backtracking \
  --strip-extras \
  --no-emit-index-url \
  --output-file="{output}" \
  "{source}"
""",
                ]
            )
            subprocess.run(command, cwd=repo_root, check=True)
            print(f"PYTHON_LOCK_UPDATED source={source} output={output} image={image}")
    except FileNotFoundError:
        print("Docker is required to regenerate Python lock files.", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        return exc.returncode
    print("PYTHON_LOCKS_UPDATED targets=2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
