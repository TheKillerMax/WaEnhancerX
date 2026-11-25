package com.waenhancer.utils

import android.content.Context
import android.content.pm.PackageManager
import android.os.Process
import android.os.SystemClock
import java.util.Collections

/** A successful, timestamped process-list observation, not proof of hook initialization. */
data class XposedRuntimeSnapshot(
    val runningPids: Map<String, Set<Int>>,
    val observedAtElapsed: Long = SystemClock.elapsedRealtime(),
    val complete: Boolean = true,
    /** True when [runningPids] came from a full process list: absence means "not running". */
    val exhaustive: Boolean = false
) {
    /** Live pids for [packageName], or null when this snapshot cannot answer. */
    fun pidsFor(packageName: String): Set<Int>? {
        if (!complete) return null
        return runningPids[packageName] ?: if (exhaustive) emptySet() else null
    }
}

private val processNamePattern = Regex("[A-Za-z_][A-Za-z0-9_]*(?:\\.[A-Za-z_][A-Za-z0-9_]*)+")

/** Only a complete, UID-verified row for each queried package can establish process absence. */
internal fun parseProcessList(
    output: String,
    expectedUids: Map<String, Int>,
    observedAtElapsed: Long = SystemClock.elapsedRealtime()
): XposedRuntimeSnapshot {
    val running = linkedMapOf<String, Set<Int>>()
    var valid = expectedUids.isNotEmpty()
    output.lineSequence().filter { it.isNotBlank() }.forEach { line ->
        val parts = line.split('|', limit = 4)
        if (parts.size != 4 || parts[0] != "PID" || parts[1].length > 255 ||
            !processNamePattern.matches(parts[1]) || parts[1] in running ||
            parts[1] !in expectedUids || parts[2].toIntOrNull() != expectedUids[parts[1]]) {
            valid = false
        } else {
            val tokens = parts[3].trim().takeIf { it.isNotEmpty() }?.split(Regex("\\s+")).orEmpty()
            val pids = tokens.mapNotNull(String::toIntOrNull)
            if (pids.size != tokens.size || pids.any { it <= 0 }) valid = false
            running[parts[1]] = Collections.unmodifiableSet(LinkedHashSet(pids))
        }
    }
    return XposedRuntimeSnapshot(
        Collections.unmodifiableMap(running), observedAtElapsed,
        complete = valid && running.keys == expectedUids.keys, exhaustive = false
    )
}

/** UID checks shared by the single on-demand root probe; no independent polling or cache. */
internal object ProfileProcessProbe {
    const val MODULE_PACKAGE_NAME = "com.waenhancer"

    fun expectedUids(context: Context): Map<String, Int>? = try {
        val processUid = Process.myUid()
        val userId = AndroidUserScope.matchingUserId(context.applicationInfo.uid, processUid)
        require(context.packageName == MODULE_PACKAGE_NAME && context.applicationInfo.uid == processUid)
        val expected = linkedMapOf<String, Int>()
        for (pkg in DeclaredWhatsAppTargets.packages() + MODULE_PACKAGE_NAME) {
            @Suppress("DEPRECATION")
            val info = try {
                context.packageManager.getApplicationInfo(pkg, 0)
            } catch (missing: PackageManager.NameNotFoundException) {
                if (pkg == MODULE_PACKAGE_NAME) throw missing
                continue // Uninstalled targets are absent from the query, not observed as stopped.
            }
            require(info.packageName == pkg && AndroidUserScope.userIdForUid(info.uid) == userId)
            if (pkg == MODULE_PACKAGE_NAME) require(info.uid == processUid)
            expected[pkg] = info.uid
        }
        Collections.unmodifiableMap(expected)
    } catch (_: PackageManager.NameNotFoundException) {
        null
    } catch (_: RuntimeException) {
        null
    } catch (_: LinkageError) {
        null
    }

    /** Every pidof result is checked against all four kernel UID fields before being reported. */
    fun command(expectedUids: Map<String, Int>): String {
        require(expectedUids.isNotEmpty() && expectedUids.all { (pkg, uid) ->
            pkg.length <= 255 && processNamePattern.matches(pkg) && uid >= 0
        })
        return "set -f\ncommand -v pidof >/dev/null 2>&1 || exit 127\n" +
            expectedUids.entries.joinToString("\n") { (pkg, expectedUid) ->
                "pids=\$(pidof '$pkg' 2>/dev/null); rc=\$?; " +
                    "case \"\$rc\" in 0) [ -n \"\$pids\" ] || exit 2;; " +
                    "1) [ -z \"\$pids\" ] || exit 2;; *) exit 2;; esac; " +
                    "owned=''; for pid in \$pids; do " +
                    "case \"\$pid\" in ''|*[!0-9]*|0) exit 2;; esac; uid=''; " +
                    "while read -r field real effective saved filesystem extra; do " +
                    "if [ \"\$field\" = 'Uid:' ]; then " +
                    "[ -z \"\$extra\" ] && [ \"\$real\" = \"\$effective\" ] && " +
                    "[ \"\$real\" = \"\$saved\" ] && [ \"\$real\" = \"\$filesystem\" ] || exit 2; " +
                    "uid=\$real; break; fi; done < \"/proc/\$pid/status\" || exit 2; " +
                    "case \"\$uid\" in ''|*[!0-9]*) exit 2;; esac; " +
                    "if [ \"\$uid\" = '$expectedUid' ]; then owned=\"\$owned \$pid\"; fi; done; " +
                    "printf 'PID|$pkg|$expectedUid|%s\\n' \"\${owned# }\""
            }
    }

    fun containsManagerProcess(snapshot: XposedRuntimeSnapshot): Boolean =
        snapshot.pidsFor(MODULE_PACKAGE_NAME)?.contains(Process.myPid()) == true
}
