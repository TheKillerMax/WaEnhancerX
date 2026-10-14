package com.waenhancer.xposed.features.customization;

import static org.junit.Assert.assertEquals;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import org.junit.Test;

public class TypedStyleHooksTest {
    @Test
    public void customDpiAcceptsResetAndSafeRange() {
        assertEquals(0, TypedStyleHookPolicy.parseDpi("0"));
        assertEquals(420, TypedStyleHookPolicy.parseDpi("420"));
        assertEquals(0, TypedStyleHookPolicy.parseDpi("119"));
        assertEquals(0, TypedStyleHookPolicy.parseDpi("invalid"));
    }

    @Test
    public void hiddenTabsAreRemovedWithoutChangingRemainingOrder() {
        ArrayList<Object> tabs = new ArrayList<>(Arrays.asList(200, 300, 600, 400));
        TypedStyleHookPolicy.filterTabIds(tabs, new HashSet<>(Arrays.asList(300, 400)));
        assertEquals(Arrays.asList(200, 600), tabs);
    }
}
