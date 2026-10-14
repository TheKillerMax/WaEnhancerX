#!/usr/bin/env python3
"""Standalone Tasker safety regression checks using production Java policy.

Requires Python 3 and JDK 17+. Android/LSPosed runtime integration and actual
WhatsApp deep-link handling must be tested separately on a device.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / "app/src/main/java/com/waenhancer/xposed/features/automation/TaskerMessagePolicy.java"
HOOK = ROOT / "app/src/main/java/com/waenhancer/xposed/features/automation/TaskerIntegrationHook.kt"
TEST = ROOT / "qa/TestTaskerMessagePolicy.java"

with tempfile.TemporaryDirectory(prefix="waex_tasker_policy_") as directory:
    subprocess.run(["javac", "--release", "17", "-d", directory,
                    str(JAVA), str(TEST)], check=True)
    subprocess.run(["java", "-cp", directory,
                    "com.waenhancer.xposed.features.automation.TestTaskerMessagePolicy"], check=True)

hook = HOOK.read_text()
checks = {
    "existing external command": 'const val ACTION_SEND_MESSAGE = "com.waenhancer.MESSAGE_SENT"' in hook,
    "existing received-message event": 'const val ACTION_MESSAGE_RECEIVED = "com.waenhancer.MESSAGE_RECEIVED"' in hook,
    "incoming event still published": 'context.sendBroadcast(broadcastIntent)' in hook,
    "existing message id extra": 'putExtra("message_id", messageId)' in hook,
    "Android 13+ exported receiver": 'Context.RECEIVER_EXPORTED' in hook,
    "input validation": 'TaskerMessagePolicy.prepare(' in hook,
    "validate exact action": 'intent.action != ACTION_SEND_MESSAGE' in hook,
    "validate feature still enabled": 'if (!isEnabled("tasker_integration", false)) return@post' in hook,
    "inspect visible activity": 'ActivityTracker.getCurrentActivity()' in hook,
    "check activity focus at launch": 'foreground.window?.decorView?.hasWindowFocus() != true' in hook,
    "same-package launch": hook.count('setPackage(context.packageName)') == 2,
    "message URI encoding": 'Uri.encode(prepared.text)' in hook,
    "primary WhatsApp deep link": 'https://api.whatsapp.com/send?phone=' in hook,
    "fallback WhatsApp deep link": 'https://wa.me/' in hook,
    "fallback only on unavailable activity": 'catch (_: ActivityNotFoundException)' in hook,
    "no silent message submission": 'sendMessageDirectly' not in hook,
    "UI thread marshaling": 'mainHandler.post {' in hook,
    "monotonic rate limit": 'SystemClock.elapsedRealtime()' in hook,
    "log only exception classes": '${t.javaClass.simpleName}' in hook,
}
for description, passed in checks.items():
    if not passed:
        raise AssertionError("Tasker integration regression: " + description)
print(f"PASS: {len(checks)} Tasker source/compatibility invariants")
