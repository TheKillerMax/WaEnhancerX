package com.waenhancer.xposed.utils;

import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.ViewTreeObserver;
import com.waenhancer.xposed.core.ViewHookDispatcher;
import java.lang.ref.WeakReference;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.WeakHashMap;
import java.util.function.BooleanSupplier;

/** Reconciles resolved Views after host binding for one active feature owner. */
public final class ViewVisibilityGuard {
    private final BooleanSupplier enabled;
    private final WeakHashMap<View, WeakReference<Registration>> registrations = new WeakHashMap<>();
    private volatile boolean active = true;

    public ViewVisibilityGuard(Object owner, BooleanSupplier enabled) {
        this.enabled = Objects.requireNonNull(enabled);
        ViewHookDispatcher.onUnregistered(Objects.requireNonNull(owner), this::release);
    }

    public void bind(View view) {
        Objects.requireNonNull(view);
        Registration registration;
        synchronized (registrations) {
            if (!active) return;
            WeakReference<Registration> reference = registrations.get(view);
            registration = reference != null ? reference.get() : null;
            if (registration == null) {
                registration = new Registration(view);
                registrations.put(view, new WeakReference<>(registration));
                view.addOnAttachStateChangeListener(registration);
            }
        }
        registration.reconcile(view);
        if (view.isAttachedToWindow()) registration.onViewAttachedToWindow(view);
    }

    private void release() {
        List<WeakReference<Registration>> pending;
        synchronized (registrations) {
            active = false;
            pending = new ArrayList<>(registrations.values());
            registrations.clear();
        }
        for (WeakReference<Registration> reference : pending) {
            Registration registration = reference.get();
            if (registration != null) registration.release();
        }
    }

    private final class Registration implements View.OnAttachStateChangeListener,
            ViewTreeObserver.OnGlobalLayoutListener {
        private final WeakReference<View> owner;
        private WeakReference<ViewTreeObserver> observer = new WeakReference<>(null);

        Registration(View view) {
            owner = new WeakReference<>(view);
        }

        private void reconcile(View view) {
            // Reuse the feature's live global/scoped lookup. GONE preserves host LayoutParams.
            if (active && view.getVisibility() != View.GONE && enabled.getAsBoolean()) {
                view.setVisibility(View.GONE);
            }
        }

        @Override public void onViewAttachedToWindow(View view) {
            if (!active) {
                dispose(view);
                return;
            }
            ViewTreeObserver current = view.getViewTreeObserver();
            if (observer.get() != current) {
                removeObserver();
                if (current.isAlive()) {
                    current.addOnGlobalLayoutListener(this);
                    observer = new WeakReference<>(current);
                }
            }
            reconcile(view);
        }

        @Override public void onViewDetachedFromWindow(View view) {
            removeObserver();
            if (!active) view.removeOnAttachStateChangeListener(this);
        }

        @Override public void onGlobalLayout() {
            View view = owner.get();
            if (view == null || !view.isAttachedToWindow()) {
                removeObserver();
            } else if (!active) {
                dispose(view);
            } else {
                reconcile(view);
            }
        }

        private void release() {
            View view = owner.get();
            if (view == null) return;
            // unhookAll may run off the UI thread. The active flag already prevents hiding.
            if (Looper.myLooper() == Looper.getMainLooper()) dispose(view);
            else new Handler(Looper.getMainLooper()).post(() -> {
                View target = owner.get();
                if (target != null) dispose(target);
            });
        }

        private void dispose(View view) {
            removeObserver();
            view.removeOnAttachStateChangeListener(this);
        }

        private void removeObserver() {
            ViewTreeObserver previous = observer.get();
            if (previous != null && previous.isAlive()) previous.removeOnGlobalLayoutListener(this);
            observer.clear();
        }
    }
}
