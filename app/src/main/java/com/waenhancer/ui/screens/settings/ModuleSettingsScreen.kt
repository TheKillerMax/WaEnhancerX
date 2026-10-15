package com.waenhancer.ui.screens.settings

import android.os.Build
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.waenhancer.ui.components.WaexFeatureTile
import com.waenhancer.ui.components.WaexTopBar
import com.waenhancer.ui.designsystem.LocalThemeMode
import com.waenhancer.ui.designsystem.LocalThemeModeUpdater
import com.waenhancer.ui.designsystem.WaexIcons
import com.waenhancer.ui.designsystem.WaexTheme
import com.waenhancer.ui.navigation.LocalWaexNavController
import com.waenhancer.ui.navigation.Screen

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ModuleSettingsScreen() {
    val navController = LocalWaexNavController.current
    val themeMode = LocalThemeMode.current
    val updateThemeMode = LocalThemeModeUpdater.current
    val colors = WaexTheme.colors
    val spacing = WaexTheme.spacing
    var showThemeSheet by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            WaexTopBar(
                title = "Module Settings",
                onBackClick = navController::popBack
            )
        },
        containerColor = colors.background
    ) { insets ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(insets)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = spacing.pageMargin, vertical = 20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            WaexFeatureTile(
                title = "App Theme",
                description = "Choose how WaEnhancerX looks",
                statusText = themeMode,
                icon = themeIcon(themeMode),
                onClick = { showThemeSheet = true },
                modifier = Modifier.fillMaxWidth()
            )
            WaexFeatureTile(
                title = "Update Settings",
                description = "Configure checks, installation, and downgrades",
                icon = WaexIcons.SystemUpdate,
                onClick = { navController.navigateTo(Screen.UpdateSettings) },
                modifier = Modifier.fillMaxWidth()
            )
        }
    }

    if (showThemeSheet) {
        val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
        val modes = listOf("System", "Light", "Dark") +
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) listOf("Monet") else emptyList()

        ModalBottomSheet(
            onDismissRequest = { showThemeSheet = false },
            sheetState = sheetState,
            containerColor = colors.surface,
            shape = WaexTheme.radius.bottomSheetShape,
            dragHandle = {
                Box(
                    Modifier
                        .padding(top = 10.dp, bottom = 6.dp)
                        .size(width = 36.dp, height = 4.dp)
                        .background(colors.outlineVariant, RoundedCornerShape(2.dp))
                )
            }
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .navigationBarsPadding()
                    .padding(horizontal = 24.dp)
                    .padding(bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(
                    text = "Choose app theme",
                    style = WaexTheme.typography.titleLg,
                    fontWeight = FontWeight.Bold,
                    color = colors.onSurface,
                    modifier = Modifier.padding(vertical = 8.dp)
                )
                modes.forEach { mode ->
                    val selected = mode == themeMode
                    Surface(
                        shape = WaexTheme.radius.cardShape,
                        color = if (selected) colors.primary.copy(alpha = 0.12f) else colors.surfaceContainerLow,
                        border = androidx.compose.foundation.BorderStroke(
                            1.dp,
                            if (selected) colors.primary else colors.outlineVariant
                        ),
                        modifier = Modifier.fillMaxWidth().clickable {
                            updateThemeMode(mode)
                            showThemeSheet = false
                        }
                    ) {
                        Row(
                            modifier = Modifier.padding(horizontal = 16.dp, vertical = 15.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                imageVector = themeIcon(mode),
                                contentDescription = null,
                                tint = if (selected) colors.primary else colors.onSurfaceVariant,
                                modifier = Modifier.size(22.dp)
                            )
                            Spacer(Modifier.width(14.dp))
                            Text(
                                text = themeLabel(mode),
                                style = WaexTheme.typography.bodyLg,
                                fontWeight = if (selected) FontWeight.Bold else FontWeight.Medium,
                                color = if (selected) colors.primary else colors.onSurface,
                                modifier = Modifier.weight(1f)
                            )
                            if (selected) {
                                Icon(
                                    imageVector = WaexIcons.Check,
                                    contentDescription = "Selected",
                                    tint = colors.primary,
                                    modifier = Modifier.size(20.dp)
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

private fun themeIcon(mode: String) = when (mode) {
    "Light" -> WaexIcons.LightMode
    "Dark" -> WaexIcons.DarkMode
    "Monet" -> WaexIcons.Palette
    else -> WaexIcons.AutoMode
}

private fun themeLabel(mode: String) = when (mode) {
    "System" -> "Follow system"
    "Monet" -> "Dynamic colors (Monet)"
    else -> mode
}
