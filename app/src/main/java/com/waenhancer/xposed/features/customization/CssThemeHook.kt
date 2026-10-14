package com.waenhancer.xposed.features.customization

import android.app.Activity
import android.content.Context
import android.content.SharedPreferences
import android.graphics.Color
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import com.waenhancer.xposed.core.BaseFeature
import com.waenhancer.xposed.utils.ActivityTracker
import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XposedBridge
import de.robv.android.xposed.XposedHelpers

/** Applies supported ID-based CSS rules to WhatsApp views. */
class CssThemeHook(
    context: Context,
    classLoader: ClassLoader,
    prefs: SharedPreferences
) : BaseFeature(context, classLoader, prefs) {

    override val name: String = "Custom Theme CSS"
    private val rules = HashMap<Int, Map<String, String>>()
    private val forcedVisibility = HashMap<Int, Int>()

    override fun hook() {
        reloadRules()
        if (rules.isEmpty()) return

        XposedHelpers.findAndHookMethod(
            View::class.java,
            "onAttachedToWindow",
            object : XC_MethodHook() {
                override fun afterHookedMethod(param: MethodHookParam) {
                    applyRule(param.thisObject as? View ?: return)
                }
            }
        )
        XposedHelpers.findAndHookMethod(
            View::class.java,
            "setVisibility",
            Int::class.javaPrimitiveType,
            object : XC_MethodHook() {
                override fun beforeHookedMethod(param: MethodHookParam) {
                    val view = param.thisObject as? View ?: return
                    forcedVisibility[view.id]?.let { param.args[0] = it }
                }
            }
        )
        ActivityTracker.addListener { activity ->
            Handler(Looper.getMainLooper()).post { applyRecursively(activity.window?.decorView) }
        }
        prefs.registerOnSharedPreferenceChangeListener { _, key ->
            if (key == "css_theme") {
                reloadRules()
                Handler(Looper.getMainLooper()).post {
                    applyRecursively(ActivityTracker.getCurrentActivity()?.window?.decorView)
                }
            }
        }
    }

    private fun reloadRules() {
        rules.clear()
        forcedVisibility.clear()
        val css = prefs.getString("css_theme", "").orEmpty()
        RULE.findAll(css).forEach { match ->
            val resourceName = match.groupValues[1]
            val id = if (resourceName.startsWith("android_")) {
                runCatching {
                    android.R.id::class.java.getField(resourceName.removePrefix("android_")).getInt(null)
                }.getOrDefault(0)
            } else {
                context.resources.getIdentifier(resourceName, "id", context.packageName)
            }
            if (id == 0) return@forEach
            val declarations = linkedMapOf<String, String>()
            match.groupValues[2].split(';').forEach { raw ->
                val separator = raw.indexOf(':')
                if (separator > 0) {
                    declarations[raw.substring(0, separator).trim().lowercase()] =
                        raw.substring(separator + 1).trim().removeSuffix("!important").trim()
                }
            }
            if (declarations.isNotEmpty()) rules[id] = declarations
        }
    }

    private fun applyRecursively(view: View?) {
        if (view == null) return
        applyRule(view)
        if (view is ViewGroup) for (index in 0 until view.childCount) applyRecursively(view.getChildAt(index))
    }

    private fun applyRule(view: View) {
        val declarations = rules[view.id] ?: return
        declarations["display"]?.let { value ->
            val visibility = when (value.lowercase()) {
                "none" -> View.GONE
                "invisible" -> View.INVISIBLE
                "block", "visible" -> View.VISIBLE
                else -> null
            }
            if (visibility != null) {
                forcedVisibility[view.id] = visibility
                view.visibility = visibility
            }
        }
        declarations["opacity"]?.toFloatOrNull()?.let { view.alpha = it.coerceIn(0f, 1f) }
        declarations["alpha"]?.toFloatOrNull()?.let { view.alpha = it.coerceIn(0f, 1f) }
        parseColor(declarations["background-color"])?.let(view::setBackgroundColor)
        if (view is TextView) {
            parseColor(declarations["color"])?.let(view::setTextColor)
            declarations["font-size"]?.replace(Regex("(?i)(sp|px|dp)$"), "")
                ?.trim()?.toFloatOrNull()?.let { view.textSize = it }
        }
    }

    private fun parseColor(value: String?): Int? = value?.let {
        runCatching { Color.parseColor(it) }.getOrNull()
    }

    private companion object {
        val RULE = Regex("(?s)#([A-Za-z0-9_]+)\\s*\\{([^}]*)}")
    }
}
