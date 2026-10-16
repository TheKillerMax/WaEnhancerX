package com.waenhancer.utils

import android.content.Context
import android.content.res.Configuration
import android.os.Build
import android.os.LocaleList
import java.util.Locale
import android.content.res.Resources
import com.waenhancer.config.PreferenceStores

object LocaleHelper {

    const val PREF_APP_LANGUAGE = "app_language"

    val SUPPORTED_LANGUAGES = listOf(
        LanguageOption("system", "Follow System", "System Default"),
        LanguageOption("en", "English", "English"),
        LanguageOption("zh-CN", "Chinese (Simplified)", "简体中文"),
        LanguageOption("es", "Spanish", "Español"),
        LanguageOption("ar", "Arabic", "العربية"),
        LanguageOption("pt", "Portuguese", "Português"),
        LanguageOption("in", "Indonesian", "Bahasa Indonesia"),
        LanguageOption("ru", "Russian", "Русский"),
        LanguageOption("tr", "Turkish", "Türkçe"),
        LanguageOption("hi", "Hindi", "हिन्दी"),
        LanguageOption("ur", "Urdu", "اردو"),
        LanguageOption("de", "German", "Deutsch"),
        LanguageOption("fr", "French", "Français")
    )

    fun getSelectedLanguageCode(context: Context): String {
        val prefs = PreferenceStores.publicStore(context)
        return prefs.getString(PREF_APP_LANGUAGE, "system") ?: "system"
    }

    fun getLanguageDisplayName(code: String): String {
        val opt = SUPPORTED_LANGUAGES.find { it.code == code }
        return opt?.nativeName ?: "Follow System"
    }

    fun applyLanguage(context: Context, langCode: String) {
        val prefs = PreferenceStores.publicStore(context)
        prefs.edit().putString(PREF_APP_LANGUAGE, langCode).apply()

        val locale = if (langCode == "system") {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                Resources.getSystem().configuration.locales[0]
            } else {
                @Suppress("DEPRECATION")
                Resources.getSystem().configuration.locale
            }
        } else if (langCode == "in") {
            Locale("in", "ID")
        } else {
            Locale.forLanguageTag(langCode)
        }
        Locale.setDefault(locale)
    }

    fun wrapContext(context: Context): Context {
        val langCode = getSelectedLanguageCode(context)
        if (langCode == "system") return context

        val locale = if (langCode == "in") Locale("in", "ID") else Locale.forLanguageTag(langCode)
        Locale.setDefault(locale)

        val config = Configuration(context.resources.configuration)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            config.setLocales(LocaleList(locale))
            return context.createConfigurationContext(config)
        } else {
            @Suppress("DEPRECATION")
            config.locale = locale
            @Suppress("DEPRECATION")
            context.resources.updateConfiguration(config, context.resources.displayMetrics)
            return context
        }
    }

    data class LanguageOption(
        val code: String,
        val englishName: String,
        val nativeName: String
    )
}
