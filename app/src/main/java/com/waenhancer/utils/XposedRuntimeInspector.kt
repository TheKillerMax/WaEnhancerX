package com.waenhancer.utils

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import com.waenhancer.xposed.utils.AppRestartHelper
import java.io.File

enum class RuntimeScopeState { IN_SCOPE, NOT_IN_SCOPE, UNAVAILABLE }

data class XposedRuntimeSnapshot(
    val scopeAvailable: Boolean,
    val scopedPackages: Set<String>,
    val runningPids: Map<String, Set<Int>>
) {
    fun scopeState(packageName: String): RuntimeScopeState = when {
        !scopeAvailable -> RuntimeScopeState.UNAVAILABLE
        packageName in scopedPackages -> RuntimeScopeState.IN_SCOPE
        else -> RuntimeScopeState.NOT_IN_SCOPE
    }
}

internal fun parseXposedRuntimeSnapshot(output: String, userId: Int): XposedRuntimeSnapshot {
    val packagePattern = Regex("[A-Za-z0-9_.]+")
    var scopeAvailable = false
    val scoped = linkedSetOf<String>()
    val running = linkedMapOf<String, Set<Int>>()
    val vectorJson = output.substringAfter("VECTOR_JSON_BEGIN\n", "")
        .substringBefore("\nVECTOR_JSON_END", "")
    if (Regex("\\\"success\\\"\\s*:\\s*true").containsMatchIn(vectorJson)) {
        scopeAvailable = true
        val packageField = Regex("\\\"APP_PACKAGE\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"")
        val userField = Regex("\\\"USER_ID\\\"\\s*:\\s*(-?\\d+)")
        Regex("\\{[^{}]*}").findAll(vectorJson).forEach { objectMatch ->
            val row = objectMatch.value
            val pkg = packageField.find(row)?.groupValues?.get(1)
            val rowUser = userField.find(row)?.groupValues?.get(1)?.toIntOrNull()
            if (pkg != null && rowUser == userId && packagePattern.matches(pkg)) {
                scoped.add(pkg)
            }
        }
    }
    output.lineSequence().forEach { line ->
        when {
            line == "SCOPE_STATUS|AVAILABLE" -> scopeAvailable = true
            line.startsWith("SCOPE|") -> line.substringAfter('|')
                .takeIf { packagePattern.matches(it) }?.let(scoped::add)
            line.startsWith("PID|") -> {
                val parts = line.split('|', limit = 3)
                if (parts.size == 3 && packagePattern.matches(parts[1])) {
                    running[parts[1]] = parts[2].split(' ')
                        .mapNotNull(String::toIntOrNull).filter { it > 0 }.toSet()
                }
            }
        }
    }
    return XposedRuntimeSnapshot(scopeAvailable, scoped, running)
}

/** Read-only, root-assisted view of LSPosed/Vector scope and live target processes. */
object XposedRuntimeInspector {
    private const val MODULE_PACKAGE = "com.waenhancer"
    private val validPackage = Regex("[A-Za-z0-9_.]+")

    @Volatile
    private var cachedSnapshot: XposedRuntimeSnapshot? = null

    fun cached(): XposedRuntimeSnapshot? = cachedSnapshot

    fun inspect(context: Context, packageNames: Collection<String>, userId: Int): XposedRuntimeSnapshot? {
        val packages = packageNames.filter { validPackage.matches(it) }.distinct()
        val snapshotFile = File(context.cacheDir, "xposed_scope_snapshot.db")
        snapshotFile.delete()
        File(snapshotFile.path + "-wal").delete()
        File(snapshotFile.path + "-shm").delete()
        val destination = shellQuote(snapshotFile.absolutePath)
        val cacheDirectory = shellQuote(context.cacheDir.absolutePath)
        val appUid = android.os.Process.myUid()
        val appGid = appUid
        val pidCommands = packages.joinToString("\n") { pkg ->
            "pids=\$(pidof $pkg 2>/dev/null || true); printf 'PID|$pkg|%s\\n' \"\$pids\""
        }
        val sql = "SELECT 'SCOPE|' || s.app_pkg_name FROM scope s " +
                "JOIN modules m ON m.mid=s.mid WHERE m.module_pkg_name='$MODULE_PACKAGE' " +
                "AND m.enabled=1 AND s.user_id=$userId;"
        val command = """
            scope_done=0
            for cli in /data/adb/modules/zygisk_vector/cli /data/adb/modules/vector/cli; do
              if [ -x "${'$'}cli" ]; then
                vector_json=${'$'}("${'$'}cli" --json scope ls $MODULE_PACKAGE 2>/dev/null || true)
                if [ -n "${'$'}vector_json" ]; then
                  printf 'VECTOR_JSON_BEGIN\\n%s\\nVECTOR_JSON_END\\n' "${'$'}vector_json"
                  scope_done=1
                  break
                fi
              fi
            done
            db=''
            for candidate in /data/adb/lspd/config/modules_config.db /data/adb/riru/modules/riru_lsposed/config/modules_config.db; do
              if [ -f "${'$'}candidate" ]; then db="${'$'}candidate"; break; fi
            done
            sqlite=''
            for candidate in /data/adb/lspd/bin/sqlite3 /system/bin/sqlite3 /system/xbin/sqlite3; do
              if [ -x "${'$'}candidate" ]; then sqlite="${'$'}candidate"; break; fi
            done
            if [ -z "${'$'}sqlite" ]; then sqlite=${'$'}(command -v sqlite3 2>/dev/null || true); fi
            if [ "${'$'}scope_done" -eq 0 ] && [ -n "${'$'}db" ] && [ -n "${'$'}sqlite" ]; then
              if "${'$'}sqlite" "${'$'}db" "PRAGMA query_only=ON; $sql"; then
                printf 'SCOPE_STATUS|AVAILABLE\\n'
              else
                printf 'SCOPE_STATUS|UNAVAILABLE\\n'
              fi
            elif [ "${'$'}scope_done" -eq 0 ] && [ -n "${'$'}db" ]; then
              if cp "${'$'}db" $destination; then
                [ ! -f "${'$'}db-wal" ] || cp "${'$'}db-wal" ${destination}-wal
                [ ! -f "${'$'}db-shm" ] || cp "${'$'}db-shm" ${destination}-shm
                chown $appUid:$appGid $destination ${destination}-wal ${destination}-shm 2>/dev/null || true
                chmod 600 $destination ${destination}-wal ${destination}-shm 2>/dev/null || true
                chcon --reference=$cacheDirectory $destination ${destination}-wal ${destination}-shm 2>/dev/null || true
                printf 'SCOPE_COPY|READY\\n'
              else
                printf 'SCOPE_STATUS|UNAVAILABLE\\n'
              fi
            elif [ "${'$'}scope_done" -eq 0 ]; then
              printf 'SCOPE_STATUS|UNAVAILABLE\\n'
            fi
            $pidCommands
        """.trimIndent()

        val output = AppRestartHelper.runRootCommand(command) ?: return null
        var snapshot = parseXposedRuntimeSnapshot(output, userId)
        if (!snapshot.scopeAvailable && output.lineSequence().any { it == "SCOPE_COPY|READY" }) {
            readCopiedScope(snapshotFile, userId)?.let { scoped ->
                snapshot = snapshot.copy(scopeAvailable = true, scopedPackages = scoped)
            }
        }
        snapshotFile.delete()
        File(snapshotFile.path + "-wal").delete()
        File(snapshotFile.path + "-shm").delete()
        return snapshot.also { cachedSnapshot = it }
    }

    private fun readCopiedScope(databaseFile: File, userId: Int): Set<String>? = runCatching {
        SQLiteDatabase.openDatabase(
            databaseFile.absolutePath,
            null,
            SQLiteDatabase.OPEN_READONLY or SQLiteDatabase.NO_LOCALIZED_COLLATORS
        ).use { database ->
            database.rawQuery(
                "SELECT s.app_pkg_name FROM scope s JOIN modules m ON m.mid=s.mid " +
                        "WHERE m.module_pkg_name=? AND m.enabled=1 AND s.user_id=?",
                arrayOf(MODULE_PACKAGE, userId.toString())
            ).use { cursor ->
                buildSet {
                    while (cursor.moveToNext()) {
                        cursor.getString(0)?.takeIf { validPackage.matches(it) }?.let(::add)
                    }
                }
            }
        }
    }.getOrNull()

    private fun shellQuote(value: String): String = "'" + value.replace("'", "'\\''") + "'"
}
