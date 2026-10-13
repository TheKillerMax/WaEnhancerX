#!/usr/bin/env python3
"""Compile real Kotlin SettingsBackupCodec and round-trip every exportable preference.

The tests use small Android and org.json compile stubs; no native APK, SDK,
private licensing code, network, or actual Android device is involved.
Requires JDK17+, kotlinc and the Kotlin runner on PATH.
"""
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'app/src/main/java/com/waenhancer'
STUBS = {
    'android/content/Context.java': '''package android.content;
public abstract class Context {
 public static final int MODE_PRIVATE = 0;
 public abstract SharedPreferences getSharedPreferences(String name, int mode);
}''',
    'android/content/SharedPreferences.java': '''package android.content;
import java.util.Map; import java.util.Set;
public interface SharedPreferences {
 Map<String, ?> getAll(); Editor edit();
 interface Editor {
  Editor putBoolean(String key, boolean value);
  Editor putString(String key, String value);
  Editor putStringSet(String key, Set<String> value);
  Editor putInt(String key, int value);
  Editor putLong(String key, long value);
  Editor putFloat(String key, float value);
  boolean commit();
 }
}''',
    'android/content/TestContext.java': '''package android.content;
import java.util.*;
public final class TestContext extends Context {
 private final Map<String,Prefs> stores = new HashMap<>();
 public TestContext(){stores.put("waex_prefs",new Prefs());stores.put("private_config",new Prefs());}
 @Override public SharedPreferences getSharedPreferences(String name,int mode){return stores.computeIfAbsent(name,k->new Prefs());}
 public void seed(String store,String key,Object v){stores.get(store).data.put(key,v);}
 public Object get(String store,String key){return stores.get(store).data.get(key);}
 public int count(){return stores.get("waex_prefs").data.size()+stores.get("private_config").data.size();}
 static final class Prefs implements SharedPreferences {
  final Map<String,Object> data = new HashMap<>();
  @Override public Map<String,?> getAll(){return new HashMap<>(data);}
  @Override public Editor edit(){return new E();}
  private final class E implements Editor {
   final Map<String,Object> edits = new HashMap<>();
   public Editor putBoolean(String k,boolean v){edits.put(k,v);return this;}
   public Editor putString(String k,String v){edits.put(k,v);return this;}
   public Editor putStringSet(String k,Set<String> v){edits.put(k,new HashSet<>(v));return this;}
   public Editor putInt(String k,int v){edits.put(k,v);return this;}
   public Editor putLong(String k,long v){edits.put(k,v);return this;}
   public Editor putFloat(String k,float v){edits.put(k,v);return this;}
   public boolean commit(){data.putAll(edits);return true;}
  }
 }
}''',
    'org/json/JSONException.java': '''package org.json;
public final class JSONException extends RuntimeException {
 public JSONException(String text){super(text);}
}''',
    'org/json/JSONArray.java': '''package org.json;
public final class JSONArray {
 public int length(){return 0;}
 public String optString(int i){return "";}
}''',
    'org/json/JSONObject.java': '''package org.json;
import java.util.Collections; import java.util.Iterator;
public final class JSONObject {
 public JSONObject(String src){throw new JSONException("JSON is outside the binary fixture");}
 public boolean has(String key){return false;}
 public JSONObject optJSONObject(String key){return null;}
 public Object opt(String key){return null;}
 public String optString(String key,String fallback){return fallback;}
 public Iterator<String> keys(){return Collections.emptyIterator();}
}''',
}
KOTLIN_TEST = '''package com.waenhancer.core.preferences
import android.content.TestContext
import com.waenhancer.config.PreferenceSchema
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream

private fun store(e: PreferenceSchema.Entry) = if(e.store == PreferenceSchema.Store.PRIVATE) "private_config" else "waex_prefs"
private fun sample(e: PreferenceSchema.Entry,i:Int): Any = when(e.type){
 PreferenceSchema.Type.BOOLEAN -> i%2==0
 PreferenceSchema.Type.STRING -> "text_"+i
 PreferenceSchema.Type.STRING_SET -> setOf("key_"+i,"second_"+i)
 PreferenceSchema.Type.INT -> 1000+i
 PreferenceSchema.Type.LONG -> 5000000000L+i
 PreferenceSchema.Type.FLOAT -> i+0.25f
}
fun main(){
 // Reflect the actual private codec resolver rather than emulating migrations.
 val resolveMethod=SettingsBackupCodec::class.java.declaredMethods.single {
   it.name == "resolveKey" && it.parameterCount == 2
 }
 resolveMethod.isAccessible = true
 fun resolve(raw:String,legacy:Boolean):String? =
   resolveMethod.invoke(SettingsBackupCodec,raw,legacy) as String?
 val currentKeys=listOf(
   "typing_online_toasts", "typing_privacy", "hide_seen_receipts", "hidereceipt",
   "hide_delivery_receipts", "hide_read_receipts", "stealth_status_view",
   "separate_groups_tabs", "bubble_colors", "channels_enhancements", "anti_revoke"
 )
 for(key in currentKeys) {
   check(PreferenceSchema.entry(key)!=null){"Missing current schema key: $key"}
   check(resolve(key,true)==key){"Legacy JSON redirected a live preference: $key"}
   check(resolve(key,false)==key){"Versioned/binary backup redirected a live key: $key"}
 }
 val trueLegacy=mapOf(
   "custom_theme" to "custom_css",
   "custom_time_format" to "segundos",
   "custom_view_dpi" to "change_dpi",
   "hide_ui_tabs" to "hidetabs",
   "chat_filters" to "chatfilter",
   "quick_home_menu" to "show_home_menu"
 )
 for((raw,mapped) in trueLegacy) {
   check(PreferenceSchema.entry(raw)==null){"Expected historical unknown alias: $raw"}
   check(resolve(raw,true)==mapped){"Old JSON alias not migrated: $raw"}
   check(resolve(raw,false)==null){"Unknown key accepted by versioned/binary backup: $raw"}
 }
 check(resolve("a_totally_unknown_setting",true)==null)
 check(resolve("a_totally_unknown_setting",false)==null)
 println("PASS: live Boolean privacy settings retained in legacy JSON; unknown old aliases migrated safely")
 val initial=TestContext()
 val expected=LinkedHashMap<String,Any>()
 PreferenceSchema.exportableKeys().sorted().forEachIndexed { i,key ->
  val schema=PreferenceSchema.entry(key)!!
  val value=sample(schema,i)
  initial.seed(store(schema),key,value)
  expected[key]=value
 }
 val bytes=ByteArrayOutputStream()
 val written=SettingsBackupCodec.encode(initial,bytes)
 check(written==expected.size){"not all settings exported"}
 val restored=TestContext()
 val count=SettingsBackupCodec.decode(restored, ByteArrayInputStream(bytes.toByteArray()))
 check(count==written){"current binary keys silently rewritten/dropped: $count/$written"}
 expected.forEach { (key,value) ->
  val schema=PreferenceSchema.entry(key)!!
  check(restored.get(store(schema),key)==value){"wrong restored key/type/value: $key"}
 }
 check(restored.count()==expected.size){"colliding aliases altered restored key count"}
 // Older WAEX Privacy UI stored this INT preference as #RRGGBB / #AARRGGBB.
 val legacyRgb=TestContext()
 legacyRgb.seed("waex_prefs", "deleted_message_color", "#335577")
 val legacyBytes=ByteArrayOutputStream()
 check(SettingsBackupCodec.encode(legacyRgb,legacyBytes)==1){"RGB color lost from binary backup"}
 val migratedRgb=TestContext()
 check(SettingsBackupCodec.decode(migratedRgb,ByteArrayInputStream(legacyBytes.toByteArray()))==1)
 check(migratedRgb.get("waex_prefs","deleted_message_color")==0xFF335577.toInt()){"RGB not converted to opaque ARGB"}
 val legacyArgb=TestContext()
 legacyArgb.seed("waex_prefs", "deleted_message_color", "#80223344")
 val alphaBytes=ByteArrayOutputStream()
 check(SettingsBackupCodec.encode(legacyArgb,alphaBytes)==1){"ARGB color lost from backup"}
 val migratedArgb=TestContext()
 check(SettingsBackupCodec.decode(migratedArgb,ByteArrayInputStream(alphaBytes.toByteArray()))==1)
 check(migratedArgb.get("waex_prefs","deleted_message_color")==0x80223344.toInt()){"ARGB transparency lost"}
 val invalidColor=TestContext()
 invalidColor.seed("waex_prefs","deleted_message_color","#XYZXYZ")
 check(SettingsBackupCodec.encode(invalidColor,ByteArrayOutputStream())==0){"Malformed color unexpectedly exported"}
 println("PASS: legacy RGB/ARGB colors restored using the INT preference schema")
 println("PASS: $written current settings preserved by key/type/value in binary round-trip")
}
'''

with tempfile.TemporaryDirectory(prefix='waex_backup_binary_') as workspace:
    root = Path(workspace)
    files = []
    for name, code in STUBS.items():
        path = root / 'sources' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code, encoding='utf-8')
        files.append(str(path))
    out_java, out_kotlin = root / 'java', root / 'kotlin'
    subprocess.run(['javac','--release','17','-d',str(out_java),*files,
                    str(SRC/'config/PreferenceSchema.java'),
                    str(SRC/'config/PreferenceStores.java')],check=True)
    test_kotlin=root/'TestBinaryRoundTrip.kt'
    test_kotlin.write_text(KOTLIN_TEST,encoding='utf-8')
    subprocess.run(['kotlinc','-jvm-target','17','-cp',str(out_java),'-d',str(out_kotlin),
                    str(SRC/'core/preferences/SettingsBackupCodec.kt'),str(test_kotlin)],check=True)
    subprocess.run(['kotlin','-cp',str(out_java)+':'+str(out_kotlin),
                    'com.waenhancer.core.preferences.TestBinaryRoundTripKt'],check=True)
