package com.waenhancer.update

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationManagerCompat
import com.waenhancer.config.PreferenceStores

class UpdateIgnoreReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val version = intent.getStringExtra("version")?.takeIf { it.isNotBlank() } ?: return
        PreferenceStores.privateStore(context).edit()
            .putString("ignored_version", version)
            .putLong("ignored_timestamp", System.currentTimeMillis())
            .apply()
        NotificationManagerCompat.from(context).cancel(UpdateCheckCoordinator.NOTIFICATION_ID)
    }
}
