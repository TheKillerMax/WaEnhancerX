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
hook_path = SRC / 'xposed/features/privacy/AntiRevokeHook.java'
registry_path = SRC / 'xposed/core/FeatureRegistry.java'
schema_path = SRC / 'config/PreferenceSchema.java'
hook = hook_path.read_text(encoding='utf-8')
registry = registry_path.read_text(encoding='utf-8')
entries = dict(re.findall(r'add\(entries,\s*"([^"]+)",\s*Type\.([A-Z_]+),', schema))
expected = {
    'antirevokestatus': 'STRING',
    'anti_revoke_indicator': 'INT',
    'deleted_message_color': 'INT',
}
for key, kind in expected.items():
    assert entries[key] == kind, (key, entries.get(key))
assert 'preferenceManager.putPublicString("antirevokestatus", if (value) "1" else "0")' in ui
assert 'PreferenceSchema.isStatusAntiRevokeEnabled(preferenceManager.getAll()[key])' in ui
write_branch = re.search(r'if \(key == "antirevokestatus"\) \{\s*// Keep the schema.*?return@update', ui, re.DOTALL)
assert write_branch and 'if (preferenceManager.putPublicString("antirevokestatus", if (value) "1" else "0")) {\n                settingsState[key] = value' in write_branch.group(0)
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
assert 'PreferenceSchema.isStatusAntiRevokeEnabled(prefs.getAll().get("antirevokestatus"))' in hook
assert 'PreferenceSchema.isStatusAntiRevokeEnabled(prefs.getAll().get("antirevokestatus"))' in registry
assert 'prefs.getBoolean("antirevokestatus", false)' not in registry
with tempfile.TemporaryDirectory(prefix='waex_deleted_indicator_') as output:
    subprocess.run(['javac', '--release', '17', '-d', output,
                    str(SRC/'ui/screens/privacy/DeletedIndicatorPreferencePolicy.java'),
                    str(ROOT/'qa/java/TestDeletedIndicatorPreferencePolicy.java')], check=True)
    subprocess.run(['java', '-cp', output,
                    'com.waenhancer.ui.screens.privacy.TestDeletedIndicatorPreferencePolicy'], check=True)
print('PASS: Anti-Revoke indicator type-safe UI and compatible hook wiring')
runner = [sys.executable, str(ROOT / 'qa/test_deleted_indicator_bridge.py')]
subprocess.run(runner, check=True)
controls = [
    ("event-boolean", hook_path, hook, "--source",
     'PreferenceSchema.isStatusAntiRevokeEnabled(prefs.getAll().get("antirevokestatus"))',
     'prefs.getBoolean("antirevokestatus", false)'),
    ("registry-boolean", registry_path, registry, "--registry",
     'PreferenceSchema.isStatusAntiRevokeEnabled(prefs.getAll().get("antirevokestatus"))',
     'prefs.getBoolean("antirevokestatus", false)'),
    ("invalid-on", schema_path, schema, "--schema",
     '"1".equals(text) || "true".equalsIgnoreCase(text)',
     '"1".equals(text) || "true".equalsIgnoreCase(text) || "2".equals(text)'),
]
with tempfile.TemporaryDirectory(prefix='waex_status_flag_mutants_') as folder:
    for name, original, content, option, old, new in controls:
        assert content.count(old) == 1, name
        mutant = Path(folder) / original.name
        mutant.write_text(content.replace(old, new, 1), encoding='utf-8')
        result = subprocess.run(runner + ['--scenario', 'status', option, str(mutant)],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding='utf-8', timeout=60)
        assert result.returncode != 0 and 'java.lang.AssertionError: STATUS_CONTRACT' in result.stdout, (name, result.stdout)
        print('PASS: compiled status preference negative control rejected: ' + name)
