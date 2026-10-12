package com.waenhancer.xposed.core;

import android.app.Activity;
import android.app.Dialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import android.os.Process;
import androidx.annotation.NonNull;
import com.waenhancer.config.PreferenceRestartTracker;
import com.waenhancer.xposed.core.components.WaexBottomSheet;
import de.robv.android.xposed.XposedBridge;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
import java.lang.ref.WeakReference;

/** Shows a WhatsApp-styled restart request after settings change in the manager app. */
public final class RestartPromptController {
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final AtomicBoolean SHOWING = new AtomicBoolean(false);
    private static volatile SharedPreferences preferences;
    private static volatile WeakReference<Activity> resumedActivity = new WeakReference<>(null);
    private static final SharedPreferences.OnSharedPreferenceChangeListener CHANGE_LISTENER =
            (sharedPreferences, key) -> {
                if (!PreferenceRestartTracker.NEED_RESTART.equals(key)
                        || !sharedPreferences.getBoolean(
                                PreferenceRestartTracker.NEED_RESTART, false)) {
                    return;
                }
                Activity activity = resumedActivity.get();
                if (activity != null) MAIN.post(() -> showIfNeeded(activity));
            };

    private RestartPromptController() {}

    public static synchronized void initialize(@NonNull SharedPreferences sharedPreferences) {
        SharedPreferences previous = preferences;
        if (previous != null) previous.unregisterOnSharedPreferenceChangeListener(CHANGE_LISTENER);
        preferences = sharedPreferences;
        sharedPreferences.registerOnSharedPreferenceChangeListener(CHANGE_LISTENER);
    }

    public static void onTargetActivityResumed(@NonNull Activity activity) {
        resumedActivity = new WeakReference<>(activity);
        showIfNeeded(activity);
        // Provider refresh is asynchronous; retries cover a return-to-app race while the
        // preference listener remains the primary real-time delivery path.
        MAIN.postDelayed(() -> showIfCurrent(activity), 250L);
        MAIN.postDelayed(() -> showIfCurrent(activity), 750L);
    }

    public static void onTargetActivityPaused(@NonNull Activity activity) {
        if (resumedActivity.get() == activity) resumedActivity = new WeakReference<>(null);
    }

    private static void showIfCurrent(Activity activity) {
        if (resumedActivity.get() == activity) showIfNeeded(activity);
    }

    private static void showIfNeeded(Activity activity) {
        SharedPreferences prefs = preferences;
        if (prefs == null || activity.isFinishing() || activity.isDestroyed()
                || !prefs.getBoolean(PreferenceRestartTracker.NEED_RESTART, false)
                || !SHOWING.compareAndSet(false, true)) {
            return;
        }

        Set<String> changed = prefs.getStringSet(
                PreferenceRestartTracker.PENDING_CHANGES, Collections.emptySet());
        String message = buildMessage(changed);

        // Consume this request once the sheet is presented. A later setting change creates a new one.
        prefs.edit()
                .putBoolean(PreferenceRestartTracker.NEED_RESTART, false)
                .remove(PreferenceRestartTracker.PENDING_CHANGES)
                .apply();

        try {
            Dialog dialog = new WaexBottomSheet(activity)
                    .asBottomSheet()
                    .setTitle("Restart required")
                    .setMessage(message)
                    .setPositiveButton("Restart WhatsApp", (ignored, which) -> restart(activity))
                    .setNegativeButton("Later", null)
                    .show();
            if (dialog == null) {
                SHOWING.set(false);
                return;
            }
            dialog.setOnDismissListener(ignored -> SHOWING.set(false));
        } catch (Throwable throwable) {
            SHOWING.set(false);
            XposedBridge.log("[WAEX] Restart prompt failed: " + throwable.getMessage());
        }
    }

    static String buildMessage(Set<String> changes) {
        if (changes == null || changes.isEmpty()) {
            return "Your WA Enhancer preferences changed. Restart WhatsApp to apply them.";
        }
        List<String> sorted = new ArrayList<>(changes);
        sorted.sort(String.CASE_INSENSITIVE_ORDER);
        StringBuilder message = new StringBuilder("Restart WhatsApp to apply:\n\n");
        int shown = Math.min(sorted.size(), 8);
        for (int i = 0; i < shown; i++) message.append("• ").append(sorted.get(i)).append('\n');
        if (sorted.size() > shown) {
            message.append("• ").append(sorted.size() - shown).append(" more\n");
        }
        return message.toString().trim();
    }

    private static void restart(Activity activity) {
        try {
            Intent launch = activity.getPackageManager()
                    .getLaunchIntentForPackage(activity.getPackageName());
            if (launch != null && launch.getComponent() != null) {
                Intent restart = Intent.makeRestartActivityTask(launch.getComponent());
                restart.setPackage(activity.getPackageName());
                activity.startActivity(restart);
            }
        } catch (Throwable throwable) {
            XposedBridge.log("[WAEX] WhatsApp relaunch failed: " + throwable.getMessage());
        }
        MAIN.postDelayed(() -> {
            Process.killProcess(Process.myPid());
            System.exit(0);
        }, 150L);
    }
}
