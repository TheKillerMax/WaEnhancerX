#!/usr/bin/env python3
"""Archive feature compatibility regression (source contracts + pure JDK preference)."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
src=root/'app/src/main/java/com/waenhancer'
archive=(src/'xposed/features/privacy/HideArchivedChatsHook.java').read_text()
menu=(src/'xposed/features/homescreen/HomeScreenHeaderActionsHook.java').read_text()
ui=(src/'ui/screens/privacy/GlobalPrivacySettingsScreen.kt').read_text()
catalog=(src/'config/FeatureCatalog.kt').read_text()
schema=(src/'config/PreferenceSchema.java').read_text()
assert '"typearchive", Type.STRING' in schema
assert 'ArchivedChatsPreferencePolicy.isHidden(prefs.getAll().get(PREF_KEY))' in archive
assert 'isEnabled(PREF_KEY' not in archive
assert 'MENU_ID_ARCHIVED' in menu
assert 'appendArchiveEntry(target, activity)' in menu
assert 'appendArchiveEntry(menu, activity)' in menu
assert 'return hasNormalWaexAction() || isArchivedHidden()' in menu
assert 'ArchivedConversationsActivity' in menu
assert 'Activity.class.isAssignableFrom(archived)' in menu
assert 'new Intent(activity, archived)' in menu
assert 'activity.startActivity(' in menu
assert 'item.setShowAsAction(MenuItem.SHOW_AS_ACTION_NEVER)' in menu
assert 'preferenceManager.putString("typearchive", if (value) "1" else "0")' in ui
assert 'click 5 times or hold' not in ui and 'click 5 times or hold' not in catalog
assert 'Hide the archive shortcut' in ui and 'Hide the archive shortcut' in catalog
with tempfile.TemporaryDirectory(prefix='waex_archive_policy_') as temp:
    subprocess.run(['javac','--release','17','-d',temp,
                    str(src/'xposed/features/privacy/ArchivedChatsPreferencePolicy.java'),
                    str(root/'qa/java/TestArchivedChatsPreferencePolicy.java')],check=True)
    subprocess.run(['java','-cp',temp,
                    'com.waenhancer.xposed.features.privacy.TestArchivedChatsPreferencePolicy'],check=True)
print('PASS: 17 archive preference, menu recovery, and UI key type invariants')
