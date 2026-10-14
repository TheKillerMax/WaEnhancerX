package com.waenhancer.xposed.features.customization;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.util.DisplayMetrics;
import androidx.annotation.NonNull;
import com.waenhancer.xposed.core.BaseFeature;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;

/** Applies the configured display density to every newly visible WhatsApp Activity. */
public final class CustomDpiHook extends BaseFeature {
    public CustomDpiHook(@NonNull Context context, @NonNull ClassLoader classLoader,
                         @NonNull SharedPreferences prefs) {
        super(context, classLoader, prefs);
    }

    @NonNull @Override public String getName() { return "Custom DPI"; }

    @Override public void hook() {
        int dpi = TypedStyleHookPolicy.parseDpi(prefs.getString("change_dpi", "0"));
        if (dpi == 0) return;
        XposedBridge.hookAllMethods(Activity.class, "onCreate", new XC_MethodHook() {
            @Override protected void beforeHookedMethod(MethodHookParam param) {
                if (param.thisObject instanceof Activity) applyDpi((Activity) param.thisObject, dpi);
            }
        });
    }

    private static void applyDpi(Activity activity, int dpi) {
        DisplayMetrics metrics = activity.getResources().getDisplayMetrics();
        metrics.density = dpi / 160f;
        metrics.densityDpi = dpi;
    }
}
