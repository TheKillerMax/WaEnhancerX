package com.waenhancer.xposed.features.conversation


import com.waenhancer.app.R
import com.waenhancer.utils.UiText

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.SharedPreferences
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import android.graphics.Color
import android.graphics.Typeface
import android.text.Spannable
import android.text.SpannableString
import android.text.SpannableStringBuilder
import android.text.style.BackgroundColorSpan
import android.text.style.ForegroundColorSpan
import android.text.style.StrikethroughSpan
import android.text.style.UnderlineSpan
import android.util.AttributeSet
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.CompoundButton
import android.widget.HeaderViewListAdapter
import android.widget.ListAdapter
import android.widget.ListView
import android.widget.LinearLayout
import android.widget.Switch
import android.widget.TextView
import com.waenhancer.xposed.core.BaseFeature
import com.waenhancer.xposed.core.components.WaexBottomSheet
import com.waenhancer.xposed.core.db.EditMessageStore
import com.waenhancer.xposed.core.db.MessageStore
import com.waenhancer.xposed.core.devkit.DexSearchEngine
import com.waenhancer.xposed.utils.ActivityTracker
import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XposedBridge
import de.robv.android.xposed.XposedHelpers
import org.luckypray.dexkit.query.FindMethod
import org.luckypray.dexkit.query.enums.StringMatchType
import org.luckypray.dexkit.query.matchers.MethodMatcher
import java.io.File
import java.lang.reflect.Field
import java.lang.reflect.Method
import java.lang.reflect.Modifier
import java.text.DateFormat
import java.util.Date
import java.util.concurrent.ConcurrentHashMap
import java.util.regex.Pattern
import android.R
import android.content.ContentValues
import android.graphics.drawable.GradientDrawable

/**
 * Anti-Edit Messages Feature for WhatsApp.
 *
 * - Renders all distinct versions in descending chronological order (Latest at top).
 * - Selectable text on all cards.
 * - Top-Right WDSSwitch "Show changes" to dynamically highlight text diffs (Green for added, Red for removed).
 */
class AntiEditMessagesHook(
    context: Context,
    classLoader: ClassLoader,
    prefs: SharedPreferences
) : BaseFeature(context, classLoader, prefs) {

    override val name: String
        get() = "AntiEditMessages"

    companion object {
        private const val TAG = "[WAEX:AntiEdit]"
        private const val PREF_KEY = "anti_edit_messages"
        private const val FIELD_ROW_ID = "waex_row_id"
        private const val FIELD_MSG_ID = "waex_msg_id"
        private const val FIELD_MSG_TEXT = "waex_msg_text"
        private val hookedAdapterClasses = ConcurrentHashMap.newKeySet<Class<*>>()
        private val timeFormatter = object : ThreadLocal<DateFormat>() {
            override fun initialValue(): DateFormat = DateFormat.getTimeInstance(DateFormat.SHORT)
        }
        private val KEY_ID_REGEX = Pattern.compile("id=([A-Za-z0-9]+)")
    }

    private val editStore: EditMessageStore by lazy { EditMessageStore.getInstance(context) }
    private var originalKeyMethod: Method? = null

    private fun isFeatureEnabled(): Boolean {
        return isEnabled(PREF_KEY, false) || isEnabled("antieditmessages", false)
    }

    override fun hook() {
        originalKeyMethod = resolveOriginalKeyMethod()
        hookMessageEditMethod()
        hookDatabaseEditInsert()
        hookListViewAdapter()
        hookViewAttachmentFallback()
    }

    // ─── 1. Bytecode Edit Interception ──────────────────────────────────────────

    private fun hookMessageEditMethod() {
        try {
            val onMessageEdit = resolveMessageEditMethod()
            if (onMessageEdit != null) {
                XposedBridge.hookMethod(
                    onMessageEdit,
                    object : XC_MethodHook() {
                        override fun beforeHookedMethod(param: MethodHookParam) {
                            if (!isFeatureEnabled()) return

                            try {
                                val fMessage = param.args.getOrNull(0) ?: return
                                val keyId = extractStableKeyId(fMessage)
                                var rowId = extractRowId(fMessage)
                                val newMessage = extractMessageText(fMessage)
                                rowId = resolveCanonicalRowId(rowId, keyId)

                                if (!newMessage.isNullOrBlank() && (!keyId.isNullOrEmpty() || rowId > 0)) {
                                    val ts = System.currentTimeMillis()
                                    val previous = editStore.getCurrentMessageFromWhatsApp(rowId, keyId)
                                    editStore.recordTransitionAsync(rowId, keyId, previous, newMessage, ts)
                                    if (!keyId.isNullOrEmpty()) {
                                    }
                                }
                            } catch (t: Throwable) {
                                XposedBridge.log("$TAG Error in onMessageEdit: ${t.javaClass.simpleName}")
                            }
                        }
                    }
                )
            }
        } catch (t: Throwable) {
            XposedBridge.log("$TAG Failed to hook onMessageEdit: ${t.javaClass.simpleName}")
        }
    }

    private fun resolveMessageEditMethod(): Method? {
        return try {
            DexSearchEngine.getInstance().findMethodWithCache(
                context,
                classLoader,
                "wpp_anti_edit_method_v14",
                { bridge, loader ->
                    val data = bridge.findMethod(
                        FindMethod.create().matcher(
                            MethodMatcher.create().addUsingString(
                                "MessageEditInfoStore/insertEditInfo/missing",
                                StringMatchType.Contains
                            )
                        )
                    ).firstOrNull() ?: bridge.findMethod(
                        FindMethod.create().matcher(
                            MethodMatcher.create().addUsingString(
                                "MessageEditInfoStore/insertEditInfo",
                                StringMatchType.Contains
                            )
                        )
                    ).firstOrNull()
                    data?.getMethodInstance(loader)
                }
            )
        } catch (t: Throwable) {
            null
        }
    }

    private fun resolveOriginalKeyMethod(): Method? {
        return try {
            DexSearchEngine.getInstance().findMethodWithCache(
                context,
                classLoader,
                "wpp_original_key_for_edited_message_v1",
                { bridge, loader ->
                    bridge.findMethod(
                        FindMethod.create().matcher(
                            MethodMatcher.create().addUsingString(
                                "FMessageUtil/getOriginalMessageKeyIfEdited",
                                StringMatchType.Contains
                            )
                        )
                    ).firstOrNull()?.getMethodInstance(loader)
                }
            )
        } catch (_: Throwable) {
            null
        }
    }

    // ─── 2. SQLite Database Interception Fallback ──────────────────────────────

    private fun hookDatabaseEditInsert() {
        try {
            XposedHelpers.findAndHookMethod(
                SQLiteDatabase::class.java,
                "insertWithOnConflict",
                String::class.java,
                String::class.java,
                ContentValues::class.java,
                Int::class.javaPrimitiveType,
                object : XC_MethodHook() {
                    override fun beforeHookedMethod(param: MethodHookParam) {
                        if (!isFeatureEnabled()) return
                        val table = param.args.getOrNull(0) as? String ?: return
                        if (table == "message_edit_info" || table == "message_add_on" || table == "message_add_on_edit_info") {
                            val values = param.args.getOrNull(2) as? ContentValues ?: return
                            val keyId = values.getAsString("original_key_id") ?: values.getAsString("key_id")
                            var rowId = values.getAsLong("message_row_id") ?: 0L
                            val editedText = values.getAsString("edited_text")
                                ?: values.getAsString("new_text")
                                ?: values.getAsString("text_data")
                            val ts = values.getAsLong("edit_timestamp")
                                ?: values.getAsLong("sender_timestamp")
                                ?: System.currentTimeMillis()
                            rowId = resolveCanonicalRowId(rowId, keyId)

                            if (!editedText.isNullOrBlank() && (!keyId.isNullOrEmpty() || rowId > 0)) {
                                editStore.recordTransitionAsync(rowId, keyId, null, editedText, ts)
                            }
                        }
                    }
                }
            )
        } catch (t: Throwable) {
            XposedBridge.log("$TAG Database insert hook error: ${t.javaClass.simpleName}")
        }
    }

    // ─── 3. ListView.setAdapter → getView Hook (Conversation Row Binding) ───────

    private fun hookListViewAdapter() {
        try {
            XposedHelpers.findAndHookMethod(
                ListView::class.java,
                "setAdapter",
                ListAdapter::class.java,
                object : XC_MethodHook() {
                    override fun beforeHookedMethod(param: MethodHookParam) {
                        val currentAct = ActivityTracker.getCurrentActivity() ?: return
                        val actName = currentAct.javaClass.simpleName
                        if (!actName.contains("Conversation")) return

                        param.thisObject as? ListView ?: return

                        var adapter = param.args.getOrNull(0) as? ListAdapter ?: return
                        if (adapter is HeaderViewListAdapter) {
                            adapter = adapter.wrappedAdapter
                        }

                        try {
                            if (!hookedAdapterClasses.add(adapter.javaClass)) return
                            val getViewMethod = XposedHelpers.findMethodBestMatch(
                                adapter.javaClass,
                                "getView",
                                Int::class.javaPrimitiveType,
                                View::class.java,
                                ViewGroup::class.java
                            ) ?: return
                            XposedBridge.hookMethod(
                                getViewMethod,
                                object : XC_MethodHook() {
                                    override fun afterHookedMethod(p: MethodHookParam) {
                                        if (!isFeatureEnabled()) return
                                        val pos = p.args.getOrNull(0) as? Int ?: return
                                        val row = p.result as? ViewGroup ?: return

                                        val item = try { adapter.getItem(pos) } catch (t: Throwable) { null } ?: return
                                        val keyId = extractStableKeyId(item)
                                        var rowId = extractRowId(item)
                                        val msgText = extractMessageText(item)
                                        rowId = resolveCanonicalRowId(rowId, keyId)

                                        XposedHelpers.removeAdditionalInstanceField(row, FIELD_ROW_ID)
                                        XposedHelpers.removeAdditionalInstanceField(row, FIELD_MSG_ID)
                                        XposedHelpers.removeAdditionalInstanceField(row, FIELD_MSG_TEXT)

                                        if (rowId > 0) {
                                            XposedHelpers.setAdditionalInstanceField(row, FIELD_ROW_ID, rowId)
                                        }
                                        if (!keyId.isNullOrEmpty()) {
                                            XposedHelpers.setAdditionalInstanceField(row, FIELD_MSG_ID, keyId)
                                            XposedHelpers.setAdditionalInstanceField(row, "waex_key_id", keyId)
                                            if (!msgText.isNullOrEmpty()) {
                                                XposedHelpers.setAdditionalInstanceField(row, FIELD_MSG_TEXT, msgText)
                                            }
                                        }

                                        val editLabel = findChildByResourceName(row, "edit_label")
                                            ?: findChildByResourceName(row, "edited_label")
                                        if (editLabel != null) {
                                            bindEditLabel(editLabel, row, rowId, keyId, msgText)
                                        }
                                    }
                                }
                            )
                        } catch (t: Throwable) {
                            XposedBridge.log("$TAG Error hooking getView: ${t.javaClass.simpleName}")
                        }
                    }
                }
            )
        } catch (t: Throwable) {
            XposedBridge.log("$TAG ListView setAdapter hook error: ${t.javaClass.simpleName}")
        }
    }

    // ─── 4. View.onAttachedToWindow Fallback ────────────────────────────────────

    private fun hookViewAttachmentFallback() {
        try {
            XposedHelpers.findAndHookMethod(
                View::class.java,
                "onAttachedToWindow",
                object : XC_MethodHook() {
                    override fun afterHookedMethod(param: MethodHookParam) {
                        if (!isFeatureEnabled()) return

                        val view = param.thisObject as? View ?: return
                        val resName = getResourceEntryName(view)

                        if (resName == "edit_label" || resName == "edited_label") {
                            val row = findParentMessageRow(view)
                            val rowId = row?.let {
                                XposedHelpers.getAdditionalInstanceField(it, FIELD_ROW_ID) as? Long
                            } ?: 0L
                            val keyId = row?.let {
                                XposedHelpers.getAdditionalInstanceField(it, FIELD_MSG_ID) as? String
                            }
                            val text = row?.let {
                                XposedHelpers.getAdditionalInstanceField(it, FIELD_MSG_TEXT) as? String
                            }
                            bindEditLabel(view, row, rowId, keyId, text)
                        } else if (view is ViewGroup) {
                            val editLabel = findChildByResourceName(view, "edit_label")
                                ?: findChildByResourceName(view, "edited_label")
                            if (editLabel != null) {
                                val rowId = XposedHelpers.getAdditionalInstanceField(view, FIELD_ROW_ID) as? Long ?: 0L
                                val keyId = XposedHelpers.getAdditionalInstanceField(view, FIELD_MSG_ID) as? String
                                val text = XposedHelpers.getAdditionalInstanceField(view, FIELD_MSG_TEXT) as? String
                                bindEditLabel(editLabel, view, rowId, keyId, text)
                            }
                        }
                    }
                }
            )
        } catch (t: Throwable) {
            XposedBridge.log("$TAG View attachment hook error: ${t.javaClass.simpleName}")
        }
    }

    private fun bindEditLabel(labelView: View, parentRow: View?, boundRowId: Long, boundKeyId: String?, boundText: String?) {
        if (labelView is TextView) {
            val originalText = labelView.text.toString()
            if (!originalText.contains("📝")) {
                val spannable = SpannableString("$originalText 📝")
                spannable.setSpan(UnderlineSpan(), 0, spannable.length, 0)
                labelView.text = spannable
            }
        }

        XposedHelpers.removeAdditionalInstanceField(labelView, FIELD_ROW_ID)
        XposedHelpers.removeAdditionalInstanceField(labelView, FIELD_MSG_ID)
        XposedHelpers.removeAdditionalInstanceField(labelView, FIELD_MSG_TEXT)
        if (boundRowId > 0) {
            XposedHelpers.setAdditionalInstanceField(labelView, FIELD_ROW_ID, boundRowId)
        }
        if (boundKeyId != null) {
            XposedHelpers.setAdditionalInstanceField(labelView, FIELD_MSG_ID, boundKeyId)
        }
        if (boundText != null) {
            XposedHelpers.setAdditionalInstanceField(labelView, FIELD_MSG_TEXT, boundText)
        }

        labelView.isClickable = true
        labelView.setOnClickListener { clickedView ->
            val row = parentRow ?: findParentMessageRow(clickedView)
            val rowId = (XposedHelpers.getAdditionalInstanceField(clickedView, FIELD_ROW_ID) as? Long)
                ?: (row?.let { XposedHelpers.getAdditionalInstanceField(it, FIELD_ROW_ID) as? Long })
                ?: 0L

            val keyId = (XposedHelpers.getAdditionalInstanceField(clickedView, FIELD_MSG_ID) as? String)
                ?: (row?.let { XposedHelpers.getAdditionalInstanceField(it, FIELD_MSG_ID) as? String })
                ?: (row?.let { XposedHelpers.getAdditionalInstanceField(it, "waex_key_id") as? String })

            val visibleBubbleText = (XposedHelpers.getAdditionalInstanceField(clickedView, FIELD_MSG_TEXT) as? String)
                ?: (row?.let { XposedHelpers.getAdditionalInstanceField(it, FIELD_MSG_TEXT) as? String })
                ?: extractTextFromMessageBubble(row)

            showEditHistoryBottomSheet(clickedView.context, rowId, keyId, visibleBubbleText)
        }
    }

    // ─── 5. WDS Bottom Sheet Display (Descending Order with Diff Highlighting) ──

    private fun showEditHistoryBottomSheet(context: Context, rowId: Long, keyId: String?, currentText: String?) {
        val currentActivity = ActivityTracker.getCurrentActivity() ?: context
        val allVersions = loadAllChronologicalVersions(context, rowId, keyId, currentText)

        val bottomSheet = WaexBottomSheet(currentActivity).asBottomSheet()
        bottomSheet.setTitle(UiText.get(R.string.waex_ui_edited_message_history_492e60cb, "Edited Message History"))

        val density = currentActivity.resources.displayMetrics.density
        val dp = { v: Int -> (v * density).toInt() }

        // Map each version number to its exact text for preceding diff lookups
        val versionTextMap = mutableMapOf<Int, String>()
        for (item in allVersions) {
            versionTextMap[item.versionNumber] = item.textData
        }

        val cardTextViews = mutableListOf<Pair<TextView, EditMessageStore.MessageItem>>()

        // Top-Right "Show changes" Switch
        val switchRow = LinearLayout(currentActivity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }

        val switchLabel = TextView(currentActivity).apply {
            text = UiText.get(R.string.waex_ui_show_changes_b12a6ef8, "Show changes")
            textSize = 13f
            setTextColor(0xFF8696A0.toInt())
            setPadding(0, 0, dp(6), 0)
        }
        switchRow.addView(switchLabel)

        val wdsSwitch = createWdsSwitch(currentActivity).apply {
            isChecked = false
            setOnCheckedChangeListener { _, isChecked ->
                for ((textView, item) in cardTextViews) {
                    if (isChecked) {
                        val prevText = versionTextMap[item.versionNumber - 1]
                        if (!prevText.isNullOrEmpty() && item.versionNumber > 1) {
                            textView.text = buildDiffSpannable(prevText, item.textData)
                        } else {
                            textView.text = item.textData
                        }
                    } else {
                        textView.text = item.textData
                    }
                }
            }
        }
        switchRow.addView(wdsSwitch)
        bottomSheet.setTopRightView(switchRow)

        val contentLayout = LinearLayout(currentActivity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(4), dp(4), dp(4), dp(12))
        }

        if (allVersions.isNotEmpty()) {
            // Render in descending order: latest version on top
            val descendingList = allVersions.reversed()
            val totalVersions = allVersions.size

            for (item in descendingList) {
                val isFirst = (item.versionNumber == 1)
                val isLatest = (item.versionNumber == totalVersions && totalVersions > 1)
                val timeStr = if (item.timestamp > 0) timeFormatter.get().format(Date(item.timestamp)) else ""

                val title = when {
                    isLatest -> UiText.get(R.string.waex_ui_version_1_s_latest_2_s_d802e8b0, "Version %1\$s (Latest) • %2\$s", item.versionNumber, timeStr)
                    isFirst && totalVersions > 1 -> UiText.get(R.string.waex_ui_version_1_original_1_s_ac2f8fb2, "Version 1 (Original) • %1\$s", timeStr)
                    totalVersions == 1 -> UiText.get(R.string.waex_ui_version_1_latest_1_s_7e28fc56, "Version 1 (Latest) • %1\$s", timeStr)
                    else -> UiText.get(R.string.waex_ui_version_1_s_2_s_4d9f20e0, "Version %1\$s • %2\$s", item.versionNumber, timeStr)
                }
                val color = if (isLatest) 0xFF21C063.toInt() else 0xFF00A884.toInt()

                val cardView = createHistoryCard(currentActivity, title, item.textData, color, dp)
                val bodyTextView = cardView.findViewById<TextView>(R.id.text1)
                if (bodyTextView != null) {
                    cardTextViews.add(bodyTextView to item)
                }
                contentLayout.addView(cardView)
            }
        } else {
            val emptyNotice = TextView(currentActivity).apply {
                text = UiText.get(R.string.waex_ui_message_was_edited_by_sender_9724779c, "Message was edited by sender.")
                textSize = 14f
                gravity = Gravity.CENTER
                setPadding(0, dp(16), 0, dp(16))
            }
            contentLayout.addView(emptyNotice)
        }

        bottomSheet.setView(contentLayout)
        bottomSheet.setPositiveButton(UiText.get(R.string.waex_ui_close_7d9eb7ac, "Close"), null)
        bottomSheet.show()
    }

    private fun loadAllChronologicalVersions(
        ctx: Context,
        rowId: Long,
        keyId: String?,
        currentText: String?
    ): List<EditMessageStore.MessageItem> {
        val result = mutableListOf<EditMessageStore.MessageItem>()
        val seenTexts = mutableSetOf<String>()

        // 1. Pull from EditMessageStore
        val stored = editStore.getMessages(rowId, keyId)
        for (item in stored) {
            if (item.textData.isNotBlank() && seenTexts.add(item.textData.trim())) {
                result.add(item)
            }
        }

        // 2. If current visible bubble text is not in the list, append it
        if (!currentText.isNullOrBlank() && seenTexts.add(currentText.trim())) {
            result.add(
                EditMessageStore.MessageItem(
                    rowId = rowId,
                    keyId = keyId ?: "",
                    textData = currentText.trim(),
                    timestamp = System.currentTimeMillis(),
                    versionNumber = result.size + 1
                )
            )
        }

        return result.mapIndexed { index, item ->
            item.copy(versionNumber = index + 1)
        }
    }

    private fun createHistoryCard(
        activity: Context,
        header: String,
        body: String,
        headerColor: Int,
        dp: (Int) -> Int
    ): View {
        val itemBox = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(12), dp(14), dp(12))
            background = GradientDrawable().apply {
                setColor(0x18888888)
                cornerRadius = dp(12).toFloat()
            }
            val lp = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                bottomMargin = dp(10)
            }
            layoutParams = lp
        }

        val headerView = TextView(activity).apply {
            text = header
            textSize = 12.5f
            setTypeface(null, Typeface.BOLD)
            setTextColor(headerColor)
        }
        itemBox.addView(headerView)

        val bodyView = TextView(activity).apply {
            id = R.id.text1
            text = body
            textSize = 15f
            setTextIsSelectable(true)
            setPadding(0, dp(6), 0, dp(2))
        }
        itemBox.addView(bodyView)

        return itemBox
    }

    // ─── Text Diff Highlighting Logic ──────────────────────────────────────────

    private enum class DiffType { UNCHANGED, ADDED, REMOVED }
    private data class DiffChunk(val type: DiffType, val text: String)

    private fun buildDiffSpannable(oldStr: String, newStr: String): CharSequence {
        val chunks = computeDiff(oldStr, newStr)
        val ssb = SpannableStringBuilder()
        for (c in chunks) {
            val start = ssb.length
            ssb.append(c.text)
            val end = ssb.length
            when (c.type) {
                DiffType.UNCHANGED -> {}
                DiffType.ADDED -> {
                    ssb.setSpan(ForegroundColorSpan(0xFF21C063.toInt()), start, end, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE)
                    ssb.setSpan(BackgroundColorSpan(0x3321C063.toInt()), start, end, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE)
                }
                DiffType.REMOVED -> {
                    ssb.setSpan(ForegroundColorSpan(0xFFEF4444.toInt()), start, end, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE)
                    ssb.setSpan(BackgroundColorSpan(0x33EF4444.toInt()), start, end, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE)
                    ssb.setSpan(StrikethroughSpan(), start, end, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE)
                }
            }
        }
        return ssb
    }

    private fun computeDiff(oldStr: String, newStr: String): List<DiffChunk> {
        val oldChars = oldStr.toCharArray()
        val newChars = newStr.toCharArray()
        val n = oldChars.size
        val m = newChars.size

        if (n > 300 || m > 300) {
            return computeWordDiff(oldStr, newStr)
        }

        val dp = Array(n + 1) { IntArray(m + 1) }
        for (i in 0 until n) {
            for (j in 0 until m) {
                if (oldChars[i] == newChars[j]) {
                    dp[i + 1][j + 1] = dp[i][j] + 1
                } else {
                    dp[i + 1][j + 1] = maxOf(dp[i + 1][j], dp[i][j + 1])
                }
            }
        }

        var i = n
        var j = m
        val resultReversed = mutableListOf<DiffChunk>()
        while (i > 0 || j > 0) {
            if (i > 0 && j > 0 && oldChars[i - 1] == newChars[j - 1]) {
                resultReversed.add(DiffChunk(DiffType.UNCHANGED, oldChars[i - 1].toString()))
                i--
                j--
            } else if (j > 0 && (i == 0 || dp[i][j - 1] >= dp[i - 1][j])) {
                resultReversed.add(DiffChunk(DiffType.ADDED, newChars[j - 1].toString()))
                j--
            } else if (i > 0 && (j == 0 || dp[i][j - 1] < dp[i - 1][j])) {
                resultReversed.add(DiffChunk(DiffType.REMOVED, oldChars[i - 1].toString()))
                i--
            }
        }
        val reversed = resultReversed.reversed()
        val merged = mutableListOf<DiffChunk>()
        for (chunk in reversed) {
            if (merged.isNotEmpty() && merged.last().type == chunk.type) {
                val last = merged.removeAt(merged.size - 1)
                merged.add(DiffChunk(last.type, last.text + chunk.text))
            } else {
                merged.add(chunk)
            }
        }
        return merged
    }

    private fun computeWordDiff(oldStr: String, newStr: String): List<DiffChunk> {
        val oldWords = oldStr.split(Regex("(?<=\\s)|(?=\\s)"))
        val newWords = newStr.split(Regex("(?<=\\s)|(?=\\s)"))
        val n = oldWords.size
        val m = newWords.size
        val dp = Array(n + 1) { IntArray(m + 1) }
        for (i in 0 until n) {
            for (j in 0 until m) {
                if (oldWords[i] == newWords[j]) {
                    dp[i + 1][j + 1] = dp[i][j] + 1
                } else {
                    dp[i + 1][j + 1] = maxOf(dp[i + 1][j], dp[i][j + 1])
                }
            }
        }
        var i = n
        var j = m
        val resultReversed = mutableListOf<DiffChunk>()
        while (i > 0 || j > 0) {
            if (i > 0 && j > 0 && oldWords[i - 1] == newWords[j - 1]) {
                resultReversed.add(DiffChunk(DiffType.UNCHANGED, oldWords[i - 1]))
                i--
                j--
            } else if (j > 0 && (i == 0 || dp[i][j - 1] >= dp[i - 1][j])) {
                resultReversed.add(DiffChunk(DiffType.ADDED, newWords[j - 1]))
                j--
            } else if (i > 0 && (j == 0 || dp[i][j - 1] < dp[i - 1][j])) {
                resultReversed.add(DiffChunk(DiffType.REMOVED, oldWords[i - 1]))
                i--
            }
        }
        val reversed = resultReversed.reversed()
        val merged = mutableListOf<DiffChunk>()
        for (chunk in reversed) {
            if (merged.isNotEmpty() && merged.last().type == chunk.type) {
                val last = merged.removeAt(merged.size - 1)
                merged.add(DiffChunk(last.type, last.text + chunk.text))
            } else {
                merged.add(chunk)
            }
        }
        return merged
    }

    private fun createWdsSwitch(ctx: Context): CompoundButton {
        return try {
            val clazz = ctx.classLoader.loadClass("com.whatsapp.ui.wds.components.toggle.WDSSwitch")
            clazz.getConstructor(Context::class.java, AttributeSet::class.java).newInstance(ctx, null) as CompoundButton
        } catch (t: Throwable) {
            try {
                val materialSwitchClass = ctx.classLoader.loadClass("com.google.android.material.materialswitch.MaterialSwitch")
                materialSwitchClass.getConstructor(Context::class.java).newInstance(ctx) as CompoundButton
            } catch (t2: Throwable) {
                Switch(ctx)
            }
        }
    }

    // ─── Multi-Level Key & Row ID Extraction ───────────────────────────────────

    private fun extractStableKeyId(messageObj: Any): String? {
        val resolver = originalKeyMethod
        if (resolver != null) {
            try {
                resolver.isAccessible = true
                val originalKey = when {
                    Modifier.isStatic(resolver.modifiers) && resolver.parameterCount == 1 ->
                        resolver.invoke(null, messageObj)
                    !Modifier.isStatic(resolver.modifiers) && resolver.parameterCount == 0 &&
                        resolver.declaringClass.isInstance(messageObj) -> resolver.invoke(messageObj)
                    else -> null
                }
                if (originalKey != null) {
                    extractMessageIdFromKey(originalKey)?.let { return it }
                }
            } catch (_: Throwable) {
            }
        }
        return extractKeyId(messageObj)
    }

    private fun extractKeyId(messageObj: Any): String? {
        try {
            var curr: Class<*>? = messageObj.javaClass
            while (curr != null && curr != Any::class.java) {
                for (field in curr.declaredFields) {
                    field.isAccessible = true
                    val valObj = field.get(messageObj) ?: continue
                    val valClass = valObj.javaClass
                    val representation = valObj.toString()

                    // JID/contact objects also contain an "id" in toString(). Only inspect
                    // objects whose type represents a message key, otherwise every message in
                    // one chat can accidentally receive the same contact ID.
                    if (valClass.name.contains("Key", ignoreCase = true)
                        || valClass.simpleName.contains("Key", ignoreCase = true)
                        || representation.startsWith("Key(")
                        || looksLikeMessageKey(valClass)) {
                        val directId = extractMessageIdFromKey(valObj)
                        if (!directId.isNullOrEmpty()) return directId
                        val matcher = KEY_ID_REGEX.matcher(representation)
                        if (matcher.find()) {
                            val id = matcher.group(1)
                            if (!id.isNullOrEmpty()) return id
                        }
                    }
                }
                curr = curr.superclass
            }

            if (looksLikeMessageKey(messageObj.javaClass)) {
                extractMessageIdFromKey(messageObj)?.let { return it }
            }

            val objStr = messageObj.toString()
            val matcher = Pattern.compile("(?:messageId|messageID|keyId)=([A-Za-z0-9_-]+)")
                .matcher(objStr)
            if (matcher.find()) {
                val id = matcher.group(1)
                if (!id.isNullOrEmpty()) return id
            }
        } catch (ignored: Throwable) {}
        return null
    }

    private fun looksLikeMessageKey(type: Class<*>): Boolean {
        var hasString = false
        var hasBoolean = false
        var current: Class<*>? = type
        while (current != null && current != Any::class.java) {
            for (field in current.declaredFields) {
                if (Modifier.isStatic(field.modifiers)) continue
                if (field.type == String::class.java) hasString = true
                if (field.type == Boolean::class.javaPrimitiveType || field.type == Boolean::class.java) {
                    hasBoolean = true
                }
            }
            current = current.superclass
        }
        return hasString && hasBoolean
    }

    private fun extractMessageIdFromKey(keyObj: Any): String? {
        try {
            var bestCandidate: String? = null
            var curr: Class<*>? = keyObj.javaClass
            while (curr != null && curr != Any::class.java) {
                for (field in curr.declaredFields) {
                    if (field.type != String::class.java) continue
                    field.isAccessible = true
                    val str = field.get(keyObj) as? String ?: continue
                    if (str.isEmpty() || str.contains("@")) continue
                    if (str.length >= 12) return str
                    if (str.length >= 6 && bestCandidate == null) bestCandidate = str
                }
                curr = curr.superclass
            }
            return bestCandidate
        } catch (ignored: Throwable) {}
        return null
    }

    private fun extractRowId(messageObj: Any): Long {
        try {
            var curr: Class<*>? = messageObj.javaClass
            while (curr != null && curr != Any::class.java) {
                for (field in curr.declaredFields) {
                    field.isAccessible = true
                    if (field.name == "A0j" || field.name == "A0k" || field.name == "rowId" || field.name == "A00" || field.name == "A01" || field.name == "_id") {
                        val v = field.get(messageObj)
                        if (v is Long && v > 0) return v
                        if (v is Int && v > 0) return v.toLong()
                    }
                }
                curr = curr.superclass
            }
        } catch (ignored: Throwable) {}
        return 0L
    }

    private fun resolveCanonicalRowId(reflectedRowId: Long, keyId: String?): Long {
        if (!keyId.isNullOrBlank()) {
            val databaseRowId = MessageStore.getInstance(context).getIdFromKey(keyId)
            if (databaseRowId > 0) return databaseRowId
        }
        return reflectedRowId
    }

    private fun extractMessageText(messageObj: Any): String? {
        try {
            var curr: Class<*>? = messageObj.javaClass
            while (curr != null && curr != Any::class.java) {
                for (field in curr.declaredFields) {
                    if (field.name == "A0Q" || field.name == "textData" || field.name == "A02" || field.name == "message") {
                        field.isAccessible = true
                        val str = field.get(messageObj) as? String
                        if (!str.isNullOrEmpty()) return str
                    }
                }
                curr = curr.superclass
            }

            for (m in messageObj.javaClass.methods) {
                if (m.returnType == String::class.java && m.parameterCount == 0 &&
                    m.name != "toString" && m.name != "hashCode" && m.name != "name"
                ) {
                    val str = m.invoke(messageObj) as? String
                    if (!str.isNullOrEmpty() && !str.contains("@") && str.length < 5000) return str
                }
            }
        } catch (ignored: Throwable) {}
        return null
    }

    private fun extractTextFromMessageBubble(row: View?): String? {
        if (row !is ViewGroup) return null
        val messageTextView = findChildByResourceName(row, "message_text")
            ?: findChildByResourceName(row, "conversation_text")
            ?: findChildByResourceName(row, "caption")
        return (messageTextView as? TextView)?.text?.toString()
    }

    private fun findChildByResourceName(viewGroup: ViewGroup, targetResName: String): View? {
        for (i in 0 until viewGroup.childCount) {
            val child = viewGroup.getChildAt(i)
            if (getResourceEntryName(child) == targetResName) return child
            if (child is ViewGroup) {
                val found = findChildByResourceName(child, targetResName)
                if (found != null) return found
            }
        }
        return null
    }

    private fun findParentMessageRow(view: View): View? {
        var current: View? = view
        while (current != null) {
            val resName = getResourceEntryName(current)
            if (resName == "conversation_row" || resName == "message_row" || resName == "row_message" || current.parent is ListView) {
                return current
            }
            current = current.parent as? View
        }
        return null
    }

    private fun getResourceEntryName(view: View): String? {
        val id = view.id
        if (id == View.NO_ID) return null
        return try {
            view.resources.getResourceEntryName(id)
        } catch (t: Throwable) {
            null
        }
    }
}
