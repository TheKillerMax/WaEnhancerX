package com.waenhancer.xposed.views;

import android.content.Context;
import android.widget.FrameLayout;
import android.widget.ListAdapter;

import java.util.concurrent.atomic.AtomicBoolean;

public class IGStatusView extends FrameLayout {

    public HorizontalListView mStatusListView;
    public ListAdapter mStatusAdapter;
    public int fragmentId = 0;

    private final AtomicBoolean updateScheduled = new AtomicBoolean();
    private final Runnable updateListRunnable = () -> {
        // A refresh consumes the current adapter state, so requests received before
        // this UI turn can share it. Requests during the refresh get their own turn.
        updateScheduled.set(false);
        if (mStatusAdapter instanceof android.widget.BaseAdapter) {
            ((android.widget.BaseAdapter) mStatusAdapter).notifyDataSetChanged();
        }
        if (mStatusListView != null) {
            mStatusListView.refreshData();
        }
        requestLayout();
        invalidate();
    };

    public IGStatusView(Context context) {
        super(context);
        HorizontalListView statusListView = new HorizontalListView(context);
        statusListView.setLayoutParams(new LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT));
        mStatusListView = statusListView;
        addView(statusListView);
    }

    public ListAdapter getAdapter() {
        return mStatusAdapter;
    }

    public void setAdapter(ListAdapter adapter) {
        this.mStatusAdapter = adapter;
        if (adapter != null && mStatusListView != null) {
            mStatusListView.setAdapter(adapter);
            mStatusListView.refreshData();
        }
    }

    @Override
    protected void onAttachedToWindow() {
        super.onAttachedToWindow();
        if (mStatusListView != null && mStatusAdapter != null) {
            mStatusListView.refreshData();
        }
    }

    @Override
    protected void onDetachedFromWindow() {
        removeCallbacks(updateListRunnable);
        updateScheduled.set(false);
        super.onDetachedFromWindow();
    }

    public void updateList() {
        if (updateScheduled.compareAndSet(false, true) && !post(updateListRunnable)) {
            updateScheduled.set(false);
        }
    }
}
