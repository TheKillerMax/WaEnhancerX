package com.waenhancer.utils

import android.content.Context
import android.os.SELinux
import com.waenhancer.update.UpdateDownloader
import com.waenhancer.xposed.utils.AppRestartHelper
import java.io.File
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

private var checks = 0
private val reader = SystemDiagnosticsReader
private val executor = Executors.newSingleThreadExecutor { Thread(it, "selinux-qa-io") }
private fun <T> io(block: () -> T): T = executor.submit<T> { block() }.get(10, TimeUnit.SECONDS)
private fun equal(expected: Any?, actual: Any?, label: String) {
    checks++
    check(expected == actual) { "$label: expected=$expected actual=$actual" }
}
private fun invoke(name: String, parameter: Boolean? = null): String {
    val method = if (parameter == null) reader.javaClass.getDeclaredMethod(name)
                 else reader.javaClass.getDeclaredMethod(name, Boolean::class.javaPrimitiveType)
    method.isAccessible = true
    return (if (parameter == null) method.invoke(reader) else method.invoke(reader, parameter)) as String
}
private fun normalize(raw: String?): String? {
    val method = reader.javaClass.getDeclaredMethod("normalizeSelinuxState", String::class.java)
    method.isAccessible = true
    return method.invoke(reader, raw) as String?
}
private fun reset() {
    for (name in listOf("cachedDiagnostics", "cachedSelinux")) {
        reader.javaClass.getDeclaredField(name).also { it.isAccessible = true }.set(reader, null)
    }
    SELinux.enforced = false; SELinux.fail = false; SELinux.calls = 0
    UpdateDownloader.rootAllowed = false; UpdateDownloader.forceFlags.clear()
    AppRestartHelper.response = "Enforcing"; AppRestartHelper.fail = false
    AppRestartHelper.commands.clear(); AppRestartHelper.threads.clear()
}

fun main(args: Array<String>) {
    try {
        check(!File("/sys/fs/selinux/enforce").exists()) {
            "This fixture requires a host without an accessible Android SELinux sysfs path"
        }
        val context = Context()
        if (args.singleOrNull() == "observe") {
            reset(); UpdateDownloader.rootAllowed = true
            val fast = reader.getOrFastSnapshot(context, false).selinux
            val full = io { reader.read(context, false).selinux }
            val direct = io { invoke("readSelinuxState", true) }
            println("OBSERVED fast_false=$fast full_after_fast=$full direct_root_allowed=$direct root_commands=${AppRestartHelper.commands.size}")
            return
        }

        for ((raw, expected) in listOf(null to null, "" to null, "  " to null,
                "1" to "Enforcing", "0" to "Permissive", " EnFoRcInG\r\n" to "Enforcing",
                " PERMISSIVE\n" to "Permissive", "Disabled" to "Disabled",
                "-1" to null, "2" to null, "true" to null, "false" to null,
                "permission denied" to null, "Enforcing\npermission denied" to null)) {
            equal(expected, normalize(raw), "explicit normalization $raw")
        }
        reset(); UpdateDownloader.rootAllowed = true
        equal("Unknown", invoke("readFastSelinuxState"), "ambiguous false must not imply permissive")
        equal(0, AppRestartHelper.commands.size, "fast path never calls root")
        equal(0, UpdateDownloader.forceFlags.size, "fast path never requests root permission")
        reset(); SELinux.enforced = true
        equal("Enforcing", invoke("readFastSelinuxState"), "positive framework evidence")
        equal(0, AppRestartHelper.commands.size, "positive fast path never calls root")
        reset(); SELinux.fail = true
        equal("Unknown", invoke("readFastSelinuxState"), "unavailable framework is unknown")

        for ((raw, expected) in listOf("Enforcing" to "Enforcing", "Permissive" to "Permissive",
                "Disabled" to "Disabled", "1" to "Enforcing", "0" to "Permissive",
                null to "Unknown", "" to "Unknown", "-1" to "Unknown", "denied" to "Unknown")) {
            reset(); AppRestartHelper.response = raw
            equal(expected, io { invoke("readSelinuxState", true) }, "authorized explicit result $raw")
            equal(listOf("getenforce"), AppRestartHelper.commands, "only existing read-only root command")
            equal(listOf("selinux-qa-io"), AppRestartHelper.threads, "root only on worker")
        }
        reset(); AppRestartHelper.fail = true
        equal("Unknown", io { invoke("readSelinuxState", true) }, "root exception does not become a state")
        reset(); SELinux.fail = true
        equal("Enforcing", io { invoke("readSelinuxState", true) }, "root can resolve reflection failure")
        reset(); SELinux.enforced = true
        equal("Enforcing", io { invoke("readSelinuxState", true) }, "true needs no root fallback")
        equal(0, AppRestartHelper.commands.size, "no extra root call for true evidence")
        reset(); AppRestartHelper.response = "Permissive"
        equal("Unknown", io { invoke("readSelinuxState", false) }, "root gate is required")
        equal(0, AppRestartHelper.commands.size, "denied root never executed")

        reset(); UpdateDownloader.rootAllowed = true
        equal("Unknown", reader.getOrFastSnapshot(context, false).selinux, "UI starts with ambiguous unknown")
        equal(0, AppRestartHelper.commands.size, "UI does not query root even if root cached")
        equal("Enforcing", io { reader.read(context, false).selinux }, "background upgrades fast unknown")
        equal(1, AppRestartHelper.commands.size, "one authorized fallback")
        repeat(5) { equal("Enforcing", io { reader.read(context, false).selinux }, "confirmed cache reused") }
        equal(1, AppRestartHelper.commands.size, "normal refreshes add no getenforce calls")
        equal(List(6) { false }, UpdateDownloader.forceFlags, "existing permission checker called once per full read")
        equal("Enforcing", reader.getOrFastSnapshot(context, false).selinux, "fast snapshot uses collected result")
        equal(1, AppRestartHelper.commands.size, "cached fast snapshot adds no root call")
        AppRestartHelper.response = "Permissive"
        equal("Permissive", io { reader.read(context, false, true).selinux }, "explicit forced refresh observes change")
        equal(2, AppRestartHelper.commands.size, "explicit force adds only one fallback")
        equal(true, UpdateDownloader.forceFlags.last(), "force contract preserved")

        reset(); UpdateDownloader.rootAllowed = true; AppRestartHelper.response = null
        equal("Unknown", reader.getOrFastSnapshot(context, false).selinux, "fast unknown before failed root probe")
        equal("Unknown", io { reader.read(context, false).selinux }, "failed root result remains unknown")
        repeat(5) { equal("Unknown", io { reader.read(context, false).selinux }, "failed probe cache reused") }
        equal(1, AppRestartHelper.commands.size, "failed root probe is not repeated per refresh")
        equal(2, SELinux.calls, "fast and initial background probes only")
        equal("Unknown", io { reader.read(context, false, true).selinux }, "force may recheck failed probe")
        equal(2, AppRestartHelper.commands.size, "only explicit force rechecks same root context")

        reset(); UpdateDownloader.rootAllowed = false
        equal("Unknown", reader.getOrFastSnapshot(context, false).selinux, "no root initial unknown")
        equal("Unknown", io { reader.read(context, false).selinux }, "no root background unknown")
        repeat(3) { equal("Unknown", io { reader.read(context, false).selinux }, "no root stable cache") }
        equal(0, AppRestartHelper.commands.size, "no su requests without existing authorization")
        UpdateDownloader.rootAllowed = true
        equal("Enforcing", io { reader.read(context, false).selinux }, "root availability change permits one upgrade")
        equal(1, AppRestartHelper.commands.size, "one upgrade for newly available root")

        reset(); SELinux.enforced = true; UpdateDownloader.rootAllowed = true
        equal("Enforcing", reader.getOrFastSnapshot(context, false).selinux, "fast positive cache")
        equal("Enforcing", io { reader.read(context, false).selinux }, "fast positive cache accepted")
        equal(0, AppRestartHelper.commands.size, "no new root requests with positive boolean")
        equal(1, SELinux.calls, "positive cache avoids duplicate framework query")
        println("PASS SELinux diagnostics JVM checks=$checks; compiled production source unchanged; no real root/device calls")
    } finally {
        executor.shutdownNow()
    }
}
