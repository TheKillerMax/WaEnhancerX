package com.waenhancer.utils

import android.content.Context

object LocalizationHelper {

    fun getLocalizedFeatureTitle(context: Context, key: String, fallback: String): String {
        val resId = context.resources.getIdentifier("feat_${key}_title", "string", context.packageName)
        return if (resId != 0) context.getString(resId) else fallback
    }

    fun getLocalizedFeatureDesc(context: Context, key: String, fallback: String): String {
        val resId = context.resources.getIdentifier("feat_${key}_desc", "string", context.packageName)
        return if (resId != 0) context.getString(resId) else fallback
    }

    fun getLocalizedSectionTitle(context: Context, section: String): String {
        val normalized = "sec_" + section.lowercase()
            .replace("&", "")
            .replace("-", "_")
            .split("\\s+".toRegex())
            .filter { it.isNotEmpty() }
            .joinToString("_")
        val resId = context.resources.getIdentifier(normalized, "string", context.packageName)
        return if (resId != 0) context.getString(resId) else section
    }
}
