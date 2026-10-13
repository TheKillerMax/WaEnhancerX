package com.waenhancer.utils

import android.content.Context
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.drawable.BitmapDrawable
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import com.waenhancer.app.R
import com.waenhancer.config.PreferenceStores
import com.waenhancer.xposed.utils.ModuleStatus
import org.json.JSONArray

data class InjectedHookItem(
    val name: String,
    val className: String,
    val category: String,
    val status: String,
    val error: String? = null
)

data class HookedAppInfo(
    val packageName: String,
    val appName: String,
    val versionName: String,
    val isInstalled: Boolean,
    val isHooked: Boolean,
    val injectedHooks: List<InjectedHookItem> = emptyList(),
    val lastActiveTime: Long = 0L,
    val scopeState: RuntimeScopeState = RuntimeScopeState.NOT_DETECTED,
    val runtimeStatus: String = "NOT_DETECTED",
    val bridgeStatus: String = "NOT_REPORTED",
    val initializationError: String? = null
)

enum class RuntimeScopeState { ACTIVE_THIS_BOOT, PREVIOUSLY_ACTIVE, NOT_DETECTED }

internal fun resolveRuntimeScopeState(
    isModuleActive: Boolean,
    wasEverHooked: Boolean,
    recordedBoot: Int,
    currentBoot: Int,
    lastActiveTime: Long,
    verificationStartedAt: Long
): RuntimeScopeState = when {
    isModuleActive && wasEverHooked && recordedBoot == currentBoot &&
            lastActiveTime >= verificationStartedAt -> RuntimeScopeState.ACTIVE_THIS_BOOT
    wasEverHooked -> RuntimeScopeState.PREVIOUSLY_ACTIVE
    else -> RuntimeScopeState.NOT_DETECTED
}

object WhatsAppPackageDetector {

    private const val MODULE_PACKAGE = "com.waenhancer"

    /**
     * A scope manager cannot expose one portable, trustworthy "is package scoped" API.
     * Require target-process evidence newer than the last time WAEX left the foreground;
     * otherwise an already-running process can retain old hooks after its scope is removed.
     */
    @Volatile
    private var scopeVerificationStartedAt = System.currentTimeMillis()

    @JvmStatic
    fun startNewScopeVerification() {
        scopeVerificationStartedAt = System.currentTimeMillis()
    }

    /**
     * Dynamically reads supported WhatsApp packages & clones from arrays.xml.
     */
    @JvmStatic
    fun getSupportedPackages(context: Context?): Set<String> {
        val packages = LinkedHashSet<String>()
        if (context != null) {
            try {
                val moduleContext = if (context.packageName == MODULE_PACKAGE) {
                    context
                } else {
                    try {
                        context.createPackageContext(MODULE_PACKAGE, Context.CONTEXT_IGNORE_SECURITY)
                    } catch (_: Throwable) {
                        context
                    }
                }
                val resId = moduleContext.resources.getIdentifier("xposed_scope", "array", MODULE_PACKAGE)
                if (resId != 0) {
                    packages.addAll(moduleContext.resources.getStringArray(resId))
                } else {
                    packages.addAll(context.resources.getStringArray(R.array.xposed_scope))
                }
                packages.remove(MODULE_PACKAGE)
            } catch (_: Throwable) {}
        }
        return packages
    }

    /**
     * Returns true if a package name matches any supported WhatsApp package from arrays.xml
     * or WhatsApp clone pattern.
     */
    @JvmStatic
    fun isWhatsAppPackageName(context: Context?, packageName: String?): Boolean {
        if (packageName.isNullOrBlank()) return false
        val pkg = packageName.lowercase()
        if (pkg == MODULE_PACKAGE || pkg.startsWith("android") || pkg.startsWith("com.android") || pkg.startsWith("com.google.android")) {
            return false
        }

        // 1. Direct match from arrays.xml
        val supportedPackages = getSupportedPackages(context)
        if (supportedPackages.contains(pkg)) {
            return true
        }

        // 2. Pattern recognition for custom clones & dual app wrappers
        return pkg.contains("whatsapp") ||
                pkg.contains("w4b") ||
                pkg.contains("gbwa") ||
                pkg.contains("fmwa") ||
                pkg.contains("yowa") ||
                pkg.contains("nowha") ||
                pkg.contains("aerow") ||
                pkg.contains("delight") ||
                pkg.contains("wtsapp") ||
                pkg.contains("wago") ||
                pkg.contains("ymwa") ||
                pkg.endsWith(".litex")
    }

    @JvmStatic
    fun isWhatsAppPackageName(packageName: String?): Boolean {
        return isWhatsAppPackageName(null, packageName)
    }

    /**
     * Registers a hooked WhatsApp package when Xposed injects into it at runtime.
     */
    @JvmStatic
    fun registerHookedPackage(context: Context, packageName: String) {
        // 1. Cross-process IPC to WAEX HookProvider
        try {
            val uri = Uri.parse("content://com.waenhancer.hookprovider")
            val extras = Bundle().apply {
                putString("package", packageName)
                putLong("timestamp", System.currentTimeMillis())
                putInt("boot_count", currentBootCount(context))
            }
            context.contentResolver.call(uri, "register_hooked_package", packageName, extras)
        } catch (_: Throwable) {}

        // 2. Broadcast to WAEX process
        try {
            val intent = Intent("com.waenhancer.ACTION_TARGET_APP_ACTIVE").apply {
                setPackage("com.waenhancer")
                putExtra("PACKAGE", packageName)
                putExtra("TIMESTAMP", System.currentTimeMillis())
            }
            context.sendBroadcast(intent)
        } catch (_: Throwable) {}

        // 3. Local fallback
        try {
            val prefs = PreferenceStores.publicStore(context)
            val existing = LinkedHashSet(prefs.getStringSet("hooked_whatsapp_packages", emptySet()) ?: emptySet())
            if (!existing.contains(packageName)) {
                existing.add(packageName)
                prefs.edit()
                    .putStringSet("hooked_whatsapp_packages", existing)
                    .apply()
            }
        } catch (_: Throwable) {}
    }

    /** Reports sanitized runtime health from a package that is executing WAEX hooks. */
    @JvmStatic
    fun reportRuntimeHealth(
        context: Context,
        packageName: String,
        runtimeStatus: String,
        bridgeStatus: String,
        error: String? = null
    ) {
        var accepted = false
        try {
            val extras = Bundle().apply {
                putString("package", packageName)
                putString("runtime_status", runtimeStatus)
                putString("bridge_status", bridgeStatus)
                putString("error", error)
                putLong("timestamp", System.currentTimeMillis())
                putInt("boot_count", currentBootCount(context))
            }
            accepted = context.contentResolver.call(
                Uri.parse("content://com.waenhancer.hookprovider"),
                "report_runtime_health",
                packageName,
                extras
            )?.getBoolean("success", false) == true
        } catch (_: Throwable) {}

        // Wake the dashboard when fresh runtime evidence arrives. This is also what makes an
        // already-running, genuinely injected target recover after the manager starts a new
        // verification window; users do not have to reopen either app to refresh the card.
        if (accepted) {
            try {
                context.sendBroadcast(Intent("com.waenhancer.ACTION_TARGET_APP_ACTIVE").apply {
                    setPackage(MODULE_PACKAGE)
                    putExtra("PACKAGE", packageName)
                    putExtra("TIMESTAMP", System.currentTimeMillis())
                })
            } catch (_: Throwable) {}
        }
    }

    @JvmStatic
    fun currentBootCount(context: Context): Int = runCatching {
        Settings.Global.getInt(context.contentResolver, Settings.Global.BOOT_COUNT)
    }.getOrElse {
        runCatching { java.io.File("/proc/sys/kernel/random/boot_id").readText().trim().hashCode() }
            .getOrDefault(-1)
    }

    /**
     * Retrieves the list of injected hooks parsed from cached JSON in HookProvider / SharedPreferences.
     */
    @JvmStatic
    fun getInjectedHooks(context: Context, packageName: String): List<InjectedHookItem> {
        val hooks = mutableListOf<InjectedHookItem>()
        try {
            val prefs = PreferenceStores.publicStore(context)
            val jsonStr = prefs.getString("injected_hooks_$packageName", null) ?: return emptyList()
            val array = JSONArray(jsonStr)
            for (i in 0 until array.length()) {
                val obj = array.getJSONObject(i)
                hooks.add(
                    InjectedHookItem(
                        name = obj.optString("name", "Unknown Feature"),
                        className = obj.optString("className", ""),
                        category = obj.optString("category", "General"),
                        status = obj.optString("status", "ACTIVE"),
                        error = if (obj.has("error")) obj.optString("error") else null
                    )
                )
            }
        } catch (_: Throwable) {}
        return hooks
    }

    /**
     * Loads the App Icon as an ImageBitmap safely for Compose.
     */
    @JvmStatic
    fun getAppIcon(context: Context, packageName: String): ImageBitmap? {
        return try {
            val drawable = context.packageManager.getApplicationIcon(packageName)
            if (drawable is BitmapDrawable && drawable.bitmap != null) {
                drawable.bitmap.asImageBitmap()
            } else {
                val width = if (drawable.intrinsicWidth > 0) drawable.intrinsicWidth else 96
                val height = if (drawable.intrinsicHeight > 0) drawable.intrinsicHeight else 96
                val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
                val canvas = Canvas(bitmap)
                drawable.setBounds(0, 0, canvas.width, canvas.height)
                drawable.draw(canvas)
                bitmap.asImageBitmap()
            }
        } catch (_: Throwable) {
            null
        }
    }

    /**
     * Discovers all installed and active WhatsApp-based applications on the device.
     */
    @JvmStatic
    fun detectWhatsAppApps(context: Context): List<HookedAppInfo> {
        val pm = context.packageManager
        val discoveredPackages = LinkedHashSet<String>()

        // 1. Read dynamically from arrays.xml
        discoveredPackages.addAll(getSupportedPackages(context))

        val isGlobalModuleActive = ModuleStatus.isModuleActive()

        // 2. Read packages that have been hooked by Xposed runtime
        var hookedSet: Set<String>? = null
        val prefs = PreferenceStores.publicStore(context)
        try {
            hookedSet = prefs.getStringSet("hooked_whatsapp_packages", null)
            if (hookedSet != null) {
                discoveredPackages.addAll(hookedSet)
            }
        } catch (_: Throwable) {}

        // 3. Scan installed apps for any additional WhatsApp clones
        try {
            val installedApps: List<ApplicationInfo> = pm.getInstalledApplications(PackageManager.GET_META_DATA)
            for (app in installedApps) {
                if (isWhatsAppPackageName(context, app.packageName)) {
                    discoveredPackages.add(app.packageName)
                }
            }
        } catch (_: Throwable) {}

        discoveredPackages.remove(MODULE_PACKAGE)

        val result = mutableListOf<HookedAppInfo>()

        for (pkg in discoveredPackages) {
            try {
                val pInfo = pm.getPackageInfo(pkg, 0)
                val label = pm.getApplicationLabel(pInfo.applicationInfo ?: continue).toString()
                val friendlyName = when {
                    label.isNotBlank() && label != pkg -> label
                    pkg == "com.whatsapp" -> "WhatsApp"
                    pkg == "com.whatsapp.w4b" -> "WhatsApp Business"
                    pkg == "com.gbwhatsapp" -> "GBWhatsApp"
                    pkg == "com.fmwhatsapp" -> "FMWhatsApp"
                    pkg == "com.yowhatsapp" || pkg == "com.yowa" -> "YoWhatsApp"
                    pkg == "com.aerowtsapp" || pkg == "com.aero" -> "Aero WhatsApp"
                    pkg == "com.delta" -> "Delta WhatsApp"
                    pkg == "com.ultra" -> "Ultra WhatsApp"
                    pkg == "com.delight" -> "Delight WhatsApp"
                    pkg == "com.ymwhatsapp" -> "YMWhatsApp"
                    pkg == "com.nowha" || pkg == "com.nowha2" -> "NO-WA"
                    pkg.contains("litex") -> "WhatsApp LiteX"
                    else -> "WhatsApp ($pkg)"
                }

                val lastActiveTime = prefs.getLong("last_active_$pkg", 0L)
                val recordedBoot = prefs.getInt("runtime_boot_$pkg", Int.MIN_VALUE)
                val currentBoot = currentBootCount(context)
                val wasEverHooked = hookedSet?.contains(pkg) == true || lastActiveTime > 0L
                val scopeState = resolveRuntimeScopeState(
                    isModuleActive = isGlobalModuleActive,
                    wasEverHooked = wasEverHooked,
                    recordedBoot = recordedBoot,
                    currentBoot = currentBoot,
                    lastActiveTime = lastActiveTime,
                    verificationStartedAt = scopeVerificationStartedAt
                )
                val activeThisBoot = scopeState == RuntimeScopeState.ACTIVE_THIS_BOOT
                val injectedHooks = if (activeThisBoot) getInjectedHooks(context, pkg) else emptyList()

                result.add(
                    HookedAppInfo(
                        packageName = pkg,
                        appName = friendlyName,
                        versionName = "v${pInfo.versionName ?: "Unknown"}",
                        isInstalled = true,
                        isHooked = activeThisBoot,
                        injectedHooks = injectedHooks,
                        lastActiveTime = lastActiveTime,
                        scopeState = scopeState,
                        runtimeStatus = prefs.getString("runtime_status_$pkg", "NOT_DETECTED") ?: "NOT_DETECTED",
                        bridgeStatus = prefs.getString("bridge_status_$pkg", "NOT_REPORTED") ?: "NOT_REPORTED",
                        initializationError = prefs.getString("runtime_error_$pkg", null)
                    )
                )
            } catch (e: PackageManager.NameNotFoundException) {
                // Only list standard WPP / Business if uninstalled as placeholders if no apps are installed
                if (pkg == "com.whatsapp" || pkg == "com.whatsapp.w4b") {
                    val name = if (pkg == "com.whatsapp") "WhatsApp" else "WhatsApp Business"
                    result.add(
                        HookedAppInfo(
                            packageName = pkg,
                            appName = name,
                            versionName = "Not Installed",
                            isInstalled = false,
                            isHooked = false,
                            injectedHooks = emptyList(),
                            lastActiveTime = 0L
                        )
                    )
                }
            }
        }

        // Filter out uninstalled placeholders if at least one app is installed
        val installedCount = result.count { it.isInstalled }
        val visible = if (installedCount > 0) {
            result.filter { it.isInstalled }
        } else {
            result
        }
        return visible.sortedWith(
            compareBy<HookedAppInfo> {
                when (it.scopeState) {
                    RuntimeScopeState.ACTIVE_THIS_BOOT -> 0
                    RuntimeScopeState.PREVIOUSLY_ACTIVE -> 1
                    RuntimeScopeState.NOT_DETECTED -> 2
                }
            }.thenBy { it.appName.lowercase() }
        )
    }
}
