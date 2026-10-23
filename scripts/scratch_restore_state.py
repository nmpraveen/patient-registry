#!/usr/bin/env python3
"""Serialize scratch attempt ownership and receipt publication on Linux/Windows."""
import argparse
from contextlib import contextmanager
import errno
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time


def fields(raw):
    result = {}
    for line in raw.decode("ascii").splitlines():
        key, value = line.split("=", 1)
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


@contextmanager
def state_lock(attempt):
    lock_path = Path(str(attempt) + ".lock")
    if lock_path.is_symlink():
        raise ValueError("invalid lock path")
    with lock_path.open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            if os.fstat(lock.fileno()).st_size == 0:
                lock.write(b"\0")
                lock.flush()
            def acquire():
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            def release():
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            def acquire():
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            def release():
                fcntl.flock(lock, fcntl.LOCK_UN)
        deadline = time.monotonic() + 5
        while True:
            try:
                acquire()
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK) or time.monotonic() >= deadline:
                    raise
                time.sleep(0.02)
        try:
            yield
        finally:
            release()


def atomic_write(path, content):
    descriptor, name = tempfile.mkstemp(prefix=".scratch-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write(args):
    attempt = Path(args.attempt)
    receipt = Path(args.receipt)
    if not attempt.is_absolute() or attempt.is_symlink() or attempt.resolve() == receipt.resolve():
        raise ValueError("invalid state path")
    attempt.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with state_lock(attempt):
        if not args.claim and fields(attempt.read_bytes())["attempt_id"] != args.attempt_id:
            raise ValueError("attempt superseded")
        now = int(time.time())
        receipt_hash = "none"
        if args.status == "success":
            if args.claim or args.stage != "complete" or args.alert != "not-needed" or not receipt.is_absolute() or receipt.is_symlink():
                raise ValueError("invalid completion")
            receipt.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            raw = ("receipt_format=medtrack-independent-scratch-restore-v1\n"
                   f"completed_epoch={now}\nattempt_id={args.attempt_id}\nalert_contract=required\n").encode("ascii")
            # Ownership is still locked: an older hook cannot replace a newer
            # attempt's receipt. A crash before state publication leaves running.
            atomic_write(receipt, raw)
            receipt_hash = hashlib.sha256(raw).hexdigest()
        content = ("attempt_format=medtrack-independent-scratch-attempt-v1\n"
                   f"attempt_id={args.attempt_id}\nstatus={args.status}\nstarted_epoch={args.started_epoch}\nupdated_epoch={now}\n"
                   f"stage={args.stage}\nalert_delivery={args.alert}\nreceipt_sha256={receipt_hash}\n").encode("ascii")
        atomic_write(attempt, content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for argument in ("attempt", "receipt", "attempt-id", "started-epoch", "stage", "status", "alert"):
        parser.add_argument("--" + argument, required=True)
    parser.add_argument("--claim", action="store_true")
    try:
        write(parser.parse_args())
    except (KeyError, ValueError, OSError, UnicodeError):
        print("SCRATCH_ATTEMPT_WRITE_FAILED", file=sys.stderr)
        sys.exit(1)
