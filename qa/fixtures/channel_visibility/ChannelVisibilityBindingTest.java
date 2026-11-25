package com.waenhancer.xposed.features.customization;
import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import com.waenhancer.fixture.ChannelExternalBoundaries;
import com.waenhancer.xposed.core.devkit.DexSearchEngine;
import de.robv.android.xposed.XposedBridge;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import static org.junit.Assert.*;
@RunWith(RobolectricTestRunner.class)
@Config(sdk = {24, 28, 34}, manifest = Config.NONE)
public class ChannelVisibilityBindingTest {
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
        preferences = context.getSharedPreferences("view-hide", Context.MODE_PRIVATE);
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
    @Test public void channelRecommendationsAreHiddenAfterHostRebind() throws Throwable {
        installChannels();
        CountingView view = new ChannelView(context);
        XposedBridge.dispatchConstructor(view);
        root.addView(view);
        view.setVisibility(View.VISIBLE);
        root.getViewTreeObserver().dispatchOnGlobalLayout();
        assertEquals("host rebind must not restore enabled recommendations", View.GONE, view.getVisibility());
    }

    @Test public void channelHidingPreservesHostLayoutParameters() throws Throwable {
        installChannels();
        CountingView view = new ChannelView(context);
        ViewGroup.LayoutParams params = new FrameLayout.LayoutParams(190, 72);
        view.setLayoutParams(params);
        XposedBridge.dispatchConstructor(view);
        assertSame(params, view.getLayoutParams());
        assertEquals("GONE is enough; host width must survive", 190, params.width);
        assertEquals(72, params.height);
    }

    @Test public void missingChannelTargetIsReported() {
        DexSearchEngine.channelTarget = null;
        assertThrows(IllegalStateException.class, this::installChannels);
    }

    @Test public void nonViewChannelTargetIsRejected() {
        DexSearchEngine.channelTarget = Object.class;
        assertThrows(IllegalStateException.class, this::installChannels);
    }
    private void installChannels() {
        hook = new ChannelRecommendationsFilterHook(context, getClass().getClassLoader(), preferences);
        hook.hook();
    }
    public static class CountingView extends FrameLayout {
        int visibilityWrites;
        public CountingView(Context context) { super(context); }
        @Override public void setVisibility(int visibility) { visibilityWrites++; super.setVisibility(visibility); }
    }
    public static final class ChannelView extends CountingView { public ChannelView(Context c) { super(c); } }
}
