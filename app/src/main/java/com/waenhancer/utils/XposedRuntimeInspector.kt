package com.waenhancer.utils

import android.os.SystemClock
import java.util.Collections

/** A successful, timestamped process-list observation, not proof of hook initialization. */
data class XposedRuntimeSnapshot(
    val runningPids: Map<String, Set<Int>>,
    val observedAtElapsed: Long = SystemClock.elapsedRealtime(),
    val complete: Boolean = true,
    /** True when [runningPids] came from a full process list: absence means "not running". */
    val exhaustive: Boolean = false,
    /** Exact Android UIDs from numeric `ps UID,PID,NAME` rows, never inferred from names. */
    val runningPidsByUid: Map<String, Map<Int, Set<Int>>> = emptyMap(),
    /** False if any applicable row lacked a trustworthy numeric UID or PID. */
    val uidQualified: Boolean = false
) {
    /** Live pids for [packageName], or null when this snapshot cannot answer. */
    fun pidsFor(packageName: String): Set<Int>? {
        if (!complete) return null
        return runningPids[packageName] ?: if (exhaustive) emptySet() else null
    }

    /** Only these PIDs can confirm injection into the installed app of this Android user. */
    fun pidsForUid(packageName: String, expectedUid: Int?): Set<Int>? {
        if (!complete || !uidQualified || expectedUid == null || expectedUid <= 0) return null
        return runningPidsByUid[packageName]?.get(expectedUid)
            ?: if (exhaustive) emptySet() else null
    }
}

private val processNamePattern = Regex("[A-Za-z_][A-Za-z0-9_]*(?:\\.[A-Za-z_][A-Za-z0-9_]*)+")

/**
 * Parses `ps` output into PIDs by name and, only with a numeric UID column, by Android UID.
 * Legacy `PID NAME` or `USER PID ... NAME` remains useful for diagnostics but must not confirm
 * injection in an Android user: a work-profile process can have the identical package name.
 * Incomplete/mixed UID rows invalidate UID-qualified observations instead of becoming "stopped".
 */
internal fun parseProcessList(output: String, observedAtElapsed: Long = SystemClock.elapsedRealtime()): XposedRuntimeSnapshot {
    val byName = linkedMapOf<String, MutableSet<Int>>()
    val byUid = linkedMapOf<String, MutableMap<Int, MutableSet<Int>>>()
    var allRowsHaveNumericUid = true
    output.lineSequence().forEach { line ->
        val tokens = line.trim().split(Regex("\\s+"))
        if (tokens.size < 2) return@forEach
        val name = tokens.last()
        if (name.length > 255 || !processNamePattern.matches(name)) return@forEach
        val pidToken = if (tokens.size == 2) tokens[0] else tokens[1]
        val pid = pidToken.toIntOrNull()?.takeIf { it > 0 }
        if (pid == null) {
            allRowsHaveNumericUid = false
            return@forEach
        }
        byName.getOrPut(name) { linkedSetOf() }.add(pid)
        val uid = if (tokens.size == 3) tokens[0].toIntOrNull()?.takeIf { it >= 0 } else null
        if (uid == null) {
            allRowsHaveNumericUid = false
        } else {
            byUid.getOrPut(name) { linkedMapOf() }.getOrPut(uid) { linkedSetOf() }.add(pid)
        }
    }
    val immutableByUid = Collections.unmodifiableMap(byUid.mapValues { (_, perUid) ->
        Collections.unmodifiableMap(perUid.mapValues { (_, pids) -> Collections.unmodifiableSet(pids) })
    })
    return XposedRuntimeSnapshot(
        Collections.unmodifiableMap(byName.mapValues { Collections.unmodifiableSet(it.value) }),
        observedAtElapsed, complete = true, exhaustive = true,
        runningPidsByUid = immutableByUid,
        uidQualified = allRowsHaveNumericUid && byName.isNotEmpty()
    )
}
