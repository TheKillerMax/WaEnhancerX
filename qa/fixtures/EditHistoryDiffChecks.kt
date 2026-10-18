package test

import com.waenhancer.xposed.features.conversation.EditHistoryDiff
import kotlin.random.Random

private var checks = 0
private fun checkCase(value: Boolean, message: String) { checks++; if (!value) throw AssertionError(message) }
private fun validUtf16(text: String): Boolean {
    var i = 0
    while (i < text.length) {
        if (text[i].isHighSurrogate()) {
            if (i + 1 >= text.length || !text[i + 1].isLowSurrogate()) return false
            i += 2
        } else { if (text[i].isLowSurrogate()) return false; i++ }
    }
    return true
}
private fun verify(old: String, new: String, checkUnicode: Boolean = true): List<EditHistoryDiff.Chunk> {
    val chunks = EditHistoryDiff.compute(old, new)
    checkCase(chunks.filter { it.type != EditHistoryDiff.Type.ADDED }.joinToString("") { it.text } == old, "old text must reconstruct exactly")
    checkCase(chunks.filter { it.type != EditHistoryDiff.Type.REMOVED }.joinToString("") { it.text } == new, "new text must reconstruct exactly")
    checkCase(chunks.none { it.text.isEmpty() }, "no empty chunks")
    checkCase(chunks.zipWithNext().none { (a, b) -> a.type == b.type }, "adjacent equal types are merged")
    if (checkUnicode) checkCase(chunks.all { validUtf16(it.text) }, "a chunk must not split a surrogate pair")
    return chunks
}
// Independent one-row LCS length oracle for ordinary character cases.
private fun lcsLength(a: String, b: String): Int {
    val row = IntArray(b.length + 1)
    for (ca in a) {
        var previous = 0
        for (j in b.indices) {
            val saved = row[j + 1]
            row[j + 1] = if (ca == b[j]) previous + 1 else maxOf(row[j + 1], row[j])
            previous = saved
        }
    }
    return row.last()
}
fun main(args: Array<String>) {
    if (args.single() == "large" || args.single() == "all") {
        val old = (0 until 6_000).joinToString(" ") { "left$it" }
        val new = (0 until 6_000).joinToString(" ") { "right$it" }
        val start = System.nanoTime()
        val chunks = verify(old, new)
        val elapsed = (System.nanoTime() - start) / 1_000_000
        checkCase(chunks.size <= 4, "oversized input uses a bounded changed region")
        println("Large text: ${old.length}/${new.length} UTF-16 units, ${chunks.size} chunks, ${elapsed} ms; JVM heap capped at 64 MiB")
        if (args.single() == "large") { println("PASS: $checks large diff checks"); return }
    }
    for ((old, new) in listOf("" to "", "" to "abc", "abc" to "", "same" to "same", "abc" to "axc", "abab" to "baba", "hello there" to "hello here", "a\n\tb" to "a  b", "a😀b" to "a😃b", "🧡" to "💚")) verify(old, new)
    val random = Random(1337)
    repeat(1_000) {
        fun text() = (0 until random.nextInt(0, 100)).map { "abcde \n"[random.nextInt(7)] }.joinToString("")
        val old = text(); val new = text()
        val chunks = verify(old, new)
        val common = chunks.filter { it.type == EditHistoryDiff.Type.UNCHANGED }.sumOf { it.text.length }
        checkCase(common == lcsLength(old, new), "ordinary LCS highlighting retains an optimal common subsequence")
    }
    val budgetOld = "ab ".repeat(900)
    val budgetNew = "cd ".repeat(900)
    checkCase(verify(budgetOld, budgetNew).size <= 4, "many short tokens trigger cell budget before matrix allocation")
    val prefix = "same ".repeat(10_000)
    val suffix = " tail".repeat(10_000)
    val localized = verify(prefix + "old😀" + suffix, prefix + "new😃" + suffix)
    checkCase(localized.first().text == prefix, "large unchanged prefix is retained")
    checkCase(localized.last().text == suffix, "large unchanged suffix is retained")
    for ((old, new) in listOf(prefix + "😀" + suffix to prefix + "😃" + suffix,
        prefix + "😀" + suffix to prefix + "🠀" + suffix,
        prefix + "a" to prefix,
        prefix to prefix + "z",
        "😀" + suffix to "😃" + suffix,
        "x".repeat(1_000_000) to "y".repeat(1_000_000))) verify(old, new)
    // Covers the original upper character boundary and one very asymmetric case.
    verify("a".repeat(300), "b".repeat(300))
    verify("a", "b ".repeat(4_000))
    println("PASS: $checks production diff checks")
}
