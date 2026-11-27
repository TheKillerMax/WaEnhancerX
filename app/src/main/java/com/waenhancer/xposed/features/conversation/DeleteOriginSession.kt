package com.waenhancer.xposed.features.conversation

import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XC_MethodHook.MethodHookParam
import de.robv.android.xposed.XposedBridge
import java.lang.ref.ReferenceQueue
import java.lang.ref.WeakReference
import java.lang.reflect.Field
import java.lang.reflect.Member
import java.lang.reflect.Method

/** One installation. Only a weak identity ticket crosses threads; never attach data to a host object. */
internal class DeleteOriginSession(private val enabled: () -> Boolean) {
    private class Pick(val owner: Any, val selection: Set<*>)
    private class Ticket(p: Pick, val ownerField: Field, val selectionField: Field) {
        val owner = WeakReference(p.owner)
        val selection = WeakReference(p.selection)
        fun recover(job: Any): Pick? {
            val o = owner.get() ?: return null
            val s = selection.get() ?: return null
            return if (ownerField.get(job) === o && selectionField.get(job) === s) Pick(o, s) else null
        }
    }
    private class Id(job: Any, queue: ReferenceQueue<Any>? = null) : WeakReference<Any>(job, queue) {
        private val hash = System.identityHashCode(job)
        override fun hashCode() = hash
        override fun equals(other: Any?): Boolean {
            if (this === other) return true
            val instance = get() ?: return false
            return other is Id && other.get() === instance
        }
    }
    private class Frame(val session: DeleteOriginSession, val param: MethodHookParam, val prev: Frame?) {
        var pick: Pick? = null
        var issued: Id? = null
        var local = false
        var store = false
        var used = false
    }
    companion object {
        private val top = ThreadLocal<Frame>()
        fun inLocalRequest() = top.get()?.let { it.local && it.session.live } == true
    }
    @Volatile private var live = false
    private val queue = ReferenceQueue<Any>()
    private val pending = HashMap<Id, Ticket>()
    fun activate() { live = true }
    @Synchronized fun close() { live = false; pending.clear() }
    fun inStoreRequest() = live && top.get()?.let { it.session === this && it.store } == true

    private fun reap() { while (true) pending.remove(queue.poll() as? Id ?: return) }
    @Synchronized private fun issue(frame: Frame, job: Any, ticket: Ticket) {
        if (!live || frame.issued != null) return
        reap()
        val id = Id(job, queue)
        pending[id] = ticket
        frame.issued = id
    }
    @Synchronized private fun cancel(id: Id) { pending.remove(id) }
    @Synchronized private fun take(job: Any): Ticket? {
        reap()
        return pending.remove(Id(job))
    }

    // An unqualified nested invocation masks (rather than borrows) its parent's authority.
    private fun around(before: (Frame, XC_MethodHook) -> Unit = { _, _ -> },
                       after: (Frame, XC_MethodHook) -> Unit = { _, _ -> }) = object : XC_MethodHook() {
        override fun beforeHookedMethod(param: MethodHookParam) {
            val f = Frame(this@DeleteOriginSession, param, top.get())
            top.set(f)
            if (live) try { before(f, this) } catch (_: Throwable) {
                // Never change the host result or expose a payload in a hook diagnostic.
            }
        }
        override fun afterHookedMethod(param: MethodHookParam) {
            val f = top.get() ?: return
            if (f.session !== this@DeleteOriginSession || f.param !== param) return
            try { if (live) after(f, this) } catch (_: Throwable) {
                // A failed constructor inspection must not manufacture a ticket.
            } finally { if (f.prev == null) top.remove() else top.set(f.prev) }
        }
    }

    // Identities alone cannot distinguish a delegate constructing the same job with *both*
    // original arguments. Require a visible direct caller. Never search past an unknown frame.
    // Unknown ART/bridge stack layouts can cost a match; they cannot authorize a transitive call.
    private fun direct(cb: XC_MethodHook, target: Member, caller: Method): Boolean {
        val trace = Throwable().stackTrace
        val hook = trace.indexOfFirst { it.className == cb.javaClass.name &&
            (it.methodName == "afterHookedMethod" || it.methodName == "beforeHookedMethod") }
        if (hook < 0) return false
        var i = hook + 1
        while (trace.getOrNull(i)?.className == XposedBridge::class.java.name) i++
        val entry = if (target is Method) target.name else "<init>"
        if (trace.getOrNull(i)?.let { it.className == target.declaringClass.name && it.methodName == entry } == true) i++
        return trace.getOrNull(i)?.let { it.className == caller.declaringClass.name && it.methodName == caller.name } == true
    }

    fun installStore(entry: Method, register: (Member, XC_MethodHook) -> Unit) {
        register(entry, around(before = { f, _ -> f.store = enabled(); f.local = f.store }))
    }

    fun installLocal(c: DeleteRoute.Local, register: (Member, XC_MethodHook) -> Unit,
                     capture: (Set<*>) -> Unit) {
        register(c.click, around(before = click@{ f, _ ->
            val l = f.param.thisObject ?: return@click
            if (!enabled() || l.javaClass != c.click.declaringClass) return@click
            val o = c.owner.get(l) ?: return@click
            val s = c.selection.get(l) as? Set<*> ?: return@click
            f.pick = Pick(o, s)
        }, after = { f, _ -> if (f.param.hasThrowable()) f.issued?.let(::cancel) }))
        register(c.construct, around(after = constructed@{ f, cb ->
            val parent = f.prev ?: return@constructed
            val p = parent.pick ?: return@constructed
            val job = f.param.thisObject ?: return@constructed
            if (parent.session !== this || parent.param.method != c.click || parent.issued != null ||
                f.param.hasThrowable() || job.javaClass != c.construct.declaringClass || !enabled() ||
                f.param.args.getOrNull(0) !== p.selection || f.param.args.getOrNull(1) !== p.owner ||
                !direct(cb, c.construct, c.click)) return@constructed
            val o = c.carried.singleOrNull { it.get(job) === p.owner } ?: return@constructed
            val s = c.carried.singleOrNull { it.get(job) === p.selection } ?: return@constructed
            if (o != s) issue(parent, job, Ticket(p, o, s))
        }))
        register(c.run, around(before = run@{ f, _ ->
            val job = f.param.thisObject ?: return@run
            val ticket = take(job) ?: return@run
            if (enabled()) f.pick = ticket.recover(job)
        }))
        register(c.api, around(before = api@{ f, cb ->
            val r = f.prev ?: return@api
            val p = r.pick ?: return@api
            if (r.session !== this || r.param.method != c.run || r.used ||
                f.param.args.getOrNull(1) !== p.selection || !enabled() || !direct(cb, c.api, c.run)) return@api
            r.used = true
            f.local = true
            capture(p.selection)
        }))
    }
}
