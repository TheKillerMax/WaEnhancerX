package com.waenhancer.utils

import android.content.Context
import android.content.pm.PackageManager
import android.os.Process
import java.util.Collections

private val packageNamePattern = Regex("[A-Za-z_][A-Za-z0-9_]*(?:\\.[A-Za-z_][A-Za-z0-9_]*)+")
private val appUserPattern = Regex("u(0|[1-9][0-9]*)_a(0|[1-9][0-9]*)")

/** Resolve packages through this manager's user, never the root shell's owner user. */
internal fun processOwners(context: Context): Map<String, Int>? = try {
    val own = context.applicationInfo
    val user = AndroidUserScope.matchingUserId(own.uid, Process.myUid())
    require(own.uid == Process.myUid() && own.packageName == context.packageName)
    require(context.packageName.length <= 255 && packageNamePattern.matches(context.packageName))
    val owners = linkedMapOf(context.packageName to own.uid)
    for (name in DeclaredWhatsAppTargets.packages()) {
        val app = try {
            @Suppress("DEPRECATION")
            context.packageManager.getApplicationInfo(name, 0)
        } catch (_: PackageManager.NameNotFoundException) {
            continue // No UID evidence: no process assertion for this package.
        }
        require(app.packageName == name && AndroidUserScope.userIdForUid(app.uid) == user)
        owners[name] = app.uid
    }
    Collections.unmodifiableMap(owners)
} catch (_: RuntimeException) {
    null
} catch (_: LinkageError) {
    null
}

/** Numeric UID from modern ps, or bionic's u<user>_a<app> name from legacy ps. */
private fun processUid(token: String): Int? {
    if (token.matches(Regex("0|[1-9][0-9]*"))) return token.toIntOrNull()
    val match = appUserPattern.matchEntire(token) ?: return null
    val user = match.groupValues[1].toLongOrNull() ?: return null
    val app = match.groupValues[2].toLongOrNull() ?: return null
    if (user > Int.MAX_VALUE / 100_000 || app >= 89_000) return null
    val uid = user * 100_000 + 10_000 + app
    return uid.takeIf { it <= Int.MAX_VALUE }?.toInt()
}

/**
 * Parse only UID-bearing records. Another user's same package is not this user's process.
 * Unknown packages remain unknown; an unresolvable row cannot prove target absence.
 */
internal fun parseProfileProcessList(output: String, owners: Map<String, Int>, observedAt: Long): XposedRuntimeSnapshot {
    val byName = owners.mapValuesTo(linkedMapOf()) { linkedSetOf<Int>() }
    val identities = mutableMapOf<Int, Pair<String, Int>>()
    var complete = true
    output.lineSequence().filter { it.isNotBlank() }.forEach { line ->
        val tokens = line.trim().split(Regex("\\s+"))
        if (tokens.size < 3) { complete = false; return@forEach }
        val name = tokens.last()
        val uid = processUid(tokens[0])
        val pid = tokens[1].toIntOrNull()?.takeIf { it > 0 }
        if (name.length > 255 || !packageNamePattern.matches(name) || uid == null || pid == null) {
            complete = false
            return@forEach
        }
        val identity = name to uid
        if (identities.put(pid, identity)?.let { it != identity } == true) complete = false
        if (owners[name] == uid) byName[name]?.add(pid)
    }
    return XposedRuntimeSnapshot(
        Collections.unmodifiableMap(byName.mapValues { Collections.unmodifiableSet(it.value) }),
        observedAt, complete = complete, exhaustive = false
    )
}
