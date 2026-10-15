package com.waenhancer.utils

import android.content.Context
import com.waenhancer.config.FeatureItem

object LocalizationHelper {

    fun getLocalizedFeatureTitle(context: Context, key: String): String {
        val resId = context.resources.getIdentifier("feat_${key}_title", "string", context.packageName)
        return if (resId != 0) context.getString(resId) else humanize(key)
    }

    fun getLocalizedFeatureDesc(context: Context, key: String): String {
        val resId = context.resources.getIdentifier("feat_${key}_desc", "string", context.packageName)
        return if (resId != 0) context.getString(resId) else ""
    }

    fun getLocalizedSectionTitle(context: Context, section: String): String {
        val resId = context.resources.getIdentifier("sec_$section", "string", context.packageName)
        return if (resId != 0) context.getString(resId) else humanize(section)
    }

    fun getTitle(context: Context, item: FeatureItem): String {
        return getLocalizedFeatureTitle(context, item.key)
    }

    fun getDesc(context: Context, item: FeatureItem): String {
        return getLocalizedFeatureDesc(context, item.key)
    }

    fun getSection(context: Context, item: FeatureItem): String {
        return getLocalizedSectionTitle(context, item.groupId)
    }

    fun getTabTitle(context: Context, tabId: String): String {
        val resId = context.resources.getIdentifier("catalog_tab_$tabId", "string", context.packageName)
        return if (resId != 0) context.getString(resId) else humanize(tabId)
    }

    private fun humanize(value: String): String = value
        .split('_', '-')
        .filter { it.isNotBlank() }
        .joinToString(" ") { it.replaceFirstChar(Char::uppercase) }
}
