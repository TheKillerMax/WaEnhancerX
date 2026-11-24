#!/usr/bin/env python3
"""Guard type-safe Anti-Revoke indicator preferences in the current Privacy UI."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'app/src/main/java/com/waenhancer'
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
controls = [
    ("reader_boolean_regression", hook.replace(
        "return isAntiRevokeStatusEnabled(context, prefs);",
        'return isEnabled("antirevokestatus", false);', 1), None, "status",
        "status reader case 0 bridge=true"),
    ("status_only_registry_regression", None, registry.replace(
        "|| AntiRevokeHook.isAntiRevokeStatusEnabled(context, prefs),",
        '|| prefs.getBoolean("antirevokestatus", false),', 1), "registry",
        "status-only registry case 0 bridge=true"),
    ("invalid_string_fail_open", hook.replace(
        'return "1".equals(value) || "true".equalsIgnoreCase((String) value);',
        'return !"0".equals(value) && !"false".equalsIgnoreCase((String) value);', 1),
        None, "status", "status reader case 6 bridge=true"),
    ("foreign_scope_leak", hook.replace(
        'key = packageName + ":" + key;', 'key = "com.whatsapp:" + key;', 1),
        None, "status", "other package status must not leak"),
]
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
        assert result.returncode != 0 and ("java.lang.AssertionError: " + expected_failure) in output, (name, output)
        print("PASS: behavioral negative rejected " + name + ": " + expected_failure)
