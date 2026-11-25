package com.waenhancer.xposed.features.customization;

import android.app.Activity;
import android.content.Context;
import android.content.ContextWrapper;
import android.content.res.Resources;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.TransitionDrawable;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import com.waenhancer.fixture.FloatingExternalBoundaries;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import org.robolectric.android.controller.ActivityController;
import static org.junit.Assert.*;

/** Actual Android attachment/layout callbacks plus the current disposal method body. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk = {24, 28, 34}, manifest = Config.NONE)
public class FloatingBottomBarOwnershipTest {
    private static final int FAB_ID = 0x7f040001;
    private final List<ActivityController<Activity>> activities = new ArrayList<>();
    private final List<FloatingBottomBarHook> owners = new ArrayList<>();
    private ActivityController<Activity> activity;
    private Context context;
    private FrameLayout root;

    @Before public void setup() throws Exception {
        FloatingExternalBoundaries.calls.set(0);
        for (Field field : FloatingBottomBarHook.class.getDeclaredFields()) {
            if (Map.class.isAssignableFrom(field.getType())) {
                field.setAccessible(true);
                ((Map<?, ?>) field.get(null)).clear();
            }
        }
        activity = newActivity();
        Resources base = activity.get().getResources();
        Resources host = new Resources(base.getAssets(), base.getDisplayMetrics(), base.getConfiguration()) {
            @Override public int getIdentifier(String name, String type, String pkg) {
                return "fab".equals(name) && "id".equals(type) ? FAB_ID : 0;
            }
        };
        context = new ContextWrapper(activity.get()) {
            @Override public Resources getResources() { return host; }
        };
        root = new FrameLayout(context);
        activity.get().setContentView(root);
        layout(root, 400, 800);
        assertTrue(root.isAttachedToWindow());
    }

    @After public void teardown() {
        for (FloatingBottomBarHook owner : owners) owner.unhookAll();
        for (ActivityController<Activity> controller : activities) controller.pause().stop().destroy();
        assertEquals("No unmodelled host boundary may execute", 0, FloatingExternalBoundaries.calls.get());
    }

    @Test public void repeatedEmptyRequestsKeepOneListenerPair() throws Exception {
        CountingContainer bar = bar(root, 0);
        for (int i = 0; i < 100; i++) position(root, bar);
        assertEquals("one layout listener registration", 1, bar.layoutAdds);
        assertEquals("one detach listener registration", 1, bar.attachAdds);
        assertEquals(1, bar.layouts.size());
        assertEquals(1, bar.attaches.size());
        assertEquals(1, pending().size());
    }

    @Test public void positiveLayoutRemovesBothListenersAndPendingEntry() throws Exception {
        CountingContainer bar = bar(root, 0);
        View fab = fab(root);
        position(root, bar);
        bar.layout(0, 0, 400, 68);
        assertNoPending(bar);
        assertEquals(offset(bar), fab.getTranslationY(), 0.001f);
    }

    @Test public void detachmentRemovesBothListenersAndPendingEntry() throws Exception {
        CountingContainer bar = bar(root, 0);
        position(root, bar);
        root.removeView(bar);
        assertFalse(bar.isAttachedToWindow());
        assertNoPending(bar);
    }

    @Test public void detachedMeasuredContainerDoesNotMoveFab() throws Exception {
        CountingContainer bar = bar(root, 68);
        View fab = fab(root);
        root.removeView(bar);
        fab.setTranslationY(37f);
        position(root, bar);
        assertEquals(37f, fab.getTranslationY(), 0f);
        assertEquals(0, bar.layoutAdds);
        assertEquals(0, bar.attachAdds);
        assertNoPending(bar);
    }

    @Test public void aContainerInAnotherWindowIsNotRegistered() throws Exception {
        ActivityController<Activity> other = newActivity();
        FrameLayout otherRoot = new FrameLayout(other.get());
        other.get().setContentView(otherRoot);
        CountingContainer foreign = bar(otherRoot, 0);
        assertTrue(foreign.isAttachedToWindow());
        assertNotSame(root.getRootView(), foreign.getRootView());
        position(root, foreign);
        assertEquals(0, foreign.layoutAdds);
        assertEquals(0, foreign.attachAdds);
        assertNoPending(foreign);
    }

    @Test public void screenDisposalCancelsAnAttachedWaitBeforeItsLaterLayout() throws Exception {
        CountingContainer bar = bar(root, 0);
        View fab = fab(root);
        position(root, bar);
        owner().onScreenDisposed(activity.get());
        assertTrue("disposal is tested before Android detachment", bar.isAttachedToWindow());
        assertNoPending(bar);
        bar.layout(0, 0, 400, 68);
        assertEquals("disposed owner must not position later", 0f, fab.getTranslationY(), 0f);
    }

    @Test public void disposingOneWindowRetainsTheOtherWindowsWait() throws Exception {
        CountingContainer first = bar(root, 0);
        position(root, first);
        ActivityController<Activity> other = newActivity();
        FrameLayout otherRoot = new FrameLayout(context);
        other.get().setContentView(otherRoot);
        CountingContainer second = bar(otherRoot, 0);
        View secondFab = fab(otherRoot);
        position(otherRoot, second);
        assertEquals(2, pending().size());
        owner().onScreenDisposed(activity.get());
        assertNoPending(first);
        assertEquals("the other screen keeps its own callback", 1, second.layouts.size());
        assertEquals(1, second.attaches.size());
        assertTrue(pending().containsKey(second));
        second.layout(0, 0, 400, 68);
        assertEquals(offset(second), secondFab.getTranslationY(), 0.001f);
        assertNoPending(second);
    }

    @Test public void reattachmentCanRegisterOneFreshWait() throws Exception {
        CountingContainer bar = bar(root, 0);
        position(root, bar);
        root.removeView(bar);
        assertNoPending(bar);
        root.addView(bar);
        assertTrue(bar.isAttachedToWindow());
        position(root, bar);
        position(root, bar);
        assertEquals(2, bar.layoutAdds);
        assertEquals(2, bar.attachAdds);
        assertEquals(1, bar.layouts.size());
        assertEquals(1, bar.attaches.size());
        bar.layout(0, 0, 400, 68);
        assertNoPending(bar);
    }

    @Test public void changingTheRequestedRootReplacesTheOldWait() throws Exception {
        FrameLayout inner = new FrameLayout(context);
        root.addView(inner, new FrameLayout.LayoutParams(400, 800));
        CountingContainer bar = bar(inner, 0);
        position(root, bar);
        Object previous = bar.layouts.iterator().next();
        position(inner, bar);
        assertEquals(2, bar.layoutAdds);
        assertEquals(2, bar.attachAdds);
        assertEquals(1, bar.layouts.size());
        assertEquals(1, bar.attaches.size());
        assertFalse(bar.layouts.contains(previous));
        assertEquals(1, pending().size());
    }

    @Test public void repeatedScreenDisposalDoesNotLoseTransitionOwnership() throws Exception {
        View tab = new View(context);
        root.addView(tab);
        FloatingBottomBarHook owner = owner();
        for (int i = 0; i < 50; i++) {
            invoke("setTabChecked", new Class<?>[]{View.class, boolean.class}, tab, i % 2 == 0);
            owner.onScreenDisposed(activity.get());
        }
        assertTrue("weak ownership must still flatten WAEX history after disposal", depth(tab.getBackground()) <= 1);
    }

    private ActivityController<Activity> newActivity() {
        ActivityController<Activity> controller = Robolectric.buildActivity(Activity.class).setup().visible();
        activities.add(controller);
        return controller;
    }

    private FloatingBottomBarHook owner() {
        FloatingBottomBarHook hook = new FloatingBottomBarHook(context, getClass().getClassLoader(),
                activity.get().getSharedPreferences("floating-methods-test", Context.MODE_PRIVATE));
        owners.add(hook);
        return hook;
    }

    private CountingContainer bar(ViewGroup parent, int height) {
        CountingContainer bar = new CountingContainer(context);
        FrameLayout.LayoutParams params = new FrameLayout.LayoutParams(400, height);
        params.bottomMargin = 22;
        parent.addView(bar, params);
        layout(parent, 400, 800);
        return bar;
    }

    private View fab(ViewGroup parent) {
        View fab = new View(context);
        fab.setId(FAB_ID);
        parent.addView(fab, new FrameLayout.LayoutParams(40, 40));
        return fab;
    }

    private static float offset(ViewGroup bar) {
        return -(bar.getHeight() + ((ViewGroup.MarginLayoutParams) bar.getLayoutParams()).bottomMargin
                + 12f * bar.getResources().getDisplayMetrics().density);
    }

    private static void layout(View view, int width, int height) {
        view.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(height, View.MeasureSpec.EXACTLY));
        view.layout(0, 0, width, height);
    }

    private static void position(ViewGroup root, ViewGroup container) throws Exception {
        invoke("positionFabsAboveBar", new Class<?>[]{ViewGroup.class, ViewGroup.class}, root, container);
    }

    private static void invoke(String name, Class<?>[] types, Object... args) throws Exception {
        Method method = FloatingBottomBarHook.class.getDeclaredMethod(name, types);
        method.setAccessible(true);
        method.invoke(null, args);
    }

    private static Map<?, ?> pending() throws Exception {
        Field field = FloatingBottomBarHook.class.getDeclaredField("pendingFabLayouts");
        field.setAccessible(true);
        return (Map<?, ?>) field.get(null);
    }

    private static void assertNoPending(CountingContainer bar) throws Exception {
        assertEquals("layout callback removed", 0, bar.layouts.size());
        assertEquals("attachment callback removed", 0, bar.attaches.size());
        assertFalse("pending weak entry removed", pending().containsKey(bar));
    }

    private static int depth(Drawable drawable) {
        if (!(drawable instanceof TransitionDrawable)) return 0;
        TransitionDrawable transition = (TransitionDrawable) drawable;
        int maximum = 0;
        for (int i = 0; i < transition.getNumberOfLayers(); i++) maximum = Math.max(maximum, depth(transition.getDrawable(i)));
        return 1 + maximum;
    }

    private static final class CountingContainer extends FrameLayout {
        int layoutAdds, attachAdds;
        final Set<OnLayoutChangeListener> layouts = new HashSet<>();
        final Set<OnAttachStateChangeListener> attaches = new HashSet<>();
        CountingContainer(Context context) { super(context); }
        @Override public void addOnLayoutChangeListener(OnLayoutChangeListener listener) {
            layoutAdds++;
            layouts.add(listener);
            super.addOnLayoutChangeListener(listener);
        }
        @Override public void removeOnLayoutChangeListener(OnLayoutChangeListener listener) {
            layouts.remove(listener);
            super.removeOnLayoutChangeListener(listener);
        }
        @Override public void addOnAttachStateChangeListener(OnAttachStateChangeListener listener) {
            attachAdds++;
            attaches.add(listener);
            super.addOnAttachStateChangeListener(listener);
        }
        @Override public void removeOnAttachStateChangeListener(OnAttachStateChangeListener listener) {
            attaches.remove(listener);
            super.removeOnAttachStateChangeListener(listener);
        }
    }
}
