package com.waenhancer.utils

import android.os.SystemClock
import com.waenhancer.xposed.utils.AppRestartHelper
import java.util.Collections

/** A successful, timestamped process observation, not proof of hook initialization. */
data class XposedRuntimeSnapshot(
    val runningPids: Map<String, Set<Int>>,
    val observedAtElapsed: Long = SystemClock.elapsedRealtime(),
    val complete: Boolean = true
) {
    fun pidsFor(packageName: String, nowElapsed: Long): Set<Int>? =
        if (complete && isRecentTimestamp(observedAtElapsed, nowElapsed)) runningPids[packageName] else null
}

private val processPackagePattern = Regex("[A-Za-z_][A-Za-z0-9_]*(?:\\.[A-Za-z_][A-Za-z0-9_]*)+")

internal fun parseXposedRuntimeSnapshot(output: String): XposedRuntimeSnapshot {
    val running = linkedMapOf<String, Set<Int>>()
    var valid = true
    output.lineSequence().filter { it.isNotBlank() }.forEach { line ->
        val parts = line.split('|', limit = 3)
        if (parts.size != 3 || parts[0] != "PID" || parts[1].length > 255 ||
            !processPackagePattern.matches(parts[1]) || parts[1] in running) {
            valid = false
        } else {
            val tokens = parts[2].trim().takeIf { it.isNotEmpty() }?.split(Regex("\\s+")).orEmpty()
            val pids = tokens.mapNotNull(String::toIntOrNull)
            if (pids.size != tokens.size || pids.any { it <= 0 }) valid = false
            running[parts[1]] = Collections.unmodifiableSet(LinkedHashSet(pids))
        }
    }
    return XposedRuntimeSnapshot(Collections.unmodifiableMap(running), complete = valid)
}

/** Root-assisted observations. An unavailable/truncated probe must never mean no running process. */
object XposedRuntimeInspector {
    @Volatile private var cachedSnapshot: XposedRuntimeSnapshot? = null

    fun cached(): XposedRuntimeSnapshot? = cachedSnapshot?.takeIf {
        it.complete && isRecentTimestamp(it.observedAtElapsed, SystemClock.elapsedRealtime())
    }

    @Synchronized
    fun inspect(packageNames: Collection<String>): XposedRuntimeSnapshot? {
        val packages = packageNames.distinct()
        if (packages.any { it.length > 255 || !processPackagePattern.matches(it) }) {
            cachedSnapshot = null
            return null
        }
        if (packages.isEmpty()) return XposedRuntimeSnapshot(emptyMap()).also { cachedSnapshot = it }
        val startedAtElapsed = SystemClock.elapsedRealtime()
        val command = "command -v pidof >/dev/null 2>&1 || exit 127\n" + packages.joinToString("\n") { pkg ->
            "pids=\$(pidof $pkg 2>/dev/null); rc=\$?; " +
                "case \"\$rc\" in 0) [ -n \"\$pids\" ] || exit 2;; " +
                "1) [ -z \"\$pids\" ] || exit 2;; *) exit 2;; esac; " +
                "printf 'PID|$pkg|%s\\n' \"\$pids\""
        }
        val completedCommand = command + "\nprintf 'END|WAEX_PROCESS_SNAPSHOT\\n'"
        val output = try { AppRestartHelper.runRootCommand(completedCommand) }
            catch (_: RuntimeException) { null }
            catch (_: LinkageError) { null }
        val lines = output?.lineSequence()?.filter { it.isNotBlank() }?.toList()
        val result = lines?.takeIf { it.lastOrNull() == "END|WAEX_PROCESS_SNAPSHOT" }
            ?.dropLast(1)?.joinToString("\n")?.let(::parseXposedRuntimeSnapshot)
            ?.copy(observedAtElapsed = startedAtElapsed)?.takeIf {
                it.complete && it.runningPids.keys == packages.toSet() &&
                    isRecentTimestamp(startedAtElapsed, SystemClock.elapsedRealtime())
            }
        cachedSnapshot = result // A failed new observation invalidates old cached proof.
        return result
    }
}
