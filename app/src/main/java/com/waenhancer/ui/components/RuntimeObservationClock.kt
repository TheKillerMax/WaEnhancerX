package com.waenhancer.ui.components

import android.os.SystemClock
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive

/** Cheap display-time invalidation; never polls root or scans installed applications. */
data class RuntimeObservationTime(val wall: Long, val elapsed: Long)

@Composable
fun rememberRuntimeObservationClock(): RuntimeObservationTime {
    val owner = LocalLifecycleOwner.current
    var now by remember { mutableStateOf(RuntimeObservationTime(System.currentTimeMillis(), SystemClock.elapsedRealtime())) }
    LaunchedEffect(owner) {
        owner.lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (isActive) {
                now = RuntimeObservationTime(System.currentTimeMillis(), SystemClock.elapsedRealtime())
                delay(5_000L)
            }
        }
    }
    return now
}
