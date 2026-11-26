package com.waenhancer.utils

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TargetScopeStateTest {
    private fun profileProbe(output: String) = RootProbe.parseRuntime(output, 0L,
        mapOf("com.waenhancer" to 10000, "com.whatsapp" to 10123, "com.whatsapp.w4b" to 10124),
        "com.waenhancer", 99)

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

    @Test fun `process list parses modern ps output and skips header`() {
        val snap = parseProcessList("  PID NAME\n  101 com.example.chat\n  202 com.example.chat:service\n  303 zygote64\n  404 com.example.chat\n", 5L)
        assertEquals(setOf(101, 404), snap.pidsFor("com.example.chat"))
        assertEquals(emptySet<Int>(), snap.pidsFor("com.other.app")) // exhaustive: absent means not running
    }

    @Test fun `process list parses legacy toolbox layout`() {
        val snap = parseProcessList("USER PID PPID VSIZE RSS WCHAN PC NAME\nu0_a12 777 1 100 50 x 0 S com.example.chat\n", 5L)
        assertEquals(setOf(777), snap.pidsFor("com.example.chat"))
    }

    @Test fun `truncated process probe is not treated as nothing running`() {
        assertEquals(null, profileProbe("WAEX_PS_BEGIN\n 10123 1 com.whatsapp\n"))
        assertEquals(null, profileProbe(""))
    }

    @Test fun `process probe filters on the shell side and always includes the manager`() {
        val command = RootProbe.processListCommand()
        assertTrue(command.contains("com\\.whatsapp\\.w4b"))
        assertTrue(command.contains("com\\.waenhancer"))
        assertTrue(command.contains("grep -E"))
    }

    @Test fun `filtered process output with a target and the manager parses`() {
        val snap = profileProbe("WAEX_PS_BEGIN\n 10123 4242 com.whatsapp\n 10000 99 com.waenhancer\nWAEX_PS_END\n")
        assertEquals(setOf(4242), snap?.pidsFor("com.whatsapp"))
        assertEquals(emptySet<Int>(), snap?.pidsFor("com.whatsapp.w4b"))
    }

    @Test fun `UID-less complete process probe stays unavailable`() {
        val snap = profileProbe("WAEX_LSPOSED_DB_OK\nWAEX_PS_BEGIN\n 99 com.waenhancer\nWAEX_PS_END\n")
        assertEquals(null, snap)
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
