package com.waenhancer.xposed.features.media;

import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.drawable.Drawable;
import android.os.Handler;
import android.os.Looper;
import android.view.Menu;
import android.view.MenuItem;
import android.widget.Toast;

import androidx.annotation.NonNull;

import com.waenhancer.xposed.core.BaseFeature;
import com.waenhancer.xposed.core.devkit.DexSearchEngine;
import com.waenhancer.xposed.features.homescreen.MenuIconLoader;

import java.io.File;
import java.lang.ref.WeakReference;
import java.lang.reflect.Method;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;

/** Adds an explicit photo/video export action to the verified current media page. */
public class DownloadViewOnceHook extends BaseFeature {
    private static final String TAG = "[WAEX][DownloadViewOnce]";
    private static final int MENU_ID_DOWNLOAD = 0x7EAD0003;
    private static final AtomicReference<Object> EXPORTING = new AtomicReference<>();

    // Created on the first export. One accepted operation at a time; the bounded
    // hand-off slot also covers a new click just as the previous worker returns.
    private static final class ExportWorker {
        static final ThreadPoolExecutor INSTANCE = create();
        private static ThreadPoolExecutor create() {
            ThreadPoolExecutor executor = new ThreadPoolExecutor(1, 1, 30, TimeUnit.SECONDS,
                    new ArrayBlockingQueue<>(1), work -> {
                        Thread thread = new Thread(work, "WAEX-view-once-export");
                        thread.setDaemon(true);
                        return thread;
                    }, new ThreadPoolExecutor.AbortPolicy());
            executor.allowCoreThreadTimeOut(true);
            return executor;
        }
    }

    public DownloadViewOnceHook(@NonNull Context context, @NonNull ClassLoader classLoader,
                                @NonNull SharedPreferences prefs) {
        super(context, classLoader, prefs);
    }

    @Override public void hook() {
        try {
            DexSearchEngine engine = DexSearchEngine.getInstance();
            engine.initialize(context);
            if (engine.getBridge() == null) return;
            Context application = context.getApplicationContext();
            if (application == null) return;
            ViewOnceMediaResolver.Contract contract = ViewOnceMediaResolver.discover(engine.getBridge(), classLoader);
            XC_MethodHook callback = new XC_MethodHook() {
                @Override protected void afterHookedMethod(MethodHookParam param) {
                    Menu menu = null;
                    for (Object argument : param.args) if (argument instanceof Menu) menu = (Menu) argument;
                    if (menu == null) return;
                    try {
                        if (param.hasThrowable() || !enabled()) {
                            menu.removeItem(MENU_ID_DOWNLOAD);
                            return;
                        }
                        bindMenu(menu, param.thisObject, application, contract);
                    } catch (RuntimeException | LinkageError failure) {
                        XposedBridge.log(TAG + " Menu update failed: " + failure.getClass().getSimpleName());
                    }
                }
            };
            hookMenuPair(contract.createMenu, contract.prepareMenu, callback);
        } catch (ReflectiveOperationException | RuntimeException | LinkageError failure) {
            XposedBridge.log(TAG + " Unsupported media viewer: " + failure.getClass().getSimpleName());
        }
    }

    private void hookMenuPair(Method create, Method prepare, XC_MethodHook callback) {
        XC_MethodHook.Unhook first = XposedBridge.hookMethod(create, callback);
        boolean complete = false;
        try {
            XposedBridge.hookMethod(prepare, callback);
            complete = true;
        } finally {
            if (!complete) {
                try { first.unhook(); }
                catch (RuntimeException | LinkageError failure) {
                    XposedBridge.log(TAG + " Menu rollback failed: " + failure.getClass().getSimpleName());
                }
            }
        }
    }

    private boolean enabled() {
        try { return isEnabled("downloadviewonce", false); }
        catch (RuntimeException ignored) { return false; }
    }

    private void bindMenu(Menu menu, Object viewer, Context application, ViewOnceMediaResolver.Contract contract) {
        if (!contract.viewerClass.isInstance(viewer)) return;
        MenuItem item = menu.findItem(MENU_ID_DOWNLOAD);
        if (item == null) item = menu.add(Menu.NONE, MENU_ID_DOWNLOAD, Menu.NONE, "Download");
        item.setShowAsAction(MenuItem.SHOW_AS_ACTION_ALWAYS);
        Drawable icon = MenuIconLoader.load(application, "ic_waex_download");
        if (icon != null) item.setIcon(icon);
        // A listener never holds the fragment, Activity, menu or a prior message.
        WeakReference<Object> target = new WeakReference<>(viewer);
        item.setOnMenuItemClickListener(clicked -> {
            if (!enabled()) return true;
            Object ticket = new Object();
            if (!EXPORTING.compareAndSet(null, ticket)) {
                showToast(application, "A media export is already in progress");
                return true;
            }
            boolean queued = false;
            try {
                File selected = contract.fileAtCurrentPage(target.get());
                if (selected == null) {
                    showToast(application, "Media not cached or available yet");
                    return true;
                }
                ExportWorker.INSTANCE.execute(() -> {
                    try {
                        // A submission can fail after a queue offer if worker creation
                        // fails. The abandoned ticket cannot execute on a later retry.
                        if (EXPORTING.get() == ticket && enabled()) saveMediaFile(application, selected);
                    } finally {
                        EXPORTING.compareAndSet(ticket, null);
                    }
                });
                queued = true;
            } catch (ReflectiveOperationException | RuntimeException | LinkageError failure) {
                XposedBridge.log(TAG + " Media selection failed: " + failure.getClass().getSimpleName());
                showToast(application, "Unable to save this media file");
            } finally {
                if (!queued) EXPORTING.compareAndSet(ticket, null);
            }
            return true;
        });
    }

    private void saveMediaFile(Context ctx, File srcFile) {
        try {
            GalleryMediaExporter.export(ctx, srcFile);
            showToast(ctx, "Media saved (WAEX)");
        } catch (Exception failure) {
            XposedBridge.log(TAG + " Export failed: " + failure.getClass().getSimpleName());
            showToast(ctx, "Unable to save this media file");
        }
    }

    private void showToast(Context context, String message) {
        new Handler(Looper.getMainLooper()).post(() -> {
            try { Toast.makeText(context, message, Toast.LENGTH_SHORT).show(); }
            catch (RuntimeException ignored) { }
        });
    }

    @NonNull @Override public String getName() { return "Download View Once"; }
}
