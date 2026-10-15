package com.waenhancer.xposed.features.customization;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.view.Menu;
import android.view.MenuItem;
import androidx.annotation.NonNull;
import com.waenhancer.xposed.core.BaseFeature;
import com.waenhancer.xposed.core.devkit.DexSearchEngine;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import org.luckypray.dexkit.query.FindClass;
import org.luckypray.dexkit.query.FindMethod;
import org.luckypray.dexkit.query.enums.StringMatchType;
import org.luckypray.dexkit.query.matchers.ClassMatcher;
import org.luckypray.dexkit.query.matchers.MethodMatcher;
import org.luckypray.dexkit.result.ClassData;
import org.luckypray.dexkit.result.MethodData;
import java.lang.reflect.Method;
import java.util.concurrent.ConcurrentHashMap;


public class NewSettingsStyleHook extends BaseFeature {

    private static final String TAG = "[WAEX][NewSettingsStyle]";

    private static final int WHATS_HAPPENING_SENDING_ENABLED_CODE = 14862;
    private static final int ME_TAB_V2_VARIANTS_CODE = 18564;

    private static final ConcurrentHashMap<Integer, Boolean> propsBoolean = new ConcurrentHashMap<>();
    private static final ConcurrentHashMap<Integer, Integer> propsInteger = new ConcurrentHashMap<>();

    public NewSettingsStyleHook(@NonNull Context context,
                                @NonNull ClassLoader classLoader,
                                @NonNull SharedPreferences prefs) {
        super(context, classLoader, prefs);
    }

    @NonNull
    @Override
    public String getName() {
        return "New Settings Style";
    }

    @NonNull
    @Override
    public String getCategory() {
        return "Customization";
    }

    @Override
    public void hook() throws Throwable {
        boolean enabled = prefs.getBoolean("novaconfig", false);
        if (!enabled) {
            return;
        }

        // WhatsApp New Settings variant 2: profile photo on toolbar + new settings UI
        int newSettings = 2;
        propsBoolean.put(WHATS_HAPPENING_SENDING_ENABLED_CODE, true);
        propsInteger.put(ME_TAB_V2_VARIANTS_CODE, newSettings);

        hookABProps();
        hookHomeMenu();
    }

    private void hookABProps() {
        DexSearchEngine engine = DexSearchEngine.getInstance();
        engine.initialize(context);

        // 1. Hook Boolean A/B Props
        try {
            Method booleanPropMethod = engine.findMethodWithCache(
                    context, classLoader, "wpp_props_boolean_method",
                    (bridge, loader) -> {
                        MethodData md = bridge.findMethod(FindMethod.create()
                                .matcher(MethodMatcher.create()
                                        .addUsingString("Unknown BooleanField", StringMatchType.Contains))
                        ).firstOrNull();
                        return md != null && md.isMethod() ? md.getMethodInstance(loader) : null;
                    }
            );

            if (booleanPropMethod != null) {
                XposedBridge.hookMethod(booleanPropMethod, new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        if (param.args != null && param.args.length > 0) {
                            for (Object arg : param.args) {
                                if (arg instanceof Integer) {
                                    int key = (Integer) arg;
                                    Boolean overrideVal = propsBoolean.get(key);
                                    if (overrideVal != null) {
                                        param.setResult(overrideVal);
                                    }
                                    break;
                                }
                            }
                        }
                    }
                });
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Failed to hook boolean A/B props: " + t.getMessage());
        }

        // 2. Hook Integer A/B Props
        try {
            Method integerPropMethod = engine.findMethodWithCache(
                    context, classLoader, "wpp_props_integer_method",
                    (bridge, loader) -> {
                        MethodData md = bridge.findMethod(FindMethod.create()
                                .matcher(MethodMatcher.create()
                                        .addUsingString("Unknown IntField", StringMatchType.Contains))
                        ).firstOrNull();
                        return md != null && md.isMethod() ? md.getMethodInstance(loader) : null;
                    }
            );

            if (integerPropMethod != null) {
                XposedBridge.hookMethod(integerPropMethod, new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        if (param.args != null && param.args.length > 0) {
                            for (Object arg : param.args) {
                                if (arg instanceof Integer) {
                                    int key = (Integer) arg;
                                    Integer overrideVal = propsInteger.get(key);
                                    if (overrideVal != null) {
                                        param.setResult(overrideVal);
                                    }
                                    break;
                                }
                            }
                        }
                    }
                });
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Failed to hook integer A/B props: " + t.getMessage());
        }
    }

    private void hookHomeMenu() {
        try {
            Class<?> homeActivityClass = resolveHomeActivityClass();
            if (homeActivityClass == null) {
                return;
            }

            int meTabMenuItemId = context.getResources().getIdentifier(
                    "me_tab_menu_item", "id", context.getPackageName());

            XposedBridge.hookAllMethods(homeActivityClass, "onCreateOptionsMenu", new XC_MethodHook() {
                @Override
                protected void afterHookedMethod(MethodHookParam param) {
                    if (param.args != null && param.args.length > 0 && param.args[0] instanceof Menu) {
                        Menu menu = (Menu) param.args[0];
                        if (meTabMenuItemId != 0) {
                            MenuItem item = menu.findItem(meTabMenuItemId);
                            if (item != null) {
                                item.setShowAsAction(MenuItem.SHOW_AS_ACTION_ALWAYS);
                            }
                        }
                    }
                }
            });
        } catch (Throwable t) {
            XposedBridge.log(TAG + " Failed to hook HomeActivity menu for me_tab_menu_item: " + t.getMessage());
        }
    }

    private Class<?> resolveHomeActivityClass() {
        try {
            return DexSearchEngine.getInstance().findClassWithCache(
                    context, classLoader, "wpp_home_activity_class",
                    (bridge, loader) -> {
                        ClassData cd = bridge.findClass(FindClass.create()
                                .matcher(ClassMatcher.create()
                                        .className(".HomeActivity", StringMatchType.EndsWith))
                        ).firstOrNull();
                        if (cd == null) {
                            cd = bridge.findClass(FindClass.create()
                                    .matcher(ClassMatcher.create()
                                            .className("HomeActivity", StringMatchType.Contains))
                            ).firstOrNull();
                        }
                        return cd != null ? cd.getInstance(loader) : null;
                    }
            );
        } catch (Throwable ignored) {
            return null;
        }
    }
}
