package com.waenhancer.utils;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.content.res.Resources;
import android.os.LocaleList;
import java.util.IllegalFormatException;
import java.util.Locale;

/**
 * Resolves WAEX-owned display resources, including when code runs inside a host app.
 * Inputs are static resource IDs and display-only arguments, never host resource IDs.
 * Does not change the host's default locale or write to the preference bridge.
 */
public final class UiText {
    private static final String MODULE_PACKAGE = "com.waenhancer";
    private static volatile Source source;
    private static volatile Cached configured;

    private UiText() {}

    private static final class Source {
        final Context application;
        final Context module;
        final SharedPreferences preferences;
        Source(Context application, Context module, SharedPreferences preferences) {
            this.application = application;
            this.module = module;
            this.preferences = preferences;
        }
    }
    private static final class Cached {
        final Source source;
        final String tag;
        final int configurationHash;
        final Resources resources;
        Cached(Source source, String tag, int hash, Resources resources) {
            this.source = source;
            this.tag = tag;
            this.configurationHash = hash;
            this.resources = resources;
        }
    }

    /** Call once with an Application context and the existing read-only/public preferences. */
    public static synchronized void initialize(Context context, SharedPreferences preferences) {
        if (context == null) return;
        Context app = context.getApplicationContext();
        if (app == null) app = context;
        Context module = null;
        try {
            module = MODULE_PACKAGE.equals(app.getPackageName())
                    ? app : app.createPackageContext(MODULE_PACKAGE, 0);
            if (!MODULE_PACKAGE.equals(module.getPackageName())) module = null;
        } catch (Exception unavailable) {
            // A hidden/unavailable module must not crash the host. No resource IDs cross packages.
        }
        source = new Source(app, module, preferences);
        configured = null;
    }

    public static Locale displayLocale() {
        Source current = source;
        String code = "system";
        if (current != null && current.preferences != null) {
            try { code = current.preferences.getString("app_language", "system"); }
            catch (RuntimeException unreadable) { code = "system"; }
        }
        Locale system = Resources.getSystem().getConfiguration().getLocales().get(0);
        return DisplayLocalePolicy.resolve(code, system);
    }

    private static Resources resources(Locale locale) {
        Source current = source;
        if (current == null || current.module == null) return null;
        Configuration original = current.module.getResources().getConfiguration();
        int hash = original.hashCode();
        String tag = locale.toLanguageTag();
        Cached old = configured;
        if (old != null && old.source == current && old.configurationHash == hash
                && old.tag.equals(tag)) return old.resources;
        synchronized (UiText.class) {
            old = configured;
            if (old != null && old.source == current && old.configurationHash == hash
                    && old.tag.equals(tag)) return old.resources;
            Resources result;
            try {
                Configuration config = new Configuration(original);
                config.setLocales(new LocaleList(locale));
                result = current.module.createConfigurationContext(config).getResources();
            }
            catch (RuntimeException unavailable) { return null; }
            configured = new Cached(current, tag, hash, result);
            return result;
        }
    }

    /** The English fallback is a static source template; arguments are never translated. */
    public static String get(int resourceId, String englishFallback, Object... arguments) {
        Locale locale = displayLocale();
        Resources res = resources(locale);
        String template = englishFallback;
        if (res != null) {
            try {
                if (MODULE_PACKAGE.equals(res.getResourcePackageName(resourceId))) {
                    template = res.getString(resourceId);
                }
            } catch (Resources.NotFoundException missing) { /* Preserve diagnostic/display fallback. */ }
        }
        return format(template, englishFallback, locale, arguments);
    }

    public static String quantity(int resourceId, int count, String englishFallback, Object... arguments) {
        Locale locale = displayLocale();
        Resources res = resources(locale);
        String template = englishFallback;
        if (res != null) {
            try {
                if (MODULE_PACKAGE.equals(res.getResourcePackageName(resourceId))) {
                    template = res.getQuantityString(resourceId, count);
                }
            } catch (Resources.NotFoundException missing) { /* Do not crash during error feedback. */ }
        }
        return format(template, englishFallback, locale, arguments);
    }

    private static String format(String template, String fallback, Locale locale, Object[] arguments) {
        if (arguments == null || arguments.length == 0) return template;
        try { return String.format(locale, template, arguments); }
        catch (IllegalFormatException malformedTranslation) {
            try { return String.format(Locale.ENGLISH, fallback, arguments); }
            catch (IllegalFormatException malformedSource) { return fallback; }
        }
    }
}
