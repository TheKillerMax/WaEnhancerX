package com.waenhancer.xposed.features.privacy;

import android.content.Context;
import android.content.SharedPreferences;
import android.view.View;
import android.view.ViewGroup;

import androidx.annotation.NonNull;

import com.waenhancer.xposed.core.BaseFeature;

import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;

/**
 * Hides WhatsApp's native Locked chats entry from the home conversation list.
 *
 * <p>WhatsApp 2.26.41.3 exposes the entry as a Button whose resource entry name is
 * {@code conversations_locked_header}. Hooking the exact view is more stable than attempting to
 * filter the conversation data list: the locked entry is a RecyclerView header, not a chat row.</p>
 */
public class HideChatsVaultHook extends BaseFeature {

    private static final String TAG = "[WAEX][HideChatsVault]";
    private static final String PREF_KEY = "hide_chats";
    private static final String LOCKED_HEADER_ID = "conversations_locked_header";

    private volatile int lockedHeaderViewId;

    public HideChatsVaultHook(@NonNull Context context,
                              @NonNull ClassLoader classLoader,
                              @NonNull SharedPreferences prefs) {
        super(context, classLoader, prefs);
    }

    @NonNull
    @Override
    public String getName() {
        return "Hide Locked Chats";
    }

    private boolean isHideChatsEnabled() {
        return isEnabled(PREF_KEY, false);
    }

    @Override
    public void hook() {
        lockedHeaderViewId = context.getResources().getIdentifier(
                LOCKED_HEADER_ID,
                "id",
                context.getPackageName()
        );

        XposedBridge.hookAllMethods(View.class, "onAttachedToWindow", new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                if (isHideChatsEnabled() && param.thisObject instanceof View) {
                    hideIfLockedHeader((View) param.thisObject);
                }
            }
        });

        // RecyclerView binding may restore the header after it has been attached. Force only this
        // exact WhatsApp view back to GONE whenever visibility is changed.
        XposedBridge.hookAllMethods(View.class, "setVisibility", new XC_MethodHook() {
            @Override
            protected void beforeHookedMethod(MethodHookParam param) {
                if (isHideChatsEnabled()
                        && param.thisObject instanceof View
                        && isLockedHeader((View) param.thisObject)) {
                    param.args[0] = View.GONE;
                    collapse((View) param.thisObject);
                }
            }
        });

        XposedBridge.log(TAG + " Hook active; header resource id=" + lockedHeaderViewId);
    }

    private void hideIfLockedHeader(View view) {
        if (!isLockedHeader(view)) return;

        collapse(view);
        if (view.getVisibility() != View.GONE) {
            view.setVisibility(View.GONE);
        }
        XposedBridge.log(TAG + " Hidden conversations_locked_header");
    }

    private boolean isLockedHeader(View view) {
        int viewId = view.getId();
        if (viewId == View.NO_ID) return false;
        if (lockedHeaderViewId != 0 && viewId == lockedHeaderViewId) return true;

        // Resource IDs vary between WhatsApp and WhatsApp Business builds.
        try {
            return LOCKED_HEADER_ID.equals(view.getResources().getResourceEntryName(viewId));
        } catch (Throwable ignored) {
            return false;
        }
    }

    private void collapse(View view) {
        ViewGroup.LayoutParams params = view.getLayoutParams();
        if (params != null && params.height != 0) {
            params.height = 0;
            view.setLayoutParams(params);
        }
    }
}
