package com.waenhancer.fixture

import com.waenhancer.app.R

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.os.Looper
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import com.waenhancer.xposed.features.customization.FilterItemsHook
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.LooperMode

private class CountedView(c: Context) : View(c) {
    var idReads = 0
    override fun getId(): Int { idReads++; return super.getId() }
}
private class CountingPreferences(private val base: SharedPreferences) : SharedPreferences by base {
    var reads = 0
    override fun getString(key: String?, defValue: String?): String? { reads++; return base.getString(key, defValue) }
}
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
@LooperMode(LooperMode.Mode.PAUSED)
class StabilityFilterTest {
    private val context = object : ContextWrapper(RuntimeEnvironment.getApplication()) {
        override fun getPackageName() = resources.getResourcePackageName(R.id.fixture_target)
    }
    private fun invoke(hook: FilterItemsHook, method: String, types: Array<Class<*>> = emptyArray(), vararg args: Any) {
        hook.javaClass.getDeclaredMethod(method, *types).also { it.isAccessible = true }.invoke(hook, *args)
    }
    @Test fun emptyRulesDoNotVisitRealViews() {
        val prefs = context.getSharedPreferences("empty", 0).also { it.edit().clear().commit() }
        val hook = FilterItemsHook(context, context.classLoader, prefs)
        val view = CountedView(context)
        repeat(1000) { invoke(hook, "applyFiltersRecursively", arrayOf(View::class.java), view) }
        assertEquals(0, view.idReads)
    }
    @Test fun realJsonRulesAffectOnlyMatchingViews() {
        assertEquals(R.id.fixture_target, context.resources.getIdentifier("fixture_target", "id", context.packageName))
        val prefs = context.getSharedPreferences("matching", 0)
        assertTrue(prefs.edit().clear().putString("filter_items", "[{\"id\":\"fixture_target\",\"behavior\":\"gone\"}]").commit())
        val hook = FilterItemsHook(context, context.classLoader, prefs)
        invoke(hook, "reloadFilters")
        val root = LinearLayout(context)
        val target = View(context).apply { id = R.id.fixture_target }
        val other = View(context).apply { id = R.id.fixture_other }
        root.addView(target, ViewGroup.LayoutParams(32, 32)); root.addView(other, ViewGroup.LayoutParams(32, 32))
        invoke(hook, "applyFiltersRecursively", arrayOf(View::class.java), root)
        assertEquals(View.GONE, target.visibility)
        assertEquals(0, target.layoutParams.width)
        assertEquals(View.VISIBLE, other.visibility)
        assertEquals(32, other.layoutParams.width)
        // Hook installation and Pro decisions are not emulated or claimed by this test.
    }
    @Test fun realHandlerCoalescesReloadsAndPublishesImmutableSnapshot() {
        val base = context.getSharedPreferences("reload", 0)
        assertTrue(base.edit().clear().putString("filter_items", "fixture_target").commit())
        val prefs = CountingPreferences(base)
        val hook = FilterItemsHook(context, context.classLoader, prefs)
        repeat(1000) { invoke(hook, "scheduleReload") }
        assertEquals(0, prefs.reads)
        shadowOf(Looper.getMainLooper()).idle()
        assertEquals(1, prefs.reads)
        val field = hook.javaClass.getDeclaredField("targetMap").also { it.isAccessible = true }
        @Suppress("UNCHECKED_CAST") val snapshot = field.get(hook) as MutableMap<Int, Any>
        assertTrue(snapshot.containsKey(R.id.fixture_target))
        assertThrows(UnsupportedOperationException::class.java) { snapshot.clear() }
        assertTrue(base.edit().putString("filter_items", "fixture_other").commit())
        invoke(hook, "scheduleReload"); shadowOf(Looper.getMainLooper()).idle()
        assertEquals(2, prefs.reads)
        assertTrue(snapshot.containsKey(R.id.fixture_target))
        assertFalse(snapshot.containsKey(R.id.fixture_other))
        assertTrue((field.get(hook) as Map<*, *>).containsKey(R.id.fixture_other))
    }
}
