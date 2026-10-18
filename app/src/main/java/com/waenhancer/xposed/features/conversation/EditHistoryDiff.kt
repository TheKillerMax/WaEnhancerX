package com.waenhancer.xposed.features.conversation

/** Exact text preservation with a fixed budget for fine-grained highlighting. */
internal object EditHistoryDiff {
    enum class Type { UNCHANGED, ADDED, REMOVED }
    data class Chunk(val type: Type, val text: String)

    private const val MAX_LCS_CELLS = 90_601L // Retains the existing 300 x 300 character case.
    private const val MAX_TOKENIZED_LENGTH = 8_192
    private val wordBoundaries = Regex("(?<=\\s)|(?=\\s)")

    fun compute(oldText: String, newText: String): List<Chunk> {
        if (oldText == newText) return if (oldText.isEmpty()) emptyList()
            else listOf(Chunk(Type.UNCHANGED, oldText))
        if (oldText.isEmpty()) return listOf(Chunk(Type.ADDED, newText))
        if (newText.isEmpty()) return listOf(Chunk(Type.REMOVED, oldText))
        if (oldText.length > MAX_TOKENIZED_LENGTH || newText.length > MAX_TOKENIZED_LENGTH) {
            return replacement(oldText, newText)
        }

        val characterDiff = oldText.length <= 300 && newText.length <= 300 &&
            oldText.none { it.isSurrogate() } && newText.none { it.isSurrogate() }
        val oldTokens = if (characterDiff) oldText.map { it.toString() } else oldText.split(wordBoundaries)
        val newTokens = if (characterDiff) newText.map { it.toString() } else newText.split(wordBoundaries)
        val n = oldTokens.size
        val m = newTokens.size
        // Use Long before multiplication: input sizes must not overflow the guard.
        if ((n.toLong() + 1) * (m.toLong() + 1) > MAX_LCS_CELLS) return replacement(oldText, newText)
        val dp = Array(n + 1) { IntArray(m + 1) }
        for (i in 0 until n) for (j in 0 until m) {
            dp[i + 1][j + 1] = if (oldTokens[i] == newTokens[j]) dp[i][j] + 1
                else maxOf(dp[i + 1][j], dp[i][j + 1])
        }
        var i = n
        var j = m
        val reversed = mutableListOf<Chunk>()
        while (i > 0 || j > 0) {
            if (i > 0 && j > 0 && oldTokens[i - 1] == newTokens[j - 1]) {
                reversed.add(Chunk(Type.UNCHANGED, oldTokens[--i]))
                j--
            } else if (j > 0 && (i == 0 || dp[i][j - 1] >= dp[i - 1][j])) {
                reversed.add(Chunk(Type.ADDED, newTokens[--j]))
            } else {
                reversed.add(Chunk(Type.REMOVED, oldTokens[--i]))
            }
        }
        // Merge with a builder, avoiding a growing String copy for every token.
        val result = mutableListOf<Chunk>()
        var type: Type? = null
        val text = StringBuilder()
        for (index in reversed.indices.reversed()) {
            val chunk = reversed[index]
            if (chunk.text.isEmpty()) continue
            if (type != null && type != chunk.type) {
                result.add(Chunk(type, text.toString()))
                text.setLength(0)
            }
            type = chunk.type
            text.append(chunk.text)
        }
        if (type != null) result.add(Chunk(type, text.toString()))
        return result
    }

    /** A large changed region is coarser than LCS, but never drops either text. */
    private fun replacement(oldText: String, newText: String): List<Chunk> {
        val sharedLength = minOf(oldText.length, newText.length)
        var prefix = 0
        while (prefix < sharedLength && oldText[prefix] == newText[prefix]) prefix++
        // Keep both halves of UTF-16 surrogate pairs in the same visual chunk.
        if (prefix > 0 && prefix < sharedLength && oldText[prefix - 1].isHighSurrogate() &&
            (oldText[prefix].isLowSurrogate() || newText[prefix].isLowSurrogate())) prefix--
        var suffix = 0
        while (suffix < sharedLength - prefix &&
            oldText[oldText.lastIndex - suffix] == newText[newText.lastIndex - suffix]) suffix++
        if (suffix > 0 && oldText[oldText.length - suffix].isLowSurrogate() &&
            (oldText.length - suffix > prefix && oldText[oldText.length - suffix - 1].isHighSurrogate() ||
                newText.length - suffix > prefix && newText[newText.length - suffix - 1].isHighSurrogate())) suffix--
        val result = mutableListOf<Chunk>()
        fun append(type: Type, text: String) { if (text.isNotEmpty()) result.add(Chunk(type, text)) }
        append(Type.UNCHANGED, oldText.substring(0, prefix))
        append(Type.REMOVED, oldText.substring(prefix, oldText.length - suffix))
        append(Type.ADDED, newText.substring(prefix, newText.length - suffix))
        append(Type.UNCHANGED, oldText.substring(oldText.length - suffix))
        return result
    }
}
