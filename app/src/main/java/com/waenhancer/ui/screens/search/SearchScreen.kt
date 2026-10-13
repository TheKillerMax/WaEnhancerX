package com.waenhancer.ui.screens.search

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.waenhancer.config.FeatureCatalog
import com.waenhancer.config.FeatureItem
import com.waenhancer.ui.components.WaexSearchBar
import com.waenhancer.ui.components.WaexEmptyState
import com.waenhancer.ui.designsystem.WaexIcons
import com.waenhancer.ui.designsystem.WaexTheme
import com.waenhancer.ui.navigation.LocalWaexNavController

typealias SearchablePreference = FeatureItem

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SearchScreen() {
    val colors = WaexTheme.colors
    val spacing = WaexTheme.spacing
    val typography = WaexTheme.typography
    val radius = WaexTheme.radius
    val navController = LocalWaexNavController.current

    var query by remember { mutableStateOf("") }

    // Registry of all available preference items sourced from the unified FeatureCatalog
    val preferenceRegistry = FeatureCatalog.ALL_FEATURES


    // Enhanced multi-token search filter: matches all query terms across title, description, section, key, and tabLabel
    val filteredPreferences = remember(query) {
        val trimmed = query.trim()
        if (trimmed.isEmpty()) {
            preferenceRegistry
        } else {
            val terms = trimmed.lowercase().split("\\s+".toRegex()).filter { it.isNotEmpty() }
            preferenceRegistry.filter { pref ->
                val haystack = "${pref.title} ${pref.description} ${pref.section} ${pref.key} ${pref.tabLabel}".lowercase()
                terms.all { term -> haystack.contains(term) }
            }
        }
    }

    val groupedPreferences = remember(filteredPreferences) {
        filteredPreferences.groupBy { it.section }
    }

    Scaffold(
        topBar = {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                color = colors.surface
            ) {
                Column(modifier = Modifier.statusBarsPadding()) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(56.dp)
                            .padding(horizontal = spacing.pageMargin),
                        verticalAlignment = Alignment.CenterVertically
                    ) {

                        IconButton(
                            onClick = { navController.popBack() },
                            modifier = Modifier
                                .size(40.dp)
                                .clip(CircleShape)
                        ) {
                            Icon(
                                imageVector = WaexIcons.Back,
                                contentDescription = "Back",
                                tint = colors.onBackground,
                                modifier = Modifier.size(20.dp)
                            )
                        }
                        Spacer(modifier = Modifier.width(10.dp))
                        WaexSearchBar(
                            query = query,
                            onQueryChange = { query = it },
                            placeholder = "Search features & preferences...",
                            modifier = Modifier.weight(1f)
                        )
                    }
                    HorizontalDivider(thickness = 1.dp, color = colors.outlineVariant.copy(alpha = 0.6f))
                }
            }
        },

        containerColor = colors.background
    ) { paddingValues ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            if (filteredPreferences.isEmpty()) {
                WaexEmptyState(
                    title = "No preferences found",
                    description = "Try searching for a different keyword or feature name.",
                    icon = WaexIcons.Search,
                    modifier = Modifier.align(Alignment.Center)
                )
            } else {
                LazyColumn(
                    contentPadding = PaddingValues(horizontal = spacing.pageMargin, vertical = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                    modifier = Modifier.fillMaxSize()
                ) {
                    groupedPreferences.forEach { (section, preferences) ->
                        item(key = "section_$section") {
                            Text(
                                text = section,
                                style = typography.bodyLg,
                                fontWeight = FontWeight.Bold,
                                color = colors.primary,
                                modifier = Modifier.padding(top = 8.dp, bottom = 4.dp)
                            )
                        }
                        items(preferences, key = { it.key }) { pref ->
                            // Custom badge color per tab category
                            val (badgeBg, badgeTextColor) = when (pref.tabLabel) {
                                "Privacy" -> Color(0xFF1E88E5).copy(alpha = 0.12f) to Color(0xFF1E88E5)
                                "Conversation" -> Color(0xFF8E24AA).copy(alpha = 0.12f) to Color(0xFF8E24AA)
                                "Media" -> Color(0xFFFB8C00).copy(alpha = 0.12f) to Color(0xFFFB8C00)
                                "Automation" -> Color(0xFF43A047).copy(alpha = 0.12f) to Color(0xFF43A047)
                                "Styles" -> Color(0xFF00ACC1).copy(alpha = 0.12f) to Color(0xFF00ACC1)
                                "Premium" -> Color(0xFFE53935).copy(alpha = 0.12f) to Color(0xFFE53935)
                                else -> colors.primaryContainer to colors.primary
                            }

                            Surface(
                                shape = radius.bentoCardShape,
                                color = colors.surfaceDim,
                                border = androidx.compose.foundation.BorderStroke(1.dp, colors.outlineVariant),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Box(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clickable {
                                            if (pref.key == "pro_features_unlock" || pref.key == "license_verification") {
                                                navController.navigateTo(com.waenhancer.ui.navigation.Screen.LicenseActivation)
                                            } else {
                                                navController.navigateToPreference(
                                                    tabIndex = pref.tabIndex,
                                                    subTabId = pref.subTabId,
                                                    preferenceKey = pref.key
                                                )
                                            }
                                        }
                                        .padding(16.dp)
                                ) {
                                    // Floating Tag Badge on top-right of the card
                                    Box(
                                        modifier = Modifier
                                            .align(Alignment.TopEnd)
                                            .clip(RoundedCornerShape(6.dp))
                                            .background(badgeBg)
                                            .padding(horizontal = 8.dp, vertical = 3.dp)
                                    ) {
                                        Text(
                                            text = pref.tabLabel,
                                            style = typography.labelSm,
                                            fontWeight = FontWeight.Bold,
                                            color = badgeTextColor,
                                            fontSize = 10.sp
                                        )
                                    }

                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Column(
                                            modifier = Modifier
                                                .weight(1f)
                                                .padding(end = 64.dp), // Prevent text overlapping the top-right badge
                                            verticalArrangement = Arrangement.spacedBy(4.dp)
                                        ) {
                                            Text(
                                                text = pref.title,
                                                style = typography.bodyLg,
                                                fontWeight = FontWeight.SemiBold,
                                                color = colors.onSurface
                                            )
                                            Text(
                                                text = pref.description,
                                                style = typography.bodyMd,
                                                color = colors.onSurfaceVariant,
                                                fontSize = 12.sp,
                                                lineHeight = 17.sp
                                            )
                                            Text(
                                                text = "Section: ${pref.section}",
                                                style = typography.labelSm,
                                                color = colors.primary,
                                                fontSize = 11.sp,
                                                fontWeight = FontWeight.Medium
                                            )
                                        }

                                        Icon(
                                            imageVector = WaexIcons.ChevronRight,
                                            contentDescription = null,
                                            tint = colors.onSurfaceVariant.copy(alpha = 0.5f),
                                            modifier = Modifier.size(16.dp)
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
}
