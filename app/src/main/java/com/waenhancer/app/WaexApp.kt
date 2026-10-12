package com.waenhancer.app

import android.app.Application
import android.content.SharedPreferences
import android.net.Uri
import com.waenhancer.config.PreferenceStores
import com.waenhancer.config.PreferenceRestartTracker
import dagger.hilt.android.HiltAndroidApp

@HiltAndroidApp
class WaexApp : Application() {
    private val preferenceListener =
        SharedPreferences.OnSharedPreferenceChangeListener { preferences, key ->
            PreferenceRestartTracker.onPreferenceChanged(preferences, key)
            contentResolver.notifyChange(PREFERENCES_URI, null)
        }

    override fun onCreate() {
        super.onCreate()
        PreferenceStores.publicStore(this).apply {
            registerOnSharedPreferenceChangeListener(preferenceListener)
            val installedVersion = packageManager.getPackageInfo(packageName, 0).versionName ?: "0"
            edit().putString("wae_version_name", installedVersion).apply()
        }
        com.waenhancer.licensing.features.BootloaderSpooferFeature.syncDefaultKeyboxAsync(this)
    }

    private companion object {
        val PREFERENCES_URI: Uri = Uri.parse("content://com.waenhancer.hookprovider/preferences")
    }
}
