package com.waenhancer.xposed.views;

import android.content.Context;
import android.widget.FrameLayout;
import android.widget.ListAdapter;

public class IGStatusView extends FrameLayout {

    public HorizontalListView mStatusListView;
    public ListAdapter mStatusAdapter;
    public int fragmentId = 0;

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
    public void setTranslationY(float translationY) {
        if (getHeight() > 0) {
            int visibility = (translationY > (float) getHeight()) ? GONE : VISIBLE;
            if (visibility == VISIBLE) {
                super.setTranslationY(translationY);
            }
            setVisibility(visibility);
        }
    }

    public void updateList() {
        post(() -> {
            if (mStatusAdapter instanceof android.widget.BaseAdapter) {
                ((android.widget.BaseAdapter) mStatusAdapter).notifyDataSetChanged();
            }
            if (mStatusListView != null) {
                mStatusListView.refreshData();
            }
            requestLayout();
            invalidate();
        });
    }
}
