package com.waenhancer.xposed.features.customization;

import android.content.Context;
import android.content.SharedPreferences;
import androidx.annotation.NonNull;
import com.waenhancer.xposed.core.BaseFeature;
import com.waenhancer.xposed.core.devkit.DexSearchEngine;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import org.luckypray.dexkit.query.FindMethod;
import org.luckypray.dexkit.query.matchers.MethodMatcher;
import org.luckypray.dexkit.result.MethodData;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Calendar;
import java.util.Locale;

public class CustomTimeHook extends BaseFeature {

    private static final String TAG = "[WAEX][CustomTime]";

    public CustomTimeHook(@NonNull Context context,
                          @NonNull ClassLoader classLoader,
                          @NonNull SharedPreferences prefs) {
        super(context, classLoader, prefs);
    }

    @NonNull
    @Override
    public String getName() {
        return "Seconds on Timestamp";
    }

    @NonNull
    @Override
    public String getCategory() {
        return "Customization";
    }

    @Override
    public void hook() throws Throwable {
        boolean secondsToTime = prefs.getBoolean("segundos", false);
        if (!secondsToTime) {
            return;
        }

        boolean ampm = prefs.getBoolean("ampm", false);
        String pattern = ampm ? "hh:mm:ss a" : "HH:mm:ss";
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern(pattern, Locale.US)
                .withZone(ZoneId.systemDefault());

        DexSearchEngine engine = DexSearchEngine.getInstance();
        engine.initialize(context);

        try {
            Method timeMethod = engine.findMethodWithCache(
                    context, classLoader, "wpp_time_to_seconds_method",
                    (bridge, loader) -> {
                        MethodData md = bridge.findMethod(FindMethod.create()
                                .matcher(MethodMatcher.create()
                                        .usingNumbers(223, 224)
                                        .modifiers(Modifier.STATIC)
                                        .returnType("java.lang.String")
                                        .paramCount(2)
                                        .paramTypes(null, "java.util.Calendar"))
                        ).firstOrNull();
                        return md != null && md.isMethod() ? md.getMethodInstance(loader) : null;
                    }
            );

            if (timeMethod != null) {
                XposedBridge.hookMethod(timeMethod, new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        if (param.args != null && param.args.length > 1 && param.args[1] instanceof Calendar) {
                            Calendar calendar = (Calendar) param.args[1];
                            String formatted = formatter.format(Instant.ofEpochMilli(calendar.getTimeInMillis()));
                            param.setResult(formatted);
                        }
                    }
                });
            } else {
                XposedBridge.log(TAG + " Could not find timeToSeconds method via DexKit");
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Failed to hook timestamp formatting: " + t.getMessage());
        }
    }
}
