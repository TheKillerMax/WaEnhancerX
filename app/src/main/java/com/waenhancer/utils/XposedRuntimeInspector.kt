package com.waenhancer.utils

import com.waenhancer.xposed.utils.AppRestartHelper

data class XposedRuntimeSnapshot(
    val runningPids: Map<String, Set<Int>>
)

internal fun parseXposedRuntimeSnapshot(output: String): XposedRuntimeSnapshot {
    val packagePattern = Regex("[A-Za-z0-9_.]+")
    val running = linkedMapOf<String, Set<Int>>()
    output.lineSequence().forEach { line ->
        if (line.startsWith("PID|")) {
            val parts = line.split('|', limit = 3)
            if (parts.size == 3 && packagePattern.matches(parts[1])) {
                running[parts[1]] = parts[2].split(' ')
                    .mapNotNull(String::toIntOrNull)
                    .filter { it > 0 }
                    .toSet()
            }
        }
    }
    return XposedRuntimeSnapshot(runningPids = running)
}

/** Root-assisted view of currently running target processes. */
object XposedRuntimeInspector {
    private val validPackage = Regex("[A-Za-z0-9_.]+")

    @Volatile
    private var cachedSnapshot: XposedRuntimeSnapshot? = null

    fun cached(): XposedRuntimeSnapshot? = cachedSnapshot

    fun inspect(packageNames: Collection<String>): XposedRuntimeSnapshot? {
        val packages = packageNames.filter { validPackage.matches(it) }.distinct()
        val command = packages.joinToString("\n") { pkg ->
            "pids=\$(pidof $pkg 2>/dev/null || true); printf 'PID|$pkg|%s\\n' \"\$pids\""
        }
        if (command.isBlank()) return XposedRuntimeSnapshot(emptyMap()).also {
            cachedSnapshot = it
        }
        val output = AppRestartHelper.runRootCommand(command) ?: return null
        return parseXposedRuntimeSnapshot(output).also { cachedSnapshot = it }
    }
}
