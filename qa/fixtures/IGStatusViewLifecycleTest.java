package com.waenhancer.xposed.views;

import android.app.Activity;
import android.app.Application;
import android.content.Context;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.FrameLayout;
import android.widget.ListView;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.Robolectric;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.Shadows;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.LooperMode;
import java.time.Duration;
import com.waenhancer.xposed.features.customization.IGStatusHook;

import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = {24, 28, 34}, manifest = Config.NONE, application = Application.class)
@LooperMode(LooperMode.Mode.PAUSED)
public class IGStatusViewLifecycleTest {
    private Context context() {
        return RuntimeEnvironment.getApplication();
    }

    private static void layout(IGStatusView view, int height) {
        view.measure(View.MeasureSpec.makeMeasureSpec(400, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(height, View.MeasureSpec.EXACTLY));
        view.layout(0, 0, 400, height);
    }

    // Match the current hook's order: change layout parameters, assign translation,
    // then let Android measure/layout later. LayoutParams does not change getHeight().
    private static void applyCollapse(IGStatusView view, int visibleHeight, int fullHeight) {
        ViewGroup.LayoutParams params = view.getLayoutParams();
        params.height = visibleHeight;
        view.setLayoutParams(params);
        view.setTranslationY(visibleHeight - fullHeight);
    }

    @Test public void fullCollapseCanExpandBeforeNextLayout() {
        IGStatusView view = new IGStatusView(context());
        view.setLayoutParams(new ViewGroup.LayoutParams(400, 78));
        layout(view, 78);
        applyCollapse(view, 0, 78);
        layout(view, 0);
        assertEquals(0, view.getHeight());
        assertEquals(-78f, view.getTranslationY(), 0f);
        applyCollapse(view, 78, 78);
        assertEquals("height remains zero until the next Android layout", 0, view.getHeight());
        layout(view, 78);
        assertEquals("returning to the top must restore the row's origin", 0f, view.getTranslationY(), 0f);
        assertEquals(View.VISIBLE, view.getVisibility());
    }

    @Test public void translationBeforeFirstLayoutIsNotDiscarded() {
        IGStatusView view = new IGStatusView(context());
        assertEquals(0, view.getHeight());
        view.setTranslationY(-12f);
        layout(view, 78);
        assertEquals(-12f, view.getTranslationY(), 0f);
    }

    @Test public void partialCollapseKeepsTheRequestedTranslation() {
        IGStatusView view = new IGStatusView(context());
        view.setLayoutParams(new ViewGroup.LayoutParams(400, 78));
        layout(view, 78);
        for (int height : new int[] {60, 17, 77, 78}) {
            applyCollapse(view, height, 78);
            layout(view, height);
            assertEquals((float) height - 78f, view.getTranslationY(), 0f);
            assertEquals(View.VISIBLE, view.getVisibility());
        }
    }

    @Test public void aBurstOfRefreshesSharesOneAnimationCallback() {
        CountingHorizontal view = new CountingHorizontal(context());
        for (int index = 0; index < 10000; index++) view.refreshData();
        assertEquals("one pending frame still supplies the maintainer's second layout pass",
                1, view.framePosts);
    }

    @Test public void aBurstOfUpdatesBindsTheLatestAdapterStateOnce() {
        Activity activity = Robolectric.buildActivity(Activity.class).setup().get();
        CountingStatus view = new CountingStatus(activity);
        Rows adapter = new Rows(activity);
        view.setAdapter(adapter);
        activity.setContentView(view);
        drain();
        view.posts = 0;
        adapter.notifications = 0;
        for (int index = 0; index < 10000; index++) {
            adapter.version = index;
            view.updateList();
        }
        assertEquals(1, view.posts);
        drain();
        assertEquals(1, adapter.notifications);
        assertTrue("the row must already exist without a horizontal gesture",
                view.mStatusListView.getChildCount() > 0);
        assertEquals(9999, view.mStatusListView.getChildAt(0).getTag());
    }

    @Test public void listViewHeaderStillBindsWithoutAFirstGesture() {
        Activity activity = Robolectric.buildActivity(Activity.class).setup().get();
        IGStatusView status = new IGStatusView(activity);
        status.setLayoutParams(new ListView.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 78));
        Rows rows = new Rows(activity);
        status.setAdapter(rows);
        ListView chats = new ListView(activity);
        chats.addHeaderView(status);
        chats.setAdapter(new Rows(activity));
        activity.setContentView(chats);
        drain();
        assertTrue(status.mStatusListView.getChildCount() > 0);
        rows.version = 8;
        status.updateList();
        drain();
        assertEquals(8, status.mStatusListView.getChildAt(0).getTag());
    }

    @Test public void anUpdateDuringNotificationIsNotLost() {
        Activity activity = Robolectric.buildActivity(Activity.class).setup().get();
        CountingStatus status = new CountingStatus(activity);
        Rows rows = new Rows(activity);
        status.setAdapter(rows);
        activity.setContentView(status);
        drain();
        rows.notifications = 0;
        rows.onNotify = () -> {
            rows.onNotify = null;
            rows.version = 19;
            status.updateList();
        };
        status.updateList();
        drain();
        assertEquals(2, rows.notifications);
        assertEquals(19, status.mStatusListView.getChildAt(0).getTag());
    }

    @Test public void rejectedPostDoesNotDisableFutureUpdates() {
        Activity activity = Robolectric.buildActivity(Activity.class).setup().get();
        CountingStatus status = new CountingStatus(activity);
        Rows rows = new Rows(activity);
        status.setAdapter(rows);
        activity.setContentView(status);
        drain();
        status.rejectNext = true;
        status.updateList();
        rows.version = 24;
        status.updateList();
        drain();
        assertEquals(24, status.mStatusListView.getChildAt(0).getTag());
    }

    @Test public void detachedStatusDoesNotDeliverAnOldUpdate() {
        Activity activity = Robolectric.buildActivity(Activity.class).setup().get();
        FrameLayout parent = new FrameLayout(activity);
        CountingStatus status = new CountingStatus(activity);
        Rows rows = new Rows(activity);
        status.setAdapter(rows);
        parent.addView(status);
        activity.setContentView(parent);
        drain();
        rows.notifications = 0;
        status.updateList();
        parent.removeView(status);
        drain();
        assertEquals("a removed screen must not receive its queued refresh", 0, rows.notifications);
        rows.version = 37;
        parent.addView(status);
        status.updateList();
        drain();
        assertEquals(1, rows.notifications);
        assertEquals(37, status.mStatusListView.getChildAt(0).getTag());
    }

    @Test public void detachedHorizontalCancelsItsFrameAndCanRefreshAgain() {
        Activity activity = Robolectric.buildActivity(Activity.class).setup().get();
        FrameLayout parent = new FrameLayout(activity);
        CountingHorizontal view = new CountingHorizontal(activity);
        Rows rows = new Rows(activity);
        view.setAdapter(rows);
        parent.addView(view);
        activity.setContentView(parent);
        drain();
        view.refreshData();
        parent.removeView(view);
        view.forcedLayouts = 0;
        drain();
        assertEquals(0, view.forcedLayouts);
        rows.version = 63;
        parent.addView(view);
        view.refreshData();
        drain();
        assertEquals(63, view.getChildAt(0).getTag());
    }

    @Test public void rowsBoundWhileCollapsedRecoverTheirMeasuredHeight() {
        IGStatusView status = new IGStatusView(context());
        Rows rows = new Rows(context());
        status.setAdapter(rows);
        layout(status, 0);
        assertTrue(status.mStatusListView.getChildCount() > 0);
        assertEquals(0, status.mStatusListView.getChildAt(0).getMeasuredHeight());
        int binds = rows.binds;
        layout(status, 78);
        assertTrue("rows first bound while collapsed must be measured again on expansion",
                status.mStatusListView.getChildAt(0).getMeasuredHeight() > 0);
        assertEquals("remeasuring must not rebind rows or repeat adapter IO", binds, rows.binds);
    }

    @Test public void actualIgAdapterRecoversFromCollapsedMeasurementWithoutRebinding() {
        IGStatusHook.items.clear();
        IGStatusHook.items.add(null);
        try {
            IGStatusView reference = new IGStatusView(context());
            reference.setAdapter(new ActualRows(context()));
            layout(reference, 78);
            int expectedHeight = reference.mStatusListView.getChildAt(0).getMeasuredHeight();
            assertTrue(expectedHeight > 0);
            for (int initialHeight : new int[] {0, 17, 60, 78}) {
                IGStatusView status = new IGStatusView(context());
                ActualRows rows = new ActualRows(context());
                status.setAdapter(rows);
                layout(status, initialHeight);
                assertTrue(status.mStatusListView.getChildCount() > 0);
                int binds = rows.binds;
                layout(status, 78);
                assertEquals("the production row must recover its normal expanded measurement",
                        expectedHeight, status.mStatusListView.getChildAt(0).getMeasuredHeight());
                assertEquals(binds, rows.binds);
            }
        } finally {
            IGStatusHook.items.clear();
        }
    }

    private static void drain() {
        Shadows.shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(100));
    }

    private static class CountingHorizontal extends HorizontalListView {
        int framePosts, forcedLayouts;
        CountingHorizontal(Context context) { super(context); }
        @Override public void postOnAnimation(Runnable action) {
            framePosts++;
            super.postOnAnimation(action);
        }
        @Override public void forceLayout() {
            forcedLayouts++;
            super.forceLayout();
        }
    }

    private static class CountingStatus extends IGStatusView {
        int posts;
        boolean rejectNext;
        CountingStatus(Context context) { super(context); }
        @Override public boolean post(Runnable action) {
            posts++;
            if (rejectNext) {
                rejectNext = false;
                return false;
            }
            return super.post(action);
        }
    }

    private static class Rows extends BaseAdapter {
        final Context context;
        int version, notifications, binds;
        Runnable onNotify;
        Rows(Context context) { this.context = context; }
        @Override public int getCount() { return 8; }
        @Override public Object getItem(int index) { return index; }
        @Override public long getItemId(int index) { return index; }
        @Override public View getView(int position, View convertView, ViewGroup parent) {
            binds++;
            View row = convertView != null ? convertView : new View(context);
            row.setLayoutParams(new ViewGroup.LayoutParams(74, 54));
            row.setMinimumWidth(74);
            row.setMinimumHeight(54);
            row.setTag(version);
            return row;
        }
        @Override public void notifyDataSetChanged() {
            notifications++;
            super.notifyDataSetChanged();
            if (onNotify != null) onNotify.run();
        }
    }

    private static class ActualRows extends IGStatusAdapter {
        int binds;
        ActualRows(Context context) { super(context, Object.class, null); }
        @Override public View getView(int position, View convertView, ViewGroup parent) {
            binds++;
            return super.getView(position, convertView, parent);
        }
    }
}
