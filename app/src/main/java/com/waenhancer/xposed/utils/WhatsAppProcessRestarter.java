package com.waenhancer.xposed.utils;

import android.app.Activity;
import android.content.Intent;
import android.os.Process;
import androidx.annotation.NonNull;
import de.robv.android.xposed.XposedBridge;

/** Relaunches the current WhatsApp task and immediately terminates its old process. */
public final class WhatsAppProcessRestarter {
    private WhatsAppProcessRestarter() {}

    public static void restart(@NonNull Activity activity) {
        try {
            Intent launchIntent = activity.getPackageManager()
                    .getLaunchIntentForPackage(activity.getPackageName());
            if (launchIntent != null && launchIntent.getComponent() != null) {
                Intent restartIntent = Intent.makeRestartActivityTask(launchIntent.getComponent());
                restartIntent.setPackage(activity.getPackageName());
                activity.startActivity(restartIntent);
            } else {
                Intent fallback = new Intent(activity, activity.getClass());
                fallback.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
                activity.startActivity(fallback);
            }
        } catch (Throwable throwable) {
            XposedBridge.log("[WAEX] WhatsApp restart launch failed: " + throwable.getMessage());
        }

        try {
            Runtime.getRuntime().exit(0);
        } catch (Throwable ignored) {
            Process.killProcess(Process.myPid());
            System.exit(0);
        }
    }
}
