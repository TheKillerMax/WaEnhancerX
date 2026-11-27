package com.waenhancer.utils

import android.content.Context
import android.os.SELinux
import com.waenhancer.update.UpdateDownloader
import java.io.File
import java.util.concurrent.CancellationException
import kotlin.properties.Delegates
import kotlin.properties.ReadWriteProperty

// Screen projections instantiate unkeyed remembered fields once per screen instance.
fun <T> remember(init: () -> ReadWriteProperty<Any?, T>): ReadWriteProperty<Any?, T> = init()
fun <T> mutableStateOf(initial: T) = Delegates.observable(initial) { _, _, _ -> }
fun mutableIntStateOf(initial: Int) = mutableStateOf(initial)
object Dispatchers { object IO }
object Lifecycle { enum class Event { ON_PAUSE, ON_RESUME } }
data class Activation(val active: Boolean = false, val notification: Int = 0)
data class Target(val packageName: String)

abstract class Screen {
    val context = Context()
    var moduleActivation = Activation()
    var scopeSnapshot = 0
    var targetEpoch = 0
    var refreshEpoch = 0
    var activeTargets = emptyList<Target>()
    val reportedApps get() = activeTargets

    fun notifyTargets() {
        scopeSnapshot++
        targetEpoch++
        refreshEpoch++
        activeTargets = listOf(Target("fixture.target.$targetEpoch"))
        moduleActivation = moduleActivation.copy(notification = targetEpoch)
    }

    abstract val shown: SystemDiagnostics
    abstract fun render()
    abstract fun click()
    abstract fun lifecycle(event: Lifecycle.Event)
    abstract fun reset()

    // One diagnostics effect slot. Execute on key changes, not on every render.
    private var lastKeys: List<Any?>? = null
    fun LaunchedEffect(vararg keys: Any?, effect: () -> Unit) {
        if (keys.toList() != lastKeys) {
            lastKeys = keys.toList()
            effect()
        }
    }

    // Deterministic boundary between a finished read and delivery to the effect.
    var atHandoff: () -> Unit = {}
    fun <T> withContext(dispatcher: Dispatchers.IO, read: () -> T): T {
        val value = read()
        val handoff = atHandoff
        atHandoff = {}
        handoff()
        return value
    }
}

fun verify(hasReset: Boolean, create: () -> Screen) {
    require(runCatching { File("/sys/fs/selinux/enforce").readText() }.isFailure) {
        "Run on a host JVM where the production kernel SELinux path is unreadable"
    }
    SELinux.enforced = false
    val seeded = SystemDiagnosticsReader.read(Context(), false)
    check(seeded.selinux == "Permissive") { "Could not seed a known mode: $seeded" }
    val flags = UpdateDownloader.requests
    check(flags == listOf(false))
    flags.clear()
    SELinux.enforced = true
    val screen = create()
    check(screen.shown === seeded && flags.isEmpty()) { "Expected the fast cached snapshot before the effect" }

    fun read(label: String, force: Boolean, mode: String) {
        val start = flags.size
        screen.render()
        val calls = flags.drop(start)
        val data = screen.shown
        check(calls == listOf(force) && data.selinux == mode && data.moduleActive == screen.moduleActivation.active) {
            "REFRESH_ASSERT|$label| expected=$mode/[$force] got=${data.selinux}/$calls moduleActive=${data.moduleActive}"
        }
    }
    fun noRead(label: String) {
        val start = flags.size
        val before = screen.shown
        screen.render()
        check(flags.size == start && screen.shown === before) {
            "REFRESH_ASSERT|$label| unexpected inventory: flags=${flags.drop(start)}"
        }
    }
    fun changeModule() {
        screen.moduleActivation = screen.moduleActivation.copy(active = !screen.moduleActivation.active)
    }

    read("initial", false, "Permissive")
    screen.click()
    read("explicit", true, "Enforcing")
    noRead("recompose")
    screen.notifyTargets()
    noRead("target")
    SELinux.enforced = false
    changeModule()
    read("module", false, "Enforcing")
    screen.click()
    read("repeat", true, "Permissive")
    screen.lifecycle(Lifecycle.Event.ON_PAUSE)
    noRead("pause")
    SELinux.enforced = true
    screen.lifecycle(Lifecycle.Event.ON_RESUME)
    read("resume", true, "Enforcing")
    if (hasReset) {
        SELinux.enforced = false
        screen.reset()
        read("reset", true, "Permissive")
    }

    // The reader can finish (even updating its cache) without delivering to the UI.
    screen.click()
    SELinux.enforced = true
    val before = screen.shown
    val start = flags.size
    screen.atHandoff = { throw CancellationException("undelivered IO result") }
    try {
        screen.render()
        error("Expected cancellation at handoff")
    } catch (_: CancellationException) {
        check(screen.shown === before && flags.drop(start) == listOf(true))
    }
    SELinux.enforced = false
    changeModule()
    read("restart", true, "Permissive")

    // A click during a read isn't represented by that read's older generation.
    SELinux.enforced = true
    screen.click()
    screen.atHandoff = screen::click
    read("in flight", true, "Enforcing")
    SELinux.enforced = false
    read("queued", true, "Permissive")
    noRead("settled")
}
