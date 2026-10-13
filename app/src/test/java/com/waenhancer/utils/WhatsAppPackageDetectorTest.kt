package com.waenhancer.utils

import org.junit.Assert.assertEquals
import org.junit.Test

class WhatsAppPackageDetectorTest {

    @Test
    fun `old same-boot injection is not active after verification restarts`() {
        assertEquals(
            RuntimeScopeState.PREVIOUSLY_ACTIVE,
            resolveRuntimeScopeState(
                isModuleActive = true,
                wasEverHooked = true,
                recordedBoot = 42,
                currentBoot = 42,
                lastActiveTime = 1_000L,
                verificationStartedAt = 2_000L
            )
        )
    }

    @Test
    fun `fresh target startup in current boot is active`() {
        assertEquals(
            RuntimeScopeState.ACTIVE_THIS_BOOT,
            resolveRuntimeScopeState(
                isModuleActive = true,
                wasEverHooked = true,
                recordedBoot = 42,
                currentBoot = 42,
                lastActiveTime = 2_001L,
                verificationStartedAt = 2_000L
            )
        )
    }

    @Test
    fun `fresh timestamp from another boot is not active`() {
        assertEquals(
            RuntimeScopeState.PREVIOUSLY_ACTIVE,
            resolveRuntimeScopeState(
                isModuleActive = true,
                wasEverHooked = true,
                recordedBoot = 41,
                currentBoot = 42,
                lastActiveTime = 2_001L,
                verificationStartedAt = 2_000L
            )
        )
    }

    @Test
    fun `never injected package is not detected`() {
        assertEquals(
            RuntimeScopeState.NOT_DETECTED,
            resolveRuntimeScopeState(
                isModuleActive = true,
                wasEverHooked = false,
                recordedBoot = 42,
                currentBoot = 42,
                lastActiveTime = 0L,
                verificationStartedAt = 2_000L
            )
        )
    }
}
