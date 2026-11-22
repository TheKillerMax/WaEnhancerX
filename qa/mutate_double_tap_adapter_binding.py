#!/usr/bin/env python3
"""Negative controls for the compiled, current double-tap adapter regression.

Each mutant compiles the real DoubleTapReactionHook and shared production
helpers. A compilation failure is never treated as a detected regression.
"""
from pathlib import Path
import re
import tempfile

from test_double_tap_adapter_binding import HOOK, ROOT, run


def main() -> None:
    source = (ROOT / HOOK).read_text(encoding="utf-8")
    mutants = (
        ("stale_bound_message", "row.setTag(TAG_BOUND_MSG, null);",
         "/* mutant: keep previously bound message */",
         1, "recycled null item cannot react to its predecessor"),
        ("missing_rebind_tap_reset", "tracker.resetAll();",
         "tracker.resetGesture();", 2,
         "a tap before row recycling cannot complete a later reaction"),
    )
    with tempfile.TemporaryDirectory(prefix="waex-doubletap-negative-") as base:
        for name, before, after, occurrences, expected in mutants:
            found = source.count(before)
            assert found == occurrences, (
                f"Invalid mutation point {name}: expected {occurrences}, got {found}"
            )
            folder = Path(base) / name
            folder.mkdir()
            changed = folder / HOOK.name
            changed.write_text(source.replace(before, after),
                               encoding="utf-8", newline="\n")
            out = folder / "execution"
            run(changed, out, allow_failure=True)
            compilation = (out / "compile.log").read_text(encoding="utf-8")
            assert "error:" not in compilation, f"Mutant {name} did not compile"
            result = (out / "tests.log").read_text(encoding="utf-8")
            summary = re.search(r"RESULT\|(\d+)\|(\d+)", result)
            assert summary and int(summary[1]) == 11 and int(summary[2]) > 0, (
                f"Mutant {name} did not fail a completed 11-case suite"
            )
            assert "FAIL|" + expected + "|" in result, (
                f"Mutant {name} escaped the targeted behavioral assertion"
            )
            print(f"PASS_NEGATIVE {name}: {summary.group(0)}")
    print(f"NEGATIVE_CONTROLS {len(mutants)}/{len(mutants)}")


if __name__ == "__main__":
    main()
