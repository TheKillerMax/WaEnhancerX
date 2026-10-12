package com.waenhancer.config

/**
 * Metadata definition for a configurable feature/preference in WA Enhancer.
 *
 * This pure Kotlin model is decoupled from Jetpack Compose UI dependencies so it can be safely
 * referenced by both the manager UI (search, navigation) and the Xposed/hook layer (restart notifications).
 */
data class FeatureItem(
    val key: String,
    val title: String,
    val description: String = "",
    val section: String = "",
    val tabIndex: Int = -1,
    val subTabId: String? = null,
    val tabLabel: String = ""
)
