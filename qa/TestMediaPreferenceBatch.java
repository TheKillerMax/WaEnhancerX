package com.waenhancer.core.preferences;

import android.content.ContentResolver;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.ApplicationInfo;
import android.net.Uri;
import com.waenhancer.ui.screens.media.MediaQuickSettingPolicy;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

/** Android-free stub integration test; compiles the real WaexPreferenceManager. */
public final class TestMediaPreferenceBatch {
    private static int checks;
    private static void check(boolean condition, String message) {
        checks++;
        if (!condition) throw new AssertionError(message);
    }

    private static final class FakeStore implements SharedPreferences {
        final Map<String, Object> values = new HashMap<>();
        int commits;
        boolean failCommit;
        boolean throwCommit;

        @Override public boolean getBoolean(String key, boolean fallback) {
            Object value = values.get(key);
            if (value == null) return fallback;
            if (!(value instanceof Boolean)) throw new ClassCastException();
            return (Boolean) value;
        }
        @Override public String getString(String key, String fallback) {
            Object v = values.get(key);
            return v == null ? fallback : (String) v;
        }
        @Override public int getInt(String key, int fallback) {
            Object v = values.get(key);
            return v == null ? fallback : (Integer) v;
        }
        @Override public float getFloat(String key, float fallback) {
            Object v = values.get(key);
            return v == null ? fallback : (Float) v;
        }
        @Override public Map<String, ?> getAll() { return Collections.unmodifiableMap(new HashMap<>(values)); }
        @Override public SharedPreferences.Editor edit() { return new Batch(); }

        private final class Batch implements Editor {
            private final Map<String, Object> adds = new HashMap<>();
            @Override public Editor putBoolean(String key, boolean value) { adds.put(key, value); return this; }
            @Override public Editor putString(String key, String value) { adds.put(key, value); return this; }
            @Override public Editor putInt(String key, int value) { adds.put(key, value); return this; }
            @Override public Editor putFloat(String key, float value) { adds.put(key, value); return this; }
            @Override public Editor remove(String key) { adds.put(key, null); return this; }
            @Override public boolean commit() {
                commits++;
                if (throwCommit) throw new IllegalStateException("Storage unavailable");
                if (failCommit) return false;
                for (Map.Entry<String, Object> entry : adds.entrySet()) {
                    if (entry.getValue() == null) values.remove(entry.getKey());
                    else values.put(entry.getKey(), entry.getValue());
                }
                return true;
            }
        }
    }

    private static final class FakeResolver extends ContentResolver {
        int notifications;
        @Override public void notifyChange(Uri uri, Object observer) { notifications++; }
    }
    private static final class FakeContext extends Context {
        final FakeStore publicStore = new FakeStore();
        final FakeStore privateStore = new FakeStore();
        final FakeResolver resolver = new FakeResolver();
        final ApplicationInfo info = new ApplicationInfo();
        FakeContext() { info.dataDir = "/path/which/does/not/exist"; }
        @Override public SharedPreferences getSharedPreferences(String name, int mode) {
            return name.equals("private_config") ? privateStore : publicStore;
        }
        @Override public ContentResolver getContentResolver() { return resolver; }
        @Override public ApplicationInfo getApplicationInfo() { return info; }
    }

    public static void main(String[] args) {
        FakeContext context = new FakeContext();
        WaexPreferenceManager manager = new WaexPreferenceManager(context);
        check(manager.putBooleans(MediaQuickSettingPolicy.changesFor("media_upload_quality", true)),
                "bulk HD update failed");
        check(context.publicStore.commits == 1, "must use ONE commit for all three keys");
        check(context.resolver.notifications == 1, "must notify once after a successful commit");
        check(manager.getBoolean("imagequality", false), "image hook flag");
        check(manager.getBoolean("video_maxfps", false), "fps hook flag");
        check(manager.getBoolean("media_upload_quality", false), "legacy UI alias retained");

        check(manager.putBooleans(MediaQuickSettingPolicy.changesFor("call_recording", true)),
                "recorder update failed");
        check(context.publicStore.commits == 2, "recorder should be a single commit");
        check(context.resolver.notifications == 2, "recorder should notify once");
        check(manager.getBoolean("call_recording_enabled", false), "canonical recorder not set");
        check(manager.getBoolean("call_recording", false), "legacy recorder flag absent");

        Map<String, Boolean> malformed = new LinkedHashMap<>();
        malformed.put("imagequality", false);
        malformed.put("admin_emoji", true); // Schema declares STRING; reject entire batch.
        check(!manager.putBooleans(malformed), "non-Boolean schema entry was accepted");
        check(manager.getBoolean("imagequality", false), "partially applied invalid update");
        check(context.publicStore.commits == 2, "invalid data reached editor");
        check(context.resolver.notifications == 2, "invalid data triggered notification");

        malformed.clear();
        malformed.put("imagequality", false);
        malformed.put("update_auto_check", true); // Private Boolean; must remain private.
        check(!manager.putBooleans(malformed), "private key accepted in public batch");
        check(manager.getBoolean("imagequality", false), "partially wrote with private key");
        check(context.publicStore.commits == 2, "private key reached editor");

        check(!manager.putBooleans(Collections.emptyMap()), "empty batch accepted");
        check(!manager.putBooleans(null), "null batch accepted");
        malformed.clear(); malformed.put("video_maxfps", null);
        check(!manager.putBooleans(malformed), "null value accepted");

        context.publicStore.failCommit = true;
        check(!manager.putBooleans(MediaQuickSettingPolicy.changesFor("media_upload_quality", false)),
                "failed commit reported success");
        check(manager.getBoolean("imagequality", false), "failed commit changed data");
        check(context.resolver.notifications == 2, "failed commit notified observers");
        context.publicStore.failCommit = false;
        context.publicStore.throwCommit = true;
        check(!manager.putBooleans(MediaQuickSettingPolicy.changesFor("call_recording", false)),
                "storage exception escaped or reported success");
        check(manager.getBoolean("call_recording_enabled", false), "exception changed data");
        check(context.resolver.notifications == 2, "storage exception notified observers");
        context.publicStore.throwCommit = false;

        check(manager.putBooleans(MediaQuickSettingPolicy.changesFor("media_upload_quality", false)),
                "disable HD update failed");
        check(!manager.getBoolean("imagequality", true), "image hook was not disabled");
        check(!manager.getBoolean("video_maxfps", true), "fps hook was not disabled");
        check(context.resolver.notifications == 3, "valid update not notified");
        System.out.println("PASS: " + checks + " production manager atomicity, schema and failure checks");
    }
}
