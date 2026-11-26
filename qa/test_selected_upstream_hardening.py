#!/usr/bin/env python3
"""Regression contracts for selected receipt, props, HMA and LID hardening."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / "app/src/main/java/com/waenhancer"


def declaration(source: str, marker: str) -> str:
    start = source.index(marker)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"Unclosed declaration: {marker}")


def check_hma_hardening(hma: str, config: str) -> None:
    """Require the live caller's rejection paths and the extracted transaction guards.

    Generated commands also execute in test_hma_backup_commands.py and the
    Android HMA suite; these source checks keep their guarded call sites connected.
    """
    repair = declaration(hma, "    suspend fun fixTargetIsolation(")
    scope = "if (!scope.isLive || !scope.contains(targetPackage)) return@synchronized false"
    backup_call = "AppRestartHelper.runRootCommand(HmaConfigFile.backupCommand(snapshot))"
    write_call = "AppRestartHelper.runRootCommand(write)"
    assert scope in repair and repair.index(scope) < repair.index(backup_call) < repair.index(write_call)
    rejected_backup = declaration(repair, "if (backup != HmaConfigFile.BACKUP_ACK)")
    assert "failed = true" in rejected_backup and "continue" in rejected_backup
    rejected_write = declaration(repair, "if (result != HmaConfigFile.WRITE_ACK || readConfigSnapshot(path)?.json != json)")
    assert "failed = true" in rejected_write and "restoreConfigSnapshot(snapshot, json)" in rejected_write
    assert "changed && !failed" in repair
    read = declaration(hma, "    private fun readConfigSnapshot(")
    assert "if (!HmaConfigFile.isConfigPath(path)) return null" in read
    assert "RootCommandRunner.runBounded(" in read and "4_000L, HmaConfigFile.MAX_COMMAND_OUTPUT" in read
    restore_call = declaration(hma, "    private fun restoreConfigSnapshot(")
    assert "HmaConfigFile.restoreCommand(snapshot, attemptedJson)" in restore_call
    assert "result == HmaConfigFile.RESTORE_ACK && readConfigSnapshot(snapshot.path)?.digest == snapshot.digest" in restore_call
    backup = declaration(config, "    public static String backupCommand(")
    assert 'String backup = snapshot.path + ".waex.bak";' in backup
    assert "requireSnapshot(snapshot)" in backup
    assert backup.count("verifiedFile(snapshot.path, snapshot.digest)") == 2
    assert backup.count("backupDestination(backup)") == 2
    assert 'copyToTemporary(snapshot.path, backup + ".XXXXXX", snapshot.digest)' in backup
    assert backup.index("verifiedFile(backup, snapshot.digest)") < backup.index("quote(BACKUP_ACK)")
    write = declaration(config, "    public static String writeCommand(")
    assert "if (bytes.length > MAX_CONFIG_BYTES)" in write
    assert 'verifiedFile(snapshot.path + ".waex.bak", snapshot.digest)' in write
    restore = declaration(config, "    public static String restoreCommand(")
    assert "if (attemptedBytes.length > MAX_CONFIG_BYTES)" in restore
    assert restore.count("verifiedFile(snapshot.path, replacementDigest)") == 2
    assert restore.count("verifiedFile(backup, snapshot.digest)") == 2
    assert restore.index("verifiedFile(snapshot.path, snapshot.digest)") < restore.index("quote(RESTORE_ACK)", restore.index("copyToTemporary("))
    copy = declaration(config, "    private static String copyToTemporary(")
    assert '"cp -p -- " + p' in copy and "sha256sum" in copy and "quote(digest)" in copy
    assert "trap 'rm -f --" in copy
    assert "[ ! -L " in declaration(config, "    private static String canonicalFile(")
    assert "[ ! -L " in declaration(config, "    private static String backupDestination(")
    assert "String p = quote(path)" in declaration(config, "    private static String canonicalFile(")


receipts = (JAVA / "xposed/features/privacy/HideReceiptsHook.java").read_text()
dispatch = declaration(receipts, "    private void hookOnDispatchMessage()")
job_hook = declaration(receipts, "    private void hookSendReadReceiptJob()")
assert "msg.arg1 == 419" in dispatch
assert "msg.arg1 == 89" not in dispatch
assert "msg.arg1 == 419 || msg.arg1 == 89" not in receipts
assert "boolean hideDelivery = shouldHideDeliveryReceipt(target);" in job_hook
delivery_veto = declaration(job_hook, "                        if (hideDelivery) {")
assert "param.setResult(null);" in delivery_veto and "return;" in delivery_veto
assert "UnsentReadLedger.track(context, target, participant," in delivery_veto
assert "ReceiptJobExecutionPolicy.isExecutionCall(" in job_hook

props = (JAVA / "xposed/features/customization/PropsOverrideHook.java").read_text()
assert "findCentralResolver(booleanGetter)" in props
assert "types[types.length - 2] != int.class" in props
assert "types[types.length - 1] != boolean.class" in props
assert "if (selected != null) return null" in props
assert "if (original instanceof Boolean) return BOOLEANS.get(id)" in props
assert "if (original instanceof Integer) return INTEGERS.get(id)" in props
settings = (JAVA / "xposed/features/customization/NewSettingsStyleHook.java").read_text()
assert "PropsOverrideHook.BOOLEANS.put" in settings
assert "PropsOverrideHook.INTEGERS.put" in settings
assert "Unknown BooleanField" not in settings

hma = (JAVA / "utils/HmaDiagnostics.kt").read_text()
check_hma_hardening(hma, (JAVA / "utils/HmaConfigFile.java").read_text())

calls = (JAVA / "xposed/features/privacy/CallPrivacyHook.java").read_text()
block = declaration(calls, "    private boolean shouldBlockCall(String callerJid)")
assert "ContactIdentityPolicy.canonicalJid(callerJid) == null" in block
assert "ContactIdentityPolicy.phoneUser(WaJid.phoneJidFor(context, callerJid))" in block
jid = (JAVA / "xposed/core/wa/WaJid.java").read_text()
assert "return isLid(raw) ? LID_TO_PHONE.resolve(context, raw) : null;" in declaration(jid, "    public static String phoneJidFor(")
assert "findContactPrivacy(callerJid, phoneJid)" in block
identity = declaration(calls, "    private JSONObject findContactPrivacy(")
assert "getContactPrivacy(prefs, rawJid)" in identity
assert "getContactPrivacy(prefs, phoneJid)" in identity
assert "wa_address_book" in calls

print("PASS: selected upstream hardening contracts")
