#!/usr/bin/env python3
"""Compile production getView and click callbacks with explicit Kotlin view doubles.

Checks adapter identity, recycled-listener invalidation and zero canonical DB
lookups in binding. The current original-key resolver body is also compiled unchanged, with counted SQLite boundaries. This is not a rendered Android/host performance measurement.
"""
from pathlib import Path
import argparse
import subprocess
import tempfile
import shutil

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, default=root / (
    'app/src/main/java/com/waenhancer/xposed/features/conversation/AntiEditMessagesHook.kt'))
parser.add_argument('--scenario', choices=['all', 'queries', 'recycle'], default='all')
parser.add_argument('--store-source', type=Path, default=root / 'app/src/main/java/com/waenhancer/xposed/core/db/EditMessageStore.kt')
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

store_source = args.store_source.read_text()

fixture = r'''
import java.util.concurrent.ConcurrentHashMap

class Context { val resources = Resources(); val packageName = "com.whatsapp" }
class Resources {
    fun getIdentifier(name: String, type: String, pkg: String) =
        if (name == "edit_label") 31 else if (name == "edited_label") 32 else 0
}
object HostResourceIds {
    fun id(context: Context, name: String): Int = context.resources.getIdentifier(name, "id", context.packageName)
}
object MessageStore {
    fun findMsgstoreDbFile(context: Context): java.io.File? = java.io.File("fixture-msgstore.db")
}
class FixtureCursor(private val resolved: String?) : AutoCloseable {
    fun moveToFirst() = resolved != null
    fun getString(index: Int): String? { check(index == 0); return resolved }
    override fun close() {}
}
class SQLiteDatabase : AutoCloseable {
    companion object {
        const val OPEN_READONLY = 1
        var queryCount = 0
        var failRead = false
        val aliases = mutableMapOf<String, String>()
        fun openDatabase(path: String, factory: Any?, flags: Int) = SQLiteDatabase()
    }
    fun rawQuery(sql: String, args: Array<String>): FixtureCursor {
        queryCount++
        if (failRead) throw IllegalStateException("fixture read failure")
        check(sql.contains("message_edit_info") && args.size == 1)
        return FixtureCursor(aliases[args.single()])
    }
    override fun close() {}
}
object XposedBridge {
    val logs = mutableListOf<String>()
    fun log(message: String) { logs.add(message) }
}
class QueuedWriter {
    val jobs = java.util.ArrayDeque<Runnable>()
    fun execute(job: Runnable) { jobs.addLast(job) }
    fun drain() { while (!jobs.isEmpty()) jobs.removeFirst().run() }
}
class EditMessageStore(private val context: Context) {
    data class MessageItem(val rowId: Long, val keyId: String, val textData: String, val timestamp: Long, val versionNumber: Int)
    data class Write(val rowId: Long, val keyId: String?, val previous: String?, val text: String, val timestamp: Long)
    private val originalKeyCache = ConcurrentHashMap<String, String>()
    private val TAG = "edit-binding-fixture"
    val writer = QueuedWriter()
    val writes = mutableListOf<Write>()
    val requests = mutableListOf<Pair<Long, String?>>()
    var stored = emptyList<MessageItem>()
    fun resolveOriginalKey(keyId: String): String STORE_BODY
    fun recordBoundSnapshotAsync(rowId: Long, keyId: String?, currentMessage: String, timestamp: Long, resolveAlias: Boolean, onAliasUnresolved: (() -> Unit)? = null) SNAPSHOT_BODY
    private fun recordTransition(rowId: Long, keyId: String?, previousMessage: String?, newMessage: String, timestamp: Long) {
        writes.add(Write(rowId, keyId, previousMessage, newMessage, timestamp))
    }
    fun getMessages(rowId: Long, keyId: String?): List<MessageItem> {
        requests.add(rowId to keyId); return stored
    }
    fun recordTransitionAsync(rowId: Long, keyId: String?, previousMessage: String?, newMessage: String, timestamp: Long) {
        throw AssertionError("Legacy snapshot writer is outside this adapter-identity fixture")
    }
}
class HistoryLoader(private val editStore: EditMessageStore) {
    fun load(ctx: Context, rowId: Long, keyId: String?, currentText: String?): List<EditMessageStore.MessageItem> LOAD_BODY
}
open class View {
    val context = Context()
    var resourceName: String? = null
    var parent: View? = null
    val fields = mutableMapOf<String, Any>()
    val tags = mutableMapOf<Int, Any>()
    fun setTag(key: Int, value: Any?) { if (value == null) tags.remove(key) else tags[key] = value }
    fun getTag(key: Int): Any? = tags[key]
    var listener: ((View) -> Unit)? = null
    var isClickable = false
    fun setOnClickListener(block: ((View) -> Unit)?) { listener = block }
    fun click() { if (isClickable) listener?.invoke(this) }
}
class TextView : View() { var text: CharSequence = "Edited" }
class ViewGroup : View() {
    var visibleText: String? = null
    val label = TextView().apply { resourceName = "edit_label"; parent = this@ViewGroup }
    @Suppress("UNCHECKED_CAST")
    fun <T : View> findViewById(id: Int): T? = (if (id == 31) label else null) as T?
}
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
    private val TAG_EDIT_DATA = 0x57414544
    private val TAG_EDIT_ORIGINAL_TEXT = 0x57414545
    private var sEditLabelResId = 0
    private var sEditedLabelResId = 0
    private data class EditData(val rowId: Long, val keyId: String?, val msgText: String?)
    private val FIELD_ROW_ID = "waex_row_id"
    private val FIELD_MSG_ID = "waex_msg_id"
    private val FIELD_MSG_TEXT = "waex_msg_text"
    private val FIELD_BINDING_TOKEN = "waex_edit_binding_token"
    var enabled = true
    private var canonicalDbQueries = 0
    val dbQueries get() = canonicalDbQueries + SQLiteDatabase.queryCount
    private val editStore = EditMessageStore(Context())
    val snapshotStore get() = editStore
    private val sSnapshotted = ConcurrentHashMap<String, String>()
    var treeSearches = 0
    val opened = mutableListOf<Message>()
    private fun isFeatureEnabled() = enabled
    private fun extractStableKeyId(item: Any) = (item as Message).key
    private fun extractRowId(item: Any) = (item as Message).id
    private fun extractMessageText(item: Any) = (item as Message).text
    private fun resolveCanonicalRowId(row: Long, key: String?): Long { canonicalDbQueries++; return row }
    private fun findChildByResourceName(row: ViewGroup, name: String): View? { treeSearches++; return row.label }
    private fun findParentMessageRow(row: View): View? = row.parent
    private fun getResourceEntryName(view: View): String? = view.resourceName
    private fun extractTextFromMessageBubble(row: View?): String? = (row as? ViewGroup)?.visibleText
    private fun showEditHistoryBottomSheet(context: Any, rowId: Long, keyId: String?, text: String?) {
        opened.add(Message(rowId, keyId, text))
    }
    private fun bindEditLabel(labelView: View, parentRow: View?, boundRowId: Long, boundKeyId: String?, boundText: String?) LABEL_BODY
    fun afterHookedMethod(p: MethodHookParam) CALLBACK_BODY
    private fun invalidateEditLabelBinding(labelView: View) INVALIDATE_BODY
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
        checkCase("waex_msg_id" !in row.label.fields && "waex_key_id" !in row.label.fields, "unsupported bind retains identity")
        println("PASS: $checks unsupported recycling checks")
        return
    }
    checkCase(first.javaClass == second.javaClass, "fixture needs distinct instances of the same hooked class")
    callback.afterHookedMethod(MethodHookParam(first, arrayOf(0), row)); row.label.click()
    checkCase(callback.opened.last() == Message(0, "first-chat", "first text"), "first keyed adapter binding")
    callback.afterHookedMethod(MethodHookParam(second, arrayOf(0), row)); row.label.click()
    checkCase(callback.opened.last() == Message(0, "second-chat", "second text"), "current adapter supplies key and text")
    checkCase(row.label.fields["waex_msg_id"] == "second-chat", "row key follows conversation")
    checkCase("waex_row_id" !in row.label.fields, "keyed binding does not guess a numeric database ID")
    checkCase(first.reads == 1 && second.reads == 1, "class hook reads current receiver")
    checkCase(callback.dbQueries == 0, "getView must not query SQLite")
    val noKey = Adapter(Message(4, null, "fourth text"))
    callback.afterHookedMethod(MethodHookParam(noKey, arrayOf(0), row)); row.label.click()
    checkCase(callback.opened.last().id == 4L && callback.opened.last().key == null, "row-only compatibility")
    checkCase("waex_key_id" !in row.label.fields && "waex_msg_id" !in row.label.fields, "keyed-to-row-only recycle clears key")
    val third = Adapter(Message(3, "third-chat", null))
    callback.afterHookedMethod(MethodHookParam(third, arrayOf(0), row)); row.label.click()
    checkCase(callback.opened.last() == Message(0, "third-chat", null), "third adapter clears old text")
    checkCase("waex_msg_text" !in row.label.fields, "old bubble text removed")
    val before = callback.opened.size
    callback.afterHookedMethod(MethodHookParam(Any(), arrayOf(0), row))
    row.fields["waex_msg_id"] = "foreign-message"
    row.fields["waex_msg_text"] = "foreign text"
    row.label.click()
    checkCase(callback.opened.size == before, "unsupported receiver invalidates prior listener")
    row.fields.clear()
    checkCase(row.label.getTag(0x57414544) == null, "unsupported receiver retained edit-data tag")
    checkCase(row.label.text.toString() == "Edited", "stale WAEX decoration retained")
    checkCase("waex_msg_id" !in row.label.fields && "waex_key_id" !in row.label.fields, "unsupported receiver clears fields")
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
    // Removed attachment hook is not recreated in the fixture. Verify the
    // current getView invalidation also preserves host-updated label text.
    callback.afterHookedMethod(MethodHookParam(first, arrayOf(0), row))
    row.label.text = "Host updated"
    callback.afterHookedMethod(MethodHookParam(Any(), arrayOf(0), row))
    checkCase(row.label.text.toString() == "Host updated",
              "invalidation clobbered a new host-supplied label")
    checkCase(row.label.getTag(0x57414544) == null, "unsupported row retained tagged edit data")
    callback.afterHookedMethod(MethodHookParam(second, arrayOf(0), row))
    val nativeClicks = intArrayOf(0)
    row.label.setOnClickListener { nativeClicks[0]++ }
    callback.afterHookedMethod(MethodHookParam(Any(), arrayOf(0), row))
    row.label.click()
    checkCase(nativeClicks[0] == 1, "invalidation erased WhatsApp's new click listener")
    val store = EditMessageStore(Context())
    SQLiteDatabase.aliases["edited-key"] = "original-key"
    val queriesBeforeSnapshot = SQLiteDatabase.queryCount
    store.recordBoundSnapshotAsync(77, "edited-key", "edited body", 201, true)
    checkCase(SQLiteDatabase.queryCount == queriesBeforeSnapshot, "snapshot alias lookup ran before writer dispatch")
    checkCase(store.writes.isEmpty() && store.writer.jobs.size == 1, "snapshot must be queued before persistence")
    store.writer.drain()
    checkCase(store.writes.single() == EditMessageStore.Write(0, "original-key", null, "edited body", 201), "snapshot lost canonical original-message identity")
    checkCase(SQLiteDatabase.queryCount == queriesBeforeSnapshot + 1, "cold alias must resolve once on writer")
    store.stored = listOf(EditMessageStore.MessageItem(0, "original-key", "original body", 101, 1))
    val versions = HistoryLoader(store).load(Context(), 77, "edited-key", "edited body")
    checkCase(store.requests.last() == (0L to "original-key"), "history lookup used the edit identity instead of original")
    checkCase(versions.map { it.textData } == listOf("original body", "edited body"), "history lost original/current text")
    checkCase(versions.all { it.rowId == 0L && it.keyId == "original-key" } && versions.map { it.versionNumber } == listOf(1, 2), "history versions kept contradictory edit-row identity")
    checkCase(SQLiteDatabase.queryCount == queriesBeforeSnapshot + 1, "cached alias unexpectedly reopened host database")
    store.recordBoundSnapshotAsync(88, null, "row body", 202, true)
    store.recordBoundSnapshotAsync(99, "plain-key", "plain body", 203, false)
    store.writer.drain()
    checkCase(store.writes[1] == EditMessageStore.Write(88, null, null, "row body", 202), "row-only snapshot identity changed")
    checkCase(store.writes[2] == EditMessageStore.Write(99, "plain-key", null, "plain body", 203), "unedited snapshot identity changed")
    checkCase(SQLiteDatabase.queryCount == queriesBeforeSnapshot + 1, "unedited or row-only snapshot queried alias database")
    store.recordBoundSnapshotAsync(0, null, "invalid identity", 204, true)
    store.recordBoundSnapshotAsync(1, "key", "   ", 204, true)
    checkCase(store.writer.jobs.isEmpty(), "invalid snapshots entered writer queue")
    val retryStore = EditMessageStore(Context())
    SQLiteDatabase.aliases["retry-edit"] = "retry-original"
    SQLiteDatabase.failRead = true
    retryStore.recordBoundSnapshotAsync(12, "retry-edit", "retry body", 205, true)
    retryStore.writer.drain()
    checkCase(retryStore.writes.single().keyId == "retry-edit" && retryStore.writes.single().rowId == 12L, "unresolved alias fabricated another identity")
    checkCase(XposedBridge.logs.last().contains("IllegalStateException"), "failed alias read did not reach production diagnostic path")
    SQLiteDatabase.failRead = false
    retryStore.recordBoundSnapshotAsync(12, "retry-edit", "retry body", 206, true)
    retryStore.writer.drain()
    checkCase(retryStore.writes.last().keyId == "retry-original" && retryStore.writes.last().rowId == 0L, "failed alias read poisoned later successful resolution")
    val rebindAdapter = Adapter(Message(901, "rebind-edit", "unchanged body"))
    val rebindCallback = Callback(rebindAdapter)
    val rebindRow = ViewGroup().apply { visibleText = "unchanged body" }
    SQLiteDatabase.aliases["rebind-edit"] = "rebind-original"
    SQLiteDatabase.failRead = true
    val beforeRebind = SQLiteDatabase.queryCount
    rebindCallback.afterHookedMethod(MethodHookParam(rebindAdapter, arrayOf(0), rebindRow))
    checkCase(SQLiteDatabase.queryCount == beforeRebind, "first retry binding queried SQLite")
    checkCase(rebindCallback.snapshotStore.writer.jobs.size == 1, "first bound snapshot was not queued")
    rebindCallback.snapshotStore.writer.drain()
    checkCase(rebindCallback.snapshotStore.writes.single().keyId == "rebind-edit", "failed lookup must retain raw identity")
    SQLiteDatabase.failRead = false
    val beforeRecoveredBinding = SQLiteDatabase.queryCount
    rebindCallback.afterHookedMethod(MethodHookParam(rebindAdapter, arrayOf(0), rebindRow))
    checkCase(SQLiteDatabase.queryCount == beforeRecoveredBinding, "recovery binding queried SQLite")
    checkCase(rebindCallback.snapshotStore.writer.jobs.size == 1, "identical rebind after alias failure did not retry")
    rebindCallback.snapshotStore.writer.drain()
    checkCase(rebindCallback.snapshotStore.writes.last().keyId == "rebind-original" && rebindCallback.snapshotStore.writes.last().rowId == 0L,
              "recovered callback did not persist canonical identity")
    repeat(100) { rebindCallback.afterHookedMethod(MethodHookParam(rebindAdapter, arrayOf(0), rebindRow)) }
    checkCase(rebindCallback.snapshotStore.writer.jobs.isEmpty(), "successful snapshot no longer deduplicates identical binds")
    val changedAdapter = Adapter(Message(902, "changed-edit", "old text"))
    val changedCallback = Callback(changedAdapter)
    val changedRow = ViewGroup().apply { visibleText = "old text" }
    SQLiteDatabase.aliases["changed-edit"] = "changed-original"
    changedCallback.afterHookedMethod(MethodHookParam(changedAdapter, arrayOf(0), changedRow))
    changedAdapter.message = Message(902, "changed-edit", "new text")
    changedRow.visibleText = "new text"
    changedCallback.afterHookedMethod(MethodHookParam(changedAdapter, arrayOf(0), changedRow))
    checkCase(changedCallback.snapshotStore.writer.jobs.size == 2, "changed text must enqueue separately")
    SQLiteDatabase.failRead = true
    changedCallback.snapshotStore.writer.jobs.removeFirst().run()
    changedCallback.afterHookedMethod(MethodHookParam(changedAdapter, arrayOf(0), changedRow))
    checkCase(changedCallback.snapshotStore.writer.jobs.size == 1, "older alias failure discarded newer snapshot reservation")
    SQLiteDatabase.failRead = false
    changedCallback.snapshotStore.writer.drain()
    checkCase(changedCallback.snapshotStore.writes.last().keyId == "changed-original" &&
              changedCallback.snapshotStore.writes.last().text == "new text", "newer snapshot lost canonical identity")
    println("PASS: writer/click alias identity, fallback and retry checks with actual extracted production bodies")
    println("PASS: $checks extracted production adapter/click checks; 10,000 source getView calls")

}
'''.replace('SNAPSHOT_BODY', body_after('fun recordBoundSnapshotAsync(', store_source)).replace('LOAD_BODY', body_after('private fun loadAllChronologicalVersions(', source)).replace('STORE_BODY', body_after('fun resolveOriginalKey(keyId: String): String', store_source)).replace('CALLBACK_BODY', body_after('override fun afterHookedMethod(p: MethodHookParam)')).replace(
    'LABEL_BODY', body_after('private fun bindEditLabel(')).replace(
    'INVALIDATE_BODY', body_after('private fun invalidateEditLabelBinding(')
    if 'private fun invalidateEditLabelBinding(' in source
    else '{ throw AssertionError("unexpected invalidation callback") }')
with tempfile.TemporaryDirectory() as folder:
    temp = Path(folder)
    path = temp / 'AdapterBindingChecks.kt'
    path.write_text(fixture)
    subprocess.run([shutil.which('kotlinc.bat') or shutil.which('kotlinc') or 'kotlinc', str(path), '-jvm-target', '17', '-include-runtime', '-d', str(temp / 'checks.jar')], check=True)
    subprocess.run(['java', '-jar', str(temp / 'checks.jar'), args.scenario], check=True)
