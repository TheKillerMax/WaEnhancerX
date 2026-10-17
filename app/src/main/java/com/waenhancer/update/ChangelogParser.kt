package com.waenhancer.update

import com.waenhancer.app.R
import com.waenhancer.utils.UiText

/**
 * Represents a categorized changelog section (e.g. Added, Fixed, Removed, Improvements).
 */
data class ChangelogSection(
    val title: String,
    val items: List<String>
)

object ChangelogParser {

    private val SECTION_HEADER_REGEX = Regex(
        "^\\s*(?:\\[([^\\]]+)\\]|###?\\s*([^\n\r]+)|\\*\\*([^*]+)\\*\\*)\\s*:?$",
        RegexOption.MULTILINE
    )

    /**
     * Parses release body markdown/plain-text into categorized sections.
     * Supports formats like:
     * - [Added], [Fixed], [Removed], [Improvements], [Updated]
     * - ## Added, ### Fixed, etc.
     * - **Added**, **Fixed**, etc.
     * If no sections are detected, returns a single section with whatever items/text exist.
     */
    fun parse(rawText: String): List<ChangelogSection> {
        val trimmed = rawText.trim()
        if (trimmed.isBlank()) return emptyList()

        val lines = trimmed.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        val sections = mutableListOf<ChangelogSection>()

        var currentTitle: String? = null
        val currentItems = mutableListOf<String>()

        fun flushCurrent() {
            val title = currentTitle
            if (title != null && currentItems.isNotEmpty()) {
                sections.add(ChangelogSection(title, currentItems.toList()))
            } else if (title == null && currentItems.isNotEmpty()) {
                // Intro text or ungrouped text
                sections.add(ChangelogSection(UiText.get(R.string.waex_ui_overview_d4b1ea57, "Overview"), currentItems.toList()))
            }
            currentItems.clear()
        }

        for (line in lines) {
            val trimmedLine = line.trim()
            if (trimmedLine.isEmpty()) continue

            val match = SECTION_HEADER_REGEX.matchEntire(trimmedLine)
            if (match != null) {
                flushCurrent()
                val detected = (match.groupValues[1].takeIf { it.isNotBlank() }
                    ?: match.groupValues[2].takeIf { it.isNotBlank() }
                    ?: match.groupValues[3].takeIf { it.isNotBlank() }
                    ?: "Highlights").trim()
                currentTitle = cleanSectionTitle(detected)
            } else {
                // Extract clean bullet item
                val cleanItem = trimmedLine
                    .removePrefix("- ")
                    .removePrefix("* ")
                    .removePrefix("• ")
                    .trim()
                if (cleanItem.isNotBlank()) {
                    currentItems.add(cleanItem)
                }
            }
        }
        flushCurrent()

        return if (sections.isEmpty() && trimmed.isNotBlank()) {
            listOf(ChangelogSection("Highlights", listOf(trimmed)))
        } else {
            sections
        }
    }

    private fun cleanSectionTitle(raw: String): String {
        val lower = raw.lowercase()
        return when {
            lower.contains("add") -> "Added"
            lower.contains("fix") -> "Fixed"
            lower.contains("remov") -> "Removed"
            lower.contains("improv") -> "Improvements"
            lower.contains("updat") -> "Updated"
            lower.contains("secur") -> "Security"
            lower.contains("deprecat") -> "Deprecated"
            else -> raw.replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
        }
    }
}
