package com.waenhancer.ui.screens.settings

import com.waenhancer.app.R
import com.waenhancer.utils.UiText

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
                title = UiText.get(R.string.update_settings_title, "Update Settings"),
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
                        text = UiText.get(R.string.waex_ui_automated_checks_adf7684a, "AUTOMATED CHECKS"),
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
                                text = UiText.get(R.string.waex_ui_auto_check_for_updates_7598a244, "Auto-Check for Updates"),
                                style = typography.bodyLg,
                                fontWeight = FontWeight.SemiBold,
                                color = colors.onSurface
                            )
                            Text(
                                text = UiText.get(R.string.waex_ui_periodically_check_the_waenhancerx_rel_0026b98e, "Periodically check the WaEnhancerX release service"),
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
                        title = UiText.get(R.string.waex_ui_check_when_module_opens_147ecac4, "Check when module opens"),
                        description = UiText.get(R.string.waex_ui_run_an_eligible_update_check_when_waen_57552a51, "Run an eligible update check when WaEnhancerX opens"),
                        checked = checkModuleOpen,
                        onCheckedChange = {
                            checkModuleOpen = it
                            prefManager.putBoolean("update_check_module_open", it)
                        }
                    )

                    HorizontalDivider(thickness = 1.dp, color = colors.outlineVariant.copy(alpha = 0.5f), modifier = Modifier.padding(vertical = 14.dp))

                    UpdateSwitchRow(
                        title = UiText.get(R.string.waex_ui_check_when_whatsapp_opens_112f6dcc, "Check when WhatsApp opens"),
                        description = UiText.get(R.string.waex_ui_ask_the_module_to_check_when_whatsapp_eef51246, "Ask the module to check when WhatsApp starts"),
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
                            Text(UiText.get(R.string.waex_ui_check_frequency_12e9b9ef, "Check frequency"), style = typography.bodyLg, fontWeight = FontWeight.SemiBold, color = colors.onSurface)
                            Text(frequencyLabel(updateFrequency), style = typography.bodyMd, color = colors.onSurfaceVariant, fontSize = 12.sp)
                        }
                        Text(UiText.get(R.string.waex_ui_change_c0bf75bd, "Change"), color = colors.primary, fontWeight = FontWeight.Bold)
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
                            Text(UiText.get(R.string.waex_ui_after_ignoring_an_update_0072f0fc, "After ignoring an update"), style = typography.bodyLg, fontWeight = FontWeight.SemiBold, color = colors.onSurface)
                            Text(ignoredLabel(ignoredBehavior), style = typography.bodyMd, color = colors.onSurfaceVariant, fontSize = 12.sp)
                        }
                        Text(UiText.get(R.string.waex_ui_change_c0bf75bd, "Change"), color = colors.primary, fontWeight = FontWeight.Bold)
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
                                text = UiText.get(R.string.waex_ui_allow_version_downgrades_cb84c618, "Allow Version Downgrades"),
                                style = typography.bodyLg,
                                fontWeight = FontWeight.SemiBold,
                                color = colors.onSurface
                            )
                            Text(
                                text = UiText.get(R.string.waex_ui_install_older_builds_over_newer_versio_0fccde02, "Install older builds over newer versions (Root needed)"),
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
                                    } else Toast.makeText(context, UiText.get(R.string.waex_ui_root_access_is_required_to_enable_vers_650bb903, "Root access is required to enable version downgrades"), Toast.LENGTH_LONG).show()
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
                                text = UiText.get(R.string.waex_ui_silent_root_install_6fff1c8e, "Silent Root Install"),
                                style = typography.bodyLg,
                                fontWeight = FontWeight.SemiBold,
                                color = colors.onSurface
                            )
                            Text(
                                text = UiText.get(R.string.waex_ui_automatically_install_downloaded_apk_v_c1ae30db, "Automatically install downloaded APK via root shell"),
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
                                    } else Toast.makeText(context, UiText.get(R.string.waex_ui_root_access_is_required_to_enable_sile_8a319a7a, "Root access is required to enable silent installation"), Toast.LENGTH_LONG).show()
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
    "every_open" -> UiText.get(R.string.waex_ui_every_eligible_app_open_dadc9b2a, "Every eligible app open")
    "six_hours" -> UiText.get(R.string.waex_ui_at_most_every_6_hours_6e9a44b5, "At most every 6 hours")
    "weekly" -> UiText.get(R.string.waex_ui_at_most_once_a_week_8226a663, "At most once a week")
    else -> UiText.get(R.string.waex_ui_at_most_once_a_day_9198c451, "At most once a day")
}

private fun ignoredLabel(value: String) = when (value) {
    "next_check" -> UiText.get(R.string.waex_ui_show_it_again_on_the_next_check_40bbb328, "Show it again on the next check")
    "after_day" -> UiText.get(R.string.waex_ui_remind_me_again_after_one_day_6522d8db, "Remind me again after one day")
    "after_week" -> UiText.get(R.string.waex_ui_remind_me_again_after_one_week_31ebcd1e, "Remind me again after one week")
    else -> UiText.get(R.string.waex_ui_wait_until_a_newer_release_is_availabl_9e7d1559, "Wait until a newer release is available")
}
