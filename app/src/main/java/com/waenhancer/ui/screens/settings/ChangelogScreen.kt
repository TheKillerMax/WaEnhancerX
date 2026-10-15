package com.waenhancer.ui.screens.settings

import android.content.Intent
import android.net.Uri
import android.widget.TextView
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.text.util.LinkifyCompat
import androidx.core.util.PatternsCompat
import com.waenhancer.ui.components.WaexTopBar
import com.waenhancer.ui.components.BuildTypeSelectionSheet
import com.waenhancer.ui.components.UpdateDownloadSheet
import com.waenhancer.ui.designsystem.WaexIcons
import com.waenhancer.ui.designsystem.WaexTheme
import com.waenhancer.ui.navigation.LocalWaexNavController
import com.waenhancer.ui.navigation.LocalWaexPreferenceManager
import com.waenhancer.ui.navigation.Screen
import com.waenhancer.update.ReleaseRepository
import com.waenhancer.update.ChangelogParser
import com.waenhancer.update.ChangelogSection
import com.waenhancer.update.WaexAsset
import com.waenhancer.update.WaexRelease
import io.noties.markwon.Markwon
import io.noties.markwon.html.HtmlPlugin
import java.text.SimpleDateFormat
import java.util.Locale

@Composable
fun ChangelogScreen() {
    val navController = LocalWaexNavController.current
    val context = LocalContext.current
    val preferences = LocalWaexPreferenceManager.current
    val colors = WaexTheme.colors
    val spacing = WaexTheme.spacing
    val typography = WaexTheme.typography
    val radius = WaexTheme.radius
    var releases by remember { mutableStateOf<List<WaexRelease>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var reloadKey by remember { mutableStateOf(0) }
    var buildSelectionRelease by remember { mutableStateOf<WaexRelease?>(null) }
    var activeDownload by remember { mutableStateOf<Pair<WaexRelease, WaexAsset>?>(null) }
    val installedVersion = remember {
        @Suppress("DEPRECATION")
        context.packageManager.getPackageInfo(context.packageName, 0).versionName.orEmpty()
    }

    LaunchedEffect(reloadKey) {
        loading = true
        error = null
        runCatching { ReleaseRepository.fetchReleases() }
            .onSuccess { releases = it }
            .onFailure { error = it.message ?: "Unable to load releases." }
        loading = false
    }

    val availableUpdate = ReleaseRepository.findUpdate(
        releases,
        installedVersion
    )
    Scaffold(
        topBar = {
            WaexTopBar(
                "Changelog & Releases",
                onBackClick = { navController.popBack() },
                actions = {
                    IconButton(onClick = { navController.navigateTo(Screen.UpdateSettings) }) {
                        Icon(WaexIcons.Settings, contentDescription = "Update settings", tint = colors.onSurface)
                    }
                }
            )
        },
        containerColor = colors.background
    ) { insets ->
        when {
            loading -> Box(Modifier.fillMaxSize().padding(insets), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = colors.primary) }
            error != null -> Column(Modifier.fillMaxSize().padding(insets).padding(spacing.pageMargin), Arrangement.Center, Alignment.CenterHorizontally) {
                Text(error!!, color = colors.onSurfaceVariant, style = typography.bodyMd)
                Spacer(Modifier.height(16.dp))
                Button(onClick = { reloadKey++ }) { Text("Try again") }
            }
            else -> LazyColumn(
                modifier = Modifier.fillMaxSize().padding(insets),
                contentPadding = PaddingValues(horizontal = spacing.pageMargin, vertical = 16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                if (releases.isEmpty()) item { Text("No releases found.", color = colors.onSurfaceVariant) }
                items(releases, key = { it.tagName }) { release ->
                    val installed = release.version.equals(com.waenhancer.update.normalizeVersion(installedVersion), true)
                    val comparison = ReleaseRepository.versionCode(release.version).compareTo(ReleaseRepository.versionCode(installedVersion))
                    val allowDowngrade = preferences.getBoolean("downgrades_enabled", false)
                    Surface(
                        shape = radius.bentoCardShape,
                        color = colors.surfaceContainerLow,
                        border = androidx.compose.foundation.BorderStroke(1.dp, colors.outlineVariant),
                        modifier = Modifier.fillMaxWidth().clickable { navController.navigateTo(Screen.ReleaseDetails(release.tagName)) }
                    ) {
                        Column(Modifier.padding(20.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) {
                                    Text(
                                        release.name,
                                        style = typography.headlineMd,
                                        fontWeight = FontWeight.Bold,
                                        color = colors.onSurface
                                    )
                                    Spacer(Modifier.height(4.dp))
                                    Text(
                                        formatReleaseDate(release.publishedAt),
                                        style = typography.bodyMd,
                                        color = colors.onSurfaceVariant,
                                        fontSize = 12.sp
                                    )
                                }
                                IconButton(onClick = { navController.navigateTo(Screen.ReleaseDetails(release.tagName)) }) {
                                    Icon(
                                        WaexIcons.ChevronRight,
                                        contentDescription = "View release details",
                                        tint = colors.onSurfaceVariant
                                    )
                                }
                            }
                            if (installed || release.tagName == availableUpdate?.tagName) {
                                Row(Modifier.padding(top = 8.dp)) {
                                    if (installed) Badge("Installed", Color(0xFF10B981))
                                    if (release.tagName == availableUpdate?.tagName) Badge("Update", colors.primary)
                                }
                            }
                            Spacer(Modifier.height(14.dp))
                            Surface(
                                shape = radius.bentoCardShape,
                                color = colors.surfaceDim,
                                border = androidx.compose.foundation.BorderStroke(
                                    1.dp,
                                    colors.outlineVariant.copy(alpha = 0.5f)
                                ),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                ChangelogBodyView(
                                    body = release.body,
                                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp)
                                )
                            }
                            if ((release.assets.isNotEmpty() || release.downloadUrl != null) && (comparison > 0 || (comparison < 0 && allowDowngrade))) {
                                Spacer(Modifier.height(14.dp))
                                Button(
                                    onClick = {
                                        if (release.assets.size > 1) {
                                            buildSelectionRelease = release
                                        } else {
                                            val asset = release.assets.firstOrNull() ?: release.defaultAsset
                                            if (asset != null) {
                                                activeDownload = release to asset
                                            } else if (release.downloadUrl != null) {
                                                activeDownload = release to WaexAsset(
                                                    name = "WaEnhancerX-${release.tagName}.apk",
                                                    downloadUrl = release.downloadUrl!!,
                                                    size = release.downloadSize
                                                )
                                            }
                                        }
                                    },
                                    modifier = Modifier.fillMaxWidth()
                                ) {
                                    Text(if (comparison > 0) "Upgrade" else "Downgrade")
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    buildSelectionRelease?.let { rel ->
        BuildTypeSelectionSheet(
            release = rel,
            onSelectAsset = { asset ->
                buildSelectionRelease = null
                activeDownload = rel to asset
            },
            onDismiss = { buildSelectionRelease = null }
        )
    }

    activeDownload?.let { (rel, asset) ->
        val isDowngrade = ReleaseRepository.versionCode(rel.version) < ReleaseRepository.versionCode(installedVersion)
        UpdateDownloadSheet(
            url = asset.downloadUrl,
            version = "${rel.tagName} (${asset.buildTypeLabel})",
            useRoot = isDowngrade || preferences.getBoolean("root_auto_install", false),
            onDismiss = { activeDownload = null }
        )
    }
}

@Composable
private fun Badge(label: String, color: Color) {
    Spacer(Modifier.width(8.dp))
    Box(Modifier.clip(CircleShape).background(color.copy(alpha = .15f)).padding(horizontal = 8.dp, vertical = 2.dp)) {
        Text(label, color = color, fontSize = 11.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
fun ChangelogBodyView(
    body: String,
    modifier: Modifier = Modifier,
    maxItemsPerCategory: Int = Int.MAX_VALUE,
    initiallyExpanded: Boolean = false
) {
    val sections = remember(body) { ChangelogParser.parse(body) }
    val expandedStates = remember(sections, initiallyExpanded) {
        mutableStateMapOf<String, Boolean>().apply {
            sections.forEach { this[it.title] = initiallyExpanded }
        }
    }
    val colors = WaexTheme.colors

    if (sections.isEmpty()) {
        MarkdownText(
            body.ifBlank { "No changelog available." },
            colors.onSurfaceVariant.toArgb(),
            maxLines = 8,
            modifier = modifier.padding(vertical = 8.dp)
        )
    } else {
        Column(modifier = modifier) {
            sections.forEachIndexed { index, section ->
                if (index > 0) {
                    HorizontalDivider(
                        thickness = 1.dp,
                        color = colors.outlineVariant.copy(alpha = 0.4f),
                        modifier = Modifier.padding(vertical = 4.dp)
                    )
                }
                val expanded = expandedStates[section.title] ?: initiallyExpanded
                ChangelogSectionRow(
                    section = section.copy(items = section.items.take(maxItemsPerCategory)),
                    expanded = expanded,
                    onToggle = { expandedStates[section.title] = !expanded }
                )
            }
        }
    }
}

@Composable
private fun ChangelogSectionRow(
    section: ChangelogSection,
    expanded: Boolean,
    onToggle: () -> Unit
) {
    val colors = WaexTheme.colors
    val typography = WaexTheme.typography
    val rotation by animateFloatAsState(if (expanded) 90f else 0f, label = "sectionChevron")

    Column(Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().clickable(onClick = onToggle).padding(vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(section.title, style = typography.titleMd, fontWeight = FontWeight.Bold, color = colors.onSurface)
            Spacer(Modifier.width(6.dp))
            Text(
                "(${section.items.size})",
                style = typography.bodySm,
                color = colors.onSurfaceVariant,
                fontSize = 12.sp,
                modifier = Modifier.weight(1f)
            )
            Icon(
                WaexIcons.ChevronRight,
                contentDescription = if (expanded) "Collapse ${section.title}" else "Expand ${section.title}",
                tint = colors.onSurfaceVariant,
                modifier = Modifier.rotate(rotation)
            )
        }
        AnimatedVisibility(
            visible = expanded,
            enter = fadeIn() + expandVertically(),
            exit = fadeOut() + shrinkVertically()
        ) {
            Column(
                modifier = Modifier.fillMaxWidth().padding(bottom = 10.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                section.items.forEach { item ->
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
                        Box(
                            Modifier.padding(top = 7.dp).size(4.dp).background(
                                colors.onSurfaceVariant,
                                CircleShape
                            )
                        )
                        Spacer(Modifier.width(10.dp))
                        MarkdownText(item, colors.onSurface.toArgb(), maxLines = 4)
                    }
                }
            }
        }
    }
}

@Composable
internal fun MarkdownText(
    markdown: String,
    textColor: Int,
    maxLines: Int = Int.MAX_VALUE,
    modifier: Modifier = Modifier
) {
    AndroidView(
        factory = { context ->
            TextView(context).apply {
                setTextColor(textColor)
                textSize = 14f
                setLineSpacing(0f, 1.18f)
                this.maxLines = maxLines
                tag = Markwon.builder(context).usePlugin(HtmlPlugin.create()).build()
            }
        },
        update = { view ->
            view.setTextColor(textColor)
            view.maxLines = maxLines
            (view.tag as Markwon).setMarkdown(view, markdown.trim())
            LinkifyCompat.addLinks(view, PatternsCompat.WEB_URL, null)
        },
        modifier = modifier.fillMaxWidth()
    )
}

internal fun formatReleaseDate(value: String): String = try {
    val input = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US)
    SimpleDateFormat("MMM dd, yyyy", Locale.US).format(input.parse(value)!!)
} catch (_: Exception) { value.substringBefore('T') }

internal fun openUrl(context: android.content.Context, url: String) {
    context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}
