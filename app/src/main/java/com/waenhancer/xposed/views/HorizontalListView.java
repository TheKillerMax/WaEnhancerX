package com.waenhancer.xposed.views;

import android.content.Context;
import android.database.DataSetObserver;
import android.util.AttributeSet;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.view.ViewGroup;
import android.view.ViewParent;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ListAdapter;

/**
 * Adapter-backed horizontal row implemented on top of Android's native scroller.
 * WhatsApp can host this view in either a RecyclerView sibling or a ListView
 * header, so child attachment and drawing must not depend on a later touch-driven
 * layout pass.
 */
public class HorizontalListView extends HorizontalScrollView {

    private final LinearLayout content;
    private final int touchSlop;
    private ListAdapter adapter;
    private float downX;
    private float downY;
    private int reconcileAttempts;
    private final Runnable reconcileChildren = new Runnable() {
        @Override
        public void run() {
            if (!isAttachedToWindow()) return;

            int adapterCount = adapter != null ? adapter.getCount() : 0;
            if (content.getChildCount() != adapterCount) {
                rebuildChildren();
            }

            // WhatsApp can publish the status snapshot shortly after this row
            // attaches without dispatching another adapter notification.
            if (++reconcileAttempts < 50 && adapterCount <= 1) {
                postDelayed(this, 100L);
            }
        }
    };

    private final DataSetObserver dataObserver = new DataSetObserver() {
        @Override
        public void onChanged() {
            refreshData();
        }

        @Override
        public void onInvalidated() {
            refreshData();
        }
    };

    public HorizontalListView(Context context) {
        this(context, null);
    }

    public HorizontalListView(Context context, AttributeSet attrs) {
        super(context, attrs);
        setFillViewport(true);
        setHorizontalScrollBarEnabled(false);
        setOverScrollMode(OVER_SCROLL_NEVER);
        touchSlop = ViewConfiguration.get(context).getScaledTouchSlop();

        content = new LinearLayout(context);
        content.setOrientation(LinearLayout.HORIZONTAL);
        content.setGravity(android.view.Gravity.TOP);
        int topPadding = Math.round(6f * context.getResources().getDisplayMetrics().density);
        content.setPadding(0, topPadding, 0, 0);
        content.setClipToPadding(false);
        addView(content, new LayoutParams(
                LayoutParams.WRAP_CONTENT, LayoutParams.MATCH_PARENT));
    }

    public ListAdapter getAdapter() {
        return adapter;
    }

    public void setAdapter(ListAdapter newAdapter) {
        if (adapter == newAdapter) {
            refreshData();
            return;
        }
        if (adapter != null) {
            adapter.unregisterDataSetObserver(dataObserver);
        }
        adapter = newAdapter;
        if (adapter != null) {
            adapter.registerDataSetObserver(dataObserver);
        }
        refreshData();
    }

    public void refreshData() {
        post(this::rebuildChildren);
    }

    private void rebuildChildren() {
        int oldScrollX = getScrollX();
        content.removeAllViews();

        if (adapter != null) {
            for (int position = 0; position < adapter.getCount(); position++) {
                View child = adapter.getView(position, null, content);
                ViewGroup.LayoutParams params = child.getLayoutParams();
                if (params == null) {
                    params = new LinearLayout.LayoutParams(
                            LayoutParams.WRAP_CONTENT, LayoutParams.MATCH_PARENT);
                }
                content.addView(child, params);
            }
        }

        content.requestLayout();
        requestLayout();
        invalidate();
        post(() -> scrollTo(Math.min(oldScrollX,
                Math.max(0, content.getWidth() - getWidth())), 0));
    }

    @Override
    protected void onAttachedToWindow() {
        super.onAttachedToWindow();
        refreshData();
        reconcileAttempts = 0;
        removeCallbacks(reconcileChildren);
        post(reconcileChildren);
    }

    @Override
    protected void onDetachedFromWindow() {
        removeCallbacks(reconcileChildren);
        super.onDetachedFromWindow();
    }

    @Override
    public boolean dispatchTouchEvent(MotionEvent event) {
        switch (event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                downX = event.getX();
                downY = event.getY();
                // Keep WhatsApp's vertical RecyclerView from taking the stream
                // before HorizontalScrollView can classify the drag.
                requestParentIntercept(false);
                break;
            case MotionEvent.ACTION_MOVE:
                float dx = Math.abs(event.getX() - downX);
                float dy = Math.abs(event.getY() - downY);
                if (dx > touchSlop && dx > dy) {
                    requestParentIntercept(false);
                } else if (dy > touchSlop && dy > dx) {
                    // Once the gesture is clearly vertical, return it to
                    // WhatsApp's chat list so dragging on the stories area
                    // scrolls the main homepage normally.
                    requestParentIntercept(true);
                }
                break;
            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_CANCEL:
                requestParentIntercept(true);
                break;
        }
        return super.dispatchTouchEvent(event);
    }

    private void requestParentIntercept(boolean allowIntercept) {
        ViewParent parent = getParent();
        if (parent != null) {
            parent.requestDisallowInterceptTouchEvent(!allowIntercept);
        }
    }
}
