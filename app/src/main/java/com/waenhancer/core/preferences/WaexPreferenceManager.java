package com.waenhancer.core.preferences;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.Uri;
import java.io.InputStream;
import java.io.OutputStream;
import com.waenhancer.config.PreferenceSchema;
import com.waenhancer.config.PreferenceStores;
import dagger.hilt.android.qualifiers.ApplicationContext;
import javax.inject.Inject;
import javax.inject.Singleton;

@Singleton
public final class WaexPreferenceManager {

    private final Context context;

    @Inject
    public WaexPreferenceManager(@ApplicationContext Context context) {
        this.context = context;
    }

    private SharedPreferences getStore(String key) {
        return PreferenceStores.storeFor(context, key);
    }

    private boolean isPublicStore(String key) {
        PreferenceSchema.Entry entry = PreferenceSchema.entry(key);
        return entry == null || entry.store == PreferenceSchema.Store.PUBLIC;
    }

    public boolean getBoolean(String key, boolean defaultValue) {
        try {
            return getStore(key).getBoolean(key, defaultValue);
        } catch (ClassCastException e) {
            try {
                Object allVal = getStore(key).getAll().get(key);
                if (allVal instanceof Boolean) {
                    return (Boolean) allVal;
                } else if (allVal instanceof String) {
                    String s = (String) allVal;
                    return "true".equalsIgnoreCase(s) || "1".equals(s);
                } else if (allVal instanceof Number) {
                    return ((Number) allVal).intValue() != 0;
                }
                return defaultValue;
            } catch (Throwable ignored) {
                return defaultValue;
            }
        }
    }

    private static final Uri PREFS_URI = Uri.parse("content://com.waenhancer.hookprovider/preferences");

    public void putBoolean(String key, boolean value) {
        getStore(key).edit().putBoolean(key, value).commit();
        if (isPublicStore(key)) {
            fixFilePermissions();
            notifyChange();
        }
    }

    /**
     * Persist related public Boolean settings as a single transaction and notify
     * injected processes once. Reject invalid/private keys before any mutation.
     * A false result means the caller must not optimistically update the UI.
     */
    public boolean putBooleans(java.util.Map<String, Boolean> values) {
        if (values == null) return false;
        try {
            // Snapshot once: validation and commit must see the same set of keys.
            java.util.Map<String, Boolean> batch = new java.util.LinkedHashMap<>(values);
            if (batch.isEmpty()) return false;
            for (java.util.Map.Entry<String, Boolean> change : batch.entrySet()) {
                String key = change.getKey();
                if (key == null || key.isEmpty() || change.getValue() == null) return false;
                PreferenceSchema.Entry definition = PreferenceSchema.entry(key);
                if (definition != null && (definition.type != PreferenceSchema.Type.BOOLEAN
                        || definition.store != PreferenceSchema.Store.PUBLIC)) return false;
            }
            SharedPreferences.Editor editor = PreferenceStores.publicStore(context).edit();
            for (java.util.Map.Entry<String, Boolean> change : batch.entrySet()) {
                editor.putBoolean(change.getKey(), change.getValue());
            }
            if (!editor.commit()) return false;
            fixFilePermissions();
            notifyChange();
            return true;
        } catch (RuntimeException ignored) {
            return false;
        }
    }

    public String getString(String key, String defaultValue) {
        try {
            return getStore(key).getString(key, defaultValue);
        } catch (ClassCastException e) {
            try {
                Object allVal = getStore(key).getAll().get(key);
                return allVal != null ? String.valueOf(allVal) : defaultValue;
            } catch (Throwable ignored) {
                return defaultValue;
            }
        }
    }

    public void putString(String key, String value) {
        getStore(key).edit().putString(key, value).commit();
        if (isPublicStore(key)) {
            fixFilePermissions();
            notifyChange();
        }
    }

    public int getInt(String key, int defaultValue) {
        return getStore(key).getInt(key, defaultValue);
    }

    public void putInt(String key, int value) {
        getStore(key).edit().putInt(key, value).commit();
        if (isPublicStore(key)) {
            fixFilePermissions();
            notifyChange();
        }
    }

    public float getFloat(String key, float defaultValue) {
        return getStore(key).getFloat(key, defaultValue);
    }

    public void putFloat(String key, float value) {
        getStore(key).edit().putFloat(key, value).commit();
        if (isPublicStore(key)) {
            fixFilePermissions();
            notifyChange();
        }
    }

    public void remove(String key) {
        getStore(key).edit().remove(key).commit();
        if (isPublicStore(key)) {
            fixFilePermissions();
            notifyChange();
        }
    }

    public java.util.Map<String, ?> getAll() {
        return PreferenceStores.publicStore(context).getAll();
    }

    public int exportSettings(Uri destination) throws Exception {
        OutputStream output = context.getContentResolver().openOutputStream(destination, "wt");
        if (output == null) throw new java.io.IOException("Could not open backup destination");
        return SettingsBackupCodec.INSTANCE.encode(context, output);
    }

    public int importSettings(Uri source) throws Exception {
        InputStream input = context.getContentResolver().openInputStream(source);
        if (input == null) throw new java.io.IOException("Could not open backup file");
        int count = SettingsBackupCodec.INSTANCE.decode(context, input);
        fixFilePermissions();
        notifyChange();
        return count;
    }

    private void notifyChange() {
        try {
            context.getContentResolver().notifyChange(PREFS_URI, null);
        } catch (Throwable ignored) {}
    }

    private void fixFilePermissions() {
        try {
            java.io.File dataDir = new java.io.File(context.getApplicationInfo().dataDir);
            java.io.File prefsDir = new java.io.File(dataDir, "shared_prefs");
            java.io.File prefsFile = new java.io.File(prefsDir, PreferenceStores.PUBLIC_NAME + ".xml");

            dataDir.setExecutable(true, false);
            dataDir.setReadable(true, false);

            prefsDir.setExecutable(true, false);
            prefsDir.setReadable(true, false);

            prefsFile.setReadable(true, false);
        } catch (Throwable ignored) {}
    }
}
