package com.waenhancer.utils

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class WhatsAppPackageDetectorTest {

    @Test
    fun `scope and injection remain independent signals`() {
        val snapshot = XposedRuntimeSnapshot(
            scopeAvailable = true,
            scopedPackages = setOf("com.whatsapp"),
            runningPids = mapOf("com.whatsapp" to setOf(1234))
        )
        assertTrue(snapshot.scopeState("com.whatsapp") == RuntimeScopeState.IN_SCOPE)
        assertTrue(snapshot.scopeState("com.whatsapp.w4b") == RuntimeScopeState.NOT_IN_SCOPE)
    }

    @Test
    fun `runtime inspection output keeps scope and pids separate`() {
        val snapshot = parseXposedRuntimeSnapshot(
            "SCOPE|com.whatsapp\nSCOPE_STATUS|AVAILABLE\nPID|com.whatsapp|123 456\n",
            userId = 0
        )
        assertTrue(snapshot.scopeAvailable)
        assertTrue(snapshot.scopeState("com.whatsapp") == RuntimeScopeState.IN_SCOPE)
        assertTrue(snapshot.scopeState("com.whatsapp.w4b") == RuntimeScopeState.NOT_IN_SCOPE)
        assertTrue(snapshot.runningPids["com.whatsapp"] == setOf(123, 456))
    }

    @Test
    fun `failed scope lookup remains unavailable rather than out of scope`() {
        val snapshot = parseXposedRuntimeSnapshot(
            "SCOPE_STATUS|UNAVAILABLE\nPID|com.whatsapp|123\n",
            userId = 0
        )
        assertFalse(snapshot.scopeAvailable)
        assertTrue(snapshot.scopeState("com.whatsapp") == RuntimeScopeState.UNAVAILABLE)
    }

    @Test
    fun `Vector CLI scope output is filtered to current Android user`() {
        val output = """
            VECTOR_JSON_BEGIN
            {"success":true,"data":[{"APP_PACKAGE":"com.whatsapp","USER_ID":0},{"APP_PACKAGE":"com.whatsapp.w4b","USER_ID":10}]}
            VECTOR_JSON_END
            PID|com.whatsapp|123
        """.trimIndent()
        val snapshot = parseXposedRuntimeSnapshot(output, userId = 0)
        assertTrue(snapshot.scopeAvailable)
        assertTrue(snapshot.scopeState("com.whatsapp") == RuntimeScopeState.IN_SCOPE)
        assertTrue(snapshot.scopeState("com.whatsapp.w4b") == RuntimeScopeState.NOT_IN_SCOPE)
    }

    @Test
    fun `same process report in current boot is injected`() {
        assertTrue(
            hasCurrentInjection(
                isModuleActive = true,
                recordedBoot = 42,
                currentBoot = 42,
                reportedPid = 1234,
                runningPids = setOf(1234),
                lastActiveTime = 1_000L,
                now = 2_000L
            )
        )
    }

    @Test
    fun `stale process id and heartbeat are not injected`() {
        assertFalse(
            hasCurrentInjection(
                isModuleActive = true,
                recordedBoot = 42,
                currentBoot = 42,
                reportedPid = 1234,
                runningPids = setOf(5678),
                lastActiveTime = 1_000L,
                now = 30_001L
            )
        )
    }

    @Test
    fun `report from another boot is not injected`() {
        assertFalse(
            hasCurrentInjection(
                isModuleActive = true,
                recordedBoot = 41,
                currentBoot = 42,
                reportedPid = 1234,
                runningPids = setOf(1234),
                lastActiveTime = 1_000L,
                now = 2_000L
            )
        )
    }

    @Test
    fun `inactive module cannot report injected`() {
        assertFalse(
            hasCurrentInjection(
                isModuleActive = false,
                recordedBoot = 42,
                currentBoot = 42,
                reportedPid = 1234,
                runningPids = setOf(1234),
                lastActiveTime = 1_000L,
                now = 2_000L
            )
        )
    }

    @Test
    fun `fresh authenticated heartbeat confirms injection without root pid output`() {
        assertTrue(
            hasCurrentInjection(
                isModuleActive = true,
                recordedBoot = 42,
                currentBoot = 42,
                reportedPid = 1234,
                runningPids = emptySet(),
                lastActiveTime = 10_000L,
                now = 20_000L
            )
        )
    }

    @Test
    fun `stale heartbeat cannot confirm injection without a matching live pid`() {
        assertFalse(
            hasCurrentInjection(
                isModuleActive = true,
                recordedBoot = 42,
                currentBoot = 42,
                reportedPid = 1234,
                runningPids = emptySet(),
                lastActiveTime = 10_000L,
                now = 40_001L
            )
        )
    }
}
