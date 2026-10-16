package com.waenhancer.update

/** Cancelling UI ownership is independent of a network callback already in the queue. */
class UpdateDownloadSession {
    private enum class State { OPEN, CANCELLED, COMPLETED }
    private var state = State.OPEN
    private var cancellation: (() -> Unit)? = null
    @Synchronized fun isActive(): Boolean = state == State.OPEN
    @Synchronized fun isCancelled(): Boolean = state == State.CANCELLED
    fun attach(cancel: () -> Unit) {
        val cancelNow = synchronized(this) {
            if (state == State.OPEN) { cancellation = cancel; false } else true
        }
        if (cancelNow) cancel()
    }
    fun cancel() {
        val action = synchronized(this) {
            if (state != State.OPEN) return
            state = State.CANCELLED
            cancellation.also { cancellation = null }
        }
        action?.invoke()
    }
    @Synchronized fun claimTerminal(): Boolean {
        if (state != State.OPEN) return false
        state = State.COMPLETED
        cancellation = null
        return true
    }
}
