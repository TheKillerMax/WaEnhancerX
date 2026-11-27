#!/usr/bin/env python3
"""Retain only individually verified graph bytes after an explicit Retry-After deferral.

A checkpoint is NOT a complete framework bundle or a passing gate. Its clock
is conservative: collection time plus the reported interval. Resume never
performs network operations and fails before the caller's acquisition while
the interval is active. Cache scoping/eviction remains a GitHub limitation.
"""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import time

from framework_dependency_bundle import LOCK, checked, load_lock, regular, sha

MANIFEST = "partial.json"


def finite(value):
    return type(value) in (float, int) and math.isfinite(value) and value >= 0


def real_directory(path):
    if path.is_symlink() or not path.is_dir():
        raise ValueError("Expected a real partial input directory: " + str(path))


def dependencies(lock):
    return {item["name"]: item for item in load_lock(lock) if item["directory"] == "deps"}


def inventory(directory, items):
    real_directory(directory)
    result = {}
    for path in sorted(directory.iterdir()):
        if path.name not in items:
            raise ValueError("Unexpected partial graph entry: " + path.name)
        item = items[path.name]
        checked(path, item)
        result[path.name] = {"bytes": item["bytes"], "sha256": item["sha256"]}
    return result


def separate(left, right):
    a, b = left.resolve(), right.resolve()
    if a == b or a in b.parents or b in a.parents:
        raise ValueError("Partial cache, producer and receipt paths must be separate")


def capture(deps, receipt, checkpoint, lock=LOCK, *, now=None):
    """Capture a failed, closed worker's pinned bytes; never accept its graph."""
    separate(deps, checkpoint)
    separate(receipt, checkpoint)
    separate(receipt, deps)
    if checkpoint.exists() or checkpoint.is_symlink():
        raise ValueError("Use a fresh checkpoint directory")
    regular(receipt)
    record = json.loads(receipt.read_text(encoding="utf-8"))
    if record.get("accepted") is not False or record.get("worker_closed") is not True:
        raise ValueError("Checkpoint requires a failed, closed acquisition worker")
    if record.get("lock_sha256") != sha(lock):
        raise ValueError("Receipt lock identity mismatch")
    items = dependencies(lock)
    seen = set()
    deferred = []
    for row in record["files"]:
        name = row["name"]
        if name in seen or name not in items:
            raise ValueError("Invalid receipt dependency inventory")
        seen.add(name)
        item = items[name]
        if (row.get("sha256"), row.get("bytes")) != (item["sha256"], item["bytes"]):
            raise ValueError("Receipt dependency identity mismatch")
        for attempt in row["attempts"]:
            if attempt.get("status") == "retry_deferred_beyond_budget":
                delay = attempt.get("retry_after_seconds")
                if attempt.get("http_status") not in (429, 503) or not finite(delay) or delay <= 0:
                    raise ValueError("Deferral is not an explicit valid server interval")
                deferred.append(delay)
    if not deferred:
        return None  # No checkpoint for integrity errors or unrelated failures.
    if len(deferred) != 1 or seen != set(items):
        raise ValueError("Ambiguous or incomplete deferred receipt")
    files = inventory(deps, items)
    if len(files) >= len(items):
        raise ValueError("Partial checkpoint must remain incomplete")
    observed = time.time() if now is None else now
    delay = deferred[0]
    deadline = observed + delay
    if not finite(observed) or not finite(deadline):
        raise ValueError("Unrepresentable server interval")
    manifest = {"schema": 1, "complete": False, "lock_sha256": sha(lock),
                "receipt_sha256": sha(receipt), "created_epoch": observed,
                "retry_after_seconds": delay, "resume_not_before_epoch": deadline,
                "files": files}
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=checkpoint.parent, prefix=".partial-") as temporary:
        stage = Path(temporary) / "checkpoint"
        folder = stage / "deps"
        folder.mkdir(parents=True)
        for name in files:
            shutil.copyfile(deps / name, folder / name)
            checked(folder / name, items[name])
        (stage / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        if checkpoint.exists() or checkpoint.is_symlink():
            raise ValueError("Checkpoint destination appeared during collection")
        os.rename(stage, checkpoint)
    return manifest


def verify(checkpoint, lock=LOCK, *, now=None):
    """Check the exact incomplete cache and enforce its conservative cooldown."""
    real_directory(checkpoint)
    names = {p.name for p in checkpoint.iterdir()}
    if names not in ({MANIFEST}, {MANIFEST, "deps"}):
        raise ValueError("Unexpected partial checkpoint paths")
    path = checkpoint / MANIFEST
    regular(path)
    m = json.loads(path.read_text(encoding="utf-8"))
    if m.get("schema") != 1 or m.get("complete") is not False or m.get("lock_sha256") != sha(lock):
        raise ValueError("Partial checkpoint identity mismatch")
    created, delay, deadline = (m.get(k) for k in
                                ("created_epoch", "retry_after_seconds", "resume_not_before_epoch"))
    observed = time.time() if now is None else now
    if (not all(finite(x) for x in (created, delay, deadline, observed)) or delay <= 0
            or not finite(created + delay) or deadline != created + delay or observed < created):
        raise ValueError("Invalid partial checkpoint clock")
    items = dependencies(lock)
    actual = inventory(checkpoint / "deps", items) if "deps" in names else {}
    if not isinstance(m.get("files"), dict) or actual != m["files"] or len(actual) >= len(items):
        raise ValueError("Partial checkpoint inventory mismatch")
    if observed < deadline:
        raise ValueError(f"Server Retry-After is still active; no acquisition before epoch {deadline}")
    return {"ready_to_resume": True, "complete": False, "verified_files": len(actual),
            "resume_not_before_epoch": deadline, "lock_sha256": sha(lock)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("capture", "verify"))
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--deps", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.mode == "capture":
        if args.deps is None or args.receipt is None:
            parser.error("capture requires --deps and --receipt")
        result = capture(args.deps, args.receipt, args.checkpoint)
        print(json.dumps({"captured": result is not None, "complete": False,
                          "verified_files": len(result["files"]) if result else 0,
                          "resume_not_before_epoch": result["resume_not_before_epoch"] if result else None}))
    else:
        if args.deps is not None or args.receipt is not None:
            parser.error("verify accepts only --checkpoint")
        print(json.dumps(verify(args.checkpoint)))


if __name__ == "__main__":
    main()
