package com.waenhancer.ui.screens.settings

import com.waenhancer.utils.UiText

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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Language
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.waenhancer.app.R
import com.waenhancer.ui.components.WaexTopBar
import com.waenhancer.ui.designsystem.LocalThemeMode
import com.waenhancer.ui.designsystem.LocalThemeModeUpdater
import com.waenhancer.ui.designsystem.InterfaceSize
import com.waenhancer.ui.designsystem.LocalInterfaceSize
import com.waenhancer.ui.designsystem.LocalInterfaceSizeUpdater
import com.waenhancer.ui.designsystem.WaexIcons
import com.waenhancer.ui.designsystem.WaexTheme
import com.waenhancer.ui.navigation.LocalWaexNavController
import com.waenhancer.ui.navigation.Screen
import com.waenhancer.utils.LocaleHelper
import android.app.Activity
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.PaddingValues
import kotlin.math.roundToInt

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ModuleSettingsScreen() {
    val navController = LocalWaexNavController.current
    val context = LocalContext.current
    val themeMode = LocalThemeMode.current
    val updateThemeMode = LocalThemeModeUpdater.current
    val interfaceSize = LocalInterfaceSize.current
    val updateInterfaceSize = LocalInterfaceSizeUpdater.current
    val colors = WaexTheme.colors
    val spacing = WaexTheme.spacing
    var showThemeSheet by remember { mutableStateOf(false) }
    var showLanguageSheet by remember { mutableStateOf(false) }

    var currentLangCode by remember {
        mutableStateOf(LocaleHelper.getSelectedLanguageCode(context))
    }

    Scaffold(
        topBar = {
            WaexTopBar(
                title = stringResource(R.string.module_settings_title),
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
                .padding(horizontal = spacing.pageMargin, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            ModuleSettingsTile(
                title = stringResource(R.string.app_theme_title),
                description = stringResource(R.string.app_theme_desc),
                value = themeMode,
                icon = themeIcon(themeMode),
                onClick = { showThemeSheet = true }
            )
            InterfaceSizePreference(
                selectedSize = interfaceSize,
                onSizeSelected = updateInterfaceSize
            )
            ModuleSettingsTile(
                title = stringResource(R.string.app_language_title),
                description = stringResource(R.string.app_language_desc),
                value = LocaleHelper.getLanguageDisplayName(currentLangCode),
                icon = Icons.Rounded.Language,
                onClick = { showLanguageSheet = true }
            )
            ModuleSettingsTile(
                title = stringResource(R.string.update_settings_title),
                description = stringResource(R.string.update_settings_desc),
                icon = WaexIcons.SystemUpdate,
                onClick = { navController.navigateTo(Screen.UpdateSettings) }
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
            val sheetDensity = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides sheetDensity) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(max = 520.dp)
                        .navigationBarsPadding()
                        .padding(horizontal = 24.dp)
                        .padding(bottom = 24.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                Text(
                    text = stringResource(R.string.choose_app_theme),
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
                        border = BorderStroke(
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
                                    contentDescription = UiText.get(R.string.waex_ui_selected_57fd7a0c, "Selected"),
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

    if (showLanguageSheet) {
        val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

        ModalBottomSheet(
            onDismissRequest = { showLanguageSheet = false },
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
            val sheetDensity = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides sheetDensity) {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .navigationBarsPadding()
                        .padding(horizontal = 24.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                    contentPadding = PaddingValues(bottom = 24.dp)
                ) {
                    item {
                        Text(
                        text = stringResource(R.string.choose_app_language),
                        style = WaexTheme.typography.titleLg,
                        fontWeight = FontWeight.SemiBold,
                        color = colors.onSurface,
                        modifier = Modifier.padding(top = 8.dp, bottom = 10.dp)
                    )
                }

                items(LocaleHelper.SUPPORTED_LANGUAGES, key = { it.code }) { lang ->
                    val selected = lang.code == currentLangCode
                    Surface(
                        shape = WaexTheme.radius.mdShape,
                        color = if (selected) colors.primary.copy(alpha = 0.10f) else colors.surface,
                        border = BorderStroke(
                            1.dp,
                            if (selected) colors.primary.copy(alpha = 0.75f) else colors.outlineVariant.copy(alpha = 0.7f)
                        ),
                        modifier = Modifier.fillMaxWidth().clickable {
                            currentLangCode = lang.code
                            LocaleHelper.applyLanguage(context, lang.code)
                            showLanguageSheet = false
                            (context as? Activity)?.recreate()
                        }
                    ) {
                        Row(
                            modifier = Modifier.padding(horizontal = 14.dp, vertical = 9.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    text = LocaleHelper.getLanguageDisplayName(lang.code),
                                    style = WaexTheme.typography.bodyMd,
                                    fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Medium,
                                    color = if (selected) colors.primary else colors.onSurface
                                )
                                if (LocaleHelper.getLanguageExplanation(lang.code) != LocaleHelper.getLanguageDisplayName(lang.code)) {
                                    Text(
                                        text = LocaleHelper.getLanguageExplanation(lang.code),
                                        style = WaexTheme.typography.labelSm,
                                        color = colors.onSurfaceVariant
                                    )
                                }
                            }
                            if (selected) {
                                Icon(
                                    imageVector = WaexIcons.Check,
                                    contentDescription = null,
                                    tint = colors.primary,
                                    modifier = Modifier.size(18.dp)
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

@Composable
private fun InterfaceSizePreference(
    selectedSize: InterfaceSize,
    onSizeSelected: (InterfaceSize) -> Unit
) {
    val colors = WaexTheme.colors
    val typography = WaexTheme.typography
    val sizes = InterfaceSize.entries
    var sliderPosition by remember(selectedSize) { mutableStateOf(selectedSize.ordinal.toFloat()) }

    Surface(
        shape = WaexTheme.radius.cardShape,
        color = colors.surfaceContainerLow,
        border = BorderStroke(1.dp, colors.outlineVariant),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(36.dp)
                        .background(colors.primary.copy(alpha = 0.14f), WaexTheme.radius.mdShape),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = WaexIcons.AutoMode,
                        contentDescription = null,
                        tint = colors.primary,
                        modifier = Modifier.size(18.dp)
                    )
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        text = stringResource(R.string.interface_size_title),
                        style = typography.bodyMd,
                        fontWeight = FontWeight.SemiBold,
                        color = colors.onSurface
                    )
                    Text(
                        text = stringResource(R.string.interface_size_desc),
                        style = typography.bodySm,
                        color = colors.onSurfaceVariant
                    )
                }
                Text(
                    text = interfaceSizeLabel(selectedSize),
                    style = typography.labelSm,
                    fontWeight = FontWeight.SemiBold,
                    color = colors.primary,
                    modifier = Modifier.padding(start = 10.dp)
                )
            }

            Slider(
                value = sliderPosition,
                onValueChange = { sliderPosition = it },
                onValueChangeFinished = {
                    val newSize = sizes[sliderPosition.roundToInt().coerceIn(sizes.indices)]
                    sliderPosition = newSize.ordinal.toFloat()
                    if (newSize != selectedSize) onSizeSelected(newSize)
                },
                valueRange = 0f..(sizes.lastIndex.toFloat()),
                steps = sizes.size - 2,
                modifier = Modifier.fillMaxWidth()
            )

            Row(modifier = Modifier.fillMaxWidth()) {
                sizes.forEach { size ->
                    Text(
                        text = interfaceSizeLabel(size),
                        style = typography.labelSm,
                        color = if (size == selectedSize) colors.primary else colors.onSurfaceVariant,
                        fontWeight = if (size == selectedSize) FontWeight.SemiBold else FontWeight.Normal,
                        modifier = Modifier.weight(1f),
                        textAlign = when (size) {
                            InterfaceSize.COMPACT -> androidx.compose.ui.text.style.TextAlign.Start
                            InterfaceSize.LARGE -> androidx.compose.ui.text.style.TextAlign.End
                            else -> androidx.compose.ui.text.style.TextAlign.Center
                        },
                        maxLines = 1
                    )
                }
            }
        }
    }
}

@Composable
private fun ModuleSettingsTile(
    title: String,
    description: String,
    icon: ImageVector,
    value: String? = null,
    onClick: () -> Unit
) {
    val colors = WaexTheme.colors
    val typography = WaexTheme.typography

    Surface(
        shape = WaexTheme.radius.cardShape,
        color = colors.surfaceContainerLow,
        border = BorderStroke(1.dp, colors.outlineVariant),
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick)
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(36.dp)
                    .background(colors.primary.copy(alpha = 0.14f), WaexTheme.radius.mdShape),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = icon,
                    contentDescription = null,
                    tint = colors.primary,
                    modifier = Modifier.size(18.dp)
                )
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    text = title,
                    style = typography.bodyMd,
                    fontWeight = FontWeight.SemiBold,
                    color = colors.onSurface
                )
                Text(
                    text = description,
                    style = typography.bodySm,
                    color = colors.onSurfaceVariant
                )
            }
            if (value != null) {
                Text(
                    text = value,
                    style = typography.labelSm,
                    fontWeight = FontWeight.SemiBold,
                    color = colors.primary,
                    modifier = Modifier.padding(start = 10.dp)
                )
            }
            Icon(
                imageVector = WaexIcons.ChevronRight,
                contentDescription = null,
                tint = colors.onSurfaceVariant,
                modifier = Modifier.padding(start = 6.dp).size(16.dp)
            )
        }
    }
}

private fun themeIcon(mode: String) = when (mode) {
    "Light" -> WaexIcons.LightMode
    "Dark" -> WaexIcons.DarkMode
    "Monet" -> WaexIcons.Palette
    else -> WaexIcons.AutoMode
}

@Composable
private fun themeLabel(mode: String) = when (mode) {
    "System" -> stringResource(R.string.theme_follow_system)
    "Light" -> stringResource(R.string.theme_light)
    "Dark" -> stringResource(R.string.theme_dark)
    "Monet" -> stringResource(R.string.theme_monet)
    else -> mode
}

@Composable
private fun interfaceSizeLabel(size: InterfaceSize) = when (size) {
    InterfaceSize.COMPACT -> stringResource(R.string.interface_size_compact)
    InterfaceSize.STANDARD -> stringResource(R.string.interface_size_standard)
    InterfaceSize.COMFORTABLE -> stringResource(R.string.interface_size_comfortable)
    InterfaceSize.LARGE -> stringResource(R.string.interface_size_large)
}
