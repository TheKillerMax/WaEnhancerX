package com.waenhancer.ui.screens.settings

import com.waenhancer.utils.UiText

import android.widget.Toast
import com.waenhancer.ui.components.WaexProChip

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInRoot
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext
import com.waenhancer.config.FeatureCatalog
import com.waenhancer.config.FeatureItem
import com.waenhancer.ui.components.StitchSwitch
import com.waenhancer.ui.designsystem.WaexIcons
import com.waenhancer.ui.designsystem.WaexTheme
import com.waenhancer.ui.navigation.LocalWaexNavController
import com.waenhancer.utils.LocalizationHelper
import kotlinx.coroutines.delay
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.ui.res.stringResource
import com.waenhancer.app.R
import com.waenhancer.core.preferences.WaexPreferenceManager
import com.waenhancer.ui.navigation.LocalIsPro
import com.waenhancer.ui.navigation.LocalOnActivatePro
import com.waenhancer.ui.navigation.LocalWaexPreferenceManager
import com.waenhancer.ui.navigation.Screen

@Composable
fun StylesSettingsScreen() {
    val colors = WaexTheme.colors
    val spacing = WaexTheme.spacing
    val typography = WaexTheme.typography
    val radius = WaexTheme.radius

    var selectedTab by remember { mutableStateOf("appearance") } // "appearance" | "layout"
    var typedEditorKey by remember { mutableStateOf<String?>(null) }
    var typedValueRevision by remember { mutableIntStateOf(0) }

    val navController = LocalWaexNavController.current
    val context = LocalContext.current
    val scrollState = rememberScrollState()
    val itemCoordinates = remember { mutableStateMapOf<String, Float>() }
    var containerY by remember { mutableStateOf(0f) }

    LaunchedEffect(navController.targetSubTabId) {
        val target = navController.targetSubTabId
        if (target == "appearance" || target == "layout") {
            selectedTab = target
            navController.targetSubTabId = null
        }
    }

    LaunchedEffect(navController.scrollToTargetKey, itemCoordinates.keys.toList()) {
        val target = navController.scrollToTargetKey
        if (target != null) {
            delay(100)
            if (itemCoordinates.containsKey(target)) {
                val yOffset = itemCoordinates[target] ?: 0f
                scrollState.animateScrollTo(yOffset.toInt())
                navController.scrollToTargetKey = null
            }
        }
    }

    LaunchedEffect(navController.highlightTargetKey) {
        val target = navController.highlightTargetKey
        if (target != null) {
            delay(2000)
            if (navController.highlightTargetKey == target) {
                navController.highlightTargetKey = null
            }
        }
    }

    val preferenceManager = LocalWaexPreferenceManager.current
    val stylesKeys = remember {
        listOf(
            "bubble_colors", "custom_theme", "custom_time_format", "custom_toolbar",
            "custom_view_dpi", "seen_tick_customization", "floating_bottom_bar",
            "unlock_premium_customization", "custom_filters",
            "dotonline", "showonlinetext", "typing_online_toasts",
            "metaai", "channels_enhancements", "chat_filters", "hide_ui_tabs",
            "instagram_status_layout", "separate_groups_tabs", "quick_home_menu",
            "contact_blocked_verify",
            "send_audio_as_voice_status", "disable_sensor_proximity"
        )
    }

    val settingsState = remember {
        mutableStateMapOf<String, Boolean>().apply {
            stylesKeys.forEach { key ->
                if (StyleNonBooleanPreferencePolicy.requiresDedicatedEditor(key)) {
                    // Do not decode a STRING or STRING_SET using getBoolean().
                    put(key, false)
                } else if (key == "seen_tick_customization") {
                    // The receipt hooks read the canonical STRING 'seentick' (0/1/2),
                    // not the old UI-only Boolean 'seen_tick_customization' flag.
                    put(key, ManualSeenTickPreferencePolicy.isEnabled(
                        preferenceManager.getString("seentick", "0")
                    ))
                } else {
                    val defaultValue = if (key == "send_audio_as_voice_status") {
                        preferenceManager.getBoolean("voice_status_enhancement", false)
                    } else false
                    val canonicalKey = StyleBooleanAliasPolicy.canonicalKey(key)
                    val legacyDefault = if (canonicalKey == key) defaultValue
                        else preferenceManager.getBoolean(key, defaultValue)
                    put(key, preferenceManager.getBoolean(canonicalKey, legacyDefault))
                }
            }
        }
    }

    val updatePreference: (String, Boolean) -> Unit = update@{ key, value ->
        if (StyleNonBooleanPreferencePolicy.requiresDedicatedEditor(key)) return@update
        if (key == "seen_tick_customization") {
            val currentPlacement = preferenceManager.getString("seentick", "0")
            val nextPlacement = ManualSeenTickPreferencePolicy.valueAfterExplicitToggle(value, currentPlacement)
            if (preferenceManager.putPublicString("seentick", nextPlacement)) {
                settingsState[key] = ManualSeenTickPreferencePolicy.isEnabled(nextPlacement)
            } else {
                // A failed commit can already have changed memory. Keep the last confirmed UI state.
                Toast.makeText(context, "Unable to save setting", Toast.LENGTH_SHORT).show()
            }
            return@update
        }
        val canonicalKey = StyleBooleanAliasPolicy.canonicalKey(key)
        val changes = if (key == "send_audio_as_voice_status") {
            // Persist the visible setting and its linked hook key atomically.
            mapOf(canonicalKey to value, "voice_status_enhancement" to value)
        } else {
            mapOf(canonicalKey to value)
        }
        if (preferenceManager.putBooleans(changes)) {
            settingsState[key] = preferenceManager.getBoolean(canonicalKey, value)
        } else {
            // Failed commits must not appear as successful changes in the UI.
            Toast.makeText(context, UiText.get(R.string.waex_ui_unable_to_save_setting_d9dcb19d, "Unable to save setting"), Toast.LENGTH_SHORT).show()
        }
    }


    val isPro = LocalIsPro.current
    val onActivatePro = LocalOnActivatePro.current

    val appearanceGroups = remember {
        FeatureCatalog.groupsFor(4, "appearance").map { StyleGroup(it.id, WaexIcons.Palette, it.items()) }
    }
    val layoutGroups = remember {
        FeatureCatalog.groupsFor(4, "layout").map { group ->
            val icon = when (group.id) {
                "conversation_list_activity_presence" -> WaexIcons.Security
                "home_layout_navigation" -> WaexIcons.GridView
                else -> WaexIcons.Extension
            }
            StyleGroup(group.id, icon, group.items())
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(scrollState)
            .onGloballyPositioned { containerCoordinates ->
                containerY = containerCoordinates.positionInRoot().y
            }
            .padding(vertical = 20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // Tab switcher header
        Surface(
            shape = radius.mdShape,
            color = colors.surfaceDim,
            border = BorderStroke(1.dp, colors.outlineVariant),
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = spacing.pageMargin)
                .height(48.dp)
        ) {
            BoxWithConstraints(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(4.dp)
            ) {
                val totalWidth = maxWidth
                val tabWidth = totalWidth / 2

                val activeIndex = if (selectedTab == "appearance") 0 else 1
                val targetOffset = tabWidth * activeIndex
                val animatedOffset by animateDpAsState(
                    targetValue = targetOffset,
                    animationSpec = spring(
                        dampingRatio = Spring.DampingRatioLowBouncy,
                        stiffness = Spring.StiffnessLow
                    ),
                    label = "styles_tab_offset"
                )

                // Sliding highlight box
                Box(
                    modifier = Modifier
                        .offset(x = animatedOffset)
                        .width(tabWidth)
                        .fillMaxHeight()
                        .clip(radius.defaultShape)
                        .background(colors.surface)
                        .border(1.dp, colors.outlineVariant, radius.defaultShape)
                )

                Row(
                    modifier = Modifier.fillMaxSize(),
                    horizontalArrangement = Arrangement.SpaceAround
                ) {
                    listOf("appearance" to UiText.get(R.string.waex_ui_appearance_3907fa7f, "Appearance"), "layout" to UiText.get(R.string.waex_ui_home_feed_ea0a795f, "Home & Feed")).forEach { (tabId, label) ->
                        val isSelected = selectedTab == tabId
                        val textColor by animateColorAsState(
                            targetValue = if (isSelected) colors.primary else colors.onSurfaceVariant,
                            animationSpec = tween(150),
                            label = "styles_tab_text_color"
                        )

                        Box(
                            modifier = Modifier
                                .fillMaxHeight()
                                .weight(1f)
                                .clickable(
                                    interactionSource = remember { MutableInteractionSource() },
                                    indication = null
                                ) { selectedTab = tabId },
                            contentAlignment = Alignment.Center
                        ) {
                            Text(
                                text = label,
                                style = typography.bodyMd,
                                fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium,
                                color = textColor
                            )
                        }
                    }
                }
            }
        }

        // Render Style Groups
        val activeGroups = if (selectedTab == "appearance") appearanceGroups else layoutGroups
        activeGroups.forEach { group ->
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = spacing.pageMargin)
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    modifier = Modifier.padding(start = 4.dp, bottom = 8.dp)
                ) {
                    Icon(
                        imageVector = group.icon,
                        contentDescription = null,
                        tint = colors.primary,
                        modifier = Modifier.size(14.dp)
                    )
                    Text(
                        text = LocalizationHelper.getLocalizedSectionTitle(context, group.title),
                        style = typography.labelSm,
                        fontWeight = FontWeight.Bold,
                        color = colors.onSurfaceVariant
                    )
                }

                Surface(
                    shape = radius.bentoCardShape,
                    color = colors.surfaceDim,
                    border = BorderStroke(1.dp, colors.outlineVariant),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column {
                        group.items.forEachIndexed { index, item ->
                            val isLocked = item.isPro && !isPro
                            val needsTypedEditor = StyleNonBooleanPreferencePolicy.requiresDedicatedEditor(item.key)
                            val isHighlighted = navController.highlightTargetKey == item.key
                            val highlightBgColor by animateColorAsState(
                                targetValue = if (isHighlighted) colors.primary.copy(alpha = 0.15f) else Color.Transparent,
                                animationSpec = tween(durationMillis = 300),
                                label = "highlight_bg"
                            )
                            val locTitle = LocalizationHelper.getTitle(context, item)
                            val locDesc = LocalizationHelper.getDesc(context, item)
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .background(highlightBgColor)
                                    .onGloballyPositioned { coordinates ->
                                        val y = coordinates.positionInRoot().y - containerY + scrollState.value
                                        itemCoordinates[item.key] = y
                                    }
                                    .clickable {
                                        if (isLocked) {
                                            onActivatePro()
                                        } else if (needsTypedEditor) {
                                            typedEditorKey = item.key
                                        } else {
                                            val currentVal = settingsState[item.key] ?: false
                                            updatePreference(item.key, !currentVal)
                                        }
                                    }
                            ) {
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(horizontal = 16.dp, vertical = 14.dp)
                                        .then(if (isLocked) Modifier.alpha(0.6f) else Modifier),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Column(
                                        modifier = Modifier.weight(1f),
                                        verticalArrangement = Arrangement.spacedBy(4.dp)
                                    ) {
                                        Text(
                                            text = locTitle,
                                            style = typography.bodyLg,
                                            fontWeight = FontWeight.Medium,
                                            color = colors.onSurface
                                        )
                                        val reqPro = stringResource(R.string.requires_pro_label)
                                        Text(
                                            text = if (needsTypedEditor) "$locDesc • ${typedStyleSummary(item.key, preferenceManager, typedValueRevision)}"
                                                else if (isLocked) "$locDesc • $reqPro" else locDesc,
                                            style = typography.bodyMd,
                                            color = colors.onSurfaceVariant,
                                            fontSize = 12.sp
                                        )
                                    }
                                    Row(
                                        verticalAlignment = Alignment.CenterVertically,
                                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                                    ) {
                                        if (item.key == "floating_bottom_bar") {
                                            IconButton(
                                                onClick = {
                                                    navController.navigateTo(Screen.FloatingBottomBarCustomizer)
                                                },
                                                modifier = Modifier.size(36.dp)
                                            ) {
                                                Icon(
                                                    imageVector = WaexIcons.Settings,
                                                    contentDescription = UiText.get(R.string.waex_ui_customize_floating_bottom_bar_58ae0180, "Customize Floating Bottom Bar"),
                                                    tint = colors.primary,
                                                    modifier = Modifier.size(20.dp)
                                                )
                                            }
                                        }
                                        if (item.key == "custom_filters") {
                                            IconButton(
                                                onClick = {
                                                    navController.navigateTo(Screen.FilterItems)
                                                },
                                                modifier = Modifier.size(36.dp)
                                            ) {
                                                Icon(
                                                    imageVector = WaexIcons.Settings,
                                                    contentDescription = UiText.get(R.string.waex_ui_configure_filter_items_1e380999, "Configure Filter Items"),
                                                    tint = colors.primary,
                                                    modifier = Modifier.size(20.dp)
                                                )
                                            }
                                        }
                                        if (needsTypedEditor) {
                                            Icon(
                                                imageVector = WaexIcons.ChevronRight,
                                                contentDescription = UiText.get(R.string.waex_ui_configure_1_s_a548a230, "Configure %1\$s", locTitle),
                                                tint = colors.primary,
                                                modifier = Modifier.size(20.dp)
                                            )
                                        } else {
                                            StitchSwitch(
                                                checked = if (isLocked) false else (settingsState[item.key] ?: false),
                                                onCheckedChange = if (isLocked) null else { isChecked -> updatePreference(item.key, isChecked) },
                                                enabled = !isLocked
                                            )
                                        }
                                    }
                                }
                                if (item.isPro) {
                                    WaexProChip(
                                        isUnlocked = isPro,
                                        modifier = Modifier.align(Alignment.TopEnd)
                                    )
                                }
                            }
                            if (index < group.items.lastIndex) {
                                HorizontalDivider(thickness = 1.dp, color = colors.outlineVariant)
                            }
                        }
                    }
                }
            }
        }
        Spacer(modifier = Modifier.height(100.dp))
    }

    typedEditorKey?.let { key ->
        TypedStyleEditorDialog(
            key = key,
            preferenceManager = preferenceManager,
            onDismiss = { typedEditorKey = null },
            onSaved = {
                typedValueRevision++
                typedEditorKey = null
            }
        )
    }

}

@Composable
private fun TypedStyleEditorDialog(
    key: String,
    preferenceManager: WaexPreferenceManager,
    onDismiss: () -> Unit,
    onSaved: () -> Unit
) {
    val context = LocalContext.current
    val completeSave: (Boolean) -> Unit = { saved ->
        if (saved) {
            onSaved()
        } else {
            // Keep the editor and its input open so the user can retry.
            Toast.makeText(context, UiText.get(R.string.waex_ui_unable_to_save_setting_d9dcb19d, "Unable to save setting"), Toast.LENGTH_SHORT).show()
        }
    }
    when (key) {
        "custom_theme" -> TextValueEditorDialog(
            title = UiText.get(R.string.feat_custom_theme_title, "Custom Theme CSS"),
            description = UiText.get(R.string.waex_ui_style_whatsapp_views_using_ids_widget_eedbeb45, "Style WhatsApp views using IDs, widget types, scoped activities, and common CSS properties. Restart WhatsApp after saving."),
            initialValue = preferenceManager.getString("css_theme", "") ?: "",
            singleLine = false,
            placeholder = "#conversation_row_date {\n  color: #FFFFFF;\n  font-size: 12sp;\n}",
            validator = ::isValidCustomCss,
            errorMessage = UiText.get(R.string.waex_ui_check_that_every_selector_has_a_matchi_c94dfb11, "Check that every selector has a matching { } block"),
            onDismiss = onDismiss,
            onSave = { completeSave(preferenceManager.putPublicString("css_theme", it.trim())) }
        )
        "custom_view_dpi" -> TextValueEditorDialog(
            title = UiText.get(R.string.waex_ui_default_dpi_9037cbe6, "Default DPI"),
            description = UiText.get(R.string.waex_ui_enter_0_to_use_the_device_default_or_a_2e3826cd, "Enter 0 to use the device default, or a DPI value from 120 to 1000."),
            initialValue = preferenceManager.getString("change_dpi", "0") ?: "0",
            singleLine = true,
            placeholder = "0",
            validator = { value ->
                value.toIntOrNull()?.let { it == 0 || it in 120..1000 } == true
            },
            errorMessage = UiText.get(R.string.waex_ui_enter_0_or_a_number_from_120_to_1000_b5a85be0, "Enter 0 or a number from 120 to 1000"),
            onDismiss = onDismiss,
            onSave = { completeSave(preferenceManager.putPublicString("change_dpi", it.trim())) }
        )
        "chat_filters" -> ChoiceValueEditorDialog(
            title = UiText.get(R.string.waex_ui_chat_filter_display_7d02ece7, "Chat filter display"),
            selectedValue = preferenceManager.getString("chatfilter", "2") ?: "2",
            choices = listOf("0" to UiText.get(R.string.waex_ui_hide_search_14bd5cb7, "Hide search"), "1" to UiText.get(R.string.waex_ui_search_icon_edfdb08d, "Search icon"), "2" to UiText.get(R.string.waex_ui_search_bar_de54d68f, "Search bar")),
            onDismiss = onDismiss,
            onSave = { completeSave(preferenceManager.putPublicString("chatfilter", it)) }
        )
        "quick_home_menu" -> ChoiceValueEditorDialog(
            title = UiText.get(R.string.feat_quick_home_menu_title, "Quick Action Home Menu"),
            selectedValue = preferenceManager.getString("waex_menu_style", "grouped") ?: "grouped",
            choices = listOf(
                "grouped" to UiText.get(R.string.waex_ui_grouped_under_waex_2485cb08, "Grouped under WAEX"),
                "separate" to UiText.get(R.string.waex_ui_separate_menu_items_36c8f114, "Separate menu items"),
                "icons" to UiText.get(R.string.waex_ui_toolbar_icons_12004bba, "Toolbar icons")
            ),
            onDismiss = onDismiss,
            onSave = { completeSave(preferenceManager.putPublicString("waex_menu_style", it)) }
        )
        "hide_ui_tabs" -> MultiChoiceValueEditorDialog(
            title = UiText.get(R.string.waex_ui_hide_home_tabs_98f3a2cc, "Hide home tabs"),
            selectedValues = preferenceManager.getStringSet("hidetabs", emptySet()) ?: emptySet(),
            choices = listOf(
                "300" to UiText.get(R.string.waex_ui_updates_22e2bada, "Updates"),
                "600" to UiText.get(R.string.waex_ui_communities_c864f329, "Communities"),
                "400" to UiText.get(R.string.waex_ui_calls_b73a5e2c, "Calls"),
                "700" to UiText.get(R.string.waex_ui_tools_ea93d6a2, "Tools")
            ),
            onDismiss = onDismiss,
            onSave = { completeSave(preferenceManager.putPublicStringSet("hidetabs", it)) }
        )
        else -> onDismiss()
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TextValueEditorDialog(
    title: String,
    description: String,
    initialValue: String,
    singleLine: Boolean,
    placeholder: String,
    validator: (String) -> Boolean = { true },
    errorMessage: String = UiText.get(R.string.waex_ui_invalid_value_d3c7d623, "Invalid value"),
    onDismiss: () -> Unit,
    onSave: (String) -> Unit
) {
    var value by remember(title, initialValue) { mutableStateOf(initialValue) }
    val valid = validator(value.trim())
    val colors = WaexTheme.colors
    val radius = WaexTheme.radius
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = colors.surface,
        shape = radius.bottomSheetShape
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .imePadding()
                .navigationBarsPadding()
                .padding(horizontal = 20.dp)
                .padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text(description, style = MaterialTheme.typography.bodyMedium, color = colors.onSurfaceVariant)
            OutlinedTextField(
                value = value,
                onValueChange = { value = it },
                modifier = Modifier.fillMaxWidth().then(if (singleLine) Modifier else Modifier.height(220.dp)),
                singleLine = singleLine,
                placeholder = { Text(placeholder) },
                isError = !valid,
                supportingText = if (!valid) ({ Text(errorMessage) }) else null
            )
            Button(
                onClick = { onSave(value) },
                enabled = valid,
                modifier = Modifier.fillMaxWidth().height(50.dp),
                shape = radius.buttonShape
            ) {
                Text(UiText.get(R.string.action_save, "Save"), fontWeight = FontWeight.Bold)
            }
            OutlinedButton(
                onClick = onDismiss,
                modifier = Modifier.fillMaxWidth().height(50.dp),
                shape = radius.buttonShape
            ) {
                Text(UiText.get(R.string.action_cancel, "Cancel"))
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ChoiceValueEditorDialog(
    title: String,
    selectedValue: String,
    choices: List<Pair<String, String>>,
    onDismiss: () -> Unit,
    onSave: (String) -> Unit
) {
    val colors = WaexTheme.colors
    val typography = WaexTheme.typography
    val radius = WaexTheme.radius
    var selected by remember(title, selectedValue) { mutableStateOf(selectedValue) }
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = colors.surface,
        shape = radius.bottomSheetShape,
        dragHandle = {
            Box(
                modifier = Modifier
                    .padding(top = 10.dp, bottom = 6.dp)
                    .size(width = 36.dp, height = 4.dp)
                    .clip(CircleShape)
                    .background(colors.outlineVariant.copy(alpha = 0.6f))
            )
        }
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp)
                .padding(bottom = 28.dp)
        ) {
            // Title
            Text(
                text = title,
                style = typography.headlineMd,
                fontWeight = FontWeight.Bold,
                color = colors.onSurface,
                modifier = Modifier.padding(bottom = 16.dp)
            )

            // Radio options
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 360.dp)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(0.dp)
            ) {
                choices.forEachIndexed { index, (value, label) ->
                    val isSelected = selected == value
                    val bgColor by animateColorAsState(
                        targetValue = if (isSelected) colors.primary.copy(alpha = 0.10f) else Color.Transparent,
                        animationSpec = tween(200),
                        label = "choice_bg_$index"
                    )
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(12.dp))
                            .background(bgColor)
                            .clickable { selected = value }
                            .padding(horizontal = 4.dp, vertical = 2.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        RadioButton(
                            selected = isSelected,
                            onClick = { selected = value },
                            colors = RadioButtonDefaults.colors(
                                selectedColor = colors.primary
                            )
                        )
                        Text(
                            text = label,
                            style = typography.bodyLg,
                            color = if (isSelected) colors.primary else colors.onSurface,
                            fontWeight = if (isSelected) FontWeight.SemiBold else FontWeight.Normal,
                            modifier = Modifier.padding(start = 4.dp)
                        )
                    }
                    if (index < choices.lastIndex) {
                        HorizontalDivider(
                            thickness = 1.dp,
                            color = colors.outlineVariant.copy(alpha = 0.4f),
                            modifier = Modifier.padding(start = 56.dp)
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Confirm button
            Button(
                onClick = { onSave(selected) },
                modifier = Modifier.fillMaxWidth().height(50.dp),
                shape = radius.fullShape,
                colors = ButtonDefaults.buttonColors(
                    containerColor = colors.primary,
                    contentColor = colors.onPrimary
                )
            ) {
                Text(text = UiText.get(R.string.action_apply, "Apply"), fontWeight = FontWeight.Bold, fontSize = 15.sp)
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Cancel
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.fillMaxWidth().height(44.dp),
                shape = radius.fullShape
            ) {
                Text(
                    text = UiText.get(R.string.action_cancel, "Cancel"),
                    fontWeight = FontWeight.Medium,
                    color = colors.onSurfaceVariant,
                    fontSize = 14.sp
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MultiChoiceValueEditorDialog(
    title: String,
    selectedValues: Set<String>,
    choices: List<Pair<String, String>>,
    onDismiss: () -> Unit,
    onSave: (Set<String>) -> Unit
) {
    val colors = WaexTheme.colors
    val typography = WaexTheme.typography
    val radius = WaexTheme.radius
    val selected = remember(title, selectedValues) { mutableStateListOf<String>().apply { addAll(selectedValues) } }
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = colors.surface,
        shape = radius.bottomSheetShape,
        dragHandle = {
            Box(
                modifier = Modifier
                    .padding(top = 10.dp, bottom = 6.dp)
                    .size(width = 36.dp, height = 4.dp)
                    .clip(CircleShape)
                    .background(colors.outlineVariant.copy(alpha = 0.6f))
            )
        }
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp)
                .padding(bottom = 28.dp)
        ) {
            // Title
            Text(
                text = title,
                style = typography.headlineMd,
                fontWeight = FontWeight.Bold,
                color = colors.onSurface,
                modifier = Modifier.padding(bottom = 16.dp)
            )

            // Checkbox options
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 360.dp)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(0.dp)
            ) {
                choices.forEachIndexed { index, (value, label) ->
                    val checked = value in selected
                    val bgColor by animateColorAsState(
                        targetValue = if (checked) colors.primary.copy(alpha = 0.10f) else Color.Transparent,
                        animationSpec = tween(200),
                        label = "multi_choice_bg_$index"
                    )
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(12.dp))
                            .background(bgColor)
                            .clickable {
                                if (checked) selected.remove(value) else selected.add(value)
                            }
                            .padding(horizontal = 4.dp, vertical = 2.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Checkbox(
                            checked = checked,
                            onCheckedChange = { enabled ->
                                if (enabled) { if (value !in selected) selected.add(value) }
                                else selected.remove(value)
                            },
                            colors = CheckboxDefaults.colors(
                                checkedColor = colors.primary,
                                uncheckedColor = colors.onSurfaceVariant
                            )
                        )
                        Text(
                            text = label,
                            style = typography.bodyLg,
                            color = if (checked) colors.primary else colors.onSurface,
                            fontWeight = if (checked) FontWeight.SemiBold else FontWeight.Normal,
                            modifier = Modifier.padding(start = 4.dp)
                        )
                    }
                    if (index < choices.lastIndex) {
                        HorizontalDivider(
                            thickness = 1.dp,
                            color = colors.outlineVariant.copy(alpha = 0.4f),
                            modifier = Modifier.padding(start = 56.dp)
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Confirm button
            Button(
                onClick = { onSave(selected.toSet()) },
                modifier = Modifier.fillMaxWidth().height(50.dp),
                shape = radius.fullShape,
                colors = ButtonDefaults.buttonColors(
                    containerColor = colors.primary,
                    contentColor = colors.onPrimary
                )
            ) {
                Text(text = UiText.get(R.string.action_apply, "Apply"), fontWeight = FontWeight.Bold, fontSize = 15.sp)
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Cancel
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.fillMaxWidth().height(44.dp),
                shape = radius.fullShape
            ) {
                Text(
                    text = UiText.get(R.string.action_cancel, "Cancel"),
                    fontWeight = FontWeight.Medium,
                    color = colors.onSurfaceVariant,
                    fontSize = 14.sp
                )
            }
        }
    }
}

private fun isValidCustomCss(css: String): Boolean {
    if (css.isBlank()) return true
    var depth = 0
    var inComment = false
    var index = 0
    while (index < css.length) {
        if (!inComment && index + 1 < css.length && css[index] == '/' && css[index + 1] == '*') {
            inComment = true
            index += 2
            continue
        }
        if (inComment && index + 1 < css.length && css[index] == '*' && css[index + 1] == '/') {
            inComment = false
            index += 2
            continue
        }
        if (!inComment) {
            when (css[index]) {
                '{' -> depth++
                '}' -> if (--depth < 0) return false
            }
        }
        index++
    }
    return !inComment && depth == 0 && css.contains('{')
}

private fun typedStyleSummary(
    key: String,
    preferenceManager: WaexPreferenceManager,
    @Suppress("UNUSED_PARAMETER") revision: Int
): String = when (key) {
    "custom_theme" -> if (preferenceManager.getString("css_theme", "").isNullOrBlank()) UiText.get(R.string.waex_ui_not_configured_dd1841d2, "Not configured") else UiText.get(R.string.waex_ui_configured_84aebc69, "Configured")
    "custom_view_dpi" -> preferenceManager.getString("change_dpi", "0")?.let { if (it == "0") UiText.get(R.string.waex_ui_device_default_aa46c373, "Device default") else "$it DPI" } ?: UiText.get(R.string.waex_ui_device_default_aa46c373, "Device default")
    "chat_filters" -> when (preferenceManager.getString("chatfilter", "2")) { "0" -> UiText.get(R.string.waex_ui_search_hidden_7723b9b3, "Search hidden"); "1" -> UiText.get(R.string.waex_ui_search_icon_edfdb08d, "Search icon"); else -> UiText.get(R.string.waex_ui_search_bar_de54d68f, "Search bar") }
    "hide_ui_tabs" -> preferenceManager.getStringSet("hidetabs", emptySet())?.let { if (it.isEmpty()) UiText.get(R.string.waex_ui_no_tabs_hidden_eb0aba28, "No tabs hidden") else UiText.get(R.string.waex_ui_1_s_hidden_416c73f0, "%1\$s hidden", it.size) } ?: UiText.get(R.string.waex_ui_no_tabs_hidden_eb0aba28, "No tabs hidden")
    "quick_home_menu" -> when (preferenceManager.getString("waex_menu_style", "grouped")) { "separate" -> UiText.get(R.string.waex_ui_separate_items_7f91460e, "Separate items"); "icons" -> UiText.get(R.string.waex_ui_toolbar_icons_12004bba, "Toolbar icons"); else -> UiText.get(R.string.waex_ui_grouped_89731456, "Grouped") }
    else -> UiText.get(R.string.waex_ui_configure_6defafa2, "Configure")
}

private data class StyleGroup(
    val title: String,
    val icon: ImageVector,
    val items: List<FeatureItem>
)


@Preview(showBackground = true)
@Composable
fun StylesSettingsScreenPreview() {
    WaexTheme {
        StylesSettingsScreen()
    }
}
