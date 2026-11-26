package com.waenhancer.xposed.features.conversation

import android.content.Context
import android.content.DialogInterface
import android.widget.CheckBox
import com.waenhancer.xposed.core.HookRegistrar
import com.waenhancer.xposed.core.devkit.DexCacheManager
import de.robv.android.xposed.XC_MethodHook.MethodHookParam
import de.robv.android.xposed.XposedBridge as X
import java.lang.reflect.Constructor
import java.lang.reflect.Field
import java.lang.reflect.Member
import java.lang.reflect.Method
import java.util.concurrent.Callable
import java.util.concurrent.CyclicBarrier
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [24, 28, 34], manifest = Config.NONE)
class DeleteOriginTest {
    class Owner {
        fun build(c: Context, a: Any, b: Any, d: Any, s: String, items: Set<*>, n: Int, flag: Boolean): Any = this
        fun oldEntry() {}
        override fun equals(other: Any?) = other is Owner
        override fun hashCode() = 7
    }
    class Jid(val raw: String)
    class Key(val id: String, val chat: Jid, val direction: Boolean)
    class Msg(val key: Key)
    class Ambiguous(val own: Key, val quoted: Key?)
    class Api {
        var calls = 0
        var scoped = false
        var body: () -> Unit = {}
        fun local(n: Int?, selection: Collection<*>, one: Boolean, two: Boolean) {
            calls++; scoped = PreserveDeleteForMeHook.isDeleteForMeInProgress(); body()
        }
    }
    class Job(var selection: Any, var owner: Any, a: Any?, b: Any?, c: Any?, n: Int, x: Boolean, y: Boolean) : Runnable {
        val api = Api()
        var arg: Collection<*>? = null
        var limit = false
        var prefix: () -> Unit = {}
        override fun equals(other: Any?) = other is Job
        override fun hashCode() = 1
        override fun run() {
            prefix()
            val s = arg ?: selection as Set<*>
            if (limit && s.size > 999) return
            val p = X.fireBefore(endpoint, api, arrayOf(null, s, false, false))
            original(p) { api.local(null, s, false, false) }
        }
    }
    class Listener(box: CheckBox?, a: Any?, b: Any?, c: Any?, val owner: Owner, n: Int?,
                   val items: Set<*>, x: Boolean, y: Boolean) : DialogInterface.OnClickListener {
        var prefix: () -> Unit = {}
        var scheduled: (Job) -> Unit = {}
        var ctorError = false
        var useOwner: Any = owner
        var useItems: Any = items
        override fun onClick(d: DialogInterface?, which: Int) {
            prefix()
            val j = job(useItems as Set<*>, useOwner as Owner)
            val p = X.fireBefore(ctor, j, arrayOf(useItems, useOwner, null, null, null, 77, false, false))
            if (ctorError) p.throwable = IllegalArgumentException()
            X.fireAfter(p)
            scheduled(j)
        }
    }
    companion object {
        private val build = Owner::class.java.declaredMethods.single { it.name == "build" }
        private val old = Owner::class.java.getDeclaredMethod("oldEntry")
        private val lc = Listener::class.java.declaredConstructors.single()
        private val click = Listener::class.java.getDeclaredMethod("onClick", DialogInterface::class.java, Integer.TYPE)
        private val ctor = Job::class.java.declaredConstructors.single()
        private val run = Job::class.java.getDeclaredMethod("run")
        private val endpoint = Api::class.java.declaredMethods.single { it.name == "local" }
        private fun job(s: Set<*>, o: Owner) = Job(s, o, null, null, null, 77, false, false)
        private fun drive(j: Job) {
            original(X.fireBefore(run, j, emptyArray())) { j.run() }
        }
        private fun press(l: Listener) {
            val w = DialogInterface.BUTTON_NEGATIVE
            val p = X.fireBefore(click, l, arrayOf(null, w))
            original(p) { l.onClick(null, w) }
        }

        // Observe the outcome AFTER reverse dispatch, including replacement of a host exception.
        private inline fun original(p: MethodHookParam, body: () -> Unit) {
            if (!p.resultWasSet) try { body() } catch (t: Throwable) { p.throwable = t }
            X.fireAfter(p)
            p.throwable?.let { throw it }
        }

        @JvmName("installLocal")
        internal fun installLocal(hook: PreserveDeleteForMeHook, keys: SelectedKeys) {
            hook.install(Index(), true, keys)
        }

        fun installStore(hook: PreserveDeleteForMeHook, entry: Method) {
            val code = Index()
            code.tags.clear()
            code.tags[entry] = listOf("CoreMessageStore/deleteMessageForMe")
            hook.install(code, false, null)
        }

        fun request(items: Set<*>, body: Runnable) {
            val l = Listener(null, null, null, null, Owner(), null, items, false, true)
            l.scheduled = { j -> j.api.body = body::run; drive(j) }
            press(l)
        }

        fun unselected(items: Set<*>, body: Runnable) {
            val j = job(items, Owner())
            j.api.body = body::run
            drive(j)
        }
    }
    // The two alias slots on Listener exist only to feed bad constructor arguments. Keep them
    // type-erased in the instruction model AND avoid a second declared owner/Set field in the host.
    private class Index : DeleteCode {
        val tags = mutableMapOf< Member, List<String>>(build to listOf("dialog/delete no messages", "pref_delete_media"),
            endpoint to listOf("UserActionsMessageDeletion/userActionDeleteMessages "))
        val edges = mutableMapOf<Method, List<Member>>(build to listOf(lc), click to listOf(ctor), run to listOf(endpoint))
        val listenerFields = setOf("owner", "items").map { Listener::class.java.getDeclaredField(it) }.toSet()
        val jobFields = setOf("owner", "selection").map { Job::class.java.getDeclaredField(it) }.toSet()
        override fun tagged(exact: Boolean, vararg strings: String): List<Member> = tags.filterValues { body ->
            strings.all { s -> body.any { if (exact) it == s else it.contains(s) } }
        }.keys.toList()
        override fun invokes(method: Method) = edges[method].orEmpty()
        override fun callers(ctor: Constructor<*>): Set<Member> = edges.filterValues { ctor in it }.keys
        override fun fields(member: Member, write: Boolean): Set<Field> = when {
            member == lc && write || member == click && !write -> listenerFields
            member == ctor && write || member == run && !write -> jobFields
            else -> emptySet()
        }
    }
    private lateinit var ctx: Context
    private lateinit var hook: PreserveDeleteForMeHook
    private lateinit var code: Index
    private val reads = AtomicInteger()
    private var readerError = false
    private val key = Key("synthetic", Jid("test@g.us"), false)
    private val batch = linkedSetOf(Msg(key))
    private val prefs get() = ctx.getSharedPreferences("origin-only", Context.MODE_PRIVATE)
    private val reader = SelectedKeys.unique(Msg::class.java, Key::class.java, Jid::class.java) {
        reads.incrementAndGet(); if (readerError) error("synthetic capture fault"); (it as Jid).raw
    }!!
    private fun listener(s: Set<*> = batch) = Listener(null, null, null, null, Owner(), null, s, false, true)
    private fun feature() = PreserveDeleteForMeHook(ctx, javaClass.classLoader!!, prefs)
    @Before fun setup() {
        ctx = RuntimeEnvironment.getApplication(); prefs.edit().putBoolean("preserve_delete_for_me", true).commit()
        X.reset(); code = Index(); hook = feature(); ctx.deleteDatabase("msgstore.db")
    }
    @After fun cleanup() { hook.unhookAll(); X.reset(); ctx.deleteDatabase("msgstore.db") }
    private fun install() { hook.beginHookTracking(); try { hook.install(code, true, reader) } finally { hook.endHookTracking() } }
    private fun scheduled(l: Listener = listener()): Job {
        lateinit var j: Job; l.scheduled = { j = it }; press(l); return j
    }
    private fun expect(j: Job, local: Boolean) {
        val n = j.api.calls; drive(j); assertEquals(n + 1, j.api.calls); assertEquals(local, j.api.scoped)
        assertFalse(PreserveDeleteForMeHook.isDeleteForMeInProgress())
    }

    @Test fun unresolvedDoesNotInstallAndV7CannotStandInForGraph() {
        DexCacheManager.getInstance(ctx).getMethod(javaClass.classLoader!!, "waex_delete_for_me_method_v7") { run }
        val e = assertThrows(IllegalStateException::class.java) { hook.install(code, true, null) }
        assertEquals("Delete-for-me selected message key contract unavailable", e.message); assertTrue(X.hooks.isEmpty())
        hook.unhookAll(); hook = feature()
        val cachedOnly = assertThrows(IllegalStateException::class.java) { hook.hook() }
        assertEquals("Delete-for-me entry point unavailable", cachedOnly.message)
        assertTrue(X.hooks.isEmpty())
        code.tags.clear()
        code.tags[run] = listOf("msgstore/delete-for-me")
        assertNull(DeleteRoute.resolve(code, true)) // a bare run isn't the direct store entry either
    }
    @Test fun brokenGraphsNeverRegisterEvenWithASyntheticReader() {
        val markers = listOf("SYNTHETIC-PRIVATE-PAYLOAD-6719", "synthetic local-delete text",
            "12345@g.us", "audit-selected-key", "SELECT audit_private FROM message")
        val brokenIndex = object : DeleteCode by code {
            override fun invokes(method: Method): List<Member> {
                throw IllegalArgumentException(markers.joinToString())
            }
        }
        val failure = assertThrows(Throwable::class.java) { hook.install(brokenIndex, true, reader) }
        // Model both failure sinks in FeatureRegistry.installLocked, including stack/cause rendering.
        val metadata = failure.message ?: failure.javaClass.name
        X.log("[WAEX] Error initializing feature [${hook.name}]: $metadata")
        X.log(failure)
        assertTrue("Resolver diagnostics disclosed fixture data", markers.none { value ->
            value in metadata || X.logs.any { value in it }
        })
        assertTrue(failure is IllegalStateException && failure.cause == null && failure.suppressed.isEmpty())
        assertEquals("Delete-for-me route search failed: IllegalArgumentException", metadata)
        assertTrue(X.hooks.isEmpty())
        assertFalse(PreserveDeleteForMeHook.isDeleteForMeInProgress())

        val both = code.tags.getValue(build)
        fun reject() {
            val absent = assertThrows(IllegalStateException::class.java) { install() }
            assertEquals("Delete-for-me entry point unavailable", absent.message)
            assertTrue(X.hooks.isEmpty())
        }
        code.tags[old] = both; reject()
        code.tags[build] = both.take(1); code.tags[old] = both.drop(1); reject()
        code = Index(); code.edges[old] = listOf(lc); reject()
        code = Index(); code.edges[run] = listOf(old); reject()
        code = Index(); code.tags.remove(endpoint); code.tags[old] = listOf("UserActionsMessageDeletion/userActionDeleteMessages "); code.edges[run] = listOf(old); reject()
        code = Index(); assertThrows(IllegalStateException::class.java) { hook.install(code, false, reader) }
    }
    @Test fun nestedImmediateWorkerIdentityAndReplay() {
        install(); val outer = listener(); val inner = listener(LinkedHashSet(batch)); lateinit var queued: Job
        inner.scheduled = { queued = it }; outer.prefix = { press(inner) }
        outer.scheduled = { expect(it, true) }; press(outer)
        expect(job(inner.items, inner.owner), false) // equal Runnable, not the scheduled instance
        val pool = Executors.newSingleThreadExecutor()
        try { pool.submit { expect(queued, true) }.get(5, TimeUnit.SECONDS) } finally { pool.shutdownNow() }
        expect(queued, false); assertEquals(2, reads.get())
    }
    @Test fun delegateAndCopiesCannotBorrowFrame() {
        install(); val l = listener(); val foreign = job(batch, l.owner)
        l.prefix = {
            val p = X.fireBefore(ctor, foreign, arrayOf(batch, l.owner, null, null, null, 77, false, false)); X.fireAfter(p)
        }
        val good = scheduled(l); expect(foreign, false); expect(good, true)
        val copy = listener(); copy.useItems = LinkedHashSet(batch); expect(scheduled(copy), false)
        val other = listener(); other.useOwner = Owner(); expect(scheduled(other), false)
        val changed = scheduled(); changed.owner = Owner(); expect(changed, false)
        val wrongArg = scheduled(); wrongArg.arg = LinkedHashSet(batch); expect(wrongArg, false)
        assertEquals(1, reads.get())
    }
    @Test fun exceptionalCallbacksAndConditionalEarlyReturn() {
        install(); val l = listener(); l.prefix = { error("before") }
        assertThrows(IllegalStateException::class.java) { press(l) }
        l.prefix = {}; l.ctorError = true; expect(scheduled(l), false); l.ctorError = false
        lateinit var abandoned: Job; l.scheduled = { abandoned = it; error("after") }
        assertThrows(IllegalStateException::class.java) { press(l) }; expect(abandoned, false)
        l.scheduled = { expect(it, true); error("after immediate run") }; assertThrows(IllegalStateException::class.java) { press(l) }
        val many = (1..1000).toMutableSet<Any>(); many.add(Msg(key)); val early = scheduled(listener(many)); early.limit = true
        drive(early); assertEquals(0, early.api.calls); assertEquals(1, reads.get()); expect(scheduled(listener(many)), true)
    }
    @Test fun captureFaultDoesNotAlterOriginalOrItsThrowable() {
        install(); readerError = true; val j = scheduled(); val original = IllegalStateException("original")
        j.api.body = { throw original }; assertSame(original, assertThrows(IllegalStateException::class.java) { drive(j) })
        assertEquals(1, reads.get()); assertTrue(j.api.scoped); assertFalse(PreserveDeleteForMeHook.isDeleteForMeInProgress())
    }
    @Test fun concurrentRequestsAndNestedUnmarkedRun() {
        install(); val pair = listOf(scheduled(), scheduled()); val barrier = CyclicBarrier(2)
        val pool = Executors.newFixedThreadPool(2)
        try {
            val work = pair.map { j -> pool.submit(Callable {
                j.api.body = {
                    barrier.await(5, TimeUnit.SECONDS); assertTrue(PreserveDeleteForMeHook.isDeleteForMeInProgress())
                    val unrelated = job(batch, Owner()); drive(unrelated); assertFalse(unrelated.api.scoped)
                    assertTrue(PreserveDeleteForMeHook.isDeleteForMeInProgress())
                }; expect(j, true)
            }) }; work.forEach { it.get(10, TimeUnit.SECONDS) }
        } finally { pool.shutdownNow() }; assertEquals(2, reads.get())
    }
    @Test fun togglesAndReinstallInvalidateQueuedWork() {
        install(); val j = scheduled(); prefs.edit().putBoolean("preserve_delete_for_me", false).commit(); expect(j, false)
        prefs.edit().putBoolean("preserve_delete_for_me", true).commit(); expect(j, false)
        val during = scheduled(); during.prefix = { prefs.edit().putBoolean("preserve_delete_for_me", false).commit() }; expect(during, false)
        prefs.edit().putBoolean("preserve_delete_for_me", true).commit(); val oldJob = scheduled()
        hook.unhookAll(); assertTrue(X.hooks.isEmpty()); hook = feature(); install(); expect(oldJob, false); expect(scheduled(), true)
    }
    @Test fun partialRegistrationIsInertAndOwnedAtEveryStep() {
        for (step in 1..4) {
            var n = 0; hook.beginHookTracking()
            try {
                assertThrows(IllegalStateException::class.java) { hook.install(code, true, reader) { m, cb ->
                    if (++n == step) error("registration"); HookRegistrar.BRIDGE.hookMethod(m, cb)
                } }; assertEquals(step - 1, X.hooks.size)
            } finally { hook.endHookTracking(); hook.unhookAll() }
            assertTrue(X.hooks.isEmpty()); hook = feature()
        }
    }
    @Test fun ambiguousKeyOrPhysicalRowIsNotEnqueued() {
        assertNull(SelectedKeys.unique(Ambiguous::class.java, Key::class.java, Jid::class.java) { "test@g.us" })
        ctx.openOrCreateDatabase("msgstore.db", 0, null).use { db ->
            db.execSQL("CREATE TABLE jid(_id INTEGER,raw_string TEXT,user TEXT)"); db.execSQL("INSERT INTO jid VALUES(1,'test@g.us','test')")
            db.execSQL("CREATE TABLE chat(_id INTEGER,jid_row_id INTEGER,subject TEXT)"); db.execSQL("INSERT INTO chat VALUES(1,1,'group')")
            db.execSQL("CREATE TABLE message(_id INTEGER,key_id TEXT,chat_row_id INTEGER,from_me INTEGER,message_type INTEGER,text_data TEXT,timestamp INTEGER,sender_jid_row_id INTEGER)")
            db.execSQL("INSERT INTO message VALUES(1,'synthetic',1,1,0,'one',10,0)")
            assertFalse(hook.captureSelectedMessages(batch, reader)); db.execSQL("UPDATE message SET from_me=0")
            db.execSQL("UPDATE jid SET raw_string='elsewhere@g.us'"); assertFalse(hook.captureSelectedMessages(batch, reader))
            db.execSQL("UPDATE jid SET raw_string='test@g.us'"); db.execSQL("INSERT INTO message SELECT * FROM message")
            assertFalse(hook.captureSelectedMessages(batch, reader)); db.execSQL("DELETE FROM message WHERE rowid=2")
            assertTrue(hook.captureSelectedMessages(batch, reader))
        }
        // Drain the existing asynchronous transport; this assertion concerns row recognition only.
        val worker = PreserveDeleteForMeHook::class.java.getDeclaredField("preservationExecutor").apply { isAccessible = true }
        (worker.get(null) as ExecutorService).submit {}.get(5, TimeUnit.SECONDS)
    }
}
