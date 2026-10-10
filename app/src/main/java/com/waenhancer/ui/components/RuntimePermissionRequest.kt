package com.waenhancer.ui.components

import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat

@Composable
fun RequestRuntimePermissionOnUse(
    permission: String,
    enabled: Boolean = true,
    onResult: (Boolean) -> Unit = {}
) {
    val context = LocalContext.current
    val launcher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission(),
        onResult = onResult
    )

    LaunchedEffect(permission, enabled) {
        if (!enabled) return@LaunchedEffect
        val granted = ContextCompat.checkSelfPermission(context, permission) ==
            PackageManager.PERMISSION_GRANTED
        if (granted) {
            onResult(true)
        } else {
            launcher.launch(permission)
        }
    }
}
