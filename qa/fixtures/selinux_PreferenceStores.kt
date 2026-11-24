package com.waenhancer.config
import android.content.Context
class FixturePreferences {
    fun getInt(key: String, fallback: Int): Int = fallback
    fun getString(key: String, fallback: String?): String? = fallback
    fun getStringSet(key: String, fallback: Set<String>): Set<String>? = fallback
}
object PreferenceStores {
    fun publicStore(context: Context) = FixturePreferences()
}
