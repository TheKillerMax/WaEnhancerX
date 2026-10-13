package com.waenhancer.xposed.features.customization;

import static org.junit.Assert.assertEquals;

import java.util.Arrays;
import org.junit.Test;

public class SeparateGroupsTabPolicyTest {
    @Test
    public void replacesCommunitiesWithoutCreatingSixthTab() {
        assertEquals(
                Arrays.asList(200, 500, 300, 400, 700),
                SeparateGroupsTabPolicy.rewrite(Arrays.asList(200, 300, 600, 400, 700))
        );
    }

    @Test
    public void remainsIdempotent() {
        assertEquals(
                Arrays.asList(200, 500, 300, 400, 700),
                SeparateGroupsTabPolicy.rewrite(Arrays.asList(200, 500, 300, 400, 700))
        );
    }

    @Test
    public void refusesSixthTabWhenNoCommunitySlotExists() {
        assertEquals(
                Arrays.asList(100, 200, 300, 400, 700),
                SeparateGroupsTabPolicy.rewrite(Arrays.asList(100, 200, 300, 400, 700))
        );
    }
}
