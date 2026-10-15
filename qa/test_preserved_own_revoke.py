#!/usr/bin/env python3
"""Regression for scoped preservation of outgoing revoke SQLite row IDs (JDK only)."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
privacy = root / "app/src/main/java/com/waenhancer/xposed/features/privacy"
original = (privacy / "AntiRevokeHook.java").read_text(encoding="utf-8")
assert 'values.getAsInteger("message_type")' in original
assert "PreservedOwnRowIdPolicy.shouldStripPlaceholderId(" in original
assert "PRESERVED_OWN_ROW_IDS.remove(String.valueOf(rowId))" not in original
assert 'values.remove("_id");' in original
with tempfile.TemporaryDirectory() as temp:
    subprocess.run(["javac", "--release", "17", "-d", temp,
                    str(privacy / "PreservedOwnRowIdPolicy.java"),
                    str(root / "qa/TestPreservedOwnRevoke.java")], check=True)
    subprocess.run(["java", "-cp", temp,
                    "com.waenhancer.xposed.features.privacy.TestPreservedOwnRevoke"], check=True)
