package com.waenhancer.utils

import android.content.Context
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.io.File
import java.nio.file.Files
import java.nio.file.attribute.PosixFilePermissions

/** Complete diagnostics and root-runner code; only the external command service is substituted. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [24, 28, 34], manifest = Config.NONE)
class HmaFlowTest {
    private lateinit var context: Context
    private lateinit var directory: File
    private lateinit var control: JSONObject
    private lateinit var module: String
    private val target = "com.whatsapp"
    private val other = "com.whatsapp.w4b"
    private val logical = "/data/misc/hide_my_applist_qa/config.json"

    @Before fun setup() {
        context = RuntimeEnvironment.getApplication()
        module = context.packageName
        val root = File(System.getenv("HMA_QA_ROOT"))
        directory = Files.createTempDirectory(root.toPath(), "flow-").toFile()
        control = JSONObject().put("paths", JSONArray()).put("files", JSONObject())
            .put("packages", JSONArray()).put("mode", "normal")
        save()
        File(root, "active-case.txt").writeText(directory.absolutePath)
    }

    private fun array(vararg values: String) = JSONArray(values.toList())
    private fun scope(whitelist: Boolean = false) = JSONObject()
        .put("useWhitelist", whitelist).put("extraAppList", JSONArray())
        .put("applyTemplates", JSONArray()).put("applyPresets", JSONArray())
    private fun document(value: JSONObject = scope().put("extraAppList", array(module))) = JSONObject()
        .put("scope", JSONObject().put(target, value)).put("templates", JSONObject())
    private fun save() = File(directory, "control.json").writeText(control.toString())
    private fun add(json: String, path: String = logical): File {
        val file = File(directory, "config-${control.getJSONObject("files").length()}.json")
        file.writeText(json)
        control.getJSONArray("paths").put(path)
        control.getJSONObject("files").put(path, file.absolutePath)
        save()
        return file
    }
    private fun add(json: JSONObject, path: String = logical) = add(json.toString(), path)
    private fun mode(value: String) { control.put("mode", value); save() }
    private fun operationMode(operation: String, value: String) {
        control.put(operation + "_mode", value); save()
    }
    private fun backup(file: File) = File(file.absolutePath + ".waex.bak")
    private fun readBackup(file: File): String {
        val copy = backup(file)
        assertTrue("verified recovery copy must exist", copy.isFile)
        return copy.readText()
    }
    private fun events(): List<JSONObject> {
        val file = File(directory, "events.jsonl")
        return if (file.exists()) file.readLines().map { JSONObject(it) } else emptyList()
    }
    private fun writes() = events().filter { it.getString("kind") == "write" }
    private fun repair(pkg: String = target) = runBlocking { HmaDiagnostics.fixTargetIsolation(context, pkg) }
    private fun report() = runBlocking { HmaDiagnostics.checkHmaStatus(context, listOf(target), true) }
    private fun blocked(expected: Boolean) {
        val report = report()
        assertEquals("diagnostic state", if (expected) HmaDiagnostics.HmaState.BLOCKING_TARGETS
            else HmaDiagnostics.HmaState.CLEAN, report.state)
        assertEquals(expected, report.targetDetails.single().isBlocking)
    }
    private fun json(file: File) = JSONObject(file.readText())
    private fun apps(value: JSONObject, key: String) = value.getJSONArray(key).let { arr ->
        (0 until arr.length()).map { arr.getString(it) }
    }
    private fun assertNoTemporaryFiles() {
        assertFalse("temporary config leaked", directory.listFiles()!!.any {
            (it.name.contains(".waex.") && !it.name.endsWith(".waex.bak")) || it.name.endsWith(".tmp")
        })
    }
    private fun paddedDocument(size: Int): String {
        val data = document().put("padding", "")
        val count = size - data.toString().toByteArray(Charsets.UTF_8).size
        assertTrue(count >= 0)
        return data.put("padding", "x".repeat(count)).toString().also {
            assertEquals(size, it.toByteArray(Charsets.UTF_8).size)
        }
    }

    @Test fun sharedAndUnappliedTemplatesRemainUnchanged() {
        val selected = scope().put("applyTemplates", array("shared"))
        val data = document(selected)
        data.getJSONObject("scope").put(other, JSONObject(selected.toString()))
        val shared = JSONObject().put("isWhitelist", false).put("appList", array(module, "example.keep"))
        val unused = JSONObject().put("isWhitelist", false).put("appList", array(module, "example.unused"))
        data.getJSONObject("templates").put("shared", shared).put("unused", unused)
        val file = add(data)
        assertTrue(repair())
        val result = json(file)
        assertEquals(shared.toString(), result.getJSONObject("templates").getJSONObject("shared").toString())
        assertEquals(unused.toString(), result.getJSONObject("templates").getJSONObject("unused").toString())
        assertEquals(selected.toString(), result.getJSONObject("scope").getJSONObject(other).toString())
        val key = result.getJSONObject("scope").getJSONObject(target).getJSONArray("applyTemplates").getString(0)
        assertNotEquals("shared", key)
        assertEquals(listOf("example.keep"), apps(result.getJSONObject("templates").getJSONObject(key), "appList"))
        blocked(false)
    }

    @Test fun onlyRunningModuleIdentifierChanges() {
        val file = add(document(scope().put("extraAppList", array(module, "com.waenhancer", "com.waenhancer.debug", "example.keep"))))
        assertTrue(repair())
        assertEquals(listOf("com.waenhancer", "com.waenhancer.debug", "example.keep"),
            apps(json(file).getJSONObject("scope").getJSONObject(target), "extraAppList"))
    }

    @Test fun undeclaredTargetDoesNotIssueCommands() {
        val data = document()
        data.getJSONObject("scope").put("example.foreign", scope().put("extraAppList", array(module)))
        val file = add(data)
        assertFalse(repair("example.foreign"))
        assertEquals(data.toString(), file.readText())
        assertTrue(events().isEmpty())
    }

    @Test fun alreadyVisibleDoesNotRewriteDocument() {
        val original = document(scope())
        val file = add(original)
        assertFalse(repair())
        assertEquals(original.toString(), file.readText())
        assertTrue(writes().isEmpty())
    }

    @Test fun whitelistRepairPreservesOtherModuleIdentifiers() {
        val s = scope(true).put("extraOppositeAppList", array(module, "com.waenhancer.debug", "example.keep"))
        val file = add(document(s))
        assertTrue(repair())
        val result = json(file).getJSONObject("scope").getJSONObject(target)
        assertEquals(listOf(module), apps(result, "extraAppList"))
        assertEquals(listOf("com.waenhancer.debug", "example.keep"), apps(result, "extraOppositeAppList"))
        blocked(false)
    }

    @Test fun blacklistUsesTargetModeForTemplateWithWhitelistEditorLabel() {
        val data = document(scope().put("applyTemplates", array("shared")))
        data.getJSONObject("templates").put("shared", JSONObject().put("isWhitelist", true).put("appList", array(module)))
        add(data)
        blocked(true)
    }

    @Test fun whitelistUsesTargetModeForTemplateWithBlacklistEditorLabel() {
        val data = document(scope(true).put("applyTemplates", array("shared")))
        data.getJSONObject("templates").put("shared", JSONObject().put("isWhitelist", false).put("appList", array(module)))
        add(data)
        blocked(false)
    }

    @Test fun whitelistExtraAppListTakesPrecedenceOverOppositeList() {
        add(document(scope(true).put("extraAppList", array(module)).put("extraOppositeAppList", array(module))))
        blocked(false)
    }

    @Test fun blacklistExtraAppListTakesPrecedenceOverOppositeList() {
        add(document(scope().put("extraAppList", array(module)).put("extraOppositeAppList", array(module))))
        blocked(true)
    }

    @Test fun ossOppositeExceptionTakesPrecedenceOverSharedTemplate() {
        val data = document(scope().put("extraOppositeAppList", array(module)).put("applyTemplates", array("shared")))
        data.getJSONObject("templates").put("shared", JSONObject().put("appList", array(module)))
        add(data)
        blocked(false)
    }

    @Test fun ossOppositeExceptionTakesPrecedenceOverPreset() {
        add(document(scope().put("extraOppositeAppList", array(module)).put("applyPresets", array("xposed"))))
        blocked(false)
    }

    @Test fun ossIgnoredPackagesForPresetsIsRespected() {
        add(document(scope().put("applyPresets", array("xposed"))).put("ignoredPackagesForPresets", array(module)))
        blocked(false)
    }

    @Test fun differentModuleInstallationDoesNotBlockRunningOne() {
        add(document(scope().put("extraAppList", array("com.waenhancer.debug"))))
        blocked(false)
    }

    @Test fun ossRepairAddsTargetLocalExceptionWithoutEditingTemplatesOrPresets() {
        val s = scope().put("extraOppositeAppList", JSONArray()).put("applyTemplates", array("shared"))
            .put("applyPresets", array("xposed", "other-preset"))
        val data = document(s)
        val templates = data.getJSONObject("templates").put("shared", JSONObject().put("appList", array(module, "example.keep")))
        val file = add(data)
        assertTrue(repair())
        val result = json(file)
        val selected = result.getJSONObject("scope").getJSONObject(target)
        assertEquals(templates.toString(), result.getJSONObject("templates").toString())
        assertEquals(listOf("xposed", "other-preset"), apps(selected, "applyPresets"))
        assertEquals(listOf(module), apps(selected, "extraOppositeAppList"))
        blocked(false)
    }

    @Test fun diagnosticReadsDocumentLargerThanLegacyEightKiBCapture() {
        add(paddedDocument(20 * 1024))
        blocked(true)
    }

    @Test fun repairPreservesLargeDocumentCompletely() {
        val text = paddedDocument(20 * 1024)
        val file = add(text)
        assertTrue(repair())
        assertEquals(JSONObject(text).getString("padding"), json(file).getString("padding"))
        blocked(false)
    }

    @Test fun exactlySixtyFourKiBDocumentCanBeRead() {
        add(paddedDocument(64 * 1024))
        blocked(true)
    }

    @Test fun largerThanSixtyFourKiBDocumentIsNeverWritten() {
        val text = paddedDocument(64 * 1024 + 1)
        val file = add(text)
        assertFalse(repair())
        assertEquals(text, file.readText())
        assertTrue(writes().isEmpty())
    }

    @Test fun emptyWriteOutputIsNotAnAcknowledgement() {
        val original = document().toString()
        val file = add(original)
        mode("empty_ack")
        assertFalse(repair())
        assertEquals(original, file.readText())
    }

    @Test fun acknowledgementWithoutPersistedContentIsRejected() {
        val original = document().toString()
        val file = add(original)
        mode("fake_ack")
        assertFalse(repair())
        assertEquals(original, file.readText())
    }

    @Test fun acknowledgementMustMatchExactly() {
        val original = document().toString()
        val file = add(original)
        mode("ack_suffix")
        assertFalse(repair())
        assertEquals(original, file.readText())
        assertEquals(original, readBackup(file))
    }

    @Test fun failedOwnerPreservationLeavesOriginalAndNoTemporaryFile() {
        val original = document().toString()
        val file = add(original)
        mode("chown_fail")
        assertFalse(repair())
        assertEquals(original, file.readText())
        assertNoTemporaryFiles()
        assertFalse(events().any { it.optString("tool") == "mv" &&
            it.getJSONArray("args").let { args -> args.getString(args.length() - 1) == file.absolutePath } })
    }

    @Test fun failedRenameLeavesOriginalAndNoTemporaryFile() {
        val original = document().toString()
        val file = add(original)
        mode("mv_fail")
        assertFalse(repair())
        assertEquals(original, file.readText())
        assertNoTemporaryFiles()
    }

    @Test fun staleSnapshotDoesNotOverwriteConcurrentWriter() {
        val file = add(document())
        val replacement = document().put("concurrent", "preserve").toString()
        control.put("replacement", replacement)
        mode("stale_before_write")
        assertFalse(repair())
        assertEquals(replacement, file.readText())
        assertNoTemporaryFiles()
    }

    @Test fun concurrentChangeAfterAcknowledgementIsNotReportedAsSuccess() {
        val file = add(document())
        val replacement = document().put("concurrent", "after-write").toString()
        control.put("replacement", replacement)
        mode("changed_after_write")
        assertFalse(repair())
        assertEquals(replacement, file.readText())
    }

    @Test fun partialMultiFileRepairReturnsFailure() {
        val original = document().toString()
        val first = add(original)
        val secondPath = "/data/system/hide_my_applist_old/config.json"
        val second = add(original, secondPath)
        control.put("faults", JSONObject().put(secondPath, "mv_fail")); save()
        assertFalse(repair())
        assertNotEquals(original, first.readText())
        assertEquals(original, second.readText())
        assertNoTemporaryFiles()
    }

    @Test fun forceStopTargetsOnlyExactKnownManagersOncePerPass() {
        val managers = listOf("com.tsng.hidemyapplist", "org.frknkrc44.hma_oss", "com.google.android.hmal")
        control.put("packages", JSONArray(managers + listOf(managers[0], "example.hma.notes", "example.hidemyapp", "example.hmal")))
        save()
        HmaDiagnostics.forceStopHmaApps(context)
        val stops = events().filter { it.optString("kind") == "stop" }.map { it.getString("package") }
        assertEquals(managers, stops)
    }

    @Test fun hmaNamedSubdirectoryOfAnotherAppIsRejected() {
        val original = document().toString()
        val file = add(original, "/data/data/example.unrelated/files/hma/config.json")
        assertFalse(repair())
        assertEquals(original, file.readText())
        assertTrue(writes().isEmpty())
    }

    @Test fun symlinkedConfigIsNotReadOrReplaced() {
        val original = document().toString()
        val targetFile = add(original)
        val link = File(directory, "config-link.json")
        Files.createSymbolicLink(link.toPath(), targetFile.toPath())
        control.getJSONObject("files").put(logical, link.absolutePath); save()
        assertFalse(repair())
        assertEquals(original, targetFile.readText())
        assertTrue(Files.isSymbolicLink(link.toPath()))
        assertTrue(writes().isEmpty())
    }

    @Test fun originalPermissionModeIsPreservedBeforeRename() {
        val file = add(document())
        Files.setPosixFilePermissions(file.toPath(), PosixFilePermissions.fromString("rw-r-----"))
        assertTrue(repair())
        assertEquals("rw-r-----", PosixFilePermissions.toString(Files.getPosixFilePermissions(file.toPath())))
        val tools = events().filter { it.optString("kind") == "tool" }.map { it.getString("tool") }
        assertTrue(tools.indexOf("chmod") in 0 until tools.lastIndexOf("mv"))
        assertTrue(tools.indexOf("chown") in 0 until tools.lastIndexOf("mv"))
        assertNoTemporaryFiles()
    }

    @Test fun malformedDocumentIsRejectedWithoutWrite() {
        val file = add("{\"scope\":")
        assertFalse(repair())
        assertEquals("{\"scope\":", file.readText())
        assertTrue(writes().isEmpty())
    }

    @Test fun failedReadNeverTriggersWrite() {
        val original = document().toString()
        val file = add(original)
        mode("read_fail")
        assertFalse(repair())
        assertEquals(original, file.readText())
        assertTrue(writes().isEmpty())
    }

    @Test fun truncatedSnapshotNeverTriggersWrite() {
        val original = document().toString()
        val file = add(original)
        mode("truncated_read")
        assertFalse(repair())
        assertEquals(original, file.readText())
        assertTrue(writes().isEmpty())
    }

    @Test fun mismatchedSnapshotDigestNeverTriggersWrite() {
        val original = document().toString()
        val file = add(original)
        mode("wrong_digest")
        assertFalse(repair())
        assertEquals(original, file.readText())
        assertTrue(writes().isEmpty())
    }

    @Test fun excessiveCommandOutputIsNotAcceptedAsValidPrefix() {
        val original = document().toString()
        val file = add(original)
        mode("oversized_output")
        assertFalse(repair())
        assertEquals(original, file.readText())
        assertTrue(writes().isEmpty())
    }

    @Test fun successfulRepairKeepsExactBackupBytesAndOriginalMode() {
        val original = document().put("extra", "Olá العربية 😀").toString(2)
        val file = add(original)
        Files.setPosixFilePermissions(file.toPath(), PosixFilePermissions.fromString("rw-r-----"))
        assertTrue(repair())
        assertEquals(original, readBackup(file))
        assertEquals("rw-r-----", PosixFilePermissions.toString(Files.getPosixFilePermissions(backup(file).toPath())))
        assertFalse(Files.isSymbolicLink(backup(file).toPath()))
        assertNoTemporaryFiles()
    }

    @Test fun failedBackupCopyDoesNotWriteLiveConfiguration() {
        val original = document().toString()
        val file = add(original)
        operationMode("backup", "cp_fail")
        assertFalse(repair())
        assertEquals(original, file.readText())
        assertFalse(backup(file).exists())
        assertTrue(writes().isEmpty())
        assertNoTemporaryFiles()
    }

    @Test fun failedBackupRenameDoesNotWriteLiveConfiguration() {
        val original = document().toString()
        val file = add(original)
        operationMode("backup", "mv_fail")
        assertFalse(repair())
        assertEquals(original, file.readText())
        assertFalse(backup(file).exists())
        assertTrue(writes().isEmpty())
        assertNoTemporaryFiles()
    }

    @Test fun backupAcknowledgementMustMatchExactly() {
        val original = document().toString()
        val file = add(original)
        operationMode("backup", "ack_suffix")
        assertFalse(repair())
        assertEquals(original, file.readText())
        assertEquals(original, readBackup(file))
        assertTrue(writes().isEmpty())
    }

    @Test fun emptyBackupAcknowledgementDoesNotAuthorizeWrite() {
        val original = document().toString()
        val file = add(original)
        operationMode("backup", "empty_ack")
        assertFalse(repair())
        assertEquals(original, file.readText())
        assertTrue(writes().isEmpty())
    }

    @Test fun fabricatedBackupAcknowledgementCannotReplaceLiveFile() {
        val original = document().toString()
        val file = add(original)
        operationMode("backup", "fake_ack")
        assertFalse(repair())
        assertEquals(original, file.readText())
        assertFalse(backup(file).exists())
        assertNoTemporaryFiles()
    }

    @Test fun symlinkedBackupDoesNotAlterItsDestinationOrTheLiveFile() {
        val original = document().toString()
        val file = add(original)
        val foreign = File(directory, "foreign-backup-target.json").also { it.writeText("preserve destination") }
        Files.createSymbolicLink(backup(file).toPath(), foreign.toPath())
        assertFalse(repair())
        assertEquals(original, file.readText())
        assertEquals("preserve destination", foreign.readText())
        assertTrue(Files.isSymbolicLink(backup(file).toPath()))
        assertTrue(writes().isEmpty())
    }

    @Test fun directoryAtBackupPathIsRejectedBeforeWrite() {
        val original = document().toString()
        val file = add(original)
        assertTrue(backup(file).mkdir())
        assertFalse(repair())
        assertEquals(original, file.readText())
        assertTrue(backup(file).listFiles()!!.isEmpty())
        assertTrue(writes().isEmpty())
    }

    @Test fun concurrentChangeBeforeBackupIsPreservedWithoutWrite() {
        val file = add(document())
        val replacement = document().put("concurrent", "before-backup").toString()
        control.put("replacement", replacement)
        operationMode("backup", "stale_before_backup")
        assertFalse(repair())
        assertEquals(replacement, file.readText())
        assertTrue(writes().isEmpty())
        assertNoTemporaryFiles()
    }

    @Test fun backupModifiedAfterAcknowledgementDoesNotAuthorizeWrite() {
        val original = document().toString()
        val file = add(original)
        control.put("backup_replacement", "changed backup")
        operationMode("backup", "corrupt_after_backup")
        assertFalse(repair())
        assertEquals(original, file.readText())
        assertEquals("changed backup", readBackup(file))
        assertNoTemporaryFiles()
    }

    @Test fun rollbackPreservesExactOriginalBytesModeAndRecoveryCopy() {
        val original = document().toString(2)
        val file = add(original)
        Files.setPosixFilePermissions(file.toPath(), PosixFilePermissions.fromString("rw-r-----"))
        mode("ack_suffix")
        assertFalse(repair())
        assertEquals(original, file.readText())
        assertEquals(original, readBackup(file))
        assertEquals("rw-r-----", PosixFilePermissions.toString(Files.getPosixFilePermissions(file.toPath())))
        assertTrue(events().any { it.optString("kind") == "restore" })
        assertNoTemporaryFiles()
    }

    @Test fun failedRestoreRetainsVerifiedBackupAndReportsFailure() {
        val original = document().toString()
        val file = add(original)
        mode("ack_suffix")
        operationMode("restore", "mv_fail")
        assertFalse(repair())
        assertNotEquals(original, file.readText())
        assertEquals(original, readBackup(file))
        assertNoTemporaryFiles()
    }

    @Test fun tamperedBackupIsNeverRestored() {
        val original = document().toString()
        val file = add(original)
        control.put("backup_replacement", "unverified backup")
        mode("ack_suffix")
        operationMode("restore", "tampered_backup")
        assertFalse(repair())
        assertNotEquals(original, file.readText())
        assertNotEquals("unverified backup", file.readText())
        assertEquals("unverified backup", readBackup(file))
        assertNoTemporaryFiles()
    }

    @Test fun changeBetweenWriteFailureAndRestoreIsPreserved() {
        val original = document().toString()
        val file = add(original)
        val replacement = document().put("concurrent", "before-restore").toString()
        control.put("replacement", replacement)
        mode("ack_suffix")
        operationMode("restore", "changed_before_restore")
        assertFalse(repair())
        assertEquals(replacement, file.readText())
        assertEquals(original, readBackup(file))
        assertNoTemporaryFiles()
    }

    @Test fun existingRegularBackupIsReplacedWithThisAttemptsSnapshot() {
        val original = document().toString()
        val file = add(original)
        backup(file).writeText("older recovery point")
        assertTrue(repair())
        assertEquals(original, readBackup(file))
        assertNoTemporaryFiles()
    }
}
