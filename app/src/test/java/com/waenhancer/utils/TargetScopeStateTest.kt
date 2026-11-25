package com.waenhancer.utils

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TargetScopeStateTest {
    private fun snap(live: Boolean, vararg pkgs: String, cache: Boolean = false) = LsposedScopeSnapshot(
        "com.waenhancer", pkgs.toSet(), live,
        when { live -> LsposedScopeSnapshot.Source.DATABASE; cache -> LsposedScopeSnapshot.Source.CACHE
            else -> LsposedScopeSnapshot.Source.UNAVAILABLE }
    )

    @Test fun `live scope containing target is in scope`() =
        assertEquals(TargetScopeState.IN_SCOPE, classifyScope("com.whatsapp", snap(true, "com.whatsapp"), false))

    @Test fun `live scope without target excludes it`() =
        assertEquals(TargetScopeState.NOT_IN_SCOPE, classifyScope("com.whatsapp", snap(true, "com.whatsapp.w4b"), false))

    @Test fun `unreadable scope never hides an installed target`() =
        assertEquals(TargetScopeState.UNVERIFIED, classifyScope("com.whatsapp", snap(false), false))

    @Test fun `stale cache without the target does not hide it`() =
        assertEquals(TargetScopeState.UNVERIFIED, classifyScope("com.whatsapp", snap(false, "com.whatsapp.w4b", cache = true), false))

    @Test fun `stale cache containing the target keeps it in scope`() =
        assertEquals(TargetScopeState.IN_SCOPE, classifyScope("com.whatsapp", snap(false, "com.whatsapp", cache = true), false))

    @Test fun `current injection overrides a live read that omits the target`() =
        assertEquals(TargetScopeState.INJECTED, classifyScope("com.whatsapp", snap(true), true))

    private fun app(hooked: Boolean) = HookedAppInfo("a.b", "A", "v1", true, hooked)

    @Test fun `manager hook marks module active`() {
        val r = ModuleActivation.resolve(true, emptyList())
        assertTrue(r.active); assertEquals(ModuleSignal.MANAGER_HOOK, r.signal)
    }

    @Test fun `no signal means inactive`() = assertFalse(ModuleActivation.resolve(false, listOf(app(false))).active)

    @Test fun `confirmed target injection proves module active without manager hook`() {
        val r = ModuleActivation.resolve(false, listOf(app(true)))
        assertTrue(r.active); assertEquals(ModuleSignal.TARGET_INJECTION, r.signal)
    }

    private val expectedUids = linkedMapOf("com.whatsapp" to 10200,
        "com.whatsapp.w4b" to 10300, "com.waenhancer" to 10100)

    @Test fun `uid process rows preserve explicit absence and unknown packages`() {
        val snap = parseProcessList("PID|com.example.chat|10200|101 404\nPID|com.other.app|10300|\n",
            mapOf("com.example.chat" to 10200, "com.other.app" to 10300), 5L)
        assertEquals(setOf(101, 404), snap.pidsFor("com.example.chat"))
        assertEquals(emptySet<Int>(), snap.pidsFor("com.other.app"))
        assertEquals(null, snap.pidsFor("com.unqueried.app"))
    }

    @Test fun `legacy toolbox rows without verified uid stay unknown`() {
        val snap = parseProcessList("USER PID PPID VSIZE RSS WCHAN PC NAME\nu0_a12 777 1 100 50 x 0 S com.example.chat\n",
            mapOf("com.example.chat" to 10200), 5L)
        assertFalse(snap.complete)
        assertEquals(null, snap.pidsFor("com.example.chat"))
    }

    @Test fun `truncated process probe is not treated as nothing running`() {
        assertEquals(null, RootProbe.parseRuntime("WAEX_PS_BEGIN\nPID|com.whatsapp|10200|1\n", expectedUids, 0L))
        assertEquals(null, RootProbe.parseRuntime("", expectedUids, 0L))
    }

    @Test fun `process command verifies profile uid and includes manager query`() {
        val command = RootProbe.processListCommand(expectedUids)
        assertTrue(command.contains("pidof 'com.whatsapp.w4b'"))
        assertTrue(command.contains("pidof 'com.waenhancer'"))
        assertTrue(command.contains("/proc/\$pid/status"))
        assertTrue(command.contains("set -f"))
        assertTrue(command.contains("'10300'"))
    }

    @Test fun `complete queried rows parse without overclaiming other packages`() {
        val snap = RootProbe.parseRuntime("WAEX_PS_BEGIN\nPID|com.whatsapp|10200|4242\nPID|com.whatsapp.w4b|10300|\nPID|com.waenhancer|10100|99\nWAEX_PS_END\n", expectedUids, 0L)
        assertEquals(setOf(4242), snap?.pidsFor("com.whatsapp"))
        assertEquals(emptySet<Int>(), snap?.pidsFor("com.whatsapp.w4b"))
        assertEquals(null, snap?.pidsFor("com.unqueried.app"))
    }

    @Test fun `omitted queried row never becomes a complete process observation`() {
        assertEquals(null, RootProbe.parseRuntime("WAEX_LSPOSED_DB_OK\nWAEX_PS_BEGIN\nPID|com.whatsapp|10200|9\nWAEX_PS_END\n", expectedUids, 0L))
    }

    @Test fun `scoped app outside the supported list is never a target`() {
        val out = WhatsAppPackageDetector.selectCandidates(setOf("com.whatsapp", "com.google.chrome", "com.waenhancer"), emptySet())
        assertEquals(listOf("com.whatsapp"), out)
    }

    @Test fun `supported app that is not in scope and has not reported is not a candidate`() {
        // Nothing scoped, nothing reported: the fixed list alone never makes a target.
        assertEquals(emptyList<String>(), WhatsAppPackageDetector.selectCandidates(emptySet(), emptySet()))
    }

    @Test fun `reported supported app is a candidate but a reported unsupported one is not`() {
        val out = WhatsAppPackageDetector.selectCandidates(emptySet(), setOf("com.whatsapp.w4b", "com.evil.app"))
        assertEquals(listOf("com.whatsapp.w4b"), out)
    }
}
