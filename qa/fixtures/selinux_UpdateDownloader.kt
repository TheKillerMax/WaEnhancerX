package com.waenhancer.update
object UpdateDownloader {
    var rootAllowed = false
    val forceFlags = mutableListOf<Boolean>()
    fun hasCachedRootAccess(): Boolean? = rootAllowed
    fun hasRootAccess(forceRefresh: Boolean = false): Boolean {
        forceFlags.add(forceRefresh)
        return rootAllowed
    }
}
