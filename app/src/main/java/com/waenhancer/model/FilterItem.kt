package com.waenhancer.model

data class FilterItem(
    val id: String,
    val behavior: String = BEHAVIOR_GONE,
    val color: Int = 0xFFFF0000.toInt(),
    val opacity: Int = 100,
    val scale: Float = 1.0f
) {
    companion object {
        const val BEHAVIOR_GONE = "gone"
        const val BEHAVIOR_COLOR = "color"
        const val BEHAVIOR_OPACITY = "opacity"
        const val BEHAVIOR_RESIZE = "resize"
    }
}
