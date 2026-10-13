package com.waenhancer.ui.screens.dashboard

import android.content.Context
import android.content.Intent
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.waenhancer.config.PreferenceStores
import com.waenhancer.ui.designsystem.WaexIcons
import com.waenhancer.ui.designsystem.WaexTheme
import com.waenhancer.ui.navigation.LocalWaexNavController
import com.waenhancer.ui.navigation.LocalWaexPreferenceManager
import com.waenhancer.ui.navigation.Screen
import com.waenhancer.utils.HookedAppInfo
import com.waenhancer.utils.InjectedHookItem
import com.waenhancer.utils.SystemDiagnostics
import com.waenhancer.utils.SystemDiagnosticsReader
import com.waenhancer.utils.UniversalVersionValidator
import com.waenhancer.utils.WhatsAppPackageDetector
import com.waenhancer.xposed.utils.AppRestartHelper
import com.waenhancer.xposed.utils.ModuleStatus
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainDashboardScreen(
    licenseState: String,
    onOpenModal: (String) -> Unit
) {
    val navController = LocalWaexNavController.current
    val colors = WaexTheme.colors
    val spacing = WaexTheme.spacing
    val typography = WaexTheme.typography
    val radius = WaexTheme.radius
    val context = LocalContext.current
    val preferenceManager = LocalWaexPreferenceManager.current
    val isModuleActive = remember { ModuleStatus.isModuleActive() }

    val backupLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("application/octet-stream")
    ) { uri ->
        if (uri != null) {
            runCatching { preferenceManager.exportSettings(uri) }
                .onSuccess { Toast.makeText(context, "$it settings backed up", Toast.LENGTH_SHORT).show() }
                .onFailure { Toast.makeText(context, "Backup failed: ${it.message}", Toast.LENGTH_LONG).show() }
        }
    }
    val restoreLauncher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            runCatching { preferenceManager.importSettings(uri) }
                .onSuccess { Toast.makeText(context, "$it settings restored. Restart WhatsApp to apply.", Toast.LENGTH_LONG).show() }
                .onFailure { Toast.makeText(context, "Restore failed: ${it.message}", Toast.LENGTH_LONG).show() }
        }
    }
    val startBackup = {
        val stamp = SimpleDateFormat("yyyyMMdd-HHmm", Locale.US).format(Date())
        runCatching { backupLauncher.launch("WAEX-settings-$stamp.waex") }
            .onFailure { Toast.makeText(context, "Could not open file picker: ${it.message}", Toast.LENGTH_LONG).show() }
        Unit
    }
    val startRestore = {
        runCatching { restoreLauncher.launch(arrayOf("application/octet-stream", "*/*")) }
            .onFailure { Toast.makeText(context, "Could not open file picker: ${it.message}", Toast.LENGTH_LONG).show() }
        Unit
    }

    var refreshTrigger by remember { mutableIntStateOf(0) }
    var systemDiagnostics by remember { mutableStateOf<SystemDiagnostics?>(null) }

    LaunchedEffect(refreshTrigger) {
        systemDiagnostics = withContext(Dispatchers.IO) { SystemDiagnosticsReader.read(context) }
    }

    // Re-check target apps on resume and whenever target app sends active broadcast
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                refreshTrigger++
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)

        val receiver = object : android.content.BroadcastReceiver() {
            override fun onReceive(c: Context?, intent: Intent?) {
                refreshTrigger++
            }
        }
        val filter = android.content.IntentFilter("com.waenhancer.ACTION_TARGET_APP_ACTIVE")
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            context.registerReceiver(receiver, filter, Context.RECEIVER_EXPORTED)
        } else {
            context.registerReceiver(receiver, filter)
        }

        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            try {
                context.unregisterReceiver(receiver)
            } catch (_: Throwable) {}
        }
    }

    // Dynamic WhatsApp Packages & Clones Detector
    val detectedApps = remember(refreshTrigger) {
        WhatsAppPackageDetector.detectWhatsAppApps(context)
    }

    val prefs = remember(context) { PreferenceStores.publicStore(context) }
    val hasUnsupportedActiveApp = detectedApps.any {
        it.isInstalled && it.isHooked && !UniversalVersionValidator.isSupported(context, it.versionName.removePrefix("v"), prefs)
    }
    val moduleVersion = remember(context) {
        @Suppress("DEPRECATION")
        context.packageManager.getPackageInfo(context.packageName, 0).versionName.orEmpty()
    }

    var showCustomizationSoon by remember { mutableStateOf(false) }

    Box(modifier = Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = spacing.pageMargin, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Module Status & Core Target Card
            Surface(
                shape = radius.cardShape,
                color = colors.surface,
                border = BorderStroke(
                    1.dp,
                    if (hasUnsupportedActiveApp) Color(0xFFEF4444).copy(alpha = 0.5f) else colors.outline
                ),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    // Header row: Status Dot + Title + Changelog pill
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Box(
                            modifier = Modifier
                                .size(10.dp)
                                .clip(CircleShape)
                                .background(
                                    when {
                                        !isModuleActive -> colors.error
                                        hasUnsupportedActiveApp -> Color(0xFFEF4444)
                                        else -> colors.primary
                                    }
                                )
                        )
                        Spacer(modifier = Modifier.width(10.dp))
                        Text(
                            text = when {
                                !isModuleActive -> "Module Inactive • v$moduleVersion"
                                hasUnsupportedActiveApp -> "Module Active • v$moduleVersion • Unsupported Target"
                                else -> "Module Active • v$moduleVersion"
                            },
                            style = typography.bodyMd,
                            fontWeight = FontWeight.SemiBold,
                            fontSize = 12.sp,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                            color = if (hasUnsupportedActiveApp) Color(0xFFEF4444) else colors.onSurface,
                            modifier = Modifier.weight(1f)
                        )
                        Box(
                            modifier = Modifier
                                .clip(radius.smShape)
                                .background(colors.surfaceDim)
                                .border(1.dp, colors.outlineVariant, radius.smShape)
                                .clickable { navController.navigateTo(Screen.Changelog) }
                                .padding(horizontal = 8.dp, vertical = 4.dp)
                        ) {
                            Text(
                                text = "Changelog",
                                style = typography.labelSm,
                                color = colors.onSurfaceVariant,
                                fontSize = 11.sp
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(14.dp))
                    HorizontalDivider(thickness = 1.dp, color = colors.outlineVariant)
                    Spacer(modifier = Modifier.height(14.dp))

                    // Target Apps: Vertical List of Cards with App Icon, Title, Package Name, Status Dot, Injected Hooks Badge, and Restart Action
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        detectedApps.forEach { app ->
                            val cleanVer = app.versionName.removePrefix("v")
                            val isVersionSupported = UniversalVersionValidator.isSupported(context, cleanVer, prefs)
                            val appIcon = remember(app.packageName) {
                                WhatsAppPackageDetector.getAppIcon(context, app.packageName)
                            }

                            val (statusDotColor, statusText, statusTextColor) = when {
                                !app.isInstalled -> Triple(
                                    colors.onSurfaceVariant.copy(alpha = 0.4f),
                                    "Not Installed",
                                    colors.onSurfaceVariant
                                )
                                app.isHooked && isVersionSupported -> Triple(
                                    colors.primary,
                                    "Injected & Active",
                                    colors.primary
                                )
                                app.isHooked && !isVersionSupported -> Triple(
                                    Color(0xFFEF4444),
                                    "Injected • Unsupported Version (Paused)",
                                    Color(0xFFEF4444)
                                )
                                !app.isHooked && !isVersionSupported -> Triple(
                                    Color(0xFFF59E0B),
                                    "Scope Pending • Unsupported Version",
                                    Color(0xFFF59E0B)
                                )
                                else -> Triple(
                                    Color(0xFFF59E0B),
                                    "Scope Pending / Not Injected",
                                    Color(0xFFF59E0B)
                                )
                            }

                            Surface(
                                shape = radius.defaultShape,
                                color = colors.surfaceDim,
                                border = BorderStroke(
                                    1.dp,
                                    if (app.isInstalled && !isVersionSupported) Color(0xFFEF4444).copy(alpha = 0.4f) else colors.outlineVariant
                                ),
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .then(
                                        if (app.isInstalled && !isVersionSupported) {
                                            Modifier.clickable { navController.navigateTo(Screen.SupportedVersions) }
                                        } else {
                                            Modifier
                                        }
                                    )
                            ) {
                                Column(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(12.dp)
                                ) {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        // App Icon Container
                                        Box(
                                            modifier = Modifier
                                                .size(44.dp)
                                                .clip(CircleShape)
                                                .background(colors.surface),
                                            contentAlignment = Alignment.Center
                                        ) {
                                            if (appIcon != null) {
                                                Image(
                                                    bitmap = appIcon,
                                                    contentDescription = app.appName,
                                                    modifier = Modifier
                                                        .size(32.dp)
                                                        .clip(CircleShape)
                                                )
                                            } else {
                                                Icon(
                                                    imageVector = WaexIcons.Security,
                                                    contentDescription = app.appName,
                                                    tint = colors.primary,
                                                    modifier = Modifier.size(24.dp)
                                                )
                                            }
                                        }

                                        Spacer(modifier = Modifier.width(12.dp))

                                        // App Info & Status Column
                                        Column(modifier = Modifier.weight(1f)) {
                                            Text(
                                                text = app.appName,
                                                style = typography.bodyMd,
                                                fontWeight = FontWeight.Bold,
                                                color = colors.onSurface,
                                                maxLines = 1,
                                                overflow = TextOverflow.Ellipsis
                                            )

                                            Text(
                                                text = "${app.packageName} • ${app.versionName}",
                                                style = typography.labelSm,
                                                color = colors.onSurfaceVariant.copy(alpha = 0.85f),
                                                fontSize = 11.sp,
                                                maxLines = 1,
                                                overflow = TextOverflow.Ellipsis
                                            )

                                            Spacer(modifier = Modifier.height(4.dp))

                                            // Status Dot & Label
                                            Row(
                                                verticalAlignment = Alignment.CenterVertically,
                                                horizontalArrangement = Arrangement.spacedBy(6.dp)
                                            ) {
                                                Box(
                                                    modifier = Modifier
                                                        .size(7.dp)
                                                        .clip(CircleShape)
                                                        .background(statusDotColor)
                                                )
                                                Text(
                                                    text = statusText,
                                                    style = typography.labelSm,
                                                    color = statusTextColor,
                                                    fontSize = 11.sp,
                                                    fontWeight = FontWeight.Medium
                                                )
                                            }
                                        }

                                        // Restart Action Button
                                        if (app.isInstalled) {
                                            Box(
                                                modifier = Modifier
                                                    .size(32.dp)
                                                    .clip(CircleShape)
                                                    .background(colors.surface)
                                                    .border(1.dp, colors.outlineVariant, CircleShape)
                                                    .clickable {
                                                        AppRestartHelper.restartPackage(
                                                            context,
                                                            app.packageName,
                                                            app.appName
                                                        )
                                                    },
                                                contentAlignment = Alignment.Center
                                            ) {
                                                Icon(
                                                    imageVector = WaexIcons.Refresh,
                                                    contentDescription = "Restart App",
                                                    tint = colors.onSurfaceVariant,
                                                    modifier = Modifier.size(15.dp)
                                                )
                                            }
                                        }
                                    }

                                    // Realtime Injected Hooks Badge / Pill (if injected and active)
                                    if (app.isHooked && app.injectedHooks.isNotEmpty()) {
                                        Spacer(modifier = Modifier.height(10.dp))
                                        HorizontalDivider(thickness = 0.5.dp, color = colors.outlineVariant.copy(alpha = 0.5f))
                                        Spacer(modifier = Modifier.height(8.dp))

                                        val activeCount = app.injectedHooks.count { it.status == "ACTIVE" }
                                        val totalCount = app.injectedHooks.size

                                        Row(
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .clip(radius.smShape)
                                                .background(colors.surface)
                                                .border(1.dp, colors.outlineVariant, radius.smShape)
                                                .clickable { navController.navigateTo(Screen.InjectedHooks(app.packageName, app.appName)) }
                                                .padding(horizontal = 10.dp, vertical = 6.dp),
                                            verticalAlignment = Alignment.CenterVertically,
                                            horizontalArrangement = Arrangement.SpaceBetween
                                        ) {
                                            Row(
                                                verticalAlignment = Alignment.CenterVertically,
                                                horizontalArrangement = Arrangement.spacedBy(6.dp)
                                            ) {
                                                Icon(
                                                    imageVector = WaexIcons.Extension,
                                                    contentDescription = null,
                                                    tint = colors.primary,
                                                    modifier = Modifier.size(14.dp)
                                                )
                                                Text(
                                                    text = "Injected Hooks ($activeCount/$totalCount Active)",
                                                    style = typography.labelSm,
                                                    fontWeight = FontWeight.SemiBold,
                                                    color = colors.onSurface,
                                                    fontSize = 11.sp
                                                )
                                            }
                                            Row(
                                                verticalAlignment = Alignment.CenterVertically,
                                                horizontalArrangement = Arrangement.spacedBy(4.dp)
                                            ) {
                                                Text(
                                                    text = "View all",
                                                    style = typography.labelSm,
                                                    color = colors.primary,
                                                    fontSize = 11.sp,
                                                    fontWeight = FontWeight.Medium
                                                )
                                                Icon(
                                                    imageVector = WaexIcons.ChevronRight,
                                                    contentDescription = null,
                                                    tint = colors.primary,
                                                    modifier = Modifier.size(13.dp)
                                                )
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            DashboardDiagnosticsCard(
                diagnostics = systemDiagnostics,
                hasUnsupportedTarget = hasUnsupportedActiveApp,
                onRefresh = { refreshTrigger++ },
                onViewDetails = { navController.navigateTo(Screen.SystemHealth) },
                onViewSupportedVersions = { navController.navigateTo(Screen.SupportedVersions) }
            )

            // Quick Backup & Maintenance Row
            Surface(
                shape = radius.cardShape,
                color = colors.surface,
                border = BorderStroke(1.dp, colors.outline),
                modifier = Modifier.fillMaxWidth()
            ) {
                Row(
                    modifier = Modifier.padding(12.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .clip(radius.defaultShape)
                            .background(colors.surfaceDim)
                            .border(1.dp, colors.outlineVariant, radius.defaultShape)
                            .clickable(onClick = startBackup)
                            .padding(vertical = 10.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(imageVector = WaexIcons.Folder, contentDescription = null, tint = colors.onSurfaceVariant, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(text = "Backup", style = typography.bodyMd, fontWeight = FontWeight.Medium, color = colors.onSurface)
                        }
                    }

                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .clip(radius.defaultShape)
                            .background(colors.surfaceDim)
                            .border(1.dp, colors.outlineVariant, radius.defaultShape)
                            .clickable(onClick = startRestore)
                            .padding(vertical = 10.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(imageVector = WaexIcons.Refresh, contentDescription = null, tint = colors.onSurfaceVariant, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(text = "Restore", style = typography.bodyMd, fontWeight = FontWeight.Medium, color = colors.onSurface)
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(80.dp))
        }

        // Customization Coming Soon Modal Overlay
        if (showCustomizationSoon) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color.Black.copy(alpha = 0.5f))
                    .clickable { showCustomizationSoon = false },
                contentAlignment = Alignment.Center
            ) {
                Surface(
                    shape = radius.lgShape,
                    color = colors.surface,
                    modifier = Modifier
                        .fillMaxWidth(0.85f)
                        .clickable(enabled = false) { }
                ) {
                    Column(
                        modifier = Modifier.padding(24.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        Box(
                            modifier = Modifier
                                .size(56.dp)
                                .clip(CircleShape)
                                .background(colors.primaryContainer),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                imageVector = WaexIcons.Palette,
                                contentDescription = null,
                                tint = colors.primary,
                                modifier = Modifier.size(24.dp)
                            )
                        }
                        Text(
                            text = "Customization",
                            style = typography.headlineMd,
                            fontWeight = FontWeight.Bold,
                            color = colors.onSurface
                        )
                        Text(
                            text = "Customization settings coming soon",
                            style = typography.bodyMd,
                            color = colors.onSurfaceVariant,
                            textAlign = TextAlign.Center
                        )
                        Button(
                            onClick = { showCustomizationSoon = false },
                            shape = radius.mdShape,
                            colors = ButtonDefaults.buttonColors(
                                containerColor = colors.primary,
                                contentColor = colors.onPrimary
                            ),
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(48.dp)
                        ) {
                            Text(text = "OK", style = typography.bodyMd, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun InjectedHookRow(hook: InjectedHookItem) {
    val colors = WaexTheme.colors
    val typography = WaexTheme.typography
    val radius = WaexTheme.radius

    val isSuccess = (hook.status == "ACTIVE")
    val dotColor = if (isSuccess) colors.primary else colors.error

    Surface(
        shape = radius.defaultShape,
        color = colors.surfaceDim,
        border = BorderStroke(1.dp, colors.outlineVariant),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(8.dp)
                    .clip(CircleShape)
                    .background(dotColor)
            )

            Spacer(modifier = Modifier.width(10.dp))

            Column(modifier = Modifier.weight(1f)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    Text(
                        text = hook.name,
                        style = typography.bodyMd,
                        fontWeight = FontWeight.SemiBold,
                        color = colors.onSurface,
                        modifier = Modifier.weight(1f, fill = false),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    Box(
                        modifier = Modifier
                            .clip(radius.smShape)
                            .background(colors.surface)
                            .border(0.5.dp, colors.outlineVariant, radius.smShape)
                            .padding(horizontal = 6.dp, vertical = 2.dp)
                    ) {
                        Text(
                            text = hook.category,
                            style = typography.labelSm,
                            fontSize = 10.sp,
                            color = colors.onSurfaceVariant
                        )
                    }
                }

                Spacer(modifier = Modifier.height(2.dp))

                Text(
                    text = hook.className,
                    style = typography.labelSm,
                    fontSize = 11.sp,
                    color = colors.onSurfaceVariant.copy(alpha = 0.8f),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )

                if (!hook.error.isNullOrBlank()) {
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(
                        text = "Error: ${hook.error}",
                        style = typography.labelSm,
                        fontSize = 10.sp,
                        color = colors.error,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }

            Spacer(modifier = Modifier.width(8.dp))

            Text(
                text = if (isSuccess) "Active" else "Failed",
                style = typography.labelSm,
                fontWeight = FontWeight.Medium,
                color = dotColor,
                fontSize = 11.sp
            )
        }
    }
}

@Composable
fun StandardNavCard(
    title: String,
    desc: String,
    icon: ImageVector,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    val colors = WaexTheme.colors
    val typography = WaexTheme.typography
    val radius = WaexTheme.radius

    Surface(
        shape = radius.cardShape,
        color = colors.surface,
        border = BorderStroke(1.dp, colors.outline),
        modifier = modifier.clickable { onClick() }
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Box(
                modifier = Modifier
                    .size(34.dp)
                    .clip(radius.defaultShape)
                    .background(colors.surfaceDim),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = icon,
                    contentDescription = null,
                    tint = colors.primary,
                    modifier = Modifier.size(18.dp)
                )
            }

            Text(
                text = title,
                style = typography.bodyMd,
                fontWeight = FontWeight.SemiBold,
                color = colors.onSurface
            )

            Text(
                text = desc,
                style = typography.labelSm,
                color = colors.onSurfaceVariant,
                fontSize = 11.sp,
                lineHeight = 15.sp,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis
            )
        }
    }
}
