#!/usr/bin/env python3
"""Execute the verbatim production getView callback body with explicit Kotlin doubles.

This validates per-invocation adapter binding, not Android views, host key
resolution, DexKit or Xposed hook installation. --source supports baseline checks.
"""
from pathlib import Path
import argparse
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, default=root / (
    "app/src/main/java/com/waenhancer/xposed/features/conversation/AntiEditMessagesHook.kt"))
args = parser.parse_args()
source = args.source.read_text()
signature = "override fun afterHookedMethod(p: MethodHookParam)"
assert source.count(signature) == 1, "callback extraction must be unambiguous"
start = source.index("{", source.index(signature))
depth = 0
quoted = False
escaped = False
end = None
for index in range(start, len(source)):
    char = source[index]
    if quoted:
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            quoted = False
        continue
    if char == '"':
        quoted = True
    elif char == "{":
        depth += 1
    elif char == "}":
        depth -= 1
        if depth == 0:
            end = index + 1
            break
assert end is not None
body = source[start:end]
fixture = r'''
class ViewGroup {
    val fields = mutableMapOf<String, Any>()
    val label = Any()
    var bound: Message? = null
}
data class Message(val id: Long, val key: String?, val text: String?)
interface ListAdapter { fun getItem(position: Int): Any? }
class Adapter(private val message: Message) : ListAdapter {
    var reads = 0
    override fun getItem(position: Int): Any? { reads++; return if (position == 0) message else null }
}
class MethodHookParam(val thisObject: Any?, val args: Array<Any?>, val result: Any?)
object XposedHelpers {
    fun removeAdditionalInstanceField(row: ViewGroup, key: String) { row.fields.remove(key) }
    fun setAdditionalInstanceField(row: ViewGroup, key: String, value: Any) { row.fields[key] = value }
}
class Callback(private val adapter: ListAdapter) {
    private val FIELD_ROW_ID = "waex_row_id"
    private val FIELD_MSG_ID = "waex_msg_id"
    private val FIELD_MSG_TEXT = "waex_msg_text"
    private fun isFeatureEnabled() = true
    private fun extractStableKeyId(item: Any) = (item as Message).key
    private fun extractRowId(item: Any) = (item as Message).id
    private fun extractMessageText(item: Any) = (item as Message).text
    private fun resolveCanonicalRowId(row: Long, key: String?) = row
    private fun findChildByResourceName(row: ViewGroup, name: String): Any? = row.label
    private fun bindEditLabel(label: Any, row: ViewGroup, id: Long, key: String?, text: String?) {
        row.bound = Message(id, key, text)
    }
    fun afterHookedMethod(p: MethodHookParam) CALLBACK_BODY
}
private var checks = 0
private fun checkCase(value: Boolean, message: String) {
    checks++
    if (!value) throw AssertionError(message)
}
fun main() {
    val first = Adapter(Message(1, "first-chat", "first text"))
    val second = Adapter(Message(2, "second-chat", "second text"))
    val third = Adapter(Message(3, "third-chat", null))
    checkCase(first.javaClass == second.javaClass, "fixture needs distinct instances of the same hooked class")
    val callback = Callback(first)
    val row = ViewGroup()
    callback.afterHookedMethod(MethodHookParam(first, arrayOf(0), row))
    checkCase(row.bound == Message(1, "first-chat", "first text"), "first adapter binding")
    callback.afterHookedMethod(MethodHookParam(second, arrayOf(0), row))
    checkCase(row.bound == Message(2, "second-chat", "second text"), "second chat must use current adapter receiver")
    checkCase(row.fields["waex_msg_id"] == "second-chat", "row key follows live conversation")
    checkCase(row.fields["waex_row_id"] == 2L, "row ID follows live conversation")
    checkCase(first.reads == 1 && second.reads == 1, "class-wide hook must not retain first adapter for item reads")
    callback.afterHookedMethod(MethodHookParam(third, arrayOf(0), row))
    checkCase(row.bound == Message(3, "third-chat", null), "third adapter binding")
    checkCase("waex_msg_text" !in row.fields, "successful recycle clears old message text")
    callback.afterHookedMethod(MethodHookParam(Any(), arrayOf(0), ViewGroup()))
    checkCase(first.reads == 1 && second.reads == 1 && third.reads == 1, "unknown receiver does not fall back to first adapter")
    val noKey = Adapter(Message(4, null, "fourth text"))
    callback.afterHookedMethod(MethodHookParam(noKey, arrayOf(0), row))
    checkCase(row.bound == Message(4, null, "fourth text"), "successful keyed-to-row-only recycle")
    checkCase("waex_key_id" !in row.fields, "successful row-only recycle must clear old fallback key")
    println("PASS: $checks extracted production getView callback checks (Kotlin doubles)")
}
'''.replace("CALLBACK_BODY", body)
with tempfile.TemporaryDirectory() as folder:
    temp = Path(folder)
    path = temp / "AdapterBindingChecks.kt"
    path.write_text(fixture)
    subprocess.run(["kotlinc", str(path), "-jvm-target", "17", "-include-runtime",
                    "-d", str(temp / "checks.jar")], check=True)
    subprocess.run(["java", "-jar", str(temp / "checks.jar")], check=True)
