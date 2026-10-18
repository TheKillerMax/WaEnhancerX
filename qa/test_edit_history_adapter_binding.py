#!/usr/bin/env python3
"""Compile production getView and click callbacks with explicit Kotlin view doubles.

Checks adapter identity, recycled-listener invalidation and zero canonical DB
lookups in binding. This is not a rendered Android/host performance measurement.
"""
from pathlib import Path
import argparse
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, default=root / (
    'app/src/main/java/com/waenhancer/xposed/features/conversation/AntiEditMessagesHook.kt'))
parser.add_argument('--scenario', choices=['all', 'queries', 'recycle'], default='all')
args = parser.parse_args()
source = args.source.read_text()

def body_after(signature, source=source):
    assert source.count(signature) == 1, 'callback extraction must be unambiguous'
    start = source.index('{', source.index(signature))
    depth, quoted, escaped = 0, False, False
    for index in range(start, len(source)):
        char = source[index]
        if quoted:
            if escaped: escaped = False
            elif char == '\\': escaped = True
            elif char == '"': quoted = False
        elif char == '"': quoted = True
        elif char == '{': depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0: return source[start:index + 1]
    raise AssertionError('unterminated method')

fixture = r'''
open class View {
    val context = Any()
    var resourceName: String? = null
    var parent: View? = null
    val fields = mutableMapOf<String, Any>()
    var listener: ((View) -> Unit)? = null
    var isClickable = false
    fun setOnClickListener(block: (View) -> Unit) { listener = block }
    fun click() { listener?.invoke(this) }
}
class TextView : View() { var text: CharSequence = "Edited" }
class ViewGroup : View() { val label = TextView().apply { resourceName = "edit_label"; parent = this@ViewGroup } }
class UnderlineSpan
class SpannableString(val value: String) : CharSequence by value {
    fun setSpan(span: Any, start: Int, end: Int, flags: Int) {}
    override fun toString() = value
}
data class Message(val id: Long, val key: String?, val text: String?)
interface ListAdapter { fun getItem(position: Int): Any? }
class Adapter(var message: Message?, var fail: Boolean = false) : ListAdapter {
    var reads = 0
    override fun getItem(position: Int): Any? {
        reads++
        if (fail) throw IllegalStateException("unsupported item")
        return if (position == 0) message else null
    }
}
class MethodHookParam(val thisObject: Any?, val args: Array<Any?>, val result: Any?)
object XposedHelpers {
    fun removeAdditionalInstanceField(row: View, key: String) { row.fields.remove(key) }
    fun setAdditionalInstanceField(row: View, key: String, value: Any) { row.fields[key] = value }
    fun getAdditionalInstanceField(row: View, key: String): Any? = row.fields[key]
}
class Callback(private val adapter: ListAdapter) {
    private val FIELD_ROW_ID = "waex_row_id"
    private val FIELD_MSG_ID = "waex_msg_id"
    private val FIELD_MSG_TEXT = "waex_msg_text"
    private val FIELD_BINDING_TOKEN = "waex_edit_binding_token"
    var enabled = true
    var dbQueries = 0
    var treeSearches = 0
    val opened = mutableListOf<Message>()
    private fun isFeatureEnabled() = enabled
    private fun extractStableKeyId(item: Any) = (item as Message).key
    private fun extractRowId(item: Any) = (item as Message).id
    private fun extractMessageText(item: Any) = (item as Message).text
    private fun resolveCanonicalRowId(row: Long, key: String?): Long { dbQueries++; return row }
    private fun findChildByResourceName(row: ViewGroup, name: String): View? { treeSearches++; return row.label }
    private fun findParentMessageRow(row: View): View? = row.parent
    private fun getResourceEntryName(view: View): String? = view.resourceName
    private fun extractTextFromMessageBubble(row: View?): String? = null
    private fun showEditHistoryBottomSheet(context: Any, rowId: Long, keyId: String?, text: String?) {
        opened.add(Message(rowId, keyId, text))
    }
    private fun bindEditLabel(labelView: View, parentRow: View?, boundRowId: Long, boundKeyId: String?, boundText: String?) LABEL_BODY
    fun afterHookedMethod(p: MethodHookParam) CALLBACK_BODY
    fun attached(param: MethodHookParam) ATTACH_BODY
}
private var checks = 0
private fun checkCase(value: Boolean, message: String) { checks++; if (!value) throw AssertionError(message) }
fun main(args: Array<String>) {
    val first = Adapter(Message(1, "first-chat", "first text"))
    val second = Adapter(Message(2, "second-chat", "second text"))
    val callback = Callback(first)
    val row = ViewGroup()
    if (args.single() == "queries" || args.single() == "all") {
        repeat(10_000) { callback.afterHookedMethod(MethodHookParam(first, arrayOf(0), row)) }
        checkCase(callback.dbQueries == 0, "scroll binding performed ${callback.dbQueries} canonical DB queries")
        row.label.click()
        checkCase(callback.opened.single().key == "first-chat", "keyed history remains accessible without row lookup")
        println("PASS: $checks callback query checks; 10,000 getView calls, ${callback.dbQueries} DB queries")
        if (args.single() == "queries") return
        callback.opened.clear()
        first.reads = 0
    }
    if (args.single() == "recycle") {
        callback.afterHookedMethod(MethodHookParam(first, arrayOf(0), row))
        row.label.click()
        val before = callback.opened.size
        callback.afterHookedMethod(MethodHookParam(Any(), arrayOf(0), row))
        row.label.click()
        checkCase(callback.opened.size == before, "unsupported recycled row opened its predecessor's history")
        checkCase("waex_msg_id" !in row.fields && "waex_key_id" !in row.fields, "unsupported bind retains identity")
        println("PASS: $checks unsupported recycling checks")
        return
    }
    checkCase(first.javaClass == second.javaClass, "fixture needs distinct instances of the same hooked class")
    callback.afterHookedMethod(MethodHookParam(first, arrayOf(0), row)); row.label.click()
    checkCase(callback.opened.last() == Message(0, "first-chat", "first text"), "first keyed adapter binding")
    callback.afterHookedMethod(MethodHookParam(second, arrayOf(0), row)); row.label.click()
    checkCase(callback.opened.last() == Message(0, "second-chat", "second text"), "current adapter supplies key and text")
    checkCase(row.fields["waex_msg_id"] == "second-chat", "row key follows conversation")
    checkCase("waex_row_id" !in row.fields, "keyed binding does not guess a numeric database ID")
    checkCase(first.reads == 1 && second.reads == 1, "class hook reads current receiver")
    checkCase(callback.dbQueries == 0, "getView must not query SQLite")
    val noKey = Adapter(Message(4, null, "fourth text"))
    callback.afterHookedMethod(MethodHookParam(noKey, arrayOf(0), row)); row.label.click()
    checkCase(callback.opened.last().id == 4L && callback.opened.last().key == null, "row-only compatibility")
    checkCase("waex_key_id" !in row.fields && "waex_msg_id" !in row.fields, "keyed-to-row-only recycle clears key")
    val third = Adapter(Message(3, "third-chat", null))
    callback.afterHookedMethod(MethodHookParam(third, arrayOf(0), row)); row.label.click()
    checkCase(callback.opened.last() == Message(0, "third-chat", null), "third adapter clears old text")
    checkCase("waex_msg_text" !in row.fields, "old bubble text removed")
    val before = callback.opened.size
    callback.afterHookedMethod(MethodHookParam(Any(), arrayOf(0), row)); row.label.click()
    checkCase(callback.opened.size == before, "unsupported receiver invalidates prior listener")
    checkCase("waex_msg_id" !in row.fields && "waex_key_id" !in row.fields, "unsupported receiver clears fields")
    for (bad in listOf(Adapter(null), Adapter(null, true), Adapter(Message(0, null, "unknown")))) {
        callback.afterHookedMethod(MethodHookParam(first, arrayOf(0), row))
        callback.afterHookedMethod(MethodHookParam(bad, arrayOf(0), row)); row.label.click()
        checkCase(callback.opened.size == before, "null/failed/unidentified row invalidates listener")
    }
    callback.afterHookedMethod(MethodHookParam(first, arrayOf(0), row))
    callback.enabled = false; row.label.click()
    checkCase(callback.opened.size == before, "disabled feature does not open a prior listener")
    callback.enabled = true; row.label.click()
    checkCase(callback.opened.last().key == "first-chat", "reenabled valid binding remains usable")
    val beforeDisabledRecycle = callback.opened.size
    callback.enabled = false
    callback.afterHookedMethod(MethodHookParam(second, arrayOf(0), row))
    callback.enabled = true; row.label.click()
    checkCase(callback.opened.size == beforeDisabledRecycle, "disabled-time recycle must invalidate prior listener before reenabling")
    callback.afterHookedMethod(MethodHookParam(second, arrayOf(0), row)); row.label.click()
    checkCase(callback.opened.last().key == "second-chat", "fresh bind after disabled recycle remains usable")
    callback.treeSearches = 0
    repeat(10_000) { callback.attached(MethodHookParam(ViewGroup(), emptyArray(), null)) }
    checkCase(callback.treeSearches == 0, "unidentified attachments must not scan subtrees")
    callback.attached(MethodHookParam(row, emptyArray(), null))
    checkCase(callback.treeSearches == 1, "identified row retains group fallback coverage")
    val directBefore = callback.opened.size
    callback.attached(MethodHookParam(row.label, emptyArray(), null)); row.label.click()
    checkCase(callback.opened.size == directBefore + 1 && callback.opened.last().key == "second-chat", "direct label attachment retains correct history")
    println("PASS: $checks extracted production adapter/click checks; 10,000 unidentified attachments, zero subtree searches")
}
'''.replace('CALLBACK_BODY', body_after('override fun afterHookedMethod(p: MethodHookParam)')).replace(
    'LABEL_BODY', body_after('private fun bindEditLabel(')).replace('ATTACH_BODY', body_after(
    'override fun afterHookedMethod(param: MethodHookParam)', source[source.index('private fun hookViewAttachmentFallback()'):source.index('private fun bindEditLabel(')]))
with tempfile.TemporaryDirectory() as folder:
    temp = Path(folder)
    path = temp / 'AdapterBindingChecks.kt'
    path.write_text(fixture)
    subprocess.run(['kotlinc', str(path), '-jvm-target', '17', '-include-runtime', '-d', str(temp / 'checks.jar')], check=True)
    subprocess.run(['java', '-jar', str(temp / 'checks.jar'), args.scenario], check=True)
