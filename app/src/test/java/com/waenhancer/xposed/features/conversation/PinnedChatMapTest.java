package com.waenhancer.xposed.features.conversation;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import java.util.Iterator;

public class PinnedChatMapTest {
    @Test
    public void spoofsSizeUntilExpandedLimitIsReached() {
        PinnedChatMap<String, String> map = new PinnedChatMap<>();
        map.setMaxLimit(60);
        map.put("one", "one");

        assertEquals(-60, map.size());
    }

    @Test
    public void iteratorSuppressionIsScopedToOneMap() {
        PinnedChatMap<String, String> first = mapWithOneEntry();
        PinnedChatMap<String, String> second = mapWithOneEntry();

        @SuppressWarnings("unchecked")
        PinnedChatMap.PinnedKeySet<String> firstKeys =
                (PinnedChatMap.PinnedKeySet<String>) first.keySet();
        firstKeys.setIteratorSuppressed(false);

        Iterator<String> firstIterator = first.keySet().iterator();
        Iterator<String> secondIterator = second.keySet().iterator();
        assertTrue(firstIterator.hasNext());
        assertFalse(secondIterator.hasNext());
    }

    private static PinnedChatMap<String, String> mapWithOneEntry() {
        PinnedChatMap<String, String> map = new PinnedChatMap<>();
        map.setMaxLimit(60);
        map.put("chat", "chat");
        return map;
    }
}
