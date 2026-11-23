#!/usr/bin/env python3
"""Kill unsafe admin-revoke reconciliation mutations using compiled production callbacks."""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app/src/main/java/com/waenhancer/xposed/features/privacy/AntiRevokeHook.java"
RUNNER = ROOT / "qa/test_revoke_sqlite_contract.py"

MUTANTS = {
    "remove-fix": ("reconcileAdminRevokeInsert(param);", "/* admin reconcile removed */"),
    "wrong-type": ("messageType != 64", "messageType != 63"),
    "skip-marker": ("!REVOKED_MESSAGES.containsKey(keyId)", "false"),
    "skip-identity": ("keyId.equals(cursor.getString(0))", "true"),
    "skip-ownership": ("cursor.getLong(1) == 0L", "cursor.getLong(1) >= 0L"),
    "skip-transaction": ("if (!db.inTransaction()) return;", "if (false) return;"),
    "allow-type64-row": (
        "cursor.getInt(2) != 15 && cursor.getInt(2) != 64",
        "cursor.getInt(2) != 15",
    ),
}


def run(source: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), "--source", str(source),
         "--scenario", "admin_revoke"],
        capture_output=True, text=True, timeout=120, check=False,
    )


def main() -> None:
    original = SOURCE.read_text(encoding="utf-8")
    reference = run(SOURCE)
    if reference.returncode != 0 or "checks passed" not in reference.stdout:
        raise AssertionError("candidate regression failed: " + reference.stdout + reference.stderr)

    with tempfile.TemporaryDirectory(prefix="waex-admin-revoke-mutants-") as directory:
        changed = Path(directory) / "AntiRevokeHook.java"
        for label, (old, new) in MUTANTS.items():
            if original.count(old) != 1:
                raise AssertionError(f"{label}: anchor not unique: {original.count(old)}")
            changed.write_text(original.replace(old, new, 1), encoding="utf-8")
            negative = run(changed)
            output = negative.stdout + negative.stderr
            if negative.returncode == 0:
                raise AssertionError(f"{label}: unsafe mutation escaped the JVM checks")
            if "error: " in output or "cannot find symbol" in output:
                raise AssertionError(f"{label}: compilation failed instead of behavior: {output[:1000]}")
            if not any(x in output for x in ("java.lang.AssertionError", "SQLITE_CONSTRAINT_PRIMARYKEY")):
                raise AssertionError(f"{label}: no behavioral rejection: {output[:1000]}")

    print(f"PASS: compiled candidate; {len(MUTANTS)} admin-revoke behavior mutants rejected")


if __name__ == "__main__":
    main()
