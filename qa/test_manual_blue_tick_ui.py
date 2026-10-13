#!/usr/bin/env python3
"""JDK source-level regression for the manual read-receipt toolbar preference.

No Android build or LSPosed runtime behavior is implied by passing.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = root / "app/src/main/java/com/waenhancer"
ui = (src / "ui/screens/settings/StylesSettingsScreen.kt").read_text()
cat = (src / "config/FeatureCatalog.kt").read_text()
schema = (src / "config/PreferenceSchema.java").read_text()
blue = (src / "xposed/features/privacy/BlueOnReplyHook.java").read_text()
receipts = (src / "xposed/features/privacy/HideReceiptsHook.java").read_text()
assert '"seentick", Type.STRING' in schema
assert '"seen_tick_customization"' in ui
assert 'preferenceManager.getString("seentick", "0")' in ui
assert 'preferenceManager.putString("seentick",' in ui
assert 'preferenceManager.putBoolean("seen_tick_customization"' not in ui
assert 'ManualSeenTickPreferencePolicy.valueAfterExplicitToggle(value, currentPlacement)' in ui
assert '"Manual Blue Tick Button"' in cat and '"Manual Blue Tick Button"' in ui
for consumer in (blue, receipts):
    assert 'prefs.getAll().get("seentick")' in consumer
assert 'if (!isHideBlueTicksEnabled()) return false;' in blue
assert '"hide_read_receipts"' in blue
assert 'ConversationRecipientPolicy.resolve(candidates)' in blue
assert 'extras.keySet()' not in blue
assert 'extractRemoteJid(' not in blue
assert 'Cannot verify chat recipient' in blue

with tempfile.TemporaryDirectory() as tmp:
    subprocess.run(['javac', '--release', '17', '-d', tmp,
                    str(src / "ui/screens/settings/ManualSeenTickPreferencePolicy.java"),
                    str(root / "qa/java/TestManualSeenTickPreferencePolicy.java")], check=True)
    subprocess.run(['java', '-cp', tmp,
                    'com.waenhancer.ui.screens.settings.TestManualSeenTickPreferencePolicy'], check=True)
print('PASS: manual read receipt preference, source wiring and hook contract')
