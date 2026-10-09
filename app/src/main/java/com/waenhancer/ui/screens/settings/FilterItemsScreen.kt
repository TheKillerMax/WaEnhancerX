package com.waenhancer.ui.screens.settings

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.waenhancer.model.FilterItem
import com.waenhancer.ui.components.WaexColorPickerDialog
import com.waenhancer.ui.components.WaexEmptyState
import com.waenhancer.ui.components.WaexTopBar
import com.waenhancer.ui.designsystem.WaexIcons
import com.waenhancer.ui.designsystem.WaexTheme
import com.waenhancer.ui.navigation.LocalIsPro
import com.waenhancer.ui.navigation.LocalOnActivatePro
import com.waenhancer.ui.navigation.LocalWaexNavController
import com.waenhancer.ui.navigation.LocalWaexPreferenceManager
import org.json.JSONArray
import org.json.JSONObject

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FilterItemsScreen() {
    val context = LocalContext.current
    val navController = LocalWaexNavController.current
    val preferenceManager = LocalWaexPreferenceManager.current
    val isPro = LocalIsPro.current
    val onActivatePro = LocalOnActivatePro.current

    val colors = WaexTheme.colors
    val spacing = WaexTheme.spacing
    val typography = WaexTheme.typography
    val radius = WaexTheme.radius

    val filtersList = remember { mutableStateListOf<FilterItem>() }
    var showEditSheet by remember { mutableStateOf(false) }
    var editingItem by remember { mutableStateOf<FilterItem?>(null) }
    var editingIndex by remember { mutableIntStateOf(-1) }
    var itemToDelete by remember { mutableStateOf<Pair<Int, FilterItem>?>(null) }

    // Load filters on initial composition
    LaunchedEffect(Unit) {
        filtersList.clear()
        val rawFilters = preferenceManager.getString("filter_items", "") ?: ""
        if (rawFilters.trim().isNotEmpty()) {
            if (rawFilters.trim().startsWith("[")) {
                try {
                    val arr = JSONArray(rawFilters)
                    for (i in 0 until arr.length()) {
                        val obj = arr.getJSONObject(i)
                        val idStr = obj.optString("id", "").trim()
                        if (idStr.isNotEmpty()) {
                            val behavior = obj.optString("behavior", FilterItem.BEHAVIOR_GONE)
                            val color = obj.optInt("color", 0xFFFF0000.toInt())
                            val opacity = obj.optInt("opacity", 100)
                            val scale = (Math.round(obj.optDouble("scale", 1.0) * 10.0) / 10.0).toFloat()
                            filtersList.add(FilterItem(idStr, behavior, color, opacity, scale))
                        }
                    }
                } catch (_: Exception) {}
            } else {
                val items = rawFilters.split("\n")
                for (item in items) {
                    val cleaned = item.trim()
                    if (cleaned.isNotEmpty()) {
                        filtersList.add(FilterItem(cleaned, FilterItem.BEHAVIOR_GONE, 0xFFFF0000.toInt(), 100, 1.0f))
                    }
                }
            }
        }
    }

    fun saveFilters() {
        val arr = JSONArray()
        for (item in filtersList) {
            try {
                val obj = JSONObject()
                obj.put("id", item.id)
                obj.put("behavior", item.behavior)
                obj.put("color", item.color)
                obj.put("opacity", item.opacity)
                obj.put("scale", (Math.round(item.scale * 10.0) / 10.0))
                arr.put(obj)
            } catch (_: Exception) {}
        }
        val filterString = arr.toString()
        preferenceManager.putString("filter_items", filterString)
        preferenceManager.putBoolean("need_restart", true)

        try {
            val authority = context.packageName + ".hookprovider"
            context.contentResolver.notifyChange(
                android.net.Uri.parse("content://$authority/preferences"),
                null
            )
            for (pkg in arrayOf("com.whatsapp", "com.whatsapp.w4b")) {
                val intent = android.content.Intent(context.packageName + ".PREFS_CHANGED")
                intent.setPackage(pkg)
                context.sendBroadcast(intent)
            }
        } catch (_: Exception) {}
    }

    Scaffold(
        topBar = {
            WaexTopBar(
                title = "Filter Items By ID",
                onBackClick = { navController.popBack() }
            )
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = {
                    editingItem = null
                    editingIndex = -1
                    showEditSheet = true
                },
                containerColor = colors.primary,
                contentColor = colors.onPrimary,
                shape = CircleShape
            ) {
                Icon(
                    imageVector = WaexIcons.AutoAwesome,
                    contentDescription = "Add Filter",
                    modifier = Modifier.size(24.dp)
                )
            }
        },
        containerColor = colors.background
    ) { paddingValues ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            if (filtersList.isEmpty()) {
                WaexEmptyState(
                    title = "No Filters Added",
                    description = "Tap + to add a view ID to remove or customize in WhatsApp.",
                    icon = WaexIcons.Palette,
                    modifier = Modifier.align(Alignment.Center)
                )
            } else {
                LazyColumn(
                    contentPadding = PaddingValues(
                        start = spacing.pageMargin,
                        end = spacing.pageMargin,
                        top = 16.dp,
                        bottom = 88.dp
                    ),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                    modifier = Modifier.fillMaxSize()
                ) {
                    itemsIndexed(filtersList, key = { index, item -> "${item.id}_$index" }) { index, item ->
                        Surface(
                            shape = radius.bentoCardShape,
                            color = colors.surfaceDim,
                            border = androidx.compose.foundation.BorderStroke(1.dp, colors.outlineVariant),
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable {
                                    editingItem = item
                                    editingIndex = index
                                    showEditSheet = true
                                }
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(16.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                // Behavior Indicator Icon / Dot
                                when (item.behavior) {
                                    FilterItem.BEHAVIOR_COLOR -> {
                                        Box(
                                            modifier = Modifier
                                                .size(36.dp)
                                                .clip(CircleShape)
                                                .background(Color(item.color))
                                                .border(1.dp, colors.outlineVariant, CircleShape)
                                        )
                                    }
                                    FilterItem.BEHAVIOR_OPACITY -> {
                                        Box(
                                            modifier = Modifier
                                                .size(36.dp)
                                                .clip(CircleShape)
                                                .background(colors.primaryContainer),
                                            contentAlignment = Alignment.Center
                                        ) {
                                            Text(
                                                text = "${item.opacity}%",
                                                style = typography.labelSm,
                                                fontWeight = FontWeight.Bold,
                                                color = colors.primary,
                                                fontSize = 10.sp
                                            )
                                        }
                                    }
                                    FilterItem.BEHAVIOR_RESIZE -> {
                                        Box(
                                            modifier = Modifier
                                                .size(36.dp)
                                                .clip(CircleShape)
                                                .background(colors.primaryContainer),
                                            contentAlignment = Alignment.Center
                                        ) {
                                            Text(
                                                text = String.format(java.util.Locale.US, "%.1fx", item.scale),
                                                style = typography.labelSm,
                                                fontWeight = FontWeight.Bold,
                                                color = colors.primary,
                                                fontSize = 10.sp
                                            )
                                        }
                                    }
                                    else -> {
                                        Box(
                                            modifier = Modifier
                                                .size(36.dp)
                                                .clip(CircleShape)
                                                .background(colors.outlineVariant.copy(alpha = 0.3f)),
                                            contentAlignment = Alignment.Center
                                        ) {
                                            Icon(
                                                imageVector = WaexIcons.Clear,
                                                contentDescription = null,
                                                tint = colors.onSurfaceVariant,
                                                modifier = Modifier.size(18.dp)
                                            )
                                        }
                                    }
                                }

                                Spacer(modifier = Modifier.width(14.dp))

                                Column(
                                    modifier = Modifier.weight(1f),
                                    verticalArrangement = Arrangement.spacedBy(2.dp)
                                ) {
                                    Text(
                                        text = item.id,
                                        style = typography.bodyLg,
                                        fontWeight = FontWeight.SemiBold,
                                        color = colors.onSurface
                                    )
                                    val scaleFormatted = String.format(java.util.Locale.US, "%.1fx", item.scale)
                                    val behaviorText = when (item.behavior) {
                                        FilterItem.BEHAVIOR_COLOR -> "Behavior: Change Color"
                                        FilterItem.BEHAVIOR_OPACITY -> "Behavior: Opacity (${item.opacity}%)"
                                        FilterItem.BEHAVIOR_RESIZE -> "Behavior: Resize ($scaleFormatted)"
                                        else -> "Behavior: Gone (Remove)"
                                    }
                                    Text(
                                        text = behaviorText,
                                        style = typography.bodyMd,
                                        color = colors.onSurfaceVariant,
                                        fontSize = 12.sp
                                    )
                                }

                                IconButton(
                                    onClick = { itemToDelete = index to item },
                                    modifier = Modifier.size(36.dp)
                                ) {
                                    Icon(
                                        imageVector = WaexIcons.Clear,
                                        contentDescription = "Delete",
                                        tint = colors.onSurfaceVariant.copy(alpha = 0.6f),
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

    // Delete Confirmation Dialog
    itemToDelete?.let { (index, item) ->
        AlertDialog(
            onDismissRequest = { itemToDelete = null },
            title = { Text("Delete Filter", style = typography.headlineMd) },
            text = { Text("Are you sure you want to delete filter \"${item.id}\"?", style = typography.bodyMd) },
            confirmButton = {
                TextButton(
                    onClick = {
                        if (index in filtersList.indices) {
                            filtersList.removeAt(index)
                            saveFilters()
                        }
                        itemToDelete = null
                    }
                ) {
                    Text("Delete", color = Color.Red, fontWeight = FontWeight.Bold)
                }
            },
            dismissButton = {
                TextButton(onClick = { itemToDelete = null }) {
                    Text("Cancel")
                }
            },
            containerColor = colors.surface
        )
    }

    // Edit/Add Filter Modal Bottom Sheet
    if (showEditSheet) {
        FilterEditBottomSheet(
            initialItem = editingItem,
            isPro = isPro,
            onActivatePro = onActivatePro,
            onDismiss = { showEditSheet = false },
            onSave = { resultItem ->
                if (editingIndex in filtersList.indices) {
                    filtersList[editingIndex] = resultItem
                } else {
                    filtersList.add(resultItem)
                }
                saveFilters()
                showEditSheet = false
            }
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FilterEditBottomSheet(
    initialItem: FilterItem?,
    isPro: Boolean,
    onActivatePro: () -> Unit,
    onDismiss: () -> Unit,
    onSave: (FilterItem) -> Unit
) {
    val context = LocalContext.current
    val colors = WaexTheme.colors
    val typography = WaexTheme.typography
    val radius = WaexTheme.radius

    val sheetState = rememberModalBottomSheetState(
        skipPartiallyExpanded = true
    )

    var idText by remember { mutableStateOf(initialItem?.id ?: "") }
    var idError by remember { mutableStateOf<String?>(null) }
    var selectedBehavior by remember { mutableStateOf(initialItem?.behavior ?: FilterItem.BEHAVIOR_GONE) }
    var selectedColor by remember { mutableIntStateOf(initialItem?.color ?: 0xFFFF0000.toInt()) }
    var opacityText by remember { mutableStateOf(initialItem?.opacity?.toString() ?: "100") }
    var scaleValue by remember {
        mutableFloatStateOf(
            (Math.round((initialItem?.scale ?: 1.0f) * 10f) / 10f).coerceIn(0.1f, 3.0f)
        )
    }
    var showColorPicker by remember { mutableStateOf(false) }

    val behaviors = listOf(
        FilterItem.BEHAVIOR_GONE to "Gone (Remove)",
        FilterItem.BEHAVIOR_COLOR to "Change Color (Pro)",
        FilterItem.BEHAVIOR_OPACITY to "Opacity (Pro)",
        FilterItem.BEHAVIOR_RESIZE to "Resize (Pro)"
    )

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
                .navigationBarsPadding()
                .imePadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp)
                .padding(top = 8.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Text(
                text = if (initialItem != null) "Edit Filter" else "Add Filter",
                style = typography.headlineMd,
                fontWeight = FontWeight.Bold,
                color = colors.onSurface
            )

            OutlinedTextField(
                value = idText,
                onValueChange = {
                    idText = it
                    if (it.isNotBlank()) idError = null
                },
                label = { Text("Filter View ID") },
                placeholder = { Text("e.g. conversation_row_date") },
                isError = idError != null,
                supportingText = idError?.let { { Text(it, color = Color.Red) } },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                shape = radius.defaultShape
            )

            Text(
                text = "Behavior",
                style = typography.labelSm,
                fontWeight = FontWeight.Bold,
                color = colors.onSurfaceVariant
            )

            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                behaviors.forEach { (behavior, label) ->
                    val isSelected = selectedBehavior == behavior
                    val isProBehavior = behavior != FilterItem.BEHAVIOR_GONE
                    Surface(
                        shape = radius.defaultShape,
                        color = if (isSelected) colors.primaryContainer else colors.surfaceDim,
                        border = androidx.compose.foundation.BorderStroke(
                            1.dp,
                            if (isSelected) colors.primary else colors.outlineVariant
                        ),
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable {
                                if (isProBehavior && !isPro) {
                                    Toast.makeText(context, "This behavior requires Pro license.", Toast.LENGTH_SHORT).show()
                                    onActivatePro()
                                } else {
                                    selectedBehavior = behavior
                                }
                            }
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 14.dp, vertical = 10.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            RadioButton(
                                selected = isSelected,
                                onClick = {
                                    if (isProBehavior && !isPro) {
                                        Toast.makeText(context, "This behavior requires Pro license.", Toast.LENGTH_SHORT).show()
                                        onActivatePro()
                                    } else {
                                        selectedBehavior = behavior
                                    }
                                },
                                colors = RadioButtonDefaults.colors(selectedColor = colors.primary)
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = label,
                                style = typography.bodyMd,
                                fontWeight = if (isSelected) FontWeight.SemiBold else FontWeight.Normal,
                                color = if (isSelected) colors.primary else colors.onSurface
                            )
                        }
                    }
                }
            }

            // Sub-controls based on behavior
            when (selectedBehavior) {
                FilterItem.BEHAVIOR_COLOR -> {
                    Surface(
                        shape = radius.defaultShape,
                        color = colors.surfaceDim,
                        border = androidx.compose.foundation.BorderStroke(1.dp, colors.outlineVariant),
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { showColorPicker = true }
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(14.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Box(
                                modifier = Modifier
                                    .size(28.dp)
                                    .clip(CircleShape)
                                    .background(Color(selectedColor))
                                    .border(1.dp, colors.outlineVariant, CircleShape)
                            )
                            Spacer(modifier = Modifier.width(12.dp))
                            Text(
                                text = "Choose Color",
                                style = typography.bodyMd,
                                color = colors.onSurface
                            )
                        }
                    }
                }
                FilterItem.BEHAVIOR_OPACITY -> {
                    OutlinedTextField(
                        value = opacityText,
                        onValueChange = { opacityText = it },
                        label = { Text("Opacity (0 - 100)") },
                        suffix = { Text("%") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        shape = radius.defaultShape
                    )
                }
                FilterItem.BEHAVIOR_RESIZE -> {
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(
                            text = "Scale: ${String.format(java.util.Locale.US, "%.1fx", scaleValue)}",
                            style = typography.bodyMd,
                            color = colors.onSurfaceVariant
                        )
                        Slider(
                            value = scaleValue,
                            onValueChange = {
                                val rounded = Math.round(it * 10f) / 10f
                                scaleValue = (Math.round(rounded * 10f) / 10f).coerceIn(0.1f, 3.0f)
                            },
                            valueRange = 0.1f..3.0f,
                            steps = 28,
                            colors = SliderDefaults.colors(
                                thumbColor = colors.primary,
                                activeTrackColor = colors.primary
                            )
                        )
                        Text(
                            text = "Note: Resizing view elements dynamically requires extra layout rendering. This may cause screens containing these elements to load with a minor delay.",
                            style = typography.labelSm,
                            color = colors.error,
                            fontSize = 11.sp
                        )
                    }
                }
            }

            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp),
                horizontalArrangement = Arrangement.End,
                verticalAlignment = Alignment.CenterVertically
            ) {
                TextButton(onClick = onDismiss) {
                    Text("Cancel")
                }
                Spacer(modifier = Modifier.width(8.dp))
                Button(
                    onClick = {
                        val trimmedId = idText.trim()
                        if (trimmedId.isEmpty()) {
                            idError = "View ID cannot be empty"
                            return@Button
                        }

                        var opacity = 100
                        if (selectedBehavior == FilterItem.BEHAVIOR_OPACITY) {
                            opacity = opacityText.toIntOrNull() ?: 100
                            opacity = opacity.coerceIn(0, 100)
                        }

                        val roundedScale = (Math.round(scaleValue * 10.0) / 10.0).toFloat()

                        onSave(
                            FilterItem(
                                id = trimmedId,
                                behavior = selectedBehavior,
                                color = selectedColor,
                                opacity = opacity,
                                scale = roundedScale
                            )
                        )
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = colors.primary),
                    shape = radius.defaultShape
                ) {
                    Text("Save", color = colors.onPrimary, fontWeight = FontWeight.Bold)
                }
            }
        }
    }

    if (showColorPicker) {
        val hexString = String.format("#%06X", 0xFFFFFF and selectedColor)
        WaexColorPickerDialog(
            initialColorHex = hexString,
            onColorSelected = { hex ->
                try {
                    selectedColor = android.graphics.Color.parseColor(hex)
                } catch (_: Exception) {}
                showColorPicker = false
            },
            onDismiss = { showColorPicker = false }
        )
    }
}
