package com.waenhancer.utils

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import com.waenhancer.xposed.utils.AppRestartHelper
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.concurrent.atomic.AtomicReference

/**
 * Diagnostics utility for detecting Hide My Applist (HMA) activity and checking
 * whether any WhatsApp target package has configured rules hiding WAEX.
 *
 * Checks are heavy (requiring root file inspection / SQLite parsing), so results
 * are evaluated on demand or cached during app launch.
 */
object HmaDiagnostics {

    private const val HMA_ZYGISK_PATH = "/data/adb/modules/hma_oss_zygisk"
    private const val LSP_CONFIG_DB = "/data/adb/lspd/config/modules_config.db"
    private const val HMA_CONFIG_GLOB = "/data/misc/hide_my_applist*/config.json"
    private const val HMA_ALT_CONFIG = "/data/adb/hma/config.json"

    private val cachedResult = AtomicReference<HmaReport?>(null)

    enum class HmaState {
        CHECKING,
        NOT_ACTIVE,
        NOT_CONFIGURED,
        CLEAN,
        BLOCKING_TARGETS
    }

    data class TargetIsolationDetail(
        val packageName: String,
        val appName: String,
        val isBlocking: Boolean,
        val reason: String
    )

    data class HmaReport(
        val state: HmaState,
        val targetDetails: List<TargetIsolationDetail> = emptyList(),
        val blockedTargets: List<String> = emptyList(),
        val message: String? = null
    )

    fun cached(): HmaReport? = cachedResult.get()

    /**
     * Inspects HMA state and verifies if any target package in [targetPackages]
     * is configured to hide WAEX.
     */
    suspend fun checkHmaStatus(
        context: Context,
        targetPackages: Collection<String>,
        forceRefresh: Boolean = false
    ): HmaReport = withContext(Dispatchers.IO) {
        if (!forceRefresh) {
            cachedResult.get()?.let { return@withContext it }
        }

        val report = runCheck(context.applicationContext, targetPackages)
        cachedResult.set(report)
        report
    }

    private fun runCheck(context: Context, targetPackages: Collection<String>): HmaReport {
        if (!isHmaInstalledAndActive(context)) {
            return HmaReport(HmaState.NOT_ACTIVE)
        }

        // Read configuration file
        val configJson = readHmaConfigJson()
        if (configJson == null) {
            return HmaReport(HmaState.NOT_CONFIGURED)
        }

        val config = try {
            JSONObject(configJson)
        } catch (_: Exception) {
            return HmaReport(HmaState.NOT_CONFIGURED)
        }

        val templates = config.optJSONObject("templates") ?: JSONObject()
        val scope = config.optJSONObject("scope") ?: JSONObject()

        // Known module package identifiers to check for concealment
        val currentPackage = context.packageName
        val moduleSignatures = setOf(currentPackage, "com.waenhancer", "com.waenhancer.debug")

        // Packages to check: target packages passed in plus DeclaredWhatsAppTargets if targetPackages is empty
        val packagesToCheck = if (targetPackages.isNotEmpty()) {
            targetPackages.toSet()
        } else {
            DeclaredWhatsAppTargets.packages()
        }

        val details = mutableListOf<TargetIsolationDetail>()
        val blockedList = mutableListOf<String>()

        for (pkg in packagesToCheck) {
            val appLabel = resolveAppLabel(context, pkg)
            val scopeObj = scope.optJSONObject(pkg)
            if (scopeObj == null) {
                details.add(
                    TargetIsolationDetail(
                        packageName = pkg,
                        appName = appLabel,
                        isBlocking = false,
                        reason = "Not configured in HMA scope"
                    )
                )
                continue
            }

            val blockReason = checkScopeBlockReason(scopeObj, templates, moduleSignatures)
            if (blockReason != null) {
                blockedList.add(pkg)
                details.add(
                    TargetIsolationDetail(
                        packageName = pkg,
                        appName = appLabel,
                        isBlocking = true,
                        reason = blockReason
                    )
                )
            } else {
                details.add(
                    TargetIsolationDetail(
                        packageName = pkg,
                        appName = appLabel,
                        isBlocking = false,
                        reason = "Active in HMA, module visible"
                    )
                )
            }
        }

        return if (blockedList.isEmpty()) {
            HmaReport(HmaState.CLEAN, targetDetails = details)
        } else {
            HmaReport(HmaState.BLOCKING_TARGETS, targetDetails = details, blockedTargets = blockedList)
        }
    }

    private fun resolveAppLabel(context: Context, packageName: String): String {
        return try {
            val pm = context.packageManager
            val info = pm.getApplicationInfo(packageName, 0)
            pm.getApplicationLabel(info).toString()
        } catch (_: Exception) {
            when {
                packageName == "com.whatsapp" -> "WhatsApp"
                packageName == "com.whatsapp.w4b" -> "WhatsApp Business"
                else -> packageName
            }
        }
    }

    private fun isHmaInstalledAndActive(context: Context): Boolean {
        // 1. Zygisk variant check
        val zygiskCheck = AppRestartHelper.runRootCommand(
            "[ -d $HMA_ZYGISK_PATH ] && [ ! -f $HMA_ZYGISK_PATH/disable ] && echo active"
        )
        if (zygiskCheck?.contains("active") == true) {
            return true
        }

        // 2. LSPosed module database check
        val dbCheck = AppRestartHelper.runRootCommand("[ -f $LSP_CONFIG_DB ] && echo exists")
        if (dbCheck?.contains("exists") == true) {
            val cacheDir = context.cacheDir
            val cacheDb = File(cacheDir, "hma_lsposed_inspect.db")
            val walDb = File(cacheDir, "hma_lsposed_inspect.db-wal")
            val shmDb = File(cacheDir, "hma_lsposed_inspect.db-shm")

            listOf(cacheDb, walDb, shmDb).forEach { if (it.exists()) it.delete() }

            val copyCmd = "cp $LSP_CONFIG_DB ${cacheDb.absolutePath} 2>/dev/null; " +
                    "cp $LSP_CONFIG_DB-wal ${walDb.absolutePath} 2>/dev/null; " +
                    "cp $LSP_CONFIG_DB-shm ${shmDb.absolutePath} 2>/dev/null; " +
                    "chmod 666 ${cacheDb.absolutePath} ${walDb.absolutePath} ${shmDb.absolutePath} 2>/dev/null"
            AppRestartHelper.runRootCommand(copyCmd)

            if (cacheDb.exists()) {
                val found = isHmaEnabledInLspDb(cacheDb)
                listOf(cacheDb, walDb, shmDb).forEach { if (it.exists()) it.delete() }
                if (found) return true
            }
        }

        // 3. Check if HMA config file exists directly as an additional check
        val configExists = AppRestartHelper.runRootCommand(
            "[ -f $HMA_CONFIG_GLOB ] || [ -f $HMA_ALT_CONFIG ] && echo exists"
        )
        return configExists?.contains("exists") == true
    }

    private fun isHmaEnabledInLspDb(dbFile: File): Boolean {
        var db: SQLiteDatabase? = null
        return try {
            db = SQLiteDatabase.openDatabase(dbFile.absolutePath, null, SQLiteDatabase.OPEN_READONLY)
            val cursor = db.rawQuery(
                "SELECT 1 FROM modules WHERE module_pkg_name LIKE ? AND enabled = 1 LIMIT 1",
                arrayOf("%hidemyapplist%")
            )
            val exists = cursor.moveToFirst()
            cursor.close()
            exists
        } catch (_: Exception) {
            false
        } finally {
            db?.close()
        }
    }


    private fun readHmaConfigJson(): String? {
        val path = findHmaConfigPath() ?: return null
        val out = AppRestartHelper.runRootCommand("cat $path 2>/dev/null")
        if (!out.isNullOrBlank() && out.startsWith("{")) {
            return out
        }
        return null
    }

    private fun findHmaConfigPath(): String? {
        val cmd = "find /data/misc -maxdepth 2 -name 'config.json' -path '*/hide_my_applist*' 2>/dev/null; " +
                "[ -f $HMA_ALT_CONFIG ] && echo $HMA_ALT_CONFIG; true"
        val out = AppRestartHelper.runRootCommand(cmd) ?: return null
        return out.lines().map { it.trim() }.firstOrNull { it.isNotBlank() && it.endsWith("config.json") }
    }

    /**
     * Fixes HMA isolation settings for the specified [targetPackage] by removing
     * any blocking rules (such as 'xposed' preset or module package in extra lists / blacklist templates).
     */
    suspend fun fixTargetIsolation(context: Context, targetPackage: String): Boolean = withContext(Dispatchers.IO) {
        val configPath = findHmaConfigPath() ?: return@withContext false
        val currentJsonStr = AppRestartHelper.runRootCommand("cat $configPath 2>/dev/null") ?: return@withContext false
        if (!currentJsonStr.startsWith("{")) return@withContext false

        val moduleSignatures = setOf(
            context.packageName,
            "com.waenhancer",
            "com.waenhancer.debug"
        )

        try {
            val root = JSONObject(currentJsonStr)
            val scope = root.optJSONObject("scope") ?: return@withContext false
            val targetScope = scope.optJSONObject(targetPackage)

            if (targetScope != null) {
                // 1. Remove module package from extraAppList
                targetScope.optJSONArray("extraAppList")?.let { arr ->
                    val filtered = JSONArray()
                    for (i in 0 until arr.length()) {
                        val v = arr.optString(i)
                        if (v !in moduleSignatures) filtered.put(v)
                    }
                    targetScope.put("extraAppList", filtered)
                }

                // 2. Remove module package from extraOppositeAppList
                targetScope.optJSONArray("extraOppositeAppList")?.let { arr ->
                    val filtered = JSONArray()
                    for (i in 0 until arr.length()) {
                        val v = arr.optString(i)
                        if (v !in moduleSignatures) filtered.put(v)
                    }
                    targetScope.put("extraOppositeAppList", filtered)
                }

                // 3. Remove "xposed" preset from applyPresets
                targetScope.optJSONArray("applyPresets")?.let { arr ->
                    val filtered = JSONArray()
                    for (i in 0 until arr.length()) {
                        val v = arr.optString(i)
                        if (!v.equals("xposed", ignoreCase = true)) filtered.put(v)
                    }
                    targetScope.put("applyPresets", filtered)
                }
            }

            // 4. Remove module package from any blacklist templates
            val templates = root.optJSONObject("templates")
            if (templates != null) {
                val keys = templates.keys()
                while (keys.hasNext()) {
                    val key = keys.next()
                    val template = templates.optJSONObject(key) ?: continue
                    val isWhitelist = template.optBoolean("isWhitelist", false)
                    if (!isWhitelist) {
                        template.optJSONArray("appList")?.let { arr ->
                            val filtered = JSONArray()
                            for (i in 0 until arr.length()) {
                                val v = arr.optString(i)
                                if (v !in moduleSignatures) filtered.put(v)
                            }
                            template.put("appList", filtered)
                        }
                    }
                }
            }

            // Write modified JSON to temporary file in app cache then copy via root
            val tempFile = File(context.cacheDir, "hma_fix_${System.currentTimeMillis()}.json")
            tempFile.writeText(root.toString())

            val copyCmd = "cp ${tempFile.absolutePath} $configPath && " +
                    "chmod 600 $configPath && " +
                    "chown system:system $configPath; " +
                    "rm -f ${tempFile.absolutePath}"
            AppRestartHelper.runRootCommand(copyCmd)

            // Clear cached diagnostic result so next check reflects new state
            cachedResult.set(null)
            true
        } catch (_: Exception) {
            false
        }
    }

    private fun checkScopeBlockReason(
        scopeObj: JSONObject,
        templates: JSONObject,
        moduleSignatures: Set<String>
    ): String? {
        val useWhitelist = scopeObj.optBoolean("useWhitelist", false)
        val extraAppList = scopeObj.optJSONArray("extraAppList")?.toStringSet() ?: emptySet()
        val extraOppositeAppList = scopeObj.optJSONArray("extraOppositeAppList")?.toStringSet() ?: emptySet()

        if (useWhitelist) {
            // Whitelist mode: if module is in opposite list, it is hidden/blocked
            if (extraOppositeAppList.any { it in moduleSignatures }) {
                return "Hidden via Whitelist mode (in invisible apps list)"
            }
        } else {
            // Blacklist mode: if module is in extraAppList, it is hidden/blocked
            if (extraAppList.any { it in moduleSignatures }) {
                return "Hidden via Blacklist mode (in additional apps to hide)"
            }
        }

        // Check applied templates
        val appliedTemplates = scopeObj.optJSONArray("applyTemplates")?.toStringSet() ?: emptySet()
        for (templateName in appliedTemplates) {
            val template = templates.optJSONObject(templateName) ?: continue
            val isTemplateWhitelist = template.optBoolean("isWhitelist", false)
            val templateApps = template.optJSONArray("appList")?.toStringSet() ?: emptySet()

            if (!isTemplateWhitelist && templateApps.any { it in moduleSignatures }) {
                return "Hidden by blacklist template \"$templateName\""
            }
        }

        // Check presets (e.g. "xposed" preset hides all Xposed modules / manager)
        val appliedPresets = scopeObj.optJSONArray("applyPresets")?.toStringSet() ?: emptySet()
        if (appliedPresets.any { it.equals("xposed", ignoreCase = true) }) {
            return "Hidden by HMA \"xposed\" preset"
        }

        return null
    }

    private fun JSONArray.toStringSet(): Set<String> {
        val set = mutableSetOf<String>()
        for (i in 0 until length()) {
            optString(i, null)?.let { set.add(it) }
        }
        return set
    }
}
