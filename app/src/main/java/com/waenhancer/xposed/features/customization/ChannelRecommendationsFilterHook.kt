package com.waenhancer.xposed.features.customization

import android.content.Context
import android.content.SharedPreferences
import android.view.View
import com.waenhancer.xposed.core.BaseFeature
import com.waenhancer.xposed.core.ViewHookDispatcher
import com.waenhancer.xposed.core.devkit.DexSearchEngine
import com.waenhancer.xposed.utils.ViewClassSelector
import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XposedBridge
import org.luckypray.dexkit.query.FindClass
import org.luckypray.dexkit.query.enums.StringMatchType
import org.luckypray.dexkit.query.matchers.ClassMatcher

/**
 * Channel Recommendations Filter Hook.
 * Automatically hides newsletter/channel recommendations and cleans up the updates tab.
 */
class ChannelRecommendationsFilterHook(
    context: Context,
    classLoader: ClassLoader,
    prefs: SharedPreferences
) : BaseFeature(context, classLoader, prefs) {

    override val name: String
        get() = "Channel Recommendations Filter"

    override fun hook() {
        if (!isEnabled("channels_enhancements", false)) return

        val recClass = DexSearchEngine.getInstance().findClassWithCache(
            context,
            classLoader,
            "waex_channel_rec_view_class_v2"
        ) { bridge, loader ->
            val candidates = bridge.findClass(
                FindClass.create().matcher(
                    ClassMatcher.create().addUsingString("hasNewsletterSubscriptions", StringMatchType.Contains)
                )
            ).map { it.getInstance(loader) }
            ViewClassSelector.uniqueView(candidates)
        }

        if (recClass == null || !View::class.java.isAssignableFrom(recClass)) {
            throw IllegalStateException("Channel recommendation View contract unavailable")
        }
        // Host binding can restore visibility after construction. Use the shared
        // owner-scoped dispatcher so BaseFeature.unhookAll also removes this rule.
        val visibilityMask = View.INVISIBLE or View.GONE
        ViewHookDispatcher.onSetFlags(this) { view, flags, mask ->
            if (recClass.isInstance(view) && (mask and visibilityMask) == visibilityMask &&
                isEnabled("channels_enhancements", false)) {
                (flags and visibilityMask.inv()) or View.GONE
            } else flags
        }
        XposedBridge.hookAllConstructors(recClass, object : XC_MethodHook() {
            override fun afterHookedMethod(param: MethodHookParam) {
                if (!isEnabled("channels_enhancements", false)) return
                val view = param.thisObject as? View ?: return
                view.visibility = View.GONE
            }
        })
    }
}
