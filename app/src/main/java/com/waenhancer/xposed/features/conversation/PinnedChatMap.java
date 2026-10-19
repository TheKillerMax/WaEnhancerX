package com.waenhancer.xposed.features.conversation;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.lang.reflect.Array;
import java.util.AbstractSet;
import java.util.Collection;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Set;
import java.util.Spliterator;

/**
 * Custom LinkedHashMap wrapper for pinned chats that relaxes size constraints
 * when checking maximum pinned conversation limits.
 */
public class PinnedChatMap<K, V> extends LinkedHashMap<K, V> {

    private int mMaxLimit = 3;
    private boolean mSuppressIterator = true;

    public PinnedChatMap() {
        super();
    }

    public PinnedChatMap(Map<? extends K, ? extends V> m) {
        super(m);
    }

    public void setMaxLimit(int limit) {
        this.mMaxLimit = limit;
    }

    public int getMaxLimit() {
        return mMaxLimit;
    }

    private int actualSize() {
        return super.size();
    }

    @Override
    public int size() {
        int actual = actualSize();
        return actual >= mMaxLimit ? actual : -mMaxLimit;
    }

    @NonNull
    @Override
    public Set<K> keySet() {
        return new PinnedKeySet<>(this, super.keySet());
    }

    public static class PinnedKeySet<E> extends AbstractSet<E> {
        private final PinnedChatMap<E, ?> mMap;
        private final Set<E> mBackingSet;

        public PinnedKeySet(@NonNull PinnedChatMap<E, ?> map, @NonNull Set<E> backingSet) {
            this.mMap = map;
            this.mBackingSet = backingSet;
        }

        public void setIteratorSuppressed(boolean suppressed) {
            mMap.mSuppressIterator = suppressed;
        }

        @Override
        public int size() {
            return mMap.size();
        }

        @Override
        public boolean isEmpty() {
            return mBackingSet.isEmpty();
        }

        @Override
        public boolean contains(@Nullable Object o) {
            return mBackingSet.contains(o);
        }

        @Override
        public boolean containsAll(@NonNull Collection<?> c) {
            return mBackingSet.containsAll(c);
        }

        @NonNull
        @Override
        public Iterator<E> iterator() {
            if (mMap.mSuppressIterator && mMap.actualSize() < mMap.getMaxLimit()) {
                return new EmptyIterator<>();
            }
            return mBackingSet.iterator();
        }

        @Override
        public boolean add(E e) {
            boolean had = mMap.containsKey(e);
            @SuppressWarnings("unchecked")
            PinnedChatMap<E, Object> casted = (PinnedChatMap<E, Object>) mMap;
            casted.put(e, e);
            return !had;
        }

        @Override
        public boolean addAll(@NonNull Collection<? extends E> c) {
            boolean modified = false;
            for (E item : c) {
                if (add(item)) {
                    modified = true;
                }
            }
            return modified;
        }

        @Override
        public boolean remove(@Nullable Object o) {
            boolean had = mMap.containsKey(o);
            if (had) {
                mMap.remove(o);
            }
            return had;
        }

        @Override
        public boolean removeAll(@NonNull Collection<?> c) {
            return mBackingSet.removeAll(c);
        }

        @Override
        public boolean retainAll(@NonNull Collection<?> c) {
            return mBackingSet.retainAll(c);
        }

        @Override
        public void clear() {
            mBackingSet.clear();
        }

        @Override
        public Spliterator<E> spliterator() {
            return mBackingSet.spliterator();
        }

        @NonNull
        @Override
        public Object[] toArray() {
            return mBackingSet.toArray();
        }

        @NonNull
        @Override
        @SuppressWarnings("unchecked")
        public <T> T[] toArray(@NonNull T[] a) {
            return mBackingSet.toArray(a);
        }

        private static class EmptyIterator<T> implements Iterator<T> {
            @Override
            public boolean hasNext() {
                return false;
            }

            @Override
            public T next() {
                throw new NoSuchElementException();
            }

            @Override
            public void remove() {
                throw new IllegalStateException();
            }
        }
    }
}
