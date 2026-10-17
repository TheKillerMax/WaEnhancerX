#!/usr/bin/env python3
"""Compile the full forwarding hook with explicit Xposed/Android doubles.
Guards the remaining score-only store path; no host transport or visual effect is certified.
"""
from pathlib import Path
import subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'app/src/main/java/com/waenhancer'
STUBS={
'Android.kt':'''package android.content
open class Context
interface SharedPreferences{fun contains(k:String):Boolean;fun getBoolean(k:String,d:Boolean):Boolean}
class ContentValues {val values=mutableMapOf<String,Any?>();fun put(k:String,v:Int){values[k]=v};fun get(k:String):Any?=values[k]}
''',
'Db.kt':'''package android.database.sqlite
class SQLiteDatabase
''',
'Base.kt':'''package com.waenhancer.xposed.core
import android.content.*
abstract class BaseFeature(val context:Context,val classLoader:ClassLoader,val prefs:SharedPreferences){abstract val name:String;abstract fun hook()}
''',
'Xposed.kt':'''package de.robv.android.xposed
open class XC_MethodHook{
 class MethodHookParam(val args:Array<Any?>)
 protected open fun beforeHookedMethod(param:MethodHookParam){}
 fun invoke(param:MethodHookParam){beforeHookedMethod(param)}
}
object XposedBridge{fun log(message:String){}}
object XposedHelpers{val hooks=mutableListOf<Pair<String,XC_MethodHook>>()
 fun findAndHookMethod(type:Class<*>,name:String,vararg args:Any?){check(type.name=="android.database.sqlite.SQLiteDatabase");hooks.add(name to (args.last() as XC_MethodHook))}}
''',
'Test.kt':'''package com.waenhancer.xposed.features.privacy
import android.content.*
import de.robv.android.xposed.*
class Prefs:SharedPreferences{val values=mutableMapOf<String,Any?>();override fun contains(k:String)=values.containsKey(k)
 override fun getBoolean(k:String,d:Boolean):Boolean=if(!contains(k))d else values[k] as Boolean}
fun main(){val p=Prefs();HideForwardedTagHook(Context(),Prefs::class.java.classLoader,p).hook();var n=0
 fun ck(label:String,value:Boolean){check(value){"ASSERTION|$label"};n++}
 ck("only database callbacks",XposedHelpers.hooks.map{it.first}==listOf("insertWithOnConflict","insert","insertOrThrow"))
 for((name,hook) in XposedHelpers.hooks){
  fun apply(table:String,score:Any?,origin:Any?,present:Boolean=true):ContentValues{
   val cv=ContentValues();if(present)cv.values["forward_score"]=score;cv.values["forward_origin"]=origin;cv.values["transport_flags"]=33554432L
   hook.invoke(XC_MethodHook.MethodHookParam(arrayOf(table,null,cv,0)))
   ck("origin unchanged $name",cv.values["forward_origin"]==origin);ck("transport flags unchanged $name",cv.values["transport_flags"]==33554432L);return cv}
  p.values.clear();ck("disabled",apply("message_forwarded",2,9).values["forward_score"]==2)
  p.values["hidetag"]=true;ck("legacy opt-in",apply("message_forwarded",2,9).values["forward_score"]==0)
  p.values["hide_forwarded_tag"]=false;ck("explicit disable wins",apply("message_forwarded",2,9).values["forward_score"]==2)
  p.values["hide_forwarded_tag"]=true;ck("canonical enable",apply("message_forwarded",2,9).values["forward_score"]==0)
  ck("other table",apply("message",2,9).values["forward_score"]==2)
  ck("absent score",!apply("message_forwarded",null,9,false).values.containsKey("forward_score"))
  for(score in listOf<Any?>(null,"2",2L,0,-1))ck("nonpositive/invalid score",apply("message_forwarded",score,9).values["forward_score"]==score)
  p.values["hide_forwarded_tag"]="true";ck("corrupt setting is not implicit permission",apply("message_forwarded",2,9).values["forward_score"]==2)
 }
 println("PASS: $n forwarding-store checks; no flag setter or origin write")
}
'''
}
def main():
 source=SRC/'xposed/features/privacy/HideForwardedTagHook.kt';text=source.read_text()
 for removed in ('FMessage_setForwardScore','hookForwardScoreSetter()', 'chatInfo/incrementUnseenImportantMessageCount','values.put("forward_origin"'):
  assert removed not in text,removed
 with tempfile.TemporaryDirectory(prefix='waex-forward-') as t:
  d=Path(t)
  for p,c in STUBS.items():(d/p).write_text(c)
  subprocess.run(['kotlinc','-jvm-target','17',str(source),*map(str,d.glob('*.kt')),'-include-runtime','-d',str(d/'test.jar')],check=True,timeout=90)
  print('COMPILE_OK: full hook with explicit Xposed adapters', flush=True)
  subprocess.run(['java','-jar',str(d/'test.jar')],check=True,timeout=60)
if __name__=='__main__':main()
