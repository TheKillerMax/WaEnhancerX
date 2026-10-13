#!/usr/bin/env python3
"""Ensure typed Styles settings never go through the generic Boolean switch."""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'app/src/main/java/com/waenhancer'
styles = (SRC/'ui/screens/settings/StylesSettingsScreen.kt').read_text(encoding='utf-8')
policy = (SRC/'ui/screens/settings/StyleNonBooleanPreferencePolicy.java').read_text(encoding='utf-8')
schema = (SRC/'config/PreferenceSchema.java').read_text(encoding='utf-8')
codec = (SRC/'core/preferences/SettingsBackupCodec.kt').read_text(encoding='utf-8')

typed = {
    'custom_theme': ('custom_css', 'STRING'),
    'custom_view_dpi': ('change_dpi', 'STRING'),
    'chat_filters': ('chatfilter', 'STRING'),
    'hide_ui_tabs': ('hidetabs', 'STRING_SET'),
    'quick_home_menu': ('show_home_menu', 'STRING')
}
for ui_key, (canonical_key, typ) in typed.items():
    assert 'case "' + ui_key + '"' in policy, f'Missing UI guard for {ui_key}'
    assert re.search(r'add\(entries,\s*"'+canonical_key+r'",\s*Type\.'+typ+r'\b', schema), canonical_key
    assert re.search(r'"'+ui_key+r'"\s+to\s+"'+canonical_key+r'"', codec), ui_key

assert 'StyleNonBooleanPreferencePolicy.requiresDedicatedEditor(key)' in styles
assert 'if (StyleNonBooleanPreferencePolicy.requiresDedicatedEditor(key)) {' in styles
assert 'if (StyleNonBooleanPreferencePolicy.requiresDedicatedEditor(key)) return@update' in styles
assert '.clickable(enabled = !needsTypedEditor)' in styles
assert 'if (needsTypedEditor) {' in styles
assert '"Needs typed editor"' in styles
assert 'StitchSwitch(' in styles  # Existing Boolean controls are retained.
# Critical special-case behavior from PRs #34 and #35 may not be overwritten.
if 'ManualSeenTickPreferencePolicy.isEnabled' in styles:
    assert 'preferenceManager.putString("seentick",' in styles
if '"disable_sensor_proximity"' in styles:
    assert 'StyleItem("Disable Screen off on proximity sensor"' in styles
with tempfile.TemporaryDirectory(prefix='waex_style_types_') as tmp:
    subprocess.run(['javac','--release','17','-d',tmp,
                    str(SRC/'ui/screens/settings/StyleNonBooleanPreferencePolicy.java'),
                    str(ROOT/'qa/TestStyleNonBooleanPreferencePolicy.java')],check=True)
    subprocess.run(['java','-cp',tmp,
                    'com.waenhancer.ui.screens.settings.TestStyleNonBooleanPreferencePolicy'],check=True)
print('PASS: STRING/STRING_SET Styles controls cannot persist through Boolean switches')
