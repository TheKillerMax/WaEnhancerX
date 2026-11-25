package com.waenhancer.xposed.features.customization;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewTreeObserver;
import android.widget.FrameLayout;
import com.waenhancer.fixture.ChannelExternalBoundaries;
import com.waenhancer.xposed.core.ViewHookDispatcher;
import com.waenhancer.xposed.core.devkit.DexSearchEngine;
import com.waenhancer.xposed.utils.ViewVisibilityGuard;
import de.robv.android.xposed.XposedBridge;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.List;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.Shadows;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = {24, 28, 34}, manifest = Config.NONE)
public class ChannelVisibilityLifecycleTest {
    private ActivityController<Activity> activity;
    private Context context;
    private SharedPreferences preferences;
    private FrameLayout root;
    private ChannelRecommendationsFilterHook hook;

    @Before public void setup() {
        activity = Robolectric.buildActivity(Activity.class).setup().visible();
        context = activity.get();
        root = new FrameLayout(context);
        activity.get().setContentView(root);
        preferences = context.getSharedPreferences("channel-lifecycle", Context.MODE_PRIVATE);
        preferences.edit().clear().putBoolean("channels_enhancements", true).commit();
        DexSearchEngine.reset();
        XposedBridge.reset();
        DexSearchEngine.channelTarget = ChannelView.class;
    }

    @After public void teardown() {
        if (hook != null) hook.unhookAll();
        activity.pause().stop().destroy();
        assertEquals("Unexpected external dependency", 0, ChannelExternalBoundaries.calls.get());
    }

    @Test public void disabledChannelAvoidsItsDexQuery() {
        preferences.edit().putBoolean("channels_enhancements", false).commit();
        install();
        assertEquals(0, DexSearchEngine.channelQueries);
        assertEquals(0, XposedBridge.constructorHookCount());
    }

    @Test public void scopedPreferenceHidesAndReconciles() throws Throwable {
        preferences.edit().remove("channels_enhancements")
                .putBoolean(context.getPackageName() + ":channels_enhancements", true).commit();
        install();
        ChannelView view = createTarget();
        assertEquals("current BaseFeature scoped key must apply on creation", View.GONE, view.getVisibility());
        root.addView(view);
        view.setVisibility(View.VISIBLE);
        root.getViewTreeObserver().dispatchOnGlobalLayout();
        assertEquals("current BaseFeature scoped key must apply on rebind", View.GONE, view.getVisibility());
    }

    @Test public void globalFalseOverridesScopedWhileInstalled() throws Throwable {
        preferences.edit().putBoolean(context.getPackageName() + ":channels_enhancements", true).commit();
        install();
        ChannelView view = createTarget();
        root.addView(view);
        preferences.edit().putBoolean("channels_enhancements", false).commit();
        view.setVisibility(View.VISIBLE);
        root.getViewTreeObserver().dispatchOnGlobalLayout();
        assertEquals("a scoped true must not override an explicit root false", View.VISIBLE, view.getVisibility());
    }

    @Test public void anotherTargetScopedKeyCannotEnableThisFeature() {
        preferences.edit().remove("channels_enhancements")
                .putBoolean("other.target:channels_enhancements", true).commit();
        install();
        assertEquals(0, DexSearchEngine.channelQueries);
        assertEquals(0, XposedBridge.constructorHookCount());
    }

    @Test public void liveToggleAllowsHostBindThenResumes() throws Throwable {
        install();
        ChannelView view = createTarget();
        root.addView(view);
        preferences.edit().putBoolean("channels_enhancements", false).commit();
        view.setVisibility(View.VISIBLE);
        root.getViewTreeObserver().dispatchOnGlobalLayout();
        assertEquals(View.VISIBLE, view.getVisibility());
        preferences.edit().putBoolean("channels_enhancements", true).commit();
        root.getViewTreeObserver().dispatchOnGlobalLayout();
        assertEquals(View.GONE, view.getVisibility());
    }

    @Test public void detachStopsReconciliationAndReattachResumes() throws Throwable {
        install();
        int before = listenerCount(root.getViewTreeObserver());
        ChannelView view = createTarget();
        root.addView(view);
        assertEquals(before + 1, listenerCount(root.getViewTreeObserver()));
        root.removeView(view);
        assertEquals("detach must remove its old observer immediately", before, listenerCount(root.getViewTreeObserver()));
        view.setVisibility(View.VISIBLE);
        root.getViewTreeObserver().dispatchOnGlobalLayout();
        assertEquals("old root must not mutate detached view", View.VISIBLE, view.getVisibility());
        root.addView(view);
        assertEquals(View.GONE, view.getVisibility());
        assertEquals(before + 1, listenerCount(root.getViewTreeObserver()));
    }

    @Test public void duplicateConstructorCallbacksRegisterOneGuard() throws Throwable {
        install();
        ChannelView view = createTarget();
        XposedBridge.dispatchConstructor(view);
        int before = listenerCount(root.getViewTreeObserver());
        root.addView(view);
        assertEquals("constructor chaining must retain one local observer", before + 1,
                listenerCount(root.getViewTreeObserver()));
        view.setVisibility(View.VISIBLE);
        view.visibilityWrites = 0;
        root.getViewTreeObserver().dispatchOnGlobalLayout();
        assertEquals(1, view.visibilityWrites);
    }

    @Test public void unchangedHiddenViewDoesNotWriteOnEveryLayout() throws Throwable {
        install();
        ChannelView view = createTarget();
        root.addView(view);
        view.visibilityWrites = 0;
        for (int i = 0; i < 100; i++) root.getViewTreeObserver().dispatchOnGlobalLayout();
        assertEquals("stable GONE is a no-op", 0, view.visibilityWrites);
    }

    @Test public void unrelatedViewsAndHostParametersSurvive() throws Throwable {
        install();
        FrameLayout unrelated = new FrameLayout(context);
        XposedBridge.dispatchConstructor(unrelated);
        root.addView(unrelated);
        ChannelView view = new ChannelView(context);
        ViewGroup.LayoutParams layout = new FrameLayout.LayoutParams(173, 91);
        view.setLayoutParams(layout);
        XposedBridge.dispatchConstructor(view);
        root.addView(view);
        for (int i = 0; i < 5; i++) {
            view.setVisibility(View.VISIBLE);
            root.getViewTreeObserver().dispatchOnGlobalLayout();
        }
        assertEquals(View.VISIBLE, unrelated.getVisibility());
        assertSame(layout, view.getLayoutParams());
        assertEquals(173, layout.width);
        assertEquals(91, layout.height);
    }

    @Test public void unhookReleasesExistingObserversAndConstructors() throws Throwable {
        install();
        int before = listenerCount(root.getViewTreeObserver());
        ChannelView view = createTarget();
        root.addView(view);
        assertEquals(1, XposedBridge.constructorHookCount());
        hook.unhookAll();
        assertEquals("real HookRegistrar must own the Kotlin callback", 0, XposedBridge.constructorHookCount());
        assertEquals("owner release must remove local observers", before, listenerCount(root.getViewTreeObserver()));
        view.setVisibility(View.VISIBLE);
        root.getViewTreeObserver().dispatchOnGlobalLayout();
        assertEquals("released owner cannot keep hiding an old view", View.VISIBLE, view.getVisibility());
        ChannelView later = createTarget();
        root.addView(later);
        assertEquals(View.VISIBLE, later.getVisibility());
    }

    @Test public void backgroundUnhookStopsBeforePostedCleanup() throws Throwable {
        install();
        int before = listenerCount(root.getViewTreeObserver());
        ChannelView view = createTarget();
        root.addView(view);
        Thread release = new Thread(hook::unhookAll, "channel-owner-release");
        release.start();
        release.join(2000);
        assertFalse("owner release must finish without waiting for the UI", release.isAlive());
        view.setVisibility(View.VISIBLE);
        root.getViewTreeObserver().dispatchOnGlobalLayout();
        assertEquals("inactive barrier must precede posted cleanup", View.VISIBLE, view.getVisibility());
        Shadows.shadowOf(Looper.getMainLooper()).idle();
        assertEquals(before, listenerCount(root.getViewTreeObserver()));
    }

    @Test public void releasedDetachedViewCannotResumeOnReattach() throws Throwable {
        install();
        ChannelView view = createTarget();
        root.addView(view);
        root.removeView(view);
        hook.unhookAll();
        int before = listenerCount(root.getViewTreeObserver());
        view.setVisibility(View.VISIBLE);
        root.addView(view);
        root.getViewTreeObserver().dispatchOnGlobalLayout();
        assertEquals(View.VISIBLE, view.getVisibility());
        assertEquals(before, listenerCount(root.getViewTreeObserver()));
    }

    @Test public void backgroundReleaseRemovesDetachedListenerWithoutReattach() throws Throwable {
        install();
        ChannelView view = createTarget();
        assertFalse(view.isAttachedToWindow());
        assertEquals(1, attachListenerCount(view));
        Thread release = new Thread(hook::unhookAll, "detached-channel-owner-release");
        release.start();
        release.join(2000);
        assertFalse("owner release must not wait for a future attach", release.isAlive());
        Shadows.shadowOf(Looper.getMainLooper()).idle();
        assertEquals("a cached detached view must release its feature listener", 0, attachListenerCount(view));
    }

    @Test public void movingToAnotherWindowDropsThePreviousObserver() throws Throwable {
        install();
        ChannelView view = createTarget();
        int firstBefore = listenerCount(root.getViewTreeObserver());
        root.addView(view);
        ViewTreeObserver first = root.getViewTreeObserver();
        ActivityController<Activity> second = Robolectric.buildActivity(Activity.class).setup().visible();
        try {
            FrameLayout secondRoot = new FrameLayout(second.get());
            second.get().setContentView(secondRoot);
            root.removeView(view);
            int secondBefore = listenerCount(secondRoot.getViewTreeObserver());
            view.setVisibility(View.VISIBLE);
            secondRoot.addView(view);
            assertNotSame(first, secondRoot.getViewTreeObserver());
            assertEquals(firstBefore, listenerCount(first));
            assertEquals(secondBefore + 1, listenerCount(secondRoot.getViewTreeObserver()));
            view.setVisibility(View.VISIBLE);
            secondRoot.getViewTreeObserver().dispatchOnGlobalLayout();
            assertEquals(View.GONE, view.getVisibility());
        } finally {
            second.pause().stop().destroy();
        }
    }

    @Test public void ownerCleanupIsIndependentAndIdempotent() throws Exception {
        Object first = new Object(), second = new Object();
        ViewVisibilityGuard left = new ViewVisibilityGuard(first, () -> true);
        ViewVisibilityGuard right = new ViewVisibilityGuard(second, () -> true);
        ChannelView a = new ChannelView(context), b = new ChannelView(context);
        int before = listenerCount(root.getViewTreeObserver());
        left.bind(a); right.bind(b); root.addView(a); root.addView(b);
        assertEquals(before + 2, listenerCount(root.getViewTreeObserver()));
        ViewHookDispatcher.unregister(first);
        ViewHookDispatcher.unregister(first);
        a.setVisibility(View.VISIBLE); b.setVisibility(View.VISIBLE);
        root.getViewTreeObserver().dispatchOnGlobalLayout();
        assertEquals(View.VISIBLE, a.getVisibility());
        assertEquals(View.GONE, b.getVisibility());
        assertEquals(before + 1, listenerCount(root.getViewTreeObserver()));
        ViewHookDispatcher.unregister(second);
        assertEquals(before, listenerCount(root.getViewTreeObserver()));
    }

    @Test public void validatedSelectorUsesASeparateCacheEntry() {
        install();
        assertEquals("unchecked first-match cache entries must not bypass the new policy",
                "waex_channel_rec_view_class_v2", DexSearchEngine.lastKey);
    }

    private void install() {
        hook = new ChannelRecommendationsFilterHook(context, getClass().getClassLoader(), preferences);
        hook.hook();
    }
    private ChannelView createTarget() throws Throwable {
        ChannelView view = new ChannelView(context);
        XposedBridge.dispatchConstructor(view);
        return view;
    }
    private static int listenerCount(ViewTreeObserver observer) throws Exception {
        Field field = ViewTreeObserver.class.getDeclaredField("mOnGlobalLayoutListeners");
        field.setAccessible(true);
        Object listeners = field.get(observer);
        if (listeners == null) return 0;
        Method size = listeners.getClass().getDeclaredMethod("size");
        size.setAccessible(true);
        return (Integer) size.invoke(listeners);
    }
    private static int attachListenerCount(View view) throws Exception {
        Field field = View.class.getDeclaredField("mListenerInfo");
        field.setAccessible(true);
        Object info = field.get(view);
        if (info == null) return 0;
        Field listeners = info.getClass().getDeclaredField("mOnAttachStateChangeListeners");
        listeners.setAccessible(true);
        List<?> values = (List<?>) listeners.get(info);
        return values == null ? 0 : values.size();
    }
    public static final class ChannelView extends FrameLayout {
        int visibilityWrites;
        public ChannelView(Context context) { super(context); }
        @Override public void setVisibility(int visibility) { visibilityWrites++; super.setVisibility(visibility); }
    }
}
