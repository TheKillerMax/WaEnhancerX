package com.waenhancer.xposed;

import android.annotation.SuppressLint;
import android.content.Context;
import android.content.ContextWrapper;
import com.waenhancer.xposed.bridge.client.PreferenceBridgeClient;
import com.waenhancer.xposed.core.FeatureRegistry;
import com.waenhancer.xposed.utils.ModuleStatus;
import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.IXposedHookZygoteInit;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XC_MethodReplacement;
import de.robv.android.xposed.XSharedPreferences;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;
import java.util.concurrent.atomic.AtomicBoolean;



/**
 * Main Xposed Entry point for Wa Enhancer X.
 * Handles scope detection, self-hook sentinel verification, and target hooking.
 */
public class MainHook implements IXposedHookLoadPackage, IXposedHookZygoteInit {

    public static final String RESTART_PERMISSION = "com.waenhancer.permission.RESTART_TARGET";

    public static final String PACKAGE_MANAGER = "com.waenhancer";
    public static final String PACKAGE_WPP = "com.whatsapp";
    public static final String PACKAGE_BUSINESS = "com.whatsapp.w4b";

    private static XSharedPreferences sPrefs;
    private static volatile PreferenceBridgeClient sPreferenceBridge;
    private static final AtomicBoolean TARGET_INITIALIZED = new AtomicBoolean(false);
    private String mModulePath;

    @Override
    public void initZygote(StartupParam startupParam) throws Throwable {
        mModulePath = startupParam.modulePath;
    }

    public static synchronized XSharedPreferences getPrefs() {
        if (sPrefs == null) {
            sPrefs = new XSharedPreferences(PACKAGE_MANAGER, "waex_prefs");
            sPrefs.reload();
        }
        return sPrefs;
    }

    @SuppressLint("UnspecifiedRegisterReceiverFlag")
    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam lpparam) throws Throwable {
        String packageName = lpparam.packageName;
        if (packageName == null) return;

        // 1. Self Hook: verify module active inside WaEnhancerX UI
        if (packageName.equals(PACKAGE_MANAGER)) {
            try {
                XposedHelpers.findAndHookMethod(
                        ModuleStatus.class.getName(),
                        lpparam.classLoader,
                        "isModuleActive",
                        XC_MethodReplacement.returnConstant(true)
                );
            } catch (Throwable t) {
                XposedBridge.log("[WAEX] Failed to hook ModuleStatus sentinel: " + t.getMessage());
            }

            // Persist the API supplied by the active framework for the manager diagnostics UI.
            try {
                XposedHelpers.findAndHookMethod(
                        "android.app.Application",
                        lpparam.classLoader,
                        "onCreate",
                        new XC_MethodHook() {
                            @Override
                            protected void afterHookedMethod(MethodHookParam param) {
                                try {
                                    Context context = (Context) param.thisObject;
                                    int apiVersion = XposedBridge.getXposedVersion();
                                    com.waenhancer.config.PreferenceStores.publicStore(context)
                                            .edit()
                                            .putInt("active_xposed_api_version", apiVersion)
                                            .commit();
                                } catch (Throwable t) {
                                    XposedBridge.log("[WAEX] Failed to save Xposed API version: " + t.getMessage());
                                }
                            }
                        }
                );
            } catch (Throwable t) {
                XposedBridge.log("[WAEX] Failed to register Xposed API recorder: " + t.getMessage());
            }

            // Bypass Android 7+ MODE_WORLD_READABLE check
            try {
                XposedHelpers.findAndHookMethod(
                        "android.app.ContextImpl",
                        lpparam.classLoader,
                        "checkMode",
                        int.class,
                        new XC_MethodHook() {
                            @Override
                            protected void beforeHookedMethod(MethodHookParam param) {
                                param.setResult(null);
                            }
                        }
                );
            } catch (Throwable ignored) {}
            return;
        }

        // 2. Target Hooking: WhatsApp, WA Business & Clones / Modded variants
        boolean isWhatsAppTarget = com.waenhancer.utils.WhatsAppPackageDetector.isWhatsAppPackageName(packageName);

        if (isWhatsAppTarget) {
            // Only hook the main package process (e.g. "com.whatsapp", not isolated or secondary background workers)
            if (lpparam.processName != null && !lpparam.processName.equals(packageName)) {
                return;
            }

            // Read the world-readable snapshot before Application startup, then begin the
            // authoritative provider fetch as soon as a Context becomes available. This overlaps
            // preference IPC with the target's attach -> onCreate work without using stale
            // entitlement/config values when hooks are installed.
            final XSharedPreferences preloadedPrefs = getPrefs();
            try {
                XposedHelpers.findAndHookMethod(
                        "android.app.Application",
                        lpparam.classLoader,
                        "attach",
                        Context.class,
                        new XC_MethodHook() {
                            @Override
                            protected void afterHookedMethod(MethodHookParam param) {
                                Context context = (Context) param.thisObject;
                                if (sPreferenceBridge == null) {
                                    synchronized (MainHook.class) {
                                        if (sPreferenceBridge == null) {
                                            sPreferenceBridge = new PreferenceBridgeClient(
                                                    context, preloadedPrefs, true);
                                        }
                                    }
                                }
                            }
                        }
                );
            } catch (Throwable t) {
                XposedBridge.log("[WAEX] Failed to start early preference preload: "
                        + t.getMessage());
            }

            // Reuse one initializer from both lifecycle entry points. Some custom
            // Application subclasses override onCreate() without calling super.
            XC_MethodHook applicationInitializer = new XC_MethodHook() {
                            @Override
                            protected void afterHookedMethod(MethodHookParam param) {
                                // onCreate: thisObject is Application; Instrumentation: args[0].
                                Object application = param.thisObject instanceof android.app.Application
                                        ? param.thisObject
                                        : (param.args != null && param.args.length == 1 ? param.args[0] : null);
                                if (!(application instanceof android.app.Application)) return;
                                Context appContext = (Context) application;
                                if (!TARGET_INITIALIZED.compareAndSet(false, true)) {
                                    return;
                                }
                                // Optional diagnostics and lifecycle tracking must not prevent
                                // unrelated Xposed features from initializing.
                                if (appContext instanceof android.app.Application) {
                                    try {
                                        com.waenhancer.xposed.utils.ActivityTracker.install(
                                                (android.app.Application) appContext);
                                    } catch (Throwable t) {
                                        XposedBridge.log("[WAEX] ActivityTracker initialization failed: "
                                                + t.getClass().getSimpleName());
                                    }
                                }

                                // Preserve current package reporting, but isolate its failures.
                                try {
                                    com.waenhancer.utils.WhatsAppPackageDetector.registerHookedPackage(
                                            appContext, packageName);
                                } catch (Throwable t) {
                                    XposedBridge.log("[WAEX] Hooked-package reporting failed: "
                                            + t.getClass().getSimpleName());
                                }
                                try {
                                    appContext.getContentResolver().call(
                                            android.net.Uri.parse("content://com.waenhancer.hookprovider"),
                                            "request_update_check", packageName, null);
                                } catch (Throwable ignored) {}

                                try {
                                    android.content.IntentFilter filter = new android.content.IntentFilter("com.waenhancer.WHATSAPP.RESTART");
                                    android.content.BroadcastReceiver receiver = new android.content.BroadcastReceiver() {
                                        @Override
                                        public void onReceive(Context context, android.content.Intent intent) {
                                            String pkg = intent.getStringExtra("PKG");
                                            if (packageName.equals(pkg)) {
                                                android.os.Process.killProcess(android.os.Process.myPid());
                                            }
                                        }
                                    };
                                    if (android.os.Build.VERSION.SDK_INT >= 33) {
                                        appContext.registerReceiver(receiver, filter, RESTART_PERMISSION,
                                                null, Context.RECEIVER_EXPORTED);
                                    } else {
                                        appContext.registerReceiver(receiver, filter, RESTART_PERMISSION, null);
                                    }
                                } catch (Throwable ignored) {}

                                boolean showHookToast = true;
                                try {
                                    PreferenceBridgeClient resolvedBridge = sPreferenceBridge;
                                    if (resolvedBridge == null) {
                                        resolvedBridge = new PreferenceBridgeClient(appContext, preloadedPrefs);
                                        sPreferenceBridge = resolvedBridge;
                                    } else {
                                        resolvedBridge.awaitInitialSync();
                                    }
                                    final PreferenceBridgeClient bridgeClient = resolvedBridge;
                                    try {
                                        com.waenhancer.xposed.core.RestartPromptController.initialize(bridgeClient);
                                    } catch (Throwable t) {
                                        XposedBridge.log("[WAEX] Restart prompt setup failed: "
                                                + t.getClass().getSimpleName());
                                    }
                                    try {
                                        android.content.IntentFilter prefsFilter = new android.content.IntentFilter(
                                                "com.waenhancer.action.PREFERENCES_CHANGED");
                                        android.content.BroadcastReceiver prefsReceiver = new android.content.BroadcastReceiver() {
                                            @Override
                                            public void onReceive(Context context, android.content.Intent intent) {
                                                bridgeClient.syncPreferences();
                                            }
                                        };
                                        if (android.os.Build.VERSION.SDK_INT >= 33) {
                                            appContext.registerReceiver(prefsReceiver, prefsFilter, RESTART_PERMISSION,
                                                    null, Context.RECEIVER_EXPORTED);
                                        } else {
                                            appContext.registerReceiver(prefsReceiver, prefsFilter,
                                                    RESTART_PERMISSION, null);
                                        }
                                    } catch (Throwable t) {
                                        XposedBridge.log("[WAEX] Failed to register preference refresh receiver: "
                                                + t.getMessage());
                                    }
                                    showHookToast = bridgeClient.getBoolean("show_hook_toast", true);

                                    // Verify universal version compatibility before loading hooks
                                    boolean isSupported = com.waenhancer.xposed.core.VersionGuard.verifyAndGuard(
                                            appContext,
                                            lpparam.classLoader,
                                            bridgeClient
                                    );

                                    if (isSupported) {
                                        try {
                                            com.waenhancer.xposed.features.updates.WhatsAppUpdateSheet.init(
                                                    bridgeClient);
                                        } catch (Throwable t) {
                                            XposedBridge.log("[WAEX] WhatsApp update-sheet setup failed: "
                                                    + t.getClass().getSimpleName());
                                        }
                                        if (showHookToast) {
                                            try {
                                                android.widget.Toast.makeText(
                                                    appContext,
                                                    "Injecting WAEX hooks into WhatsApp...",
                                                    android.widget.Toast.LENGTH_SHORT
                                                ).show();
                                            } catch (Throwable t) {
                                                XposedBridge.log("[WAEX] Injection toast unavailable: "
                                                        + t.getClass().getSimpleName());
                                            }
                                        }
                                        FeatureRegistry registry = new FeatureRegistry(appContext, lpparam.classLoader, bridgeClient);
                                        registry.initializeAll();
                                        registry.reportInjectedHooks(appContext, packageName);
                                    } else {
                                        XposedBridge.log("[WAEX] Feature initialization halted due to unverified WhatsApp version.");
                                    }
                                } catch (Throwable t) {
                                    XposedBridge.log("[WAEX] Error initializing FeatureRegistry: " + t.getMessage());
                                    showInjectionErrorSheet(t, packageName, lpparam.processName);
                                }
                            }
                        };

            // Keep the previous hook for compatible runtimes. Both callbacks are
            // protected by TARGET_INITIALIZED.compareAndSet(false, true).
            try {
                XposedHelpers.findAndHookMethod(
                        "android.app.Application", lpparam.classLoader,
                        "onCreate", applicationInitializer);
            } catch (Throwable t) {
                XposedBridge.log("[WAEX] Error hooking Application.onCreate in target: " + t.getMessage());
            }

            // Instrumentation normally invokes the actual Application.onCreate,
            // including subclasses that bypass the superclass implementation.
            // Hook registration is independent so either entry point can work.
            try {
                XposedHelpers.findAndHookMethod(
                        "android.app.Instrumentation", lpparam.classLoader,
                        "callApplicationOnCreate", android.app.Application.class,
                        applicationInitializer);
            } catch (Throwable t) {
                XposedBridge.log("[WAEX] Cannot hook Instrumentation.callApplicationOnCreate: " +
                        t.getClass().getSimpleName());
            }
        }
    }

    private static void showInjectionErrorSheet(Throwable throwable, String packageName, String processName) {
        String error = throwable.getMessage() != null
                ? throwable.getMessage()
                : throwable.getClass().getSimpleName();

        java.io.StringWriter stackTrace = new java.io.StringWriter();
        throwable.printStackTrace(new java.io.PrintWriter(stackTrace));
        String diagnostic = "WaEnhancer X hook injection failed\n"
                + "Package: " + packageName + "\n"
                + "Process: " + processName + "\n\n"
                + stackTrace;

        android.app.Activity currentActivity =
                com.waenhancer.xposed.utils.ActivityTracker.getCurrentActivity();
        if (currentActivity != null) {
            showInjectionErrorSheet(currentActivity, error, diagnostic);
            return;
        }

        com.waenhancer.xposed.utils.ActivityTracker.addListener(
                new com.waenhancer.xposed.utils.ActivityTracker.ActivityListener() {
                    @Override
                    public void onActivityResumed(android.app.Activity activity) {
                        com.waenhancer.xposed.utils.ActivityTracker.removeListener(this);
                        showInjectionErrorSheet(activity, error, diagnostic);
                    }
                }
        );
    }

    private static void showInjectionErrorSheet(
            android.app.Activity activity,
            String error,
            String diagnostic
    ) {
        activity.runOnUiThread(() -> {
            if (activity.isFinishing() || activity.isDestroyed()) return;

            new com.waenhancer.xposed.core.components.WaexBottomSheet(activity)
                    .asBottomSheet()
                    .setTitle("WaEnhancer X injection failed")
                    .setMessage(
                            "WaEnhancer X could not finish loading its hooks.\n\n"
                                    + error
                                    + "\n\nCopy the error details when reporting this issue."
                    )
                    .setPositiveButton("Copy error", (dialog, which) -> {
                        android.content.ClipboardManager clipboard =
                                (android.content.ClipboardManager) activity.getSystemService(Context.CLIPBOARD_SERVICE);
                        if (clipboard != null) {
                            clipboard.setPrimaryClip(
                                    android.content.ClipData.newPlainText("WaEnhancer X injection error", diagnostic)
                            );
                        }
                    })
                    .setNegativeButton("Close", (dialog, which) -> dialog.dismiss())
                    .show();
        });
    }
}
