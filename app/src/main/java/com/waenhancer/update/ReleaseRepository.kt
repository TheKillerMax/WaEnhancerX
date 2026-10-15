package com.waenhancer.update

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

data class WaexAsset(
    val name: String,
    val downloadUrl: String,
    val size: Long,
) {
    val isDebug: Boolean
        get() = name.contains("debug", ignoreCase = true)

    val buildTypeLabel: String
        get() = when {
            isDebug -> "Debug Build"
            name.contains("release", ignoreCase = true) -> "Release Build"
            else -> "Standard Build"
        }

    val formattedSize: String
        get() {
            if (size <= 0) return ""
            val mb = size / (1024.0 * 1024.0)
            return String.format(java.util.Locale.US, "%.1f MB", mb)
        }
}

data class WaexRelease(
    val tagName: String,
    val name: String,
    val body: String,
    val publishedAt: String,
    val htmlUrl: String,
    val assets: List<WaexAsset> = emptyList(),
) {
    val version: String get() = ReleaseRepository.versionFromTag(tagName)
    val defaultAsset: WaexAsset? get() = assets.firstOrNull { !it.isDebug } ?: assets.firstOrNull()
    val downloadUrl: String? get() = defaultAsset?.downloadUrl
    val downloadSize: Long get() = defaultAsset?.size ?: 0L
}

object ReleaseRepository {
    const val RELEASE_REPOSITORY = "Xposed-Modules-Repo/com.waenhancer"
    const val RELEASES_URL = "https://github.com/$RELEASE_REPOSITORY/releases"
    const val RELEASES_API = "https://api.github.com/repos/$RELEASE_REPOSITORY/releases?per_page=100"
    private const val RELEASE_ASSET_PATH_PREFIX = "/$RELEASE_REPOSITORY/releases/download/"
    private val versionPattern = Regex("^\\d+\\.\\d+(\\.\\d+)?(-[a-zA-Z0-9.-]+)?$")
    private val client = OkHttpClient.Builder().connectTimeout(15, TimeUnit.SECONDS).build()

    suspend fun fetchReleases(): List<WaexRelease> = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url(RELEASES_API)
            .header("Accept", "application/vnd.github+json")
            .header("X-GitHub-Api-Version", "2022-11-28")
            .header("User-Agent", "WaEnhancer X")
            .build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) error(if (response.code == 403 || response.code == 429) "Rate limit exceeded. Please try again later." else "Release service returned ${response.code}.")
            val array = JSONArray(response.body?.string() ?: error("Release service returned an empty response."))
            buildList {
                for (i in 0 until array.length()) {
                    val item = array.optJSONObject(i) ?: continue
                    parseRelease(item)?.let(::add)
                }
            }.sortedByDescending { versionCode(it.version) }
        }
    }

    suspend fun fetchRelease(tagName: String): WaexRelease? = fetchReleases().firstOrNull {
        it.tagName.equals(tagName, true) || it.name.equals(tagName, true) ||
            it.version.equals(normalizeVersion(tagName), true)
    }

    fun findUpdate(releases: List<WaexRelease>, installedVersion: String): WaexRelease? {
        val installed = versionCode(normalizeVersion(installedVersion))
        return releases.asSequence()
            .filter { versionCode(it.version) > installed }
            .maxByOrNull { versionCode(it.version) }
    }

    fun versionCode(version: String): Long {
        val normalized = normalizeVersion(version)
        val dashIndex = normalized.indexOf('-')
        val base = if (dashIndex > 0) normalized.substring(0, dashIndex) else normalized
        val parts = base.split('.')
        val major = parts.getOrNull(0)?.toLongOrNull() ?: return 0L
        val minor = parts.getOrNull(1)?.toLongOrNull() ?: 0L
        val patch = parts.getOrNull(2)?.toLongOrNull() ?: 0L
        val baseCode = major * 1_000_000L + minor * 1_000L + patch
        if (dashIndex < 0) return baseCode * 1_000L + 999L
        val suffixNum = Regex("\\d+").findAll(normalized.substring(dashIndex)).lastOrNull()?.value?.toLongOrNull()?.coerceIn(1L, 998L) ?: 1L
        return baseCode * 1_000L + suffixNum
    }

    fun versionFromTag(tagName: String): String {
        val tag = tagName.trim().removePrefix("debug-")
        val separator = tag.indexOf('-')
        val versionPart = if (separator > 0 && tag.substring(0, separator).all(Char::isDigit)) {
            tag.substring(separator + 1)
        } else tag
        return normalizeVersion(versionPart)
    }

    internal fun isOfficialReleaseAssetUrl(value: String): Boolean {
        val url = value.toHttpUrlOrNull() ?: return false
        return url.isHttps && url.host.equals("github.com", ignoreCase = true) &&
            url.encodedPath.startsWith(RELEASE_ASSET_PATH_PREFIX, ignoreCase = true) &&
            url.encodedPath.endsWith(".apk", ignoreCase = true)
    }

    private fun parseRelease(item: JSONObject): WaexRelease? {
        if (item.optBoolean("draft", false)) return null
        val tag = item.optString("tag_name").trim()
        if (!versionPattern.matches(versionFromTag(tag))) return null

        val rawAssets = item.optJSONArray("assets")
        val parsedAssets = buildList {
            if (rawAssets != null) {
                for (i in 0 until rawAssets.length()) {
                    val asset = rawAssets.optJSONObject(i) ?: continue
                    val assetName = asset.optString("name").trim()
                    val assetUrl = asset.optString("browser_download_url")
                        .takeIf(::isOfficialReleaseAssetUrl)
                    if (assetName.endsWith(".apk", ignoreCase = true) && assetUrl != null) {
                        add(WaexAsset(assetName, assetUrl, asset.optLong("size")))
                    }
                }
            }
        }

        return WaexRelease(
            tagName = tag,
            name = item.optString("name").trim().ifBlank { tag },
            body = item.optString("body").trim().ifBlank { "No changelog available." },
            publishedAt = item.optString("published_at"),
            htmlUrl = item.optString("html_url").takeIf(::isOfficialReleasePageUrl).orEmpty(),
            assets = parsedAssets,
        )
    }

    private fun isOfficialReleasePageUrl(value: String): Boolean {
        val url = value.toHttpUrlOrNull() ?: return false
        return url.isHttps && url.host.equals("github.com", ignoreCase = true) &&
            url.encodedPath.startsWith("/$RELEASE_REPOSITORY/releases/", ignoreCase = true)
    }
}

fun normalizeVersion(value: String): String = value.trim().removePrefix("v").removePrefix("V").substringBefore('+').trim()
