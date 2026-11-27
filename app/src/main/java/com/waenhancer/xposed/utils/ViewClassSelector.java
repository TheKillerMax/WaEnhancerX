package com.waenhancer.xposed.utils;

import android.view.View;
import android.view.ViewGroup;

/** A string anchor alone must not select an arbitrary or ambiguous host object. */
public final class ViewClassSelector {
    private ViewClassSelector() {}

    public static Class<?> uniqueView(Iterable<Class<?>> candidates) {
        return uniqueAssignable(candidates, View.class);
    }

    public static Class<?> uniqueViewGroup(Iterable<Class<?>> candidates) {
        return uniqueAssignable(candidates, ViewGroup.class);
    }

    private static Class<?> uniqueAssignable(Iterable<Class<?>> candidates, Class<?> base) {
        Class<?> target = null;
        for (Class<?> candidate : candidates) {
            if (candidate == null || !base.isAssignableFrom(candidate)) continue;
            if (target != null && target != candidate) {
                throw new IllegalStateException("View selector matched multiple distinct Views");
            }
            target = candidate;
        }
        return target;
    }
}
