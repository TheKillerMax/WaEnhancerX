#!/usr/bin/env python3
"""JDK regression for provider-side preference schema type enforcement."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
bridge = root / "app/src/main/java/com/waenhancer/xposed/bridge"
provider = (bridge / "HookProvider.java").read_text(encoding="utf-8")
schema = (root / "app/src/main/java/com/waenhancer/config/PreferenceSchema.java").read_text(encoding="utf-8")
assert "PreferenceSchema.entry(key)" in provider
assert "entry.store == PreferenceSchema.Store.PRIVATE" in provider
assert "PreferenceWriteTypePolicy.accepts(entry.type.name(), type)" in provider
assert provider.index("PreferenceWriteTypePolicy.accepts(entry.type.name(), type)") < provider.index('if ("boolean".equals(type) && op.getBoolean')
for enum in ("BOOLEAN", "STRING", "STRING_SET", "INT", "LONG", "FLOAT"):
    assert enum in schema, f"schema type missing: {enum}"
with tempfile.TemporaryDirectory() as temp:
    subprocess.run(["javac", "--release", "17", "-d", temp,
                    str(bridge / "PreferenceWriteTypePolicy.java"),
                    str(root / "qa/java/TestPreferenceWriteTypePolicy.java")], check=True)
    subprocess.run(["java", "-cp", temp,
                    "com.waenhancer.xposed.bridge.TestPreferenceWriteTypePolicy"], check=True)
