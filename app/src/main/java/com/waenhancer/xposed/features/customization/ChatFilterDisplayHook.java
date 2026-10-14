package com.waenhancer.xposed.features.customization;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import androidx.annotation.NonNull;
import com.waenhancer.xposed.core.BaseFeature;
import com.waenhancer.xposed.core.devkit.DexSearchEngine;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import org.luckypray.dexkit.query.FindMethod;
import org.luckypray.dexkit.query.enums.StringMatchType;
import org.luckypray.dexkit.query.matchers.MethodMatcher;
import java.lang.reflect.Method;

/** Controls whether chat search is hidden, shown as an icon, or shown as a full bar. */
public final class ChatFilterDisplayHook extends BaseFeature {
    private static final String TAG = "[WAEX][ChatFilterDisplay]";

    public ChatFilterDisplayHook(@NonNull Context context, @NonNull ClassLoader classLoader,
                                 @NonNull SharedPreferences prefs) {
        super(context, classLoader, prefs);
    }

    @NonNull @Override public String getName() { return "Chat Filter Display"; }

    @Override public void hook() throws Throwable {
        String mode = prefs.getString("chatfilter", "2");
        if (!"0".equals(mode) && !"1".equals(mode)) return;

        DexSearchEngine engine = DexSearchEngine.getInstance();
        engine.initialize(context);
        if (engine.getBridge() == null) throw new IllegalStateException("DexKit unavailable");
        int searchBarId = context.getResources().getIdentifier(
                "my_search_bar", "id", context.getPackageName());

        hookHeaderInsertion(engine, searchBarId);
        hookSearchBarRenderer(engine);
        hookSearchMenu(mode);
    }

    private void hookHeaderInsertion(DexSearchEngine engine, int searchBarId) {
        for (String marker : new String[] {
                "HeaderFooterRecyclerViewAdapter/addHeaderViewItemIfNeeded",
                "HeaderFooterRecyclerViewAdapter/addFooterViewItemAtPositionIfNeeded"
        }) {
            try {
                var results = engine.getBridge().findMethod(FindMethod.create().matcher(
                        MethodMatcher.create().addUsingString(marker, StringMatchType.Contains)));
                for (var data : results) {
                    Method method = data.getMethodInstance(classLoader);
                    XposedBridge.hookMethod(method, new XC_MethodHook() {
                        @Override protected void beforeHookedMethod(MethodHookParam param) {
                            View view = firstView(param.args);
                            if (view == null || searchBarId == 0) return;
                            if (view.getId() == searchBarId
                                    || view.findViewById(searchBarId) != null) {
                                if (method.getReturnType() == void.class) param.setResult(null);
                                else if (!method.getReturnType().isPrimitive()) param.setResult(null);
                            }
                        }
                    });
                }
                if (!results.isEmpty()) return;
            } catch (Throwable ignored) {}
        }
        XposedBridge.log(TAG + " Search-bar insertion method not found");
    }

    private void hookSearchBarRenderer(DexSearchEngine engine) {
        try {
            var results = engine.getBridge().findMethod(FindMethod.create().matcher(
                    MethodMatcher.create().addUsingString(
                            "search_bar_render_start", StringMatchType.EndsWith)));
            for (var data : results) {
                Method method = data.getMethodInstance(classLoader);
                XposedBridge.hookMethod(method, new XC_MethodHook() {
                    @Override protected void beforeHookedMethod(MethodHookParam param) {
                        if (method.getReturnType() == void.class
                                || !method.getReturnType().isPrimitive()) param.setResult(null);
                    }
                });
            }
        } catch (Throwable error) {
            XposedBridge.log(TAG + " Search renderer hook unavailable: " + error);
        }
    }

    private void hookSearchMenu(String mode) {
        Class<?> home = XposedHelpers.findClassIfExists(
                "com.whatsapp.home.ui.HomeActivity", classLoader);
        if (home == null) home = XposedHelpers.findClassIfExists("com.whatsapp.HomeActivity", classLoader);
        if (home == null) return;
        int searchItemId = context.getResources().getIdentifier(
                "menuitem_search", "id", context.getPackageName());
        if (searchItemId == 0) return;
        XposedBridge.hookAllMethods(home, "onPrepareOptionsMenu", new XC_MethodHook() {
            @Override protected void afterHookedMethod(MethodHookParam param) {
                if (param.args.length == 0 || !(param.args[0] instanceof Menu)) return;
                MenuItem item = ((Menu) param.args[0]).findItem(searchItemId);
                if (item != null) item.setVisible("1".equals(mode));
            }
        });
    }

    private static View firstView(Object[] args) {
        if (args == null) return null;
        for (Object arg : args) if (arg instanceof View) return (View) arg;
        return null;
    }
}
