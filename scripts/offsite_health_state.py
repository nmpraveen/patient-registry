#!/usr/bin/env python3
"""Cache verified remote object identities without replacing periodic full scrubs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def object_identity(stat: dict) -> dict | None:
    hashes = stat.get("Hashes") or {}
    usable_hash = any(isinstance(value, str) and value.strip() for value in hashes.values())
    if stat.get("IsDir") or not stat.get("ID") or not isinstance(stat.get("Size"), int) or not usable_hash:
        return None  # Providers without stable identity + content hashes get full hashing.
    return {key: stat.get(key) for key in ("ID", "Size", "ModTime", "Hashes")}


def can_reuse(receipt: dict, identity: dict | None, expected: str, now: int, maximum_age: int) -> bool:
    return bool(identity and receipt.get("identity") == identity and receipt.get("sha256") == expected
                and isinstance(receipt.get("hashed_epoch"), int)
                and 0 <= now - receipt["hashed_epoch"] <= maximum_age)


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def verify(remote: str, expected: str, config: str, cache_root: Path, mode: str, maximum_age: int) -> str:
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        raise ValueError("Invalid ciphertext hash")
    cache_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(cache_root, 0o700)
    cache_file = cache_root / (hashlib.sha256(remote.encode()).hexdigest() + ".json")
    command = ["rclone", "--config", config]

    def identity():
        result = subprocess.run(command + ["lsjson", remote, "--stat", "--hash"], check=True, capture_output=True, text=True)
        return object_identity(json.loads(result.stdout))

    before = identity()
    try:
        receipt = json.loads(cache_file.read_text())
    except (FileNotFoundError, ValueError):
        receipt = {}
    now = int(time.time())
    if mode == "incremental" and can_reuse(receipt, before, expected, now, maximum_age):
        return "identity-verified"
    digest = hashlib.sha256()
    process = subprocess.Popen(command + ["cat", remote], stdout=subprocess.PIPE)
    try:
        for chunk in iter(lambda: process.stdout.read(1024 * 1024), b""):
            digest.update(chunk)
    finally:
        process.stdout.close()
    if process.wait() != 0 or digest.hexdigest() != expected:
        raise ValueError("Ciphertext stream hash mismatch")
    after = identity()
    if before != after:
        raise ValueError("Remote object changed during hashing")
    atomic_json(cache_file, {"identity": after, "sha256": expected, "hashed_epoch": now})
    return "stream-hashed"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--remote", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("all", "incremental"), required=True)
    parser.add_argument("--maximum-age", type=int, default=691200)
    args = parser.parse_args()
    print(verify(args.remote, args.sha256, args.config, args.cache_root, args.mode, args.maximum_age))
