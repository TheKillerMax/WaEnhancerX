package com.waenhancer.ui.components

import android.graphics.Color as AndroidColor
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.waenhancer.ui.designsystem.WaexTheme

private val PRESET_COLORS = listOf(
    "#EF4444", "#DC2626", "#E11D48", "#F43F5E",
    "#F97316", "#F59E0B", "#EAB308", "#10B981",
    "#14B8A6", "#06B6D4", "#3B82F6", "#6366F1",
    "#8B5CF6", "#A855F7", "#D946EF", "#EC4899"
)

@OptIn(ExperimentalLayoutApi::class, ExperimentalMaterial3Api::class)
@Composable
fun WaexColorPickerDialog(
    initialColorHex: String,
    onColorSelected: (String) -> Unit,
    onDismiss: () -> Unit
) {
    val colors = WaexTheme.colors
    val typography = WaexTheme.typography
    val radius = WaexTheme.radius
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    var selectedColorHex by remember { mutableStateOf(initialColorHex.ifEmpty { "#EF4444" }) }
    var parsedColor by remember(selectedColorHex) {
        mutableStateOf(
            try {
                Color(AndroidColor.parseColor(selectedColorHex))
            } catch (_: Throwable) {
                Color(0xFFEF4444)
            }
        )
    }

    val hsv = remember(parsedColor) {
        val hsvArray = FloatArray(3)
        AndroidColor.colorToHSV(parsedColor.toArgb(), hsvArray)
        hsvArray
    }

    var hue by remember(parsedColor) { mutableFloatStateOf(hsv[0]) }
    var saturation by remember(parsedColor) { mutableFloatStateOf(hsv[1]) }
    var value by remember(parsedColor) { mutableFloatStateOf(hsv[2]) }

    fun updateFromHsv(h: Float, s: Float, v: Float) {
        val argb = AndroidColor.HSVToColor(floatArrayOf(h, s, v))
        val hex = String.format("#%06X", 0xFFFFFF and argb)
        selectedColorHex = hex
        parsedColor = Color(argb)
    }

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
                .padding(bottom = 24.dp)
        ) {
                Text(
                    text = "Select Accent Color",
                    style = typography.headlineMd,
                    color = colors.onSurface,
                    fontWeight = FontWeight.Bold
                )

                Spacer(modifier = Modifier.height(16.dp))

                // Live Preview & Hex Input
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    Box(
                        modifier = Modifier
                            .size(52.dp)
                            .clip(CircleShape)
                            .background(parsedColor)
                            .border(2.dp, colors.outline, CircleShape)
                    )

                    OutlinedTextField(
                        value = selectedColorHex,
                        onValueChange = { input ->
                            val cleanInput = if (!input.startsWith("#")) "#$input" else input
                            selectedColorHex = cleanInput
                            try {
                                if (cleanInput.length == 7) {
                                    parsedColor = Color(AndroidColor.parseColor(cleanInput))
                                }
                            } catch (_: Throwable) {}
                        },
                        label = { Text("Hex Code", style = typography.labelSm) },
                        textStyle = typography.bodyMd.copy(fontWeight = FontWeight.Bold),
                        modifier = Modifier.weight(1f),
                        singleLine = true,
                        shape = RoundedCornerShape(12.dp)
                    )
                }

                Spacer(modifier = Modifier.height(16.dp))

                // Presets Palette
                Text(
                    text = "Presets",
                    style = typography.labelSm,
                    color = colors.onSurfaceVariant,
                    fontWeight = FontWeight.Medium
                )

                Spacer(modifier = Modifier.height(8.dp))

                FlowRow(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    PRESET_COLORS.forEach { hex ->
                        val presetColor = try {
                            Color(AndroidColor.parseColor(hex))
                        } catch (_: Throwable) {
                            Color.Red
                        }
                        val isSelected = selectedColorHex.equals(hex, ignoreCase = true)

                        Box(
                            modifier = Modifier
                                .size(32.dp)
                                .clip(CircleShape)
                                .background(presetColor)
                                .border(
                                    width = if (isSelected) 3.dp else 1.dp,
                                    color = if (isSelected) colors.onSurface else Color.Transparent,
                                    shape = CircleShape
                                )
                                .clickable {
                                    selectedColorHex = hex
                                    parsedColor = presetColor
                                }
                        )
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))

                // Sliders (Hue, Saturation, Brightness)
                Text(
                    text = "Hue",
                    style = typography.labelSm,
                    color = colors.onSurfaceVariant
                )
                Slider(
                    value = hue,
                    onValueChange = {
                        hue = it
                        updateFromHsv(hue, saturation, value)
                    },
                    valueRange = 0f..360f,
                    colors = SliderDefaults.colors(
                        thumbColor = colors.primary,
                        activeTrackColor = colors.primary
                    )
                )

                Text(
                    text = "Saturation",
                    style = typography.labelSm,
                    color = colors.onSurfaceVariant
                )
                Slider(
                    value = saturation,
                    onValueChange = {
                        saturation = it
                        updateFromHsv(hue, saturation, value)
                    },
                    valueRange = 0f..1f,
                    colors = SliderDefaults.colors(
                        thumbColor = colors.primary,
                        activeTrackColor = colors.primary
                    )
                )

                Text(
                    text = "Brightness",
                    style = typography.labelSm,
                    color = colors.onSurfaceVariant
                )
                Slider(
                    value = value,
                    onValueChange = {
                        value = it
                        updateFromHsv(hue, saturation, value)
                    },
                    valueRange = 0f..1f,
                    colors = SliderDefaults.colors(
                        thumbColor = colors.primary,
                        activeTrackColor = colors.primary
                    )
                )

                Spacer(modifier = Modifier.height(16.dp))

                // Actions
                Button(
                    onClick = {
                        onColorSelected(selectedColorHex)
                        onDismiss()
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = colors.primary),
                    shape = radius.buttonShape,
                    modifier = Modifier.fillMaxWidth().height(50.dp)
                ) {
                    Text("Apply", color = colors.onPrimary, fontWeight = FontWeight.Bold)
                }
                Spacer(modifier = Modifier.height(10.dp))
                OutlinedButton(
                    onClick = onDismiss,
                    shape = radius.buttonShape,
                    modifier = Modifier.fillMaxWidth().height(50.dp)
                ) {
                    Text("Cancel", color = colors.onSurface)
                }
        }
    }
}
