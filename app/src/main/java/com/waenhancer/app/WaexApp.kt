package com.waenhancer.app

import android.app.Application
import android.content.SharedPreferences
import android.net.Uri
import com.waenhancer.config.PreferenceStores
import dagger.hilt.android.HiltAndroidApp

@HiltAndroidApp
class WaexApp : Application() {
    private val preferenceListener =
        SharedPreferences.OnSharedPreferenceChangeListener { _, _ ->
            contentResolver.notifyChange(PREFERENCES_URI, null)
        }

    override fun onCreate() {
        super.onCreate()
        PreferenceStores.publicStore(this)
            .registerOnSharedPreferenceChangeListener(preferenceListener)
        com.waenhancer.licensing.features.BootloaderSpooferFeature.syncDefaultKeyboxAsync(this)
    }

    private companion object {
        val PREFERENCES_URI: Uri = Uri.parse("content://com.waenhancer.hookprovider/preferences")
    }
}
