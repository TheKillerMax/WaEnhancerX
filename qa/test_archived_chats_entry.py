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
assert '"archive_open_via_menu", Type.BOOLEAN' in schema
assert '"archive_open_via_title_long_press", Type.BOOLEAN' in schema
assert '"archive_open_via_title_triple_tap", Type.BOOLEAN' in schema
assert 'ArchivedChatsPreferencePolicy.isHidden(prefs.getAll().get(PREF_KEY))' in archive
assert 'isEnabled(PREF_KEY' not in archive
assert 'MENU_ID_ARCHIVED' in menu
assert 'appendArchiveEntry(target, activity)' in menu
assert 'appendArchiveEntry(menu, activity)' in menu
assert 'return hasNormalWaexAction() || (isArchivedHidden() && isArchiveMenuEnabled())' in menu
assert 'ArchivedConversationsActivity' in menu
assert 'Activity.class.isAssignableFrom(archived)' in menu
assert 'new Intent(activity, archived)' in menu
assert 'activity.startActivity(' in menu
assert 'item.setShowAsAction(MenuItem.SHOW_AS_ACTION_NEVER)' in menu
assert 'attachHomeTitleLongPressHook(homeActivityClass)' in menu
assert 'findAndHookMethod(View.class, "performLongClick"' in menu
assert 'scheduleHomeTitleLongPress(activity)' in menu
assert 'getIdentifier(\n                    "toolbar_logo", "id", activity.getPackageName())' in menu
assert 'activity.findViewById(id)' in menu
assert 'title.setLongClickable(true)' in menu
assert 'title.setOnLongClickListener' in menu
assert 'title.setOnClickListener(clicked -> handleArchiveTitleTap(activity))' in menu
assert 'archiveTitleTapCount >= 3' in menu
assert 'isArchiveTitleTripleTapEnabled()' in menu
assert 'findHomeTitle(root, activity)' in menu
assert 'view instanceof ImageView && entryName.equals("toolbar_logo")' in menu
assert 'homeActivityClass.isInstance(activity)' in menu
assert 'isWhatsAppHomeTitle(view, activity)' in menu
assert '!isArchiveTitleLongPressEnabled()' in menu
assert '!isArchivedHidden() || !isArchiveMenuEnabled()' in menu
assert 'isArchivedHidden() && isArchiveMenuEnabled()' in menu
assert 'param.setResult(true)' in menu
assert 'entryName.contains("toolbar_title")' in menu
assert 'actual.equalsIgnoreCase("WhatsApp")' in menu
assert 'preferenceManager.putString("typearchive", if (value) "1" else "0")' in ui
assert 'click 5 times or hold' not in ui and 'click 5 times or hold' not in catalog
assert 'Hide the archive shortcut' in ui and 'Hide the archive shortcut' in catalog
assert 'item.key == "typearchive" && settingsState["typearchive"] == true' in ui
assert 'OPEN ARCHIVED CHATS' in ui
assert 'Show in 3-dots / WAEX menu' in ui
assert 'Long-press WhatsApp title' in ui
assert 'Tap WhatsApp title 3 times' in ui
assert 'preferenceManager.putBoolean("archive_open_via_menu", checked)' in ui
assert 'preferenceManager.putBoolean("archive_open_via_title_long_press", checked)' in ui
assert 'preferenceManager.putBoolean("archive_open_via_title_triple_tap", checked)' in ui
assert ui.count('Keep at least one opening method enabled') == 3
with tempfile.TemporaryDirectory(prefix='waex_archive_policy_') as temp:
    subprocess.run(['javac','--release','17','-d',temp,
                    str(src/'xposed/features/privacy/ArchivedChatsPreferencePolicy.java'),
                    str(root/'qa/java/TestArchivedChatsPreferencePolicy.java')],check=True)
    subprocess.run(['java','-cp',temp,
                    'com.waenhancer.xposed.features.privacy.TestArchivedChatsPreferencePolicy'],check=True)
print('PASS: 17 archive preference, menu recovery, and UI key type invariants')
