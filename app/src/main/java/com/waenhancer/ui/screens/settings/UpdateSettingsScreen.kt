package com.waenhancer.ui.screens.settings

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.waenhancer.ui.components.StitchSwitch
import com.waenhancer.ui.components.WaexTopBar
import com.waenhancer.ui.designsystem.WaexIcons
import com.waenhancer.ui.designsystem.WaexTheme
import com.waenhancer.ui.navigation.LocalWaexNavController
import com.waenhancer.ui.navigation.LocalWaexPreferenceManager
import com.waenhancer.update.UpdateDownloader
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import androidx.compose.foundation.BorderStroke

@Composable
fun UpdateSettingsScreen() {
    val navController = LocalWaexNavController.current
    val prefManager = LocalWaexPreferenceManager.current
    val colors = WaexTheme.colors
    val spacing = WaexTheme.spacing
    val typography = WaexTheme.typography
    val radius = WaexTheme.radius
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var autoCheckUpdates by remember { mutableStateOf(prefManager.getBoolean("update_auto_check", true)) }
    var allowDowngrades by remember { mutableStateOf(prefManager.getBoolean("downgrades_enabled", false)) }
    var rootAutoInstall by remember { mutableStateOf(prefManager.getBoolean("root_auto_install", false)) }
    var updateFrequency by remember { mutableStateOf(prefManager.getString("update_frequency", "daily")) }
    var checkModuleOpen by remember { mutableStateOf(prefManager.getBoolean("update_check_module_open", true)) }
    var checkWhatsAppOpen by remember { mutableStateOf(prefManager.getBoolean("update_check_whatsapp_open", true)) }
    var ignoredBehavior by remember { mutableStateOf(prefManager.getString("update_ignored_behavior", "next_release")) }

    Scaffold(
        topBar = {
            WaexTopBar(
                title = "Update Settings",
                onBackClick = { navController.popBack() }
            )
        },
        containerColor = colors.background
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = spacing.pageMargin, vertical = 20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // General Update Behaviors Card
            Surface(
                shape = radius.bentoCardShape,
                color = colors.surfaceDim,
                border = BorderStroke(1.dp, colors.outlineVariant),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    Text(
                        text = "AUTOMATED CHECKS",
                        style = typography.labelSm,
                        fontWeight = FontWeight.Bold,
                        color = colors.primary,
                        letterSpacing = 0.5.sp
                    )
                    Spacer(modifier = Modifier.height(14.dp))

                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = "Auto-Check for Updates",
                                style = typography.bodyLg,
                                fontWeight = FontWeight.SemiBold,
                                color = colors.onSurface
                            )
                            Text(
                                text = "Periodically check the WaEnhancerX release service",
                                style = typography.bodyMd,
                                color = colors.onSurfaceVariant,
                                fontSize = 12.sp
                            )
                        }
                        StitchSwitch(
                            checked = autoCheckUpdates,
                            onCheckedChange = {
                                autoCheckUpdates = it
                                prefManager.putBoolean("update_auto_check", it)
                            }
                        )
                    }

                    HorizontalDivider(thickness = 1.dp, color = colors.outlineVariant.copy(alpha = 0.5f), modifier = Modifier.padding(vertical = 14.dp))

                    UpdateSwitchRow(
                        title = "Check when module opens",
                        description = "Run an eligible update check when WaEnhancerX opens",
                        checked = checkModuleOpen,
                        onCheckedChange = {
                            checkModuleOpen = it
                            prefManager.putBoolean("update_check_module_open", it)
                        }
                    )

                    HorizontalDivider(thickness = 1.dp, color = colors.outlineVariant.copy(alpha = 0.5f), modifier = Modifier.padding(vertical = 14.dp))

                    UpdateSwitchRow(
                        title = "Check when WhatsApp opens",
                        description = "Ask the module to check when WhatsApp starts",
                        checked = checkWhatsAppOpen,
                        onCheckedChange = {
                            checkWhatsAppOpen = it
                            prefManager.putBoolean("update_check_whatsapp_open", it)
                        }
                    )

                    HorizontalDivider(thickness = 1.dp, color = colors.outlineVariant.copy(alpha = 0.5f), modifier = Modifier.padding(vertical = 14.dp))

                    val frequencies = listOf("every_open", "six_hours", "daily", "weekly")
                    Row(
                        modifier = Modifier.fillMaxWidth().clickable {
                            updateFrequency = frequencies[(frequencies.indexOf(updateFrequency).coerceAtLeast(0) + 1) % frequencies.size]
                            prefManager.putString("update_frequency", updateFrequency)
                        },
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text("Check frequency", style = typography.bodyLg, fontWeight = FontWeight.SemiBold, color = colors.onSurface)
                            Text(frequencyLabel(updateFrequency), style = typography.bodyMd, color = colors.onSurfaceVariant, fontSize = 12.sp)
                        }
                        Text("Change", color = colors.primary, fontWeight = FontWeight.Bold)
                    }

                    HorizontalDivider(thickness = 1.dp, color = colors.outlineVariant.copy(alpha = 0.5f), modifier = Modifier.padding(vertical = 14.dp))

                    val ignoredOptions = listOf("next_release", "next_check", "after_day", "after_week")
                    Row(
                        modifier = Modifier.fillMaxWidth().clickable {
                            ignoredBehavior = ignoredOptions[(ignoredOptions.indexOf(ignoredBehavior).coerceAtLeast(0) + 1) % ignoredOptions.size]
                            prefManager.putString("update_ignored_behavior", ignoredBehavior)
                        },
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text("After ignoring an update", style = typography.bodyLg, fontWeight = FontWeight.SemiBold, color = colors.onSurface)
                            Text(ignoredLabel(ignoredBehavior), style = typography.bodyMd, color = colors.onSurfaceVariant, fontSize = 12.sp)
                        }
                        Text("Change", color = colors.primary, fontWeight = FontWeight.Bold)
                    }

                    HorizontalDivider(
                        thickness = 1.dp,
                        color = colors.outlineVariant.copy(alpha = 0.5f),
                        modifier = Modifier.padding(vertical = 14.dp)
                    )

                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = "Allow Version Downgrades",
                                style = typography.bodyLg,
                                fontWeight = FontWeight.SemiBold,
                                color = colors.onSurface
                            )
                            Text(
                                text = "Install older builds over newer versions (Root needed)",
                                style = typography.bodyMd,
                                color = colors.onSurfaceVariant,
                                fontSize = 12.sp
                            )
                        }
                        StitchSwitch(
                            checked = allowDowngrades,
                            onCheckedChange = {
                                if (!it) {
                                    allowDowngrades = false
                                    prefManager.putBoolean("downgrades_enabled", false)
                                } else scope.launch {
                                    val granted = withContext(Dispatchers.IO) { UpdateDownloader.hasRootAccess() }
                                    if (granted) {
                                        allowDowngrades = true
                                        prefManager.putBoolean("downgrades_enabled", true)
                                    } else Toast.makeText(context, "Root access is required to enable version downgrades", Toast.LENGTH_LONG).show()
                                }
                            }
                        )
                    }

                    HorizontalDivider(
                        thickness = 1.dp,
                        color = colors.outlineVariant.copy(alpha = 0.5f),
                        modifier = Modifier.padding(vertical = 14.dp)
                    )

                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = "Silent Root Install",
                                style = typography.bodyLg,
                                fontWeight = FontWeight.SemiBold,
                                color = colors.onSurface
                            )
                            Text(
                                text = "Automatically install downloaded APK via root shell",
                                style = typography.bodyMd,
                                color = colors.onSurfaceVariant,
                                fontSize = 12.sp
                            )
                        }
                        StitchSwitch(
                            checked = rootAutoInstall,
                            onCheckedChange = {
                                if (!it) {
                                    rootAutoInstall = false
                                    prefManager.putBoolean("root_auto_install", false)
                                } else scope.launch {
                                    val granted = withContext(Dispatchers.IO) { UpdateDownloader.hasRootAccess() }
                                    if (granted) {
                                        rootAutoInstall = true
                                        prefManager.putBoolean("root_auto_install", true)
                                    } else Toast.makeText(context, "Root access is required to enable silent installation", Toast.LENGTH_LONG).show()
                                }
                            }
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(24.dp))
        }
    }
}

@Composable
private fun UpdateSwitchRow(
    title: String,
    description: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit
) {
    val colors = WaexTheme.colors
    val typography = WaexTheme.typography
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.weight(1f)) {
            Text(title, style = typography.bodyLg, fontWeight = FontWeight.SemiBold, color = colors.onSurface)
            Text(description, style = typography.bodyMd, color = colors.onSurfaceVariant, fontSize = 12.sp)
        }
        StitchSwitch(checked = checked, onCheckedChange = onCheckedChange)
    }
}

private fun frequencyLabel(value: String) = when (value) {
    "every_open" -> "Every eligible app open"
    "six_hours" -> "At most every 6 hours"
    "weekly" -> "At most once a week"
    else -> "At most once a day"
}

private fun ignoredLabel(value: String) = when (value) {
    "next_check" -> "Show it again on the next check"
    "after_day" -> "Remind me again after one day"
    "after_week" -> "Remind me again after one week"
    else -> "Wait until a newer release is available"
}
