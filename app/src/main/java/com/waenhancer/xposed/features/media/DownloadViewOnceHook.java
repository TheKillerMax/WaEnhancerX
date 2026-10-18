package com.waenhancer.xposed.features.media;

import com.waenhancer.app.R;
import com.waenhancer.utils.UiText;

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
            hookAudioViewer(engine, application, contract);
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

    private void hookAudioViewer(DexSearchEngine engine, Context application, ViewOnceMediaResolver.Contract media) {
        try {
            ViewOnceAudioResolver audio = ViewOnceAudioResolver.discover(engine.getBridge(), classLoader, media);
            XC_MethodHook callback = new XC_MethodHook() {
                @Override protected void afterHookedMethod(MethodHookParam param) {
                    if (!(param.args[0] instanceof Menu)) return;
                    Menu menu = (Menu) param.args[0];
                    try {
                        if (param.hasThrowable() || !Boolean.TRUE.equals(param.getResult())
                                || !enabled() || !audio.hasAudio(param.thisObject)) {
                            menu.removeItem(MENU_ID_DOWNLOAD);
                            return;
                        }
                        bindAction(menu, param.thisObject, application, audio::fileAtActivity, true);
                    } catch (ReflectiveOperationException | RuntimeException | LinkageError failure) {
                        menu.removeItem(MENU_ID_DOWNLOAD);
                        XposedBridge.log(TAG + " Audio menu update failed: " + failure.getClass().getSimpleName());
                    }
                }
            };
            hookMenuPair(audio.createMenu, audio.prepareMenu, callback);
        } catch (ReflectiveOperationException | RuntimeException | LinkageError failure) {
            // An optional audio contract cannot prevent the independent photo/video hooks.
            XposedBridge.log(TAG + " Unsupported audio viewer: " + failure.getClass().getSimpleName());
        }
    }

    private boolean enabled() {
        try { return isEnabled("downloadviewonce", false); }
        catch (RuntimeException ignored) { return false; }
    }

    private void bindMenu(Menu menu, Object viewer, Context application, ViewOnceMediaResolver.Contract contract) {
        if (!contract.viewerClass.isInstance(viewer)) return;
        bindAction(menu, viewer, application, contract::fileAtCurrentPage, false);
    }

    private interface MediaSelection { File select(Object viewer) throws ReflectiveOperationException; }

    private void bindAction(Menu menu, Object viewer, Context application, MediaSelection selection, boolean audio) {
        MenuItem item = menu.findItem(MENU_ID_DOWNLOAD);
        if (item == null) item = menu.add(Menu.NONE, MENU_ID_DOWNLOAD, Menu.NONE,
                UiText.get(R.string.waex_ui_download_d6eafe82, "Download"));
        item.setShowAsAction(MenuItem.SHOW_AS_ACTION_ALWAYS);
        Drawable icon = MenuIconLoader.load(application, "ic_waex_download");
        if (icon != null) item.setIcon(icon);
        // A listener never holds the fragment, Activity, menu or a prior message.
        WeakReference<Object> target = new WeakReference<>(viewer);
        item.setOnMenuItemClickListener(clicked -> {
            if (!enabled()) return true;
            Object ticket = new Object();
            if (!EXPORTING.compareAndSet(null, ticket)) {
                showToast(application, UiText.get(R.string.waex_ui_media_export_in_progress_v36,
                        "A media export is already in progress"));
                return true;
            }
            boolean queued = false;
            try {
                File selected = selection.select(target.get());
                if (selected == null) {
                    showToast(application, UiText.get(R.string.waex_ui_media_not_cached_or_available_yet_45e16ba0,
                            "Media not cached or available yet"));
                    return true;
                }
                ExportWorker.INSTANCE.execute(() -> {
                    try {
                        // A submission can fail after a queue offer if worker creation
                        // fails. The abandoned ticket cannot execute on a later retry.
                        if (EXPORTING.get() == ticket && enabled()) {
                            if (audio) saveAudioFile(application, selected);
                            else saveMediaFile(application, selected);
                        }
                    } finally {
                        EXPORTING.compareAndSet(ticket, null);
                    }
                });
                queued = true;
            } catch (ReflectiveOperationException | RuntimeException | LinkageError failure) {
                XposedBridge.log(TAG + " Media selection failed: " + failure.getClass().getSimpleName());
                showToast(application, UiText.get(R.string.waex_ui_media_save_failed_v30,
                        "Unable to save this media file"));
            } finally {
                if (!queued) EXPORTING.compareAndSet(ticket, null);
            }
            return true;
        });
    }

    private void saveAudioFile(Context ctx, File srcFile) {
        try {
            GalleryMediaExporter.exportAudio(ctx, srcFile);
            showToast(ctx, UiText.get(R.string.waex_ui_audio_saved_v36, "Audio saved (WAEX)"));
        } catch (Exception failure) {
            XposedBridge.log(TAG + " Audio export failed: " + failure.getClass().getSimpleName());
            showToast(ctx, UiText.get(R.string.waex_ui_audio_save_failed_v36,
                    "Unable to save this audio file"));
        }
    }

    private void saveMediaFile(Context ctx, File srcFile) {
        try {
            GalleryMediaExporter.export(ctx, srcFile);
            showToast(ctx, UiText.get(R.string.waex_ui_media_saved_v30, "Media saved (WAEX)"));
        } catch (Exception failure) {
            XposedBridge.log(TAG + " Export failed: " + failure.getClass().getSimpleName());
            showToast(ctx, UiText.get(R.string.waex_ui_media_save_failed_v30,
                    "Unable to save this media file"));
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
