package com.waenhancer.xposed.features.automation;

import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class PresenceStateStoreTest {
    @Test
    public void evictsOldPresenceEntries() {
        String prefix = "waex-test-" + System.nanoTime() + "-";
        for (int index = 0; index < 2050; index++) {
            PresenceStateStore.update(prefix + index + "@s.whatsapp.net", true);
        }

        assertTrue(PresenceStateStore.stateCount() <= 2048);
    }
}
