package com.waenhancer.utils

import android.content.Context
import android.os.SELinux
import com.waenhancer.update.UpdateDownloader
import com.waenhancer.xposed.utils.AppRestartHelper
import java.io.File

// The complete production class is compiled unchanged. Android/root APIs below
// are configured doubles. The real absolute kernel path must be unreadable on
// the host JVM; no path is rewritten and no system file is created or modified.
private var checks = 0
private var scenarios = 0
private val failures = mutableListOf<String>()
private val context = Context()

private fun checkCase(value: Boolean, label: String) {
    checks++
    if (!value) throw AssertionError(label)
}

private fun cached(name: String, value: Any?) {
    SystemDiagnosticsReader::class.java.getDeclaredField(name).also {
        it.isAccessible = true
        it.set(SystemDiagnosticsReader, value)
    }
}

private fun reset() {
    cached("cachedDiagnostics", null)
    cached("cachedSelinux", null)
    SELinux.enforced = false; SELinux.failure = null; SELinux.calls = 0
    UpdateDownloader.allowed = false; UpdateDownloader.requests.clear()
    AppRestartHelper.output = null; AppRestartHelper.failure = null; AppRestartHelper.commands.clear()
    context.packageManager.lookups.clear()
}

private fun scenario(label: String, action: () -> Unit) {
    scenarios++
    reset()
    try { action() }
    catch (error: Throwable) { failures += "$label: ${error.javaClass.simpleName}: ${error.message}" }
}

private fun fast() = SystemDiagnosticsReader.getOrFastSnapshot(context, moduleActive = false)
private fun full(force: Boolean = false) = SystemDiagnosticsReader.read(context, moduleActive = false, forceRefresh = force)
private fun normalize(raw: String?): String? {
    val method = SystemDiagnosticsReader::class.java.getDeclaredMethod("normalizeSelinuxState", String::class.java)
    method.isAccessible = true
    return method.invoke(SystemDiagnosticsReader, raw) as String?
}

fun main() {
    require(runCatching { File("/sys/fs/selinux/enforce").readText() }.isFailure) {
        "This host-JVM fixture requires the exact production SELinux file to be unreadable"
    }
    scenario("false reflection is ambiguous and fast path has no root") {
        UpdateDownloader.allowed = true
        AppRestartHelper.output = "Enforcing"
        checkCase(fast().selinux == "Unknown", "false became a claimed kernel mode")
        checkCase(UpdateDownloader.requests.isEmpty(), "fast path probed root")
        checkCase(AppRestartHelper.commands.isEmpty(), "fast path executed root")
        checkCase(context.packageManager.lookups == listOf(context.packageName), "fast path scanned manager packages")
    }
    scenario("missing reflection evidence remains unknown") {
        SELinux.failure = IllegalAccessException("hidden API unavailable")
        checkCase(fast().selinux == "Unknown", "absent evidence became Enforcing")
        checkCase(AppRestartHelper.commands.isEmpty(), "fast failure executed root")
    }
    scenario("reflection linkage failure remains unknown") {
        SELinux.failure = UnsatisfiedLinkError("native boundary unavailable")
        checkCase(fast().selinux == "Unknown", "linkage failure became a mode")
    }
    scenario("positive reflection evidence remains enforcing") {
        SELinux.enforced = true
        checkCase(fast().selinux == "Enforcing", "verified true was discarded")
        checkCase(SELinux.calls == 1, "reflection call count")
        checkCase(AppRestartHelper.commands.isEmpty(), "verified fast mode executed root")
    }
    scenario("explicit numeric and named states retain their meanings") {
        for ((raw, mode) in listOf("1" to "Enforcing", "1\n" to "Enforcing", " EnFoRcInG " to "Enforcing",
                                  "0" to "Permissive", "0\n" to "Permissive", "pErMiSsIvE" to "Permissive",
                                  "Disabled\n" to "Disabled")) {
            checkCase(normalize(raw) == mode, "normalizer changed $raw")
        }
    }
    scenario("errors and malformed observations are not modes") {
        for (raw in listOf(null, "", "-1", "2", "permission denied", "Enforcing\nerror", "true", "false")) {
            checkCase(normalize(raw) == null, "unverified observation accepted: $raw")
        }
    }
    scenario("ambiguous false permits an authorized enforcing root read") {
        for (raw in listOf("1\n", "Enforcing\n")) {
            reset(); UpdateDownloader.allowed = true; AppRestartHelper.output = raw
            checkCase(full().selinux == "Enforcing", "false short-circuited verified root result")
            checkCase(AppRestartHelper.commands == listOf("getenforce"), "root command was not the single read-only probe")
        }
    }
    scenario("verified zero and permissive remain permissive") {
        for (raw in listOf("0\n", "Permissive\n")) {
            reset(); UpdateDownloader.allowed = true; AppRestartHelper.output = raw
            checkCase(full().selinux == "Permissive", "verified permissive was discarded")
            checkCase(AppRestartHelper.commands == listOf("getenforce"), "permissive was guessed without evidence")
        }
    }
    scenario("verified disabled is preserved") {
        UpdateDownloader.allowed = true; AppRestartHelper.output = "Disabled\n"
        checkCase(full().selinux == "Disabled", "disabled was relabeled")
        checkCase(AppRestartHelper.commands == listOf("getenforce"), "disabled did not come from the read-only probe")
    }
    scenario("unavailable root is never executed") {
        AppRestartHelper.output = "Enforcing"
        checkCase(full().selinux == "Unknown", "false with unavailable root became a mode")
        checkCase(AppRestartHelper.commands.isEmpty(), "root authorization ignored")
    }
    scenario("positive reflection avoids a redundant root command") {
        SELinux.enforced = true; UpdateDownloader.allowed = true
        AppRestartHelper.failure = AssertionError("No root read needed")
        checkCase(full().selinux == "Enforcing", "positive result lost")
        checkCase(AppRestartHelper.commands.isEmpty(), "unnecessary root read")
    }
    scenario("missing reflection can use the authorized root result") {
        SELinux.failure = IllegalAccessException("hidden API unavailable")
        UpdateDownloader.allowed = true; AppRestartHelper.output = "Permissive"
        checkCase(full().selinux == "Permissive", "root fallback unavailable after reflection failure")
        checkCase(AppRestartHelper.commands == listOf("getenforce"), "wrong root command")
    }
    scenario("bad root output remains unknown") {
        for (raw in listOf(null, "", "permission denied", "-1", "Enforcing\nerror")) {
            reset(); UpdateDownloader.allowed = true; AppRestartHelper.output = raw
            checkCase(full().selinux == "Unknown", "bad root output became a mode: $raw")
            checkCase(AppRestartHelper.commands == listOf("getenforce"), "root fallback did not run")
        }
    }
    scenario("root boundary failure remains unknown") {
        UpdateDownloader.allowed = true; AppRestartHelper.failure = java.io.IOException("read denied")
        checkCase(full().selinux == "Unknown", "root read failure escaped or became a mode")
        checkCase(AppRestartHelper.commands == listOf("getenforce"), "unexpected retry")
    }
    scenario("fast unknown is resolved by the following full refresh") {
        checkCase(fast().selinux == "Unknown", "fast unknown missing")
        UpdateDownloader.allowed = true; AppRestartHelper.output = "Enforcing"
        checkCase(full().selinux == "Enforcing", "fast unknown poisoned the full cache")
        checkCase(SystemDiagnosticsReader.cached()?.selinux == "Enforcing", "resolved snapshot was not stored")
    }
    scenario("a cached unknown never blocks a normal full refresh") {
        cached("cachedSelinux", "Unknown")
        UpdateDownloader.allowed = true; AppRestartHelper.output = "Disabled"
        checkCase(full().selinux == "Disabled", "unknown cache blocked another observation")
        checkCase(AppRestartHelper.commands == listOf("getenforce"), "unknown cache suppressed probe")
    }
    scenario("known cache retains the existing non-forced refresh contract") {
        cached("cachedSelinux", "Enforcing")
        UpdateDownloader.allowed = true; AppRestartHelper.output = "Permissive"
        checkCase(full().selinux == "Enforcing", "known cache bypassed without force")
        checkCase(AppRestartHelper.commands.isEmpty(), "known cache caused root execution")
    }
    scenario("forced refresh replaces a known mode with current evidence") {
        cached("cachedSelinux", "Enforcing")
        UpdateDownloader.allowed = true; AppRestartHelper.output = "Permissive"
        checkCase(full(force = true).selinux == "Permissive", "forced refresh kept an old mode")
        checkCase(UpdateDownloader.requests == listOf(true), "root cache refresh flag lost")
        checkCase(AppRestartHelper.commands == listOf("getenforce"), "forced refresh did not read current state")
    }
    scenario("failed forced refresh does not present the old mode as new evidence") {
        cached("cachedSelinux", "Enforcing")
        UpdateDownloader.allowed = true; AppRestartHelper.output = "unavailable"
        checkCase(full(force = true).selinux == "Unknown", "old or default mode claimed after refresh failure")
        checkCase(SystemDiagnosticsReader.cached()?.selinux == "Unknown", "failure snapshot not updated")
    }
    scenario("cached fast snapshot performs no new root or reflection probe") {
        SELinux.enforced = true
        val first = fast()
        val second = fast()
        checkCase(first === second, "fast snapshot not reused")
        checkCase(SELinux.calls == 1, "cached fast snapshot repeated reflection")
        checkCase(UpdateDownloader.requests.isEmpty() && AppRestartHelper.commands.isEmpty(), "cached fast snapshot executed root")
    }
    println("SELINUX_DIAGNOSTICS scenarios=$scenarios checks=$checks failures=${failures.size}")
    failures.forEach { println("FAIL: $it") }
    if (failures.isNotEmpty()) throw AssertionError("SELinux diagnostics regressions")
}
