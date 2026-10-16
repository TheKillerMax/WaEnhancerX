package com.waenhancer.fixture

import android.os.SystemClock
import androidx.compose.runtime.*
import androidx.compose.runtime.snapshots.Snapshot
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.LifecycleRegistry
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.waenhancer.ui.components.RuntimeObservationTime
import com.waenhancer.ui.components.rememberRuntimeObservationClock
import com.waenhancer.utils.isRecentTimestamp
import kotlinx.coroutines.*
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.shadows.ShadowSystemClock
import java.time.Duration

private class EmptyApplier : AbstractApplier<Unit>(Unit) {
    override fun insertBottomUp(index: Int, instance: Unit) {}
    override fun insertTopDown(index: Int, instance: Unit) {}
    override fun remove(index: Int, count: Int) {}
    override fun move(from: Int, to: Int, count: Int) {}
    override fun onClear() {}
}
private class TestOwner : LifecycleOwner {
    val registry = LifecycleRegistry.createUnsafe(this)
    override val lifecycle: Lifecycle get() = registry
}

@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class StabilityClockTest {
    @Test fun freshBetweenPulsesAndLifecycleCancellation() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val owner = TestOwner().apply { registry.currentState = Lifecycle.State.STARTED }
        val clock = BroadcastFrameClock()
        val recomposer = Recomposer(coroutineContext + clock)
        val loop = launch(clock) { recomposer.runRecomposeAndApplyChanges() }
        val composition = Composition(EmptyApplier(), recomposer)
        val trigger = mutableStateOf(0)
        val seen = mutableListOf<RuntimeObservationTime>()
        var frame = 0L
        fun settle() {
            Snapshot.sendApplyNotifications()
            repeat(3) {
                runCurrent()
                Snapshot.sendApplyNotifications()
                clock.sendFrame(++frame * 16_000_000L)
                runCurrent()
                Snapshot.sendApplyNotifications()
            }
        }
        try {
            composition.setContent {
                CompositionLocalProvider(LocalLifecycleOwner provides owner) {
                    trigger.value
                    val observation = rememberRuntimeObservationClock()
                    SideEffect { seen.add(observation) }
                }
            }
            settle()
            assertTrue(seen.isNotEmpty())
            repeat(25) {
                ShadowSystemClock.advanceBy(Duration.ofMillis(101))
                val heartbeat = System.currentTimeMillis()
                trigger.value++
                settle()
                assertEquals("Clock reused a prior composition time", SystemClock.elapsedRealtime(), seen.last().elapsed)
                assertTrue("Fresh heartbeat was falsely future", isRecentTimestamp(heartbeat, seen.last().wall))
            }
            val now = seen.last()
            assertFalse(isRecentTimestamp(now.wall + 1L, now.wall))
            assertFalse(isRecentTimestamp(now.wall - 25_001L, now.wall))
            val beforePulse = seen.size
            advanceTimeBy(5_001L); settle()
            assertTrue("Periodic invalidation stopped", seen.size > beforePulse)
            owner.registry.currentState = Lifecycle.State.CREATED
            settle()
            val stopped = seen.size
            advanceTimeBy(15_001L); settle()
            assertEquals("Stopped lifecycle continued invalidating", stopped, seen.size)
            owner.registry.currentState = Lifecycle.State.STARTED
            settle()
            assertTrue("Resume did not restart invalidation", seen.size > stopped)
        } finally {
            composition.dispose()
            recomposer.cancel()
            loop.cancelAndJoin()
            owner.registry.currentState = Lifecycle.State.DESTROYED
            Dispatchers.resetMain()
        }
    }
}
