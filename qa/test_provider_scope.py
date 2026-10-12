#!/usr/bin/env python3
"""Compile and exercise production Binder UID/package checks without Android."""
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
xml_path = root / "app/src/main/res/values/arrays.xml"
xml = ET.parse(xml_path).getroot()
scopes = [item.text.strip() for group in xml.findall("string-array")
          if group.attrib.get("name") == "xposed_scope" for item in group.findall("item")
          if item.text and item.text.strip()]
assert scopes, f"No xposed_scope declared in {xml_path}"
# Verify the provider actually delegates to this production policy.
provider = (root / "app/src/main/java/com/waenhancer/xposed/bridge/HookProvider.java").read_text(encoding="utf-8")
assert "CallerScopePolicy.isTrusted(" in provider, "Provider must use tested UID policy"
assert "CallerScopePolicy.ownsPackage(" in provider, "Provider must use tested ownership policy"
source = root / "app/src/main/java/com/waenhancer/xposed/bridge/CallerScopePolicy.java"
harness = root / "qa/java/TestScopePolicy.java"
with tempfile.TemporaryDirectory() as temp:
    subprocess.run(["javac", "-d", temp, str(source), str(harness)], check=True)
    subprocess.run(["java", "-cp", temp,
                    "com.waenhancer.xposed.bridge.TestScopePolicy", *scopes], check=True)
