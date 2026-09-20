#!/usr/bin/env python3
"""Bounded request-log deltas and recoverable audit export acknowledgements."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import uuid


ACK_TABLE = "patients_auditevidenceexportack"
UNACKNOWLEDGED = (
    "NOT EXISTS (SELECT 1 FROM patients_auditevidenceexportack ack "
    "WHERE ack.event_id = patients_auditevent.event_id)"
)


def metadata(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)


def fsync_directory(path: Path) -> None:
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def durable_tree(path: Path) -> None:
    for item in path.iterdir():
        if item.is_file() and not item.is_symlink():
            with item.open("rb") as stream:
                os.fsync(stream.fileno())
    fsync_directory(path)


def open_log(path: Path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Unsafe log source")
    return gzip.open(path, "rb") if path.suffix == ".gz" else path.open("rb")


def prefix_matches(path: Path, cursor: dict) -> bool:
    with open_log(path) as stream:
        prefix = stream.read(cursor["prefix_bytes"])
        if len(prefix) != cursor["prefix_bytes"] or hashlib.sha256(prefix).hexdigest() != cursor["prefix_sha256"]:
            return False
        if cursor["offset"]:
            stream.seek(cursor["offset"] - 1)
            if not stream.read(1):
                return False
        return True


def ordered_logs(current: Path) -> list[Path]:
    """Oldest retained rotation through current; reject ambiguous filenames."""
    rotations = []
    if current.name == "gunicorn-access.log":
        seen = set()
        for path in current.parent.glob(current.name + ".*"):
            match = re.fullmatch(re.escape(current.name) + r"\.(\d+)(?:\.gz)?", path.name)
            if not match or path.is_symlink():
                raise ValueError("Ambiguous or unsafe Gunicorn rotation")
            number = int(match[1])
            if number in seen:
                raise ValueError("Duplicate Gunicorn rotation generation")
            seen.add(number)
            rotations.append((number, path))
        paths = [path for _, path in sorted(rotations, reverse=True)]
    else:
        seen = set()
        for path in current.parent.glob("caddy-access-*.json*"):
            match = re.fullmatch(r"caddy-access-([0-9T:Z.\-]+)\.json(?:\.gz)?", path.name)
            if not match or path.is_symlink() or match[1] in seen:
                raise ValueError("Ambiguous or unsafe Caddy rotation")
            seen.add(match[1])
            rotations.append((match[1], path))
        paths = [path for _, path in sorted(rotations)]
    if current.exists():
        if current.is_symlink():
            raise ValueError("Unsafe current log")
        paths.append(current)
    return paths


def capture_log(current: Path, cursor: dict | None, budget: int) -> tuple[bytes, dict | None]:
    """Read complete new lines, draining a retained rotated file before current.

    Cursors include a prefix fingerprint so copytruncate/rewrite is distinguishable
    from append even if the new file has already grown past the previous offset.
    Missing continuity fails closed; it never silently skips an unobserved suffix.
    """
    paths = ordered_logs(current)
    known_rotations = [path.stat().st_ino for path in paths if path != current]
    if cursor:
        if not isinstance(cursor.get("offset"), int) or cursor["offset"] < 0:
            raise ValueError("Invalid log cursor")
        inode_matches = [path for path in paths if path.stat().st_ino == cursor.get("inode") and prefix_matches(path, cursor)]
        fingerprint_matches = [path for path in paths if path != current and cursor["prefix_bytes"] > 0 and prefix_matches(path, cursor)]
        if len(inode_matches) == 1:
            previous = inode_matches[0]
            # Copytruncate may preserve the current inode and even its prefix.
            # A newly observed copy with the same prefix makes that case
            # ambiguous; stop instead of skipping old/new records.
            if previous == current and any(path.stat().st_ino not in cursor.get("known_rotations", []) for path in fingerprint_matches):
                raise ValueError("Ambiguous copytruncate log continuity")
            if previous == current and cursor["prefix_bytes"] == 0 and any(
                path != current and path.stat().st_ino not in cursor.get("known_rotations", []) for path in paths
            ):
                raise ValueError("Empty cursor cannot prove copytruncate continuity")
        elif not inode_matches and len(fingerprint_matches) == 1:
            previous = fingerprint_matches[0]
        else:
            raise ValueError(f"Log rotation continuity missing for {current.name}")
        index = paths.index(previous)
        sources = [(path, cursor["offset"] if path == previous else 0) for path in paths[index:]]
        if current.name == "gunicorn-access.log" and previous != current:
            start = int(previous.name.split(".")[2])
            generations = {int(path.name.split(".")[2]) for path in paths[index:] if path != current}
            if generations != set(range(1, start + 1)):
                raise ValueError("Missing intermediate Gunicorn rotation")
    elif current.exists():
        sources = [(current, 0)]
    else:
        return b"", None
    chunks = []
    result_cursor = cursor
    for path, offset in sources:
        with open_log(path) as stream:
            stream.seek(offset)
            block = stream.read(budget + 1)
            if path != current and block and len(block) <= budget and not block.endswith(b"\n"):
                raise ValueError(f"Closed rotated log has an incomplete final line: {current.name}")
            if block:
                stop = block[:budget].rfind(b"\n") + 1
                if not stop and len(block) > budget:
                    raise ValueError(f"Security log line exceeds export bound: {current.name}")
                block_to_keep = block[:stop]
            else:
                block_to_keep = b""
            new_offset = offset + len(block_to_keep)
            # Fingerprint only acknowledged bytes: an initially empty file must
            # not acquire a fingerprint of bytes that have not been exported.
            stream.seek(0)
            prefix = stream.read(min(new_offset, 4096))
            result_cursor = {
                "offset": new_offset,
                "prefix_bytes": len(prefix),
                "prefix_sha256": hashlib.sha256(prefix).hexdigest(),
                "inode": path.stat().st_ino,
                "known_rotations": known_rotations,
            }
            chunks.append(block_to_keep)
            budget -= len(block_to_keep)
            # An incomplete line or a bounded remainder must be retried before
            # switching to the newly opened log after rotation.
            if len(block_to_keep) != len(block) or budget == 0:
                break
    return b"".join(chunks), result_cursor


def capture_logs(log_root: Path, stage: Path, previous_meta: Path | None, maximum: int) -> str:
    previous = json.loads(metadata(previous_meta).get("log_cursors_json", "{}")) if previous_meta else {}
    cursors = {}
    for name in ("caddy-access.json", "gunicorn-access.log"):
        content, cursor = capture_log(log_root / name, previous.get(name), maximum)
        (stage / (name.rsplit(".", 1)[0] + ".jsonl")).write_bytes(content)
        if cursor is not None:
            cursors[name] = cursor
    return json.dumps(cursors, separators=(",", ":"), sort_keys=True)


def acknowledge_segment(segment: Path, execute) -> None:
    values = metadata(segment / "segment.meta")
    sequence = int(values["sequence"])
    chain = metadata(segment / "chain.env")["chain_sha256"]
    if sequence < 1 or not re.fullmatch(r"[0-9a-f]{64}", chain) or not re.fullmatch(r"segment-\d{8}-\d{8}T\d{6}Z", segment.name):
        raise ValueError("Invalid segment acknowledgement identity")
    # A database restored from another branch of the evidence chain must not
    # reuse acknowledgements belonging to a different segment at this sequence.
    execute(f"DELETE FROM {ACK_TABLE} WHERE segment_sequence={sequence} AND segment_chain_sha256 <> '{chain}'")
    batch = []
    with (segment / "audit-events.jsonl").open() as stream:
        for line in stream:
            event = json.loads(line)
            event_id = str(uuid.UUID(event["event_id"]))
            batch.append(f"('{event_id}',{sequence},'{chain}','{segment.name}',CURRENT_TIMESTAMP)")
            if len(batch) == 500:
                write_ack_batch(batch, execute)
                batch.clear()
    if batch:
        write_ack_batch(batch, execute)


def write_ack_batch(batch: list[str], execute) -> None:
    execute(
        f"INSERT INTO {ACK_TABLE} (event_id,segment_sequence,segment_chain_sha256,segment_name,acknowledged_at) VALUES "
        + ",".join(batch)
        + " ON CONFLICT (event_id) DO NOTHING"
    )


def reconcile_acknowledgements(evidence_root: Path, execute, progress: tuple[int, str] | None = None) -> None:
    checkpoint = metadata(evidence_root / "state/checkpoint.env")
    sequence = int(checkpoint["sequence"])
    segments = sorted((evidence_root / "segments").glob("segment-*"))
    head_chain = checkpoint.get("chain_sha256") or metadata(segments[-1] / "chain.env")["chain_sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", head_chain):
        raise ValueError("Invalid checkpoint hash")
    proven_sequence = 0
    if progress:
        for segment in segments:
            values = metadata(segment / "segment.meta")
            if int(values["sequence"]) == progress[0] and metadata(segment / "chain.env")["chain_sha256"] == progress[1]:
                proven_sequence = progress[0]
                break
        anchor_path = evidence_root / "state/anchor.env"
        if not proven_sequence and anchor_path.exists():
            anchor = metadata(anchor_path)
            if int(anchor["next_sequence"]) - 1 == progress[0] and anchor["previous_chain_sha256"] == progress[1]:
                proven_sequence = progress[0]
    execute("BEGIN")
    if not proven_sequence or proven_sequence > sequence:
        # Missing/foreign/ahead progress cannot certify earlier UUID coverage.
        # Discard only the recoverable ledger and replay available evidence.
        execute(f"DELETE FROM {ACK_TABLE}")
        proven_sequence = 0
    for segment in segments:
        if int(metadata(segment / "segment.meta")["sequence"]) > proven_sequence:
            acknowledge_segment(segment, execute)
    execute(
        "INSERT INTO patients_auditevidenceexportstate (id,segment_sequence,segment_chain_sha256) "
        f"VALUES (1,{sequence},'{head_chain}') ON CONFLICT (id) DO UPDATE SET "
        "segment_sequence=EXCLUDED.segment_sequence,segment_chain_sha256=EXCLUDED.segment_chain_sha256"
    )
    execute("COMMIT")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("logs", "ack", "sync"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--stage", type=Path)
    parser.add_argument("--previous-meta", type=Path)
    parser.add_argument("--maximum", type=int, default=10485760)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--database")
    parser.add_argument("--username")
    args = parser.parse_args()
    if args.mode == "logs":
        if args.maximum <= 0 or args.stage is None:
            parser.error("positive --maximum and --stage required")
        print(capture_logs(args.root, args.stage, args.previous_meta, args.maximum))
    elif args.mode == "sync":
        durable_tree(args.root)
        fsync_directory(args.root.parent)
    else:
        if not args.repo or not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value or "") for value in (args.database, args.username)):
            parser.error("--repo and simple database/user identifiers required")
        command = ["docker", "compose", "-f", str(args.repo / "docker-compose.yml"), "-f", str(args.repo / "docker-compose.prod.yml"),
                   "exec", "-T", "db", "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "--username=" + args.username, "--dbname=" + args.database]
        progress_result = subprocess.run(command + ["--tuples-only", "--no-align", "--command="
            "SELECT segment_sequence || ':' || segment_chain_sha256 FROM patients_auditevidenceexportstate WHERE id=1"],
            check=True, capture_output=True, text=True).stdout.strip()
        progress = None
        if progress_result:
            number, chain = progress_result.split(":", 1)
            progress = (int(number), chain)
        # A single psql transaction, streamed in bounded batches, replaces
        # thousands of per-segment Docker/psql launches at full retention.
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
        try:
            reconcile_acknowledgements(args.root, lambda sql: process.stdin.write(sql + ";\n"), progress)
            process.stdin.close()
            if process.wait() != 0:
                raise RuntimeError("Audit acknowledgement transaction failed")
        except BaseException:
            process.kill()
            process.wait()
            raise


if __name__ == "__main__":
    main()
