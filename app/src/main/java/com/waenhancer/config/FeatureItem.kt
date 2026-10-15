package com.waenhancer.config

/**
 * Navigation metadata for a configurable feature/preference in WA Enhancer.
 *
 * This pure Kotlin model is decoupled from Jetpack Compose UI dependencies so it can be safely
 * referenced by both the manager UI (search, navigation) and the Xposed/hook layer (restart notifications).
 */
data class FeatureItem(
    val key: String,
    /** Stable group id. Display text is always resolved from string resources. */
    val groupId: String,
    val tabIndex: Int = -1,
    val subTabId: String? = null,
    /** Stable category id. Display text is always resolved from string resources. */
    val tabId: String = "settings",
    val isPro: Boolean = false
)
