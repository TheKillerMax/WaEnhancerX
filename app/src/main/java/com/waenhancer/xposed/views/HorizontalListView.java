package com.waenhancer.xposed.views;

import android.content.Context;
import android.database.DataSetObserver;
import android.graphics.Rect;
import android.os.SystemClock;
import android.util.AttributeSet;
import android.view.GestureDetector;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewParent;
import android.widget.AdapterView;
import android.widget.ListAdapter;
import android.widget.Scroller;

import java.util.LinkedList;
import java.util.Queue;

public class HorizontalListView extends AdapterView<ListAdapter> {

    protected ListAdapter mAdapter;
    private int mLeftViewIndex = -1;
    private int mRightViewIndex = 0;
    protected int mCurrentX = 0;
    protected int mNextX = 0;
    private int mMaxX = Integer.MAX_VALUE;
    private int mDisplayOffset = 0;
    protected Scroller mScroller;
    private GestureDetector mGesture;
    private final Queue<View> mRemovedViewQueue = new LinkedList<>();
    private OnItemSelectedListener mOnItemSelected;
    private OnItemClickListener mOnItemClicked;
    private OnItemLongClickListener mOnItemLongClicked;
    private boolean mDataChanged = false;

    private final DataSetObserver mDataObserver = new DataSetObserver() {
        @Override
        public void onChanged() {
            synchronized (HorizontalListView.this) {
                mDataChanged = true;
            }
            invalidate();
            requestLayout();
        }

        @Override
        public void onInvalidated() {
            reset();
            invalidate();
            requestLayout();
        }
    };

    private final GestureDetector.OnGestureListener mOnGesture = new GestureDetector.SimpleOnGestureListener() {
        @Override
        public boolean onDown(MotionEvent event) {
            return HorizontalListView.this.onDown(event);
        }

        @Override
        public boolean onFling(MotionEvent first, MotionEvent second, float velocityX, float velocityY) {
            return HorizontalListView.this.onFling(first, second, velocityX, velocityY);
        }

        @Override
        public boolean onScroll(MotionEvent first, MotionEvent second, float distanceX, float distanceY) {
            ViewParent parent = getParent();
            if (parent != null) {
                parent.requestDisallowInterceptTouchEvent(true);
            }
            synchronized (HorizontalListView.this) {
                mNextX += (int) distanceX;
            }
            requestLayout();
            return true;
        }

        @Override
        public boolean onSingleTapConfirmed(MotionEvent event) {
            Rect viewRect = new Rect();
            for (int index = 0; index < getChildCount(); index++) {
                View child = getChildAt(index);
                viewRect.set(child.getLeft(), child.getTop(), child.getRight(), child.getBottom());
                if (viewRect.contains((int) event.getX(), (int) event.getY())) {
                    int itemPosition = mLeftViewIndex + 1 + index;
                    if (mOnItemClicked != null && mAdapter != null) {
                        mOnItemClicked.onItemClick(
                                HorizontalListView.this,
                                child,
                                itemPosition,
                                mAdapter.getItemId(itemPosition)
                        );
                    }
                    if (mOnItemSelected != null && mAdapter != null) {
                        mOnItemSelected.onItemSelected(
                                HorizontalListView.this,
                                child,
                                itemPosition,
                                mAdapter.getItemId(itemPosition)
                        );
                    }
                    MotionEvent motionEvent = MotionEvent.obtain(
                            SystemClock.uptimeMillis(),
                            SystemClock.uptimeMillis(),
                            MotionEvent.ACTION_DOWN,
                            event.getX() - child.getLeft(),
                            event.getY() - child.getTop(),
                            0
                    );
                    child.dispatchTouchEvent(motionEvent);
                    motionEvent.recycle();
                    child.performClick();
                    break;
                }
            }
            return true;
        }

        @Override
        public void onLongPress(MotionEvent event) {
            Rect viewRect = new Rect();
            for (int index = 0; index < getChildCount(); index++) {
                View child = getChildAt(index);
                viewRect.set(child.getLeft(), child.getTop(), child.getRight(), child.getBottom());
                if (viewRect.contains((int) event.getX(), (int) event.getY())) {
                    int itemPosition = mLeftViewIndex + 1 + index;
                    if (mOnItemLongClicked != null && mAdapter != null) {
                        mOnItemLongClicked.onItemLongClick(
                                HorizontalListView.this,
                                child,
                                itemPosition,
                                mAdapter.getItemId(itemPosition)
                        );
                    }
                    break;
                }
            }
        }
    };

    public HorizontalListView(Context context) {
        super(context);
        initView();
    }

    public HorizontalListView(Context context, AttributeSet attrs) {
        super(context, attrs);
        initView();
    }

    private void initView() {
        mLeftViewIndex = -1;
        mRightViewIndex = 0;
        mDisplayOffset = 0;
        mCurrentX = 0;
        mNextX = 0;
        mMaxX = Integer.MAX_VALUE;
        mScroller = new Scroller(getContext());
        mGesture = new GestureDetector(getContext(), mOnGesture);
    }

    @Override
    public void setOnItemSelectedListener(OnItemSelectedListener listener) {
        mOnItemSelected = listener;
    }

    @Override
    public void setOnItemClickListener(OnItemClickListener listener) {
        mOnItemClicked = listener;
    }

    @Override
    public void setOnItemLongClickListener(OnItemLongClickListener listener) {
        mOnItemLongClicked = listener;
    }

    @Override
    public ListAdapter getAdapter() {
        return mAdapter;
    }

    @Override
    public View getSelectedView() {
        return null;
    }

    @Override
    public void setAdapter(ListAdapter adapter) {
        if (mAdapter != null) {
            mAdapter.unregisterDataSetObserver(mDataObserver);
        }
        mAdapter = adapter;
        if (mAdapter != null) {
            mAdapter.registerDataSetObserver(mDataObserver);
        }
        reset();
    }

    private void reset() {
        initView();
        removeAllViewsInLayout();
        requestLayout();
    }

    @Override
    public void setSelection(int position) {
    }

    private void addAndMeasureChild(View child, int viewPosition) {
        LayoutParams params = child.getLayoutParams();
        if (params == null) {
            params = new LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT);
        }
        addViewInLayout(child, viewPosition, params, true);
        child.measure(
                MeasureSpec.makeMeasureSpec(getWidth(), MeasureSpec.AT_MOST),
                MeasureSpec.makeMeasureSpec(getHeight(), MeasureSpec.AT_MOST)
        );
    }

    private void fillList(int dx) {
        int edge = 0;
        View lastChild = getChildAt(getChildCount() - 1);
        if (lastChild != null) {
            edge = lastChild.getRight();
        }
        fillListRight(edge, dx);

        edge = 0;
        View firstChild = getChildAt(0);
        if (firstChild != null) {
            edge = firstChild.getLeft();
        }
        fillListLeft(edge, dx);
    }

    private void fillListRight(int rightEdge, int dx) {
        int edge = rightEdge;
        while (edge + dx < getWidth() && mAdapter != null && mRightViewIndex < mAdapter.getCount()) {
            View child = mAdapter.getView(mRightViewIndex, mRemovedViewQueue.poll(), this);
            addAndMeasureChild(child, -1);
            edge += child.getMeasuredWidth();

            if (mRightViewIndex == mAdapter.getCount() - 1) {
                mMaxX = mCurrentX + edge - getWidth();
            }
            if (mMaxX < 0) {
                mMaxX = 0;
            }
            mRightViewIndex++;
        }
    }

    private void fillListLeft(int leftEdge, int dx) {
        int edge = leftEdge;
        while (edge + dx > 0 && mLeftViewIndex >= 0 && mAdapter != null) {
            View child = mAdapter.getView(mLeftViewIndex, mRemovedViewQueue.poll(), this);
            addAndMeasureChild(child, 0);
            edge -= child.getMeasuredWidth();
            mLeftViewIndex--;
            mDisplayOffset -= child.getMeasuredWidth();
        }
    }

    private void removeNonVisibleItems(int dx) {
        View child = getChildAt(0);
        while (child != null && child.getRight() + dx <= 0) {
            mDisplayOffset += child.getMeasuredWidth();
            mRemovedViewQueue.offer(child);
            removeViewInLayout(child);
            mLeftViewIndex++;
            child = getChildAt(0);
        }

        child = getChildAt(getChildCount() - 1);
        while (child != null && child.getLeft() + dx >= getWidth()) {
            mRemovedViewQueue.offer(child);
            removeViewInLayout(child);
            mRightViewIndex--;
            child = getChildAt(getChildCount() - 1);
        }
    }

    private void positionItems(int dx) {
        if (getChildCount() > 0) {
            mDisplayOffset += dx;
            int left = mDisplayOffset;
            for (int index = 0; index < getChildCount(); index++) {
                View child = getChildAt(index);
                int childWidth = child.getMeasuredWidth();
                child.layout(left, 0, left + childWidth, child.getMeasuredHeight());
                left += childWidth;
            }
        }
    }

    public synchronized void scrollTo(int x) {
        mScroller.startScroll(mNextX, 0, x - mNextX, 0);
        requestLayout();
    }

    @Override
    public boolean dispatchTouchEvent(MotionEvent event) {
        switch (event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                requestParentIntercept(false);
                break;
            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_CANCEL:
                requestParentIntercept(true);
                break;
        }
        return mGesture.onTouchEvent(event);
    }

    private void requestParentIntercept(boolean allowIntercept) {
        ViewParent parent = getParent();
        if (parent != null) {
            parent.requestDisallowInterceptTouchEvent(!allowIntercept);
        }
    }

    protected boolean onFling(MotionEvent first, MotionEvent second, float velocityX, float velocityY) {
        synchronized (this) {
            mScroller.fling(mNextX, 0, (int) -velocityX, 0, 0, mMaxX, 0, 0);
        }
        requestLayout();
        return true;
    }

    protected boolean onDown(MotionEvent event) {
        mScroller.forceFinished(true);
        return true;
    }

    @Override
    protected synchronized void onLayout(boolean changed, int left, int top, int right, int bottom) {
        super.onLayout(changed, left, top, right, bottom);
        if (mAdapter == null) return;

        if (mDataChanged) {
            int oldCurrentX = mCurrentX;
            initView();
            removeAllViewsInLayout();
            mNextX = oldCurrentX;
            mDataChanged = false;
        }

        if (mScroller.computeScrollOffset()) {
            mNextX = mScroller.getCurrX();
        }
        if (mNextX <= 0) {
            mNextX = 0;
            mScroller.forceFinished(true);
        }
        if (mNextX >= mMaxX) {
            mNextX = mMaxX;
            mScroller.forceFinished(true);
        }

        int dx = mCurrentX - mNextX;
        removeNonVisibleItems(dx);
        fillList(dx);
        positionItems(dx);
        mCurrentX = mNextX;

        if (!mScroller.isFinished()) {
            post(this::requestLayout);
        }
    }
}
