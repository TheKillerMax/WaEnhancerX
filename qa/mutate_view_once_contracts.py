#!/usr/bin/env python3
"""Require compiled behavioral rejection of focused view-once regressions."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from test_view_once_contracts import EXPECTED_CHECKS, PRODUCTION

ROOT = Path(__file__).resolve().parents[1]
HOOK = "com/waenhancer/xposed/features/privacy/AntiViewOnceHook.java"
CONTRACT = "com/waenhancer/xposed/features/privacy/ViewOnceMessageContract.java"
MUTATIONS = (
    ("reverse_ownership", CONTRACT, "!fields.own.getBoolean(key)", "fields.own.getBoolean(key)"),
    ("ignore_key_ambiguity", CONTRACT,
     "if (key != null && !key.equals(candidate)) return null;",
     "if (key != null && !key.equals(candidate)) continue;"),
    ("bind_unrelated_setters", HOOK,
     "if (messages.accepts(target)) targets.add(target);",
     "for (Method extra : type.getDeclaredMethods()) if (messages.accepts(extra)) targets.add(extra);"),
    ("ignore_scoped_privacy", HOOK,
     "if (!active || !getPrivacy().isOn(PrivacyToggle.ANTI_VIEW_ONCE)) return;",
     'if (!active || !prefs.getBoolean("anti_view_once", false)) return;'),
    ("remove_partial_activation_gate", HOOK,
     "if (!active || !getPrivacy().isOn(PrivacyToggle.ANTI_VIEW_ONCE)) return;",
     "if (!getPrivacy().isOn(PrivacyToggle.ANTI_VIEW_ONCE)) return;"),
    ("accept_incomplete_key", CONTRACT,
     'return id != null && !id.isEmpty() && fields.chat.get(key) != null\n                    && !fields.own.getBoolean(key);',
     "return !fields.own.getBoolean(key);"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("--out must be fresh")
    args.out.mkdir(parents=True)
    sources = {name: (args.source_root / "app/src/main/java" / name).read_bytes()
               for name in PRODUCTION}
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in sources.items()}

    def run(row):
        name, changed, old, new = row
        base = args.out / name
        source = base / "source"
        for relative, value in sources.items():
            if relative == changed:
                text = value.decode("utf-8").replace("\r\n", "\n")
                if text.count(old) != 1:
                    raise RuntimeError("Mutation no longer matches exactly once: " + name)
                value = text.replace(old, new).encode("utf-8")
            target = source / "app/src/main/java" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
        with (base / "driver.log").open("w", encoding="utf-8") as stream:
            code = subprocess.run(
                [sys.executable, str(ROOT / "qa/test_view_once_contracts.py"),
                 "--source-root", str(source), "--out", str(base / "evidence")],
                stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                check=False, timeout=120).returncode
        result = json.loads((base / "evidence/RESULT.json").read_text())
        totals = result["observed_totals"]
        rejected = (code == 1 and result["compile_exit"] == 0
                    and result["run_exit"] not in (0, None)
                    and len(totals) == 1 and int(totals[0][0]) == EXPECTED_CHECKS
                    and int(totals[0][1]) > 0 and not result["accepted"])
        return {"name": name, "behavioral_rejection": rejected,
                "compile_exit": result["compile_exit"], "run_exit": result["run_exit"],
                "totals": totals,
                "mutated_sha256": result["source_sha256"][changed]}

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(run, MUTATIONS))
    unchanged = all(hashlib.sha256(
        (args.source_root / "app/src/main/java" / name).read_bytes()).hexdigest() == value
                    for name, value in hashes.items())
    accepted = unchanged and all(row["behavioral_rejection"] for row in rows)
    result = {"accepted": accepted, "source_sha256": hashes, "sources_unchanged": unchanged,
              "mutants": rows, "scope": "Compiled JVM behavioral controls; no real host execution"}
    (args.out / "RESULT.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    if not accepted:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
