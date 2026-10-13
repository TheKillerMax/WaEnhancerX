#!/usr/bin/env python3
"""Compiles production Java helpers with JDK, exercises memory and concurrency invariants."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / "app/src/main/java/com/waenhancer/xposed/features/automation"
with tempfile.TemporaryDirectory() as directory:
    subprocess.run(["javac", "-d", directory,
                    str(source / "ToastThrottle.java"),
                    str(source / "PresenceStateStore.java"),
                    str(root / "qa/TestNotificationState.java")], check=True)
    subprocess.run(["java", "-cp", directory,
                    "com.waenhancer.xposed.features.automation.TestNotificationState"], check=True)

presence = (source / "PresenceToastsHook.java").read_text()
anti_revoke = (root / "app/src/main/java/com/waenhancer/xposed/features/privacy/AntiRevokeHook.java").read_text()
anti_edit = (root / "app/src/main/java/com/waenhancer/xposed/features/conversation/AntiEditMessagesHook.kt").read_text()
assert "Executors.newSingleThreadExecutor().execute" not in presence
assert "ThreadPoolExecutor.DiscardOldestPolicy" in presence
assert "TOAST_THROTTLE.shouldEmit" in presence
assert "context, prefs, senderJid, uiHandler" in anti_revoke
assert "private void showDeletedMessageToast(" in anti_revoke
assert "messageTextCache" not in anti_edit
assert "MAX_RECENT_REVOKES = 4096" in anti_revoke
assert "StatusKeyHandoff.record(keyId)" in anti_revoke
assert "String pendingDbKey = StatusKeyHandoff.consume();" in anti_revoke
assert "sStatusKeyByThread" not in anti_revoke
assert 't.getMessage()' not in anti_revoke, 'Throwable messages may contain private status IDs'
assert '${t.message}' not in anti_edit, 'Throwable messages may contain private chat content'
assert "DelMessageStore.getInstance(context).getTimestampByMessageId(keyId) > 0L" in anti_revoke
assert "TIME_FORMAT.get().format" in anti_revoke
assert "if (!(renderedRow instanceof ViewGroup)) return;" in anti_revoke
assert "timeFormatter.get().format" in anti_edit
assert "stateCount()" in (source / "PresenceStateStore.java").read_text()
privacy = root / "app/src/main/java/com/waenhancer/xposed/features/privacy"
with tempfile.TemporaryDirectory(prefix="waex_status_key_handoff_") as directory:
    subprocess.run(["javac", "--release", "17", "-d", directory,
                    str(privacy / "StatusKeyHandoff.java"),
                    str(root / "qa/TestStatusKeyHandoff.java")], check=True)
    subprocess.run(["java", "-cp", directory,
                    "com.waenhancer.xposed.features.privacy.TestStatusKeyHandoff"], check=True)

print("PASS: no per-notification executor, bridged delete-toast setting, unused text cache removed")
