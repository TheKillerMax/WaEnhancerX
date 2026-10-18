package test

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import com.waenhancer.xposed.core.db.EditMessageStore

private var checks = 0
private fun checkCase(value: Boolean, message: String) {
    checks++
    if (!value) throw AssertionError(message)
}

private fun newStore(): EditMessageStore {
    SQLiteOpenHelper.nextDatabase = SQLiteDatabase()
    val constructor = EditMessageStore::class.java.getDeclaredConstructor(Context::class.java)
    constructor.isAccessible = true
    return constructor.newInstance(Context())
}

private fun texts(store: EditMessageStore, row: Long, key: String?): List<String> =
    store.getMessages(row, key).map { it.textData }

private fun row(id: Long, key: String, text: String?) =
    mutableMapOf<String, Any?>("_id" to id, "key_id" to key, "text_data" to text)

fun main(args: Array<String>) {
    val scenario = args.firstOrNull() ?: "all"
    if (scenario == "cache" || scenario == "all") {
        for (keyFirst in listOf(false, true)) {
            val store = newStore()
            if (keyFirst) {
                store.recordTransition(88, "77", "key-original", "key-edited", 20000)
                store.recordTransition(77, null, "row-original", "row-edited", 10000)
            } else {
                store.recordTransition(77, null, "row-original", "row-edited", 10000)
                store.recordTransition(88, "77", "key-original", "key-edited", 20000)
            }
            checkCase(texts(store, 0, "77") == listOf("key-original", "key-edited"),
                "numeric-looking message key must not reuse row-ID cache")
            checkCase(texts(store, 77, null) == listOf("row-original", "row-edited"),
                "row-ID history must not reuse numeric-looking key cache")
            store.recordTransition(90, "row:77", "prefixed-original", "prefixed-edited", 30000)
            checkCase(texts(store, 0, "row:77") == listOf("prefixed-original", "prefixed-edited"),
                "literal prefixed message IDs cannot collide with row namespace")
            checkCase(texts(store, 77, null) == listOf("row-original", "row-edited"), "unrelated histories stay intact")
            val callerCopy = store.getMessages(77, null) as MutableList<EditMessageStore.MessageItem>
            callerCopy.clear()
            checkCase(texts(store, 77, null).size == 2, "caller mutation does not alter cached list")
            checkCase(store.getMessages(0, null).isEmpty(), "missing identifiers cannot select every history")
        }
    }
    if (scenario == "lookup" || scenario == "all") {
        val store = newStore()
        val host = SQLiteDatabase()
        SQLiteDatabase.host = host
        host.rows("message").add(row(1, "wanted", "wanted text"))
        host.rows("message").add(row(9, "other-chat", "unrelated private text"))
        host.rows("message_ftsv2_content").add(mutableMapOf("docid" to 1L, "c0content" to "wanted FTS"))
        host.rows("message_ftsv2_content").add(mutableMapOf("docid" to 9L, "c0content" to "unrelated FTS"))

        checkCase(store.getCurrentMessageFromWhatsApp(9, "wanted") == "wanted text", "key wins mismatched reflected row")
        host.queries.clear()
        checkCase(store.getCurrentMessageFromWhatsApp(9, "missing") == "", "missing key must not disclose another row")
        checkCase(host.queries.none { it.contains("/_id=?/") || it.contains("/docid=?/") },
            "missing key performs no unverified numeric fallback")
        host.rows("message")[0]["text_data"] = ""
        checkCase(store.getCurrentMessageFromWhatsApp(9, "wanted") == "wanted FTS", "empty text uses key-verified FTS ID")
        host.rows("message")[0]["text_data"] = null
        checkCase(store.getCurrentMessageFromWhatsApp(9, "wanted") == "wanted FTS", "null text uses key-verified FTS ID")
        host.noTextColumn = true
        checkCase(store.getCurrentMessageFromWhatsApp(9, "wanted") == "wanted FTS", "missing text column resolves key before FTS")
        checkCase(store.getCurrentMessageFromWhatsApp(9, "missing") == "", "schema fallback cannot bypass missing key")
        host.noTextColumn = false
        host.rows("message").add(row(2, "wanted", "other same-key chat"))
        checkCase(store.getCurrentMessageFromWhatsApp(9, "wanted") == "", "duplicate host keys are ambiguous")
        host.rows("message").removeAt(2)
        host.rejectKeyQueries = true
        checkCase(store.getCurrentMessageFromWhatsApp(9, "wanted") == "", "key query failure cannot bypass identity")
        host.rejectKeyQueries = false
        checkCase(store.getCurrentMessageFromWhatsApp(9, null) == "unrelated private text", "row-only compatibility remains")
        checkCase(store.getCurrentMessageFromWhatsApp(0, null) == "", "missing all identities remains empty")
        host.rows("message")[1]["text_data"] = ""
        checkCase(store.getCurrentMessageFromWhatsApp(9, null) == "unrelated FTS", "row-only FTS compatibility remains")
        checkCase(store.getCurrentMessageFromWhatsApp(0, "wanted") == "wanted FTS", "verified key does not require reflected row")
        checkCase(host.openCount == host.closeCount, "host DB handle closes on every successful or early-return path")

        // Actual store transition must not invent an original from another numeric row.
        val recording = newStore()
        recording.recordTransition(9, "not-in-host", null, "new edit", 40000)
        checkCase(texts(recording, 9, "not-in-host") == listOf("new edit"), "no unrelated original is persisted")
    }
    println("PASS: $checks whole EditMessageStore checks ($scenario; explicit Android DB doubles)")
}
