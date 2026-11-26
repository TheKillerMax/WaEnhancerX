#!/usr/bin/env python3
"""Guard type-safe Anti-Revoke indicator preferences in the current Privacy UI."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'app/src/main/java/com/waenhancer'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, help='Fresh directory for behavioral negative logs and source identities')
args = parser.parse_args()
if args.out:
    args.out.mkdir(parents=True, exist_ok=False)
ui = (SRC / 'ui/screens/privacy/GlobalPrivacySettingsScreen.kt').read_text()
schema = (SRC / 'config/PreferenceSchema.java').read_text()
hook = (SRC / 'xposed/features/privacy/AntiRevokeHook.java').read_text()
entries = dict(re.findall(r'add\(entries,\s*"([^"]+)",\s*Type\.([A-Z_]+),', schema))
expected = {
    'antirevokestatus': 'STRING',
    'anti_revoke_indicator': 'INT',
    'deleted_message_color': 'INT',
}
for key, kind in expected.items():
    assert entries[key] == kind, (key, entries.get(key))
assert 'preferenceManager.putString("antirevokestatus", if (value) "1" else "0")' in ui
assert 'preferenceManager.putInt("anti_revoke_indicator", valKey.toInt())' in ui
assert 'preferenceManager.putInt("deleted_message_color", colorInt)' in ui
assert 'preferenceManager.getAll()["deleted_message_color"]' in ui
assert 'DeletedIndicatorPreferencePolicy.toColorHex(' in ui
assert 'DeletedIndicatorPreferencePolicy.toArgbOrNull(' in ui
for unsafe in ['putString("anti_revoke_indicator",', 'putString("deleted_message_color",',
               'putBoolean("antirevokestatus",']:
    assert unsafe not in ui, unsafe
# Existing hooks read canonical INT values or legacy String values without loss.
assert 'prefs.getInt("deleted_message_color",' in hook
assert 'prefs.getInt("anti_revoke_indicator", 2)' in hook
# Registration and live events must use the same typed reader for this STRING key.
assert 'return isAntiRevokeStatusEnabled(context, prefs);' in hook
assert 'public static boolean isAntiRevokeStatusEnabled(Context context, SharedPreferences prefs)' in hook
registry = (SRC / 'xposed/core/FeatureRegistry.java').read_text()
assert '|| AntiRevokeHook.isAntiRevokeStatusEnabled(context, prefs),' in registry
assert '|| prefs.getBoolean("antirevokestatus", false),' not in registry
with tempfile.TemporaryDirectory(prefix='waex_deleted_indicator_') as output:
    subprocess.run(['javac', '--release', '17', '-d', output,
                    str(SRC/'ui/screens/privacy/DeletedIndicatorPreferencePolicy.java'),
                    str(ROOT/'qa/java/TestDeletedIndicatorPreferencePolicy.java')], check=True)
    subprocess.run(['java', '-cp', output,
                    'com.waenhancer.ui.screens.privacy.TestDeletedIndicatorPreferencePolicy'], check=True)
print('PASS: Anti-Revoke indicator type-safe UI and compatible hook wiring')
subprocess.run([sys.executable, str(ROOT / 'qa/test_deleted_indicator_bridge.py')], check=True)

# Each negative compiles the same actual bridge and reader. A compilation failure
# is not an accepted rejection: the corresponding behavioral assertion must fail.

def replace_once(source, old, new):
    assert source.count(old) == 1, "Mutation anchor must match exactly once: " + old
    return source.replace(old, new, 1)

controls = [
    ("reader_boolean_regression", replace_once(hook, 
        "return isAntiRevokeStatusEnabled(context, prefs);",
        'return isEnabled("antirevokestatus", false);'), None, "status",
        "status reader case 0 bridge=true"),
    ("status_only_registry_regression", None, replace_once(registry, 
        "|| AntiRevokeHook.isAntiRevokeStatusEnabled(context, prefs),",
        '|| prefs.getBoolean("antirevokestatus", false),'), "registry",
        "status-only registry case 0 bridge=true"),
    ("invalid_string_fail_open", replace_once(hook, 
        'return "1".equals(value) || "true".equalsIgnoreCase((String) value);',
        'return !"0".equals(value) && !"false".equalsIgnoreCase((String) value);'),
        None, "status", "status reader case 6 bridge=true"),
    ("foreign_scope_leak", replace_once(hook, 
        'key = packageName + ":" + key;', 'key = "com.whatsapp:" + key;'),
        None, "status", "other package status must not leak"),
    ("swallowed_assertion", replace_once(hook,
        '} catch (RuntimeException | LinkageError error) {', '} catch (Throwable error) {'),
        None, "status", "unexpected preference assertion must propagate"),
]
results = []
with tempfile.TemporaryDirectory(prefix="waex-status-negative-") as folder:
    for name, changed_hook, changed_registry, scenario, expected_failure in controls:
        command = [sys.executable, str(ROOT / "qa/test_deleted_indicator_bridge.py"),
                   "--scenario", scenario]
        if changed_hook is not None:
            assert changed_hook != hook, name
            candidate = Path(folder) / (name + ".java")
            candidate.write_text(changed_hook, encoding="utf-8")
            command += ["--source", str(candidate)]
        if changed_registry is not None:
            assert changed_registry != registry, name
            candidate = Path(folder) / (name + ".java")
            candidate.write_text(changed_registry, encoding="utf-8")
            command += ["--registry-source", str(candidate)]
        result = subprocess.run(command, text=True, capture_output=True, timeout=120)
        output = result.stdout + result.stderr
        if args.out:
            (args.out / (name + ".log")).write_text(output, encoding="utf-8")
        results.append({"name": name, "returncode": result.returncode,
                        "compile_succeeded": "COMPILE_OK: actual BaseFeature" in output,
                        "expected_failure": expected_failure,
                        "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest()})
        assert result.returncode != 0 and "COMPILE_OK: actual BaseFeature" in output and ("java.lang.AssertionError: " + expected_failure) in output, (name, output)
        print("PASS: behavioral negative rejected " + name + ": " + expected_failure)

if args.out:
    paths = [SRC / "xposed/features/privacy/AntiRevokeHook.java", SRC / "xposed/core/FeatureRegistry.java",
             SRC / "xposed/core/BaseFeature.kt", SRC / "xposed/bridge/client/PreferenceBridgeClient.java",
             SRC / "config/PreferenceSchema.java", ROOT / "qa/test_deleted_indicator_bridge.py", Path(__file__)]
    (args.out / "result.json").write_text(json.dumps({"behavioral_mutants": results,
        "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
        "scope": "Production status readers/registry predicate/BaseFeature with real preference bridge; explicit Android boundaries"}, indent=2) + "\n", encoding="utf-8")
