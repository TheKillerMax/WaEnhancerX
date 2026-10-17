package com.waenhancer.xposed.features.privacy

import android.content.ContentValues
import android.content.Context
import android.content.SharedPreferences
import android.database.sqlite.SQLiteDatabase
import com.waenhancer.xposed.core.BaseFeature
import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XposedBridge
import de.robv.android.xposed.XposedHelpers

/**
 * Adjusts the persisted forwarding score without intercepting message flags or origin metadata.
 */
class HideForwardedTagHook(
    context: Context,
    classLoader: ClassLoader,
    prefs: SharedPreferences
) : BaseFeature(context, classLoader, prefs) {

    override val name: String = "Hide Forwarded Tag"

    override fun hook() {
        hookDatabaseInsertion()
    }

    private fun isFeatureEnabled(): Boolean {
        return try {
            if (prefs.contains("hide_forwarded_tag")) prefs.getBoolean("hide_forwarded_tag", false)
            else prefs.getBoolean("hidetag", false)
        } catch (_: RuntimeException) { false }
    }

    // Do not hook FMessage's numeric methods: the old selector resolved a flags OR setter.
    // Preserve message flags and origin metadata. This store-only path does not claim to hide
    // every already-rendered or in-memory forwarded label.
    private fun hookDatabaseInsertion() {
        try {
            val insertHooks = object : XC_MethodHook() {
                override fun beforeHookedMethod(param: MethodHookParam) {
                    if (!isFeatureEnabled()) return
                    val table = param.args[0] as? String ?: return
                    if (table == "message_forwarded") {
                        val values = param.args.getOrNull(2) as? ContentValues
                        val score = values?.get("forward_score")
                        if (score is Int && score > 0) values.put("forward_score", 0)
                    }
                }
            }

            XposedHelpers.findAndHookMethod(
                SQLiteDatabase::class.java,
                "insertWithOnConflict",
                String::class.java,
                String::class.java,
                ContentValues::class.java,
                Int::class.javaPrimitiveType,
                insertHooks
            )

            XposedHelpers.findAndHookMethod(
                SQLiteDatabase::class.java,
                "insert",
                String::class.java,
                String::class.java,
                ContentValues::class.java,
                insertHooks
            )

            XposedHelpers.findAndHookMethod(
                SQLiteDatabase::class.java,
                "insertOrThrow",
                String::class.java,
                String::class.java,
                ContentValues::class.java,
                insertHooks
            )
        } catch (t: Throwable) {
            XposedBridge.log("[WAEX] Error hooking SQLite message_forwarded: ${t.javaClass.simpleName}")
        }
    }

}
