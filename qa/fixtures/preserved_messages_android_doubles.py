"""Explicit platform/Xposed/DexKit doubles; SQL is executed by the Python SQLite bridge."""

JAVA = {
    'Cursor.java': r'''package android.database;
import java.io.Closeable;
public final class Cursor implements Closeable {
 private final String[] columns; private final Object[][] rows; private int position=-1;
 public Cursor(String[] columns,Object[][] rows){this.columns=columns;this.rows=rows;}
 public int getColumnCount(){return columns.length;}
 public int getColumnIndex(String name){for(int i=0;i<columns.length;i++)if(columns[i].equals(name))return i;return -1;}
 public boolean moveToFirst(){position=0;return rows.length>0;}
 public boolean moveToNext(){position++;return position<rows.length;}
 public String getString(int index){Object value=rows[position][index];return value==null?null:value.toString();}
 public long getLong(int index){String value=getString(index);return value==null?0:Long.parseLong(value);}
 public int getInt(int index){return (int)getLong(index);}
 public void close(){}
}''',
}

KOTLIN = {
    'Context.kt': r'''package android.content
import android.net.Uri
import android.os.Bundle
import java.io.File
open class Context(val root:File) {
 val applicationContext:Context get()=this
 val filesDir=File(root,"files").apply{mkdirs()}
 val contentResolver=ContentResolver()
 fun getDatabasePath(name:String)=File(File(root,"databases").apply{mkdirs()},name)
}
interface SharedPreferences {fun getBoolean(key:String,default:Boolean):Boolean}
class ContentValues {val values=linkedMapOf<String,Any?>();fun put(k:String,v:String?){values[k]=v};fun put(k:String,v:Int){values[k]=v};fun put(k:String,v:Long){values[k]=v}}
class ContentResolver {
 val calls=mutableListOf<Bundle>();var fail=false;var consumer:((Bundle)->Unit)?=null
 fun call(uri:Uri,method:String,arg:String?,bundle:Bundle):Bundle?{
  if(fail)throw IllegalStateException("controlled provider failure")
  check(uri.text=="content://com.waenhancer.hookprovider");check(method=="record_preserved_message")
  calls.add(bundle);consumer?.invoke(bundle);return Bundle()
 }
}
''',
    'Bundle.kt': r'''package android.os
class Bundle {val values=linkedMapOf<String,Any?>();fun putString(k:String,v:String?){values[k]=v};fun putLong(k:String,v:Long){values[k]=v};fun putBoolean(k:String,v:Boolean){values[k]=v};fun getString(k:String)=values[k] as? String;fun getLong(k:String)=values[k] as? Long?:0L;fun getBoolean(k:String)=values[k] as? Boolean?:false}
''',
    'Uri.kt': r'''package android.net
class Uri private constructor(val text:String){companion object {fun parse(text:String)=Uri(text)}}
''',
    'SQLite.kt': r'''package android.database.sqlite
import android.content.*
import android.database.Cursor
import java.io.Closeable
import java.util.Base64
class SQLiteDatabase(val path:String):Closeable {
 private val process=ProcessBuilder(System.getenv("WAEX_SQL_PYTHON"),System.getenv("WAEX_SQL_BRIDGE"),"--sqlite-bridge",path).start()
 private val input=process.inputStream.bufferedReader()
 private val output=process.outputStream.bufferedWriter()
 var queries=0;var closed=false
 private data class Reply(val last:Long,val changed:Int,val cursor:Cursor)
 private fun encode(value:Any?):String=when(value){null->"n";is Number->"i$value";else->"s"+Base64.getEncoder().encodeToString(value.toString().toByteArray(Charsets.UTF_8))}
 private fun decode(value:String):Any?=when(value.first()){'n'->null;'i'->value.drop(1).toLong();else->String(Base64.getDecoder().decode(value.drop(1)),Charsets.UTF_8)}
 @Synchronized private fun request(kind:String,sql:String,args:List<Any?> = emptyList()):Reply {
  check(!closed)
  val failThis=failSqlOnce?.let{sql.contains(it)}==true
  if(failThis)failSqlOnce=null
  val encoded=Base64.getEncoder().encodeToString(sql.toByteArray(Charsets.UTF_8))
  output.write((listOf(if(failThis)"f" else kind,encoded)+args.map(::encode)).joinToString("\t"));output.newLine();output.flush()
  val line=input.readLine()?:error("SQLite worker ended: "+process.errorStream.bufferedReader().readText())
  val parts=line.split('\t');check(parts[0]=="OK"){"SQLite bridge: "+String(Base64.getDecoder().decode(parts[1]))}
  val columns=parts[3].toInt();val rows=parts[4].toInt();var offset=5
  val names=Array(columns){decode(parts[offset++]) as String}
  val data=Array(rows){Array<Any?>(columns){decode(parts[offset++])}}
  return Reply(parts[1].toLong(),parts[2].toInt(),Cursor(names,data))
 }
 fun rawQuery(sql:String,args:Array<String>?):Cursor{queries++;return request("q",sql,args?.toList().orEmpty()).cursor}
 fun execSQL(sql:String){request("e",sql)}
 fun insertWithOnConflict(table:String,hack:String?,values:ContentValues,conflict:Int):Long {
  check(conflict==CONFLICT_REPLACE)
  return request("e","INSERT OR REPLACE INTO $table (${values.values.keys.joinToString(",")}) VALUES (${values.values.keys.joinToString(","){"?"}})",values.values.values.toList()).last
 }
 fun update(table:String,values:ContentValues,where:String,args:Array<String>):Int=request("e","UPDATE $table SET ${values.values.keys.joinToString(","){"$it = ?"}} WHERE $where",values.values.values.toList()+args.toList()).changed
 fun query(table:String,columns:Array<String>,selection:String?,args:Array<String>?,group:String?,having:String?,order:String?):Cursor = rawQuery("SELECT ${columns.joinToString(",")} FROM $table"+(selection?.let{" WHERE $it"}?:"")+(order?.let{" ORDER BY $it"}?:""),args)
 fun delete(table:String,where:String,args:Array<String>):Int=request("e","DELETE FROM $table WHERE $where",args.toList()).changed
 override fun close(){if(!closed){closed=true;output.close();check(process.waitFor()==0){process.errorStream.bufferedReader().readText()};input.close()}}
 companion object {
  const val OPEN_READONLY=1;const val CONFLICT_REPLACE=5
  var failSqlOnce:String?=null
  fun openDatabase(path:String,factory:Any?,flags:Int)=SQLiteDatabase(path)
 }
}
abstract class SQLiteOpenHelper(val context:Context,val name:String,factory:Any?,val version:Int) {
 private var opened:SQLiteDatabase?=null
 val writableDatabase:SQLiteDatabase get(){
  opened?.let{return it}
  val db=SQLiteDatabase(context.getDatabasePath(name).absolutePath)
  val old=db.rawQuery("PRAGMA user_version",null).use{it.moveToFirst();it.getInt(0)}
  if(old!=version){
   db.execSQL("BEGIN IMMEDIATE")
   try{if(old==0)onCreate(db) else if(old<version)onUpgrade(db,old,version) else error("downgrade refused");db.execSQL("PRAGMA user_version = $version");db.execSQL("COMMIT")}
   catch(failure:Throwable){db.execSQL("ROLLBACK");db.close();throw failure}
  }
  opened=db;return db
 }
 val readableDatabase:SQLiteDatabase get()=writableDatabase
 abstract fun onCreate(db:SQLiteDatabase)
 abstract fun onUpgrade(db:SQLiteDatabase,oldVersion:Int,newVersion:Int)
 fun close(){opened?.close();opened=null}
}
''',
    'BaseFeature.kt': r'''package com.waenhancer.xposed.core
import android.content.*
abstract class BaseFeature(protected val context:Context,protected val classLoader:ClassLoader,protected val prefs:SharedPreferences){abstract val name:String;abstract fun hook();fun isEnabled(key:String,default:Boolean)=prefs.getBoolean(key,default)}
''',
    'Names.kt': r'''package com.waenhancer.utils
import android.content.Context
object ContactNameResolver {val requests=mutableListOf<String>();@JvmStatic fun resolveName(context:Context,jid:String,first:Any?,second:Any?):String{requests.add(jid);return "Name($jid)"}}
''',
    'Xposed.kt': r'''package de.robv.android.xposed
import java.lang.reflect.Member
open class XC_MethodHook {
 class MethodHookParam(var thisObject:Any?,var args:Array<Any?> = emptyArray()){
  val extras=mutableMapOf<String,Any?>();var result:Any?=null;var throwable:Throwable?=null
  fun setObjectExtra(key:String,value:Any?){extras[key]=value};fun getObjectExtra(key:String)=extras[key]
 }
 protected open fun beforeHookedMethod(param:MethodHookParam){}
 protected open fun afterHookedMethod(param:MethodHookParam){}
 fun before(param:MethodHookParam)=beforeHookedMethod(param)
 fun after(param:MethodHookParam)=afterHookedMethod(param)
}
object XposedBridge {
 val methodHooks=mutableListOf<Pair<Member,XC_MethodHook>>();val databaseHooks=mutableListOf<XC_MethodHook>();val logs=mutableListOf<String>()
 @JvmStatic fun hookMethod(method:Member,hook:XC_MethodHook){methodHooks.add(method to hook)}
 @JvmStatic fun hookAllMethods(type:Class<*>,name:String,hook:XC_MethodHook){check(type.name=="android.database.sqlite.SQLiteDatabase"&&name=="delete");databaseHooks.add(hook)}
 @JvmStatic fun log(text:String){logs.add(text)}
}
''',
    'DexSearchEngine.kt': r'''package com.waenhancer.xposed.core.devkit
import android.content.Context
import java.lang.reflect.Method
import org.luckypray.dexkit.DexKitBridge
class DexSearchEngine {fun findMethodWithCache(context:Context,loader:ClassLoader,key:String,lookup:(DexKitBridge,ClassLoader)->Method?):Method?{
 keys.add(key)
 return if(key.contains("collection_action")) {val bridge=lookupBridge;if(bridge!=null)lookup(bridge,loader) else dedicated} else selected
 }
 companion object {var selected:Method?=null;var dedicated:Method?=null;var lookupBridge:DexKitBridge?=null;val keys=mutableListOf<String>();private val instance=DexSearchEngine();@JvmStatic fun getInstance()=instance}}
''',
    'DexKitBridgeDouble.kt': r'''package org.luckypray.dexkit
import org.luckypray.dexkit.query.FindMethod
import org.luckypray.dexkit.result.MethodData
class DexKitBridge(val candidates:List<MethodData> = emptyList()) {val queries=mutableListOf<FindMethod>();fun findMethod(query:FindMethod):List<MethodData>{queries.add(query);return candidates.filter{candidate->query.value.strings.all{(text,type)->candidate.literals.any{if(type.name=="Equals")it==text else it.contains(text)}}}}}
''',
    'DexKitResultDouble.kt': r'''package org.luckypray.dexkit.result
import java.lang.reflect.Method
class ClassData(val name:String="",val methods:List<MethodData> = emptyList(),val interfaces:List<ClassData> = emptyList())
class MethodData(val name:String="",val paramTypeNames:List<String> = emptyList(),val declaredClass:ClassData?=null,val invokes:List<MethodData> = emptyList(),val isConstructor:Boolean=false,val returnTypeName:String="void",val reflected:Method?=null,val literals:List<String> = emptyList()) {val paramCount:Int get()=paramTypeNames.size;fun getMethodInstance(loader:ClassLoader):Method=reflected?:error("unexecuted native selector")}
''',
    'DexKitFindDouble.kt': r'''package org.luckypray.dexkit.query
import org.luckypray.dexkit.query.matchers.MethodMatcher
class FindMethod {lateinit var value:MethodMatcher;fun matcher(value:MethodMatcher)=apply{this.value=value};companion object{fun create()=FindMethod()}}
''',
    'DexKitMatcherDouble.kt': r'''package org.luckypray.dexkit.query.matchers
import org.luckypray.dexkit.query.enums.StringMatchType
class MethodMatcher {val strings=mutableListOf<Pair<String,StringMatchType>>();fun addUsingString(text:String,type:StringMatchType)=apply{strings.add(text to type)};companion object{fun create()=MethodMatcher()}}
''',
    'DexKitMatchTypeDouble.kt': r'''package org.luckypray.dexkit.query.enums
enum class StringMatchType {Contains,Equals}
''',
    'HostJid.kt': r'''package com.whatsapp.infra.core.jid
open class Jid(private val text:String){override fun toString()=text}
''',
}
