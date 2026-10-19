package com.waenhancer.xposed.features.conversation

import android.content.Context
import android.content.SharedPreferences
import android.database.sqlite.SQLiteDatabase
import com.waenhancer.xposed.core.db.PreservedMessageStore
import com.waenhancer.xposed.core.devkit.DexSearchEngine
import com.whatsapp.infra.core.jid.Jid
import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XposedBridge
import java.io.File

private var checks=0
private fun ck(label:String,actual:Any?,expected:Any?){check(actual==expected){"ASSERTION|$label actual=$actual expected=$expected"};checks++}
private class Prefs(var enabled:Boolean=true):SharedPreferences {override fun getBoolean(key:String,default:Boolean)=if(key=="preserve_delete_for_me")enabled else default}
private open class KeyBase(@JvmField val chat:Jid)
private class Key(chat:Jid,@JvmField val id:String,@JvmField val fromMe:Boolean):KeyBase(chat)
private class FlatKey(@JvmField val chat:Jid,@JvmField val id:String,@JvmField val fromMe:Boolean)
private class Message(@JvmField val key:FlatKey) {fun Atl():FlatKey=key}
private open class MessageBase(@JvmField val key:FlatKey)
private class InheritedMessage(key:FlatKey):MessageBase(key)
private class Conflicting(@JvmField val one:FlatKey,@JvmField val two:FlatKey)
private class UnknownJid {override fun toString()="22222@s.whatsapp.net"}
private class UnknownKey(@JvmField val chat:UnknownJid,@JvmField val id:String,@JvmField val fromMe:Boolean)
private class Envelope(@JvmField val chat:Jid,@JvmField val id:String,@JvmField val fromMe:Boolean,@JvmField val key:FlatKey)
private class StaticKey(@JvmField val key:FlatKey){companion object{@JvmField var other=FlatKey(Jid("11111@s.whatsapp.net"),"wrong",false)}}
private class StaticOnly {companion object{@JvmField var key=FlatKey(Jid("11111@s.whatsapp.net"),"wrong",false)}}
private class Task(@JvmField val selected:Set<Any>):Runnable {override fun run(){}}
private open class ParentTask(@JvmField val selected:Set<Any>):Runnable {override fun run(){}}
private class ChildTask(selected:Set<Any>):ParentTask(selected)
private class GlobalTask:Runnable {override fun run(){};companion object {@JvmField var selected:Set<Any> = emptySet()}}
private class DeleteMethods {fun deleteForMe(){}}
private class CollectionAction {
 fun deleteForMe(messages:Collection<Any>,first:Boolean,second:Boolean){}
 fun wrongSet(messages:Set<Any>,first:Boolean,second:Boolean){}
 fun wrongReturn(messages:Collection<Any>,first:Boolean,second:Boolean):Boolean=true
 fun wrongArity(messages:Collection<Any>,first:Boolean){}
 companion object {@JvmStatic fun staticAction(messages:Collection<Any>,first:Boolean,second:Boolean){}}
}

private fun context(root:File,name:String)=Context(File(root,name).apply{mkdirs()})
private fun store(ctx:Context):PreservedMessageStore=PreservedMessageStore::class.java.getDeclaredConstructor(Context::class.java).apply{isAccessible=true}.newInstance(ctx)
private fun rows(db:SQLiteDatabase,sql:String):List<List<String?>> = db.rawQuery(sql,null).use {cursor->
 val result=mutableListOf<List<String?>>()
 while(cursor.moveToNext())result.add((0 until cursor.columnCount).map(cursor::getString))
 result
}
private fun host(ctx:Context):SQLiteDatabase=SQLiteDatabase(ctx.getDatabasePath("msgstore.db").absolutePath).apply {
 execSQL("CREATE TABLE jid (_id INTEGER PRIMARY KEY, raw_string TEXT, user TEXT)")
 execSQL("CREATE TABLE chat (_id INTEGER PRIMARY KEY, jid_row_id INTEGER, subject TEXT)")
 execSQL("CREATE TABLE message (_id INTEGER PRIMARY KEY,key_id TEXT,chat_row_id INTEGER,from_me INTEGER,message_type INTEGER,text_data TEXT,timestamp INTEGER,sender_jid_row_id INTEGER)")
 execSQL("INSERT INTO jid VALUES (1,'11111@s.whatsapp.net','11111'),(2,'22222@s.whatsapp.net','22222'),(3,'22222@lid','22222'),(4,'99999-88888@g.us','99999-88888')")
 execSQL("INSERT INTO chat VALUES (11,1,NULL),(22,2,NULL),(33,3,NULL),(44,4,'Group')")
 execSQL("INSERT INTO message VALUES (101,'shared',11,0,0,'other chat',11,1),(202,'shared',22,0,0,'right chat',22,2),(203,'shared',22,1,0,'own direction',23,2),(303,'shared',33,0,0,'LID namespace',33,3),(404,'group',44,0,0,'group text',44,2)")
}
private fun install(ctx:Context,prefs:Prefs,methodName:String="deleteForMe"):Pair<PreserveDeleteForMeHook,XC_MethodHook> {
 XposedBridge.methodHooks.clear();XposedBridge.databaseHooks.clear()
 DexSearchEngine.dedicated=null;DexSearchEngine.lookupBridge=null
 DexSearchEngine.selected=if(methodName=="run")Task::class.java.getDeclaredMethod("run") else DeleteMethods::class.java.getDeclaredMethod("deleteForMe")
 val feature=PreserveDeleteForMeHook(ctx,Task::class.java.classLoader,prefs);feature.hook()
 ck("one controlled bytecode callback installed",XposedBridge.methodHooks.size,1)
 ck("one database callback installed",XposedBridge.databaseHooks.size,1)
 return feature to XposedBridge.methodHooks.single().second
}

private fun actionChecks(root:File){
 val ctx=context(root,"dedicated-action");val db=host(ctx);val prefs=Prefs()
 val feature=PreserveDeleteForMeHook(ctx,Task::class.java.classLoader,prefs)
 val action=CollectionAction::class.java.getDeclaredMethod("deleteForMe",Collection::class.java,Boolean::class.javaPrimitiveType,Boolean::class.javaPrimitiveType)
 try {
  DexSearchEngine.selected=null;DexSearchEngine.lookupBridge=null;DexSearchEngine.dedicated=action
  XposedBridge.methodHooks.clear();XposedBridge.databaseHooks.clear();feature.hook()
  ck("dedicated action installed from valid cache",XposedBridge.methodHooks.singleOrNull()?.first,action)
  ck("old negative cache key is not reused",DexSearchEngine.keys.any{it=="wpp_delete_for_me_collection_action_v8"},true)
  val callback=XposedBridge.methodHooks.single().second
  val selected=arrayListOf<Any>(Message(flat()),Message(flat(own=true)),Message(flat("22222@lid")))
  val original=selected.toList();val args=arrayOf<Any?>(selected,true,false)
  val param=XC_MethodHook.MethodHookParam(CollectionAction(),args)
  callback.before(param)
  ck("all collection rows captured before original action",ctx.contentResolver.calls.size,3)
  ck("collection argument unchanged",selected,original);ck("argument array unchanged",param.args===args,true)
  ck("action booleans unchanged",param.args.drop(1),listOf(true,false))
  ck("dedicated action scope active during callback",PreserveDeleteForMeHook.isDeleteForMeInProgress(),true)
  callback.after(param);ck("synchronous action scope removed",PreserveDeleteForMeHook.isDeleteForMeInProgress(),false)
  ctx.contentResolver.calls.clear();prefs.enabled=false
  val disabled=XC_MethodHook.MethodHookParam(CollectionAction(),args);callback.before(disabled);callback.after(disabled)
  ck("disabled dedicated action creates no capture",ctx.contentResolver.calls.size,0)
  prefs.enabled=true
  val empty=XC_MethodHook.MethodHookParam(CollectionAction(),arrayOf(emptyList<Any>(),false,false));callback.before(empty);callback.after(empty)
  ck("empty selection creates no scope",PreserveDeleteForMeHook.isDeleteForMeInProgress(),false)
  for(name in listOf("wrongSet","wrongReturn","wrongArity","staticAction")){
   DexSearchEngine.dedicated=CollectionAction::class.java.declaredMethods.single{it.name==name}
   XposedBridge.methodHooks.clear();feature.hook()
   ck("invalid cached dedicated signature rejected: $name",XposedBridge.methodHooks.size,0)
  }
 } finally {DexSearchEngine.dedicated=null;db.close()}
}
private fun capture(feature:PreserveDeleteForMeHook,task:Any):Boolean=PreserveDeleteForMeHook::class.java.getDeclaredMethod("captureRunnableMessages",Any::class.java).apply{isAccessible=true}.invoke(feature,task) as Boolean
private fun flat(jid:String="22222@s.whatsapp.net",id:String="shared",own:Boolean=false)=FlatKey(Jid(jid),id,own)
private fun selection(value:Any?):List<Any>? {
 val type=Class.forName("com.waenhancer.xposed.features.conversation.PreservedMessageSelection")
 val companion=type.getDeclaredField("Companion").get(null)
 val result=companion.javaClass.getMethod("read",Any::class.java).invoke(companion,value)?:return null
 return listOf(type.getMethod("getId").invoke(result),type.getMethod("getChatJid").invoke(result),type.getMethod("getFromMe").invoke(result))
}

private fun identityChecks(){
 val expected=listOf("shared","22222@s.whatsapp.net",false)
 ck("direct typed key",selection(flat()),expected)
 ck("inherited key fields",selection(Key(Jid("22222@s.whatsapp.net"),"shared",false)),expected)
 ck("message key and accessor agree",selection(Message(flat())),expected)
 ck("inherited message key",selection(InheritedMessage(flat())),expected)
 ck("static foreign key ignored",selection(StaticKey(flat())),expected)
 ck("static key does not identify instance",selection(StaticOnly()),null)
 ck("distinct keys remain ambiguous",selection(Conflicting(flat(),flat("22222@lid"))),null)
 ck("same full identity may be repeated",selection(Conflicting(flat(),flat())),expected)
 ck("unknown JID-shaped object rejected",selection(UnknownKey(UnknownJid(),"shared",false)),null)
 ck("envelope fields cannot replace owned key",selection(Envelope(Jid("11111@s.whatsapp.net"),"wrong",true,flat())),expected)
 ck("invalid JID rejected",selection(flat("+22222")),null)
 ck("blank key rejected",selection(flat(id=" ")),null)
 ck("null key rejected",selection(null),null)
 ck("LID retains namespace",selection(flat("22222@lid")),listOf("shared","22222@lid",false))
 ck("direction retained",selection(flat(own=true)),listOf("shared","22222@s.whatsapp.net",true))
}

private fun captureChecks(root:File,scenario:String){
 val ctx=context(root,"capture-$scenario");val db=host(ctx);val prefs=Prefs();val (feature,callback)=install(ctx,prefs,"run")
 try {
  if(scenario=="inherited"){
   ck("inherited selected Set is captured",capture(feature,ChildTask(setOf(Message(flat())))),true)
   ck("inherited selection correct",ctx.contentResolver.calls.single().getString("text"),"right chat");return
  }
  if(scenario=="static"){
   GlobalTask.selected=setOf(Message(flat()))
   ck("static Set is not a selection",capture(feature,GlobalTask()),false)
   ck("static Set creates no request",ctx.contentResolver.calls.size,0);return
  }
  val task=Task(linkedSetOf(Message(flat()),Message(flat(own=true)),Message(flat("22222@lid"))))
  ck("selected full keys capture",capture(feature,task),true)
  ck("same ID preserves three identities",ctx.contentResolver.calls.map{listOf(it.getString("jid"),it.getBoolean("fromMe"),it.getString("text"))}.toSet(),setOf(listOf("22222@s.whatsapp.net",false,"right chat"),listOf("22222@s.whatsapp.net",true,"own direction"),listOf("22222@lid",false,"LID namespace")))
  ck("source rows never deleted",rows(db,"SELECT COUNT(*) FROM message").single().single(),"5")
  ck("LID sent to namespace-aware name resolver",com.waenhancer.utils.ContactNameResolver.requests.contains("22222@lid"),true)
  ctx.contentResolver.calls.clear()
  db.execSQL("INSERT INTO message VALUES (204,'shared',22,0,0,'duplicate physical row',24,2)")
  ck("two physical rows for full key rejected",capture(feature,Task(setOf(Message(flat())))),false)
  ck("ambiguity sends no capture",ctx.contentResolver.calls.size,0)
  db.execSQL("DELETE FROM message WHERE _id=204")
  db.execSQL("INSERT INTO message VALUES (205,'revoked',22,0,15,'placeholder',25,2)")
  ck("type 15 placeholder not captured",capture(feature,Task(setOf(Message(flat(id="revoked"))))),false)
  ck("unmatched key not captured",capture(feature,Task(setOf(Message(flat(id="missing"))))),false)
  val group=Task(setOf(Message(flat("99999-88888@g.us","group"))))
  ck("group row captured",capture(feature,group),true)
  val bundle=ctx.contentResolver.calls.single()
  ck("group name retained",bundle.getString("name"),"Group")
  ck("group sender uses exact namespace",bundle.getString("senderName"),"Name(22222@s.whatsapp.net)")
  ctx.contentResolver.calls.clear()
  val param=XC_MethodHook.MethodHookParam(Task(setOf(Message(flat()))))
  callback.before(param);ck("runnable selection enters scope",PreserveDeleteForMeHook.isDeleteForMeInProgress(),true)
  callback.after(param);ck("runnable scope removed",PreserveDeleteForMeHook.isDeleteForMeInProgress(),false)
  ck("capture log makes no persistence assertion",XposedBridge.logs.any{it.contains("Copied")},false)
 } finally {db.close()}
}

private fun scopeChecks(root:File,disabledInner:Boolean){
 val ctx=context(root,"scope-$disabledInner");val prefs=Prefs();val (_,callback)=install(ctx,prefs)
 val outer=XC_MethodHook.MethodHookParam(DeleteMethods());val inner=XC_MethodHook.MethodHookParam(DeleteMethods())
 callback.before(outer);ck("outer scope entered",PreserveDeleteForMeHook.isDeleteForMeInProgress(),true)
 var otherThread=true;Thread{otherThread=PreserveDeleteForMeHook.isDeleteForMeInProgress()}.apply{start();join()};ck("scope stays on owning thread",otherThread,false)
 if(disabledInner)prefs.enabled=false
 callback.before(inner)
 val failure=IllegalArgumentException("controlled host failure");inner.throwable=failure;inner.result="unchanged"
 callback.after(inner)
 ck("nested callback retains outer scope",PreserveDeleteForMeHook.isDeleteForMeInProgress(),true)
 ck("host exception unchanged",inner.throwable===failure,true);ck("host result unchanged",inner.result,"unchanged")
 prefs.enabled=true;callback.after(outer);ck("outer scope closes",PreserveDeleteForMeHook.isDeleteForMeInProgress(),false)
 callback.after(XC_MethodHook.MethodHookParam(DeleteMethods()));ck("unentered after is neutral",PreserveDeleteForMeHook.isDeleteForMeInProgress(),false)
}

private fun databaseChecks(root:File){
 val ctx=context(root,"db-target");val db=host(ctx);val otherCtx=context(root,"db-other");val foreign=host(otherCtx)
 val prefs=Prefs();val (_,callback)=install(ctx,prefs);val dbCallback=XposedBridge.databaseHooks.single()
 val outer=XC_MethodHook.MethodHookParam(DeleteMethods());callback.before(outer)
 try {
  val foreignParam=XC_MethodHook.MethodHookParam(foreign,arrayOf("message","_id = ?",arrayOf("202")))
  dbCallback.before(foreignParam)
  ck("other database is never queried",foreign.queries,0);ck("other database never captured",ctx.contentResolver.calls.size,0)
  val originalArgs=arrayOf<Any?>("message","_id = ?",arrayOf("203"));val targetParam=XC_MethodHook.MethodHookParam(db,originalArgs)
  dbCallback.before(targetParam)
  ck("target database row captured",ctx.contentResolver.calls.single().getString("text"),"own direction")
  ck("target identity retained",ctx.contentResolver.calls.single().getString("jid"),"22222@s.whatsapp.net")
  ck("database arguments retained",targetParam.args===originalArgs,true)
  ctx.contentResolver.calls.clear()
  db.execSQL("INSERT INTO message VALUES (999,'unknown',999,0,0,'unknown chat',99,0),(998,'invalid-direction',22,2,0,'bad direction',98,0)")
  dbCallback.before(XC_MethodHook.MethodHookParam(db,arrayOf("message","_id IN (?,?)",arrayOf("998","999"))))
  ck("unknown identity and direction skipped",ctx.contentResolver.calls.size,0)
  dbCallback.before(XC_MethodHook.MethodHookParam(db,arrayOf("chat","_id = ?",arrayOf("22"))))
  ck("unrelated table skipped",ctx.contentResolver.calls.size,0)
  prefs.enabled=false;dbCallback.before(XC_MethodHook.MethodHookParam(db,arrayOf("message","_id = ?",arrayOf("202"))))
  ck("disabled callback skipped",ctx.contentResolver.calls.size,0)
 } finally {callback.after(outer);db.close();foreign.close()}
}

private fun storeChecks(root:File){
 val ctx=context(root,"store");val vault=store(ctx)
 try {
  vault.insertPreservedMessage("22222@s.whatsapp.net","Phone","Phone","shared","received",10,false,false)
  vault.insertPreservedMessage("22222@s.whatsapp.net","Phone","You","shared","sent",11,true,false)
  vault.insertPreservedMessage("22222@lid","LID","LID","shared","linked-id",12,false,false)
  val stored=vault.getAllPreservedMessages()
  ck("vault keeps chat/direction/namespaces",stored.map{listOf(it.jid,it.isFromMe,it.text)}.toSet(),setOf(listOf("22222@s.whatsapp.net",false,"received"),listOf("22222@s.whatsapp.net",true,"sent"),listOf("22222@lid",false,"linked-id")))
  vault.insertPreservedMessage("22222@s.whatsapp.net","Phone","Phone","shared","updated",13,false,false)
  ck("same identity replaces only itself",vault.getAllPreservedMessages().size,3)
  ck("replacement exact",vault.getAllPreservedMessages().single{it.jid=="22222@s.whatsapp.net"&&!it.isFromMe}.text,"updated")
  ck("LID name does not borrow phone",vault.getContactNameByJid("22222@lid"),"LID")
  vault.insertPreservedMessage("22222@lid","LID",null," ","ignored",1,false,false)
  ck("blank message ID rejected",vault.getAllPreservedMessages().size,3)
 } finally {vault.close()}
}

private fun migrationChecks(root:File,old:Int,failCopy:Boolean=false){
 val ctx=context(root,"migration-$old-$failCopy");val path=ctx.getDatabasePath("waex_preserved_messages.db").absolutePath
 val columns="_id,jid,contact_name,sender_name,msg_id,text_data,timestamp,from_me,is_group"
 val before:List<List<String?>>
 SQLiteDatabase(path).use{db->
  val sender=if(old>=2)"sender_name TEXT," else ""
  val unique=if(old==3)"UNIQUE(jid,msg_id,from_me)" else "UNIQUE(msg_id)"
  db.execSQL("CREATE TABLE preserved_messages (_id INTEGER PRIMARY KEY AUTOINCREMENT,jid TEXT NOT NULL,contact_name TEXT,$sender msg_id TEXT,text_data TEXT,timestamp INTEGER DEFAULT 0,from_me INTEGER DEFAULT 0,is_group INTEGER DEFAULT 0,$unique)")
  db.execSQL("INSERT INTO preserved_messages (_id,jid,contact_name,msg_id,text_data,timestamp,from_me,is_group) VALUES (7,'11111@s.whatsapp.net','Legacy','legacy-a','text '' quote',123,0,0),(11,'22222@lid',NULL,'legacy-b','texto ñ',456,1,0)")
  if(old>=2)db.execSQL("UPDATE preserved_messages SET sender_name='Sender' WHERE _id=7")
  db.execSQL("PRAGMA user_version = $old")
  before=rows(db,"SELECT ${if(old==1)columns.replace("sender_name","NULL AS sender_name") else columns} FROM preserved_messages ORDER BY _id")
 }
 val vault=store(ctx)
 try {
  if(failCopy){
   SQLiteDatabase.failSqlOnce="INSERT INTO preserved_messages ("
   var rejected=false;try{vault.writableDatabase}catch(_:RuntimeException){rejected=true}
   ck("copy failure propagates from helper",rejected,true)
   SQLiteDatabase(path).use{db->
    ck("failed migration keeps version",rows(db,"PRAGMA user_version").single().single(),old.toString())
    ck("failed migration keeps original rows",rows(db,"SELECT ${if(old==1)columns.replace("sender_name","NULL AS sender_name") else columns} FROM preserved_messages ORDER BY _id"),before)
    ck("failed rename rolled back",rows(db,"SELECT name FROM sqlite_master WHERE type='table' AND name='preserved_messages_v2_backup'").size,0)
   }
  }
  val db=vault.writableDatabase
  ck("migration preserves every field and row ID",rows(db,"SELECT $columns FROM preserved_messages ORDER BY _id"),before)
  ck("migration version advances",rows(db,"PRAGMA user_version").single().single(),"3")
  ck("backup removed only after copy",rows(db,"SELECT name FROM sqlite_master WHERE type='table' AND name='preserved_messages_v2_backup'").size,0)
  vault.insertPreservedMessage("11111@s.whatsapp.net","Legacy","You","legacy-a","other direction",999,true,false)
  vault.insertPreservedMessage("22222@s.whatsapp.net","Other","Other","legacy-a","other chat",999,false,false)
  ck("migrated uniqueness permits distinct identities",vault.getAllPreservedMessages().size,4)
  ck("old rows still present after inserts",rows(db,"SELECT _id FROM preserved_messages WHERE _id IN (7,11) ORDER BY _id"),listOf(listOf("7"),listOf("11")))
 } finally {vault.close()}
}

private fun integratedChecks(root:File){
 val hostContext=context(root,"integrated-host");val db=host(hostContext);val vault=store(context(root,"integrated-manager"));val (feature,_)=install(hostContext,Prefs(),"run")
 hostContext.contentResolver.consumer={b->vault.insertPreservedMessage(b.getString("jid")!!,b.getString("name"),b.getString("senderName"),b.getString("msgId")!!,b.getString("text")!!,b.getLong("timestamp"),b.getBoolean("fromMe"),b.getBoolean("isGroup"))}
 try {
  ck("hook submits selected rows into real SQL store",capture(feature,Task(linkedSetOf(Message(flat()),Message(flat(own=true)),Message(flat("22222@lid"))))),true)
  ck("integrated vault has three exact identities",vault.getAllPreservedMessages().map{listOf(it.jid,it.isFromMe,it.text)}.toSet(),setOf(listOf("22222@s.whatsapp.net",false,"right chat"),listOf("22222@s.whatsapp.net",true,"own direction"),listOf("22222@lid",false,"LID namespace")))
  ck("integrated host data untouched",rows(db,"SELECT COUNT(*) FROM message").single().single(),"5")
 } finally {db.close();vault.close()}
}

fun main(args:Array<String>){
 val root=File(args[0]);val scenario=args.getOrElse(1){"all"}
 when(scenario){
  "selection"->captureChecks(root,"selection")
  "store"->storeChecks(root)
  "scope"->scopeChecks(root,false)
  "disabled_inner"->scopeChecks(root,true)
  "static"->captureChecks(root,"static")
  "inherited"->captureChecks(root,"inherited")
  "database"->databaseChecks(root)
  "action"->actionChecks(root)
  "all"->{identityChecks();captureChecks(root,"selection");captureChecks(root,"inherited");captureChecks(root,"static");scopeChecks(root,false);scopeChecks(root,true);databaseChecks(root);storeChecks(root);for(old in 1..3)migrationChecks(root,old);migrationChecks(root,1,true);migrationChecks(root,2,true);integratedChecks(root);actionChecks(root)
   try {Class.forName("com.waenhancer.xposed.features.conversation.PreservedSelectorChecksKt").getMethod("selectorChecks",File::class.java).invoke(null,root)} catch(_:ClassNotFoundException){println("Native lookup fixture omitted for real DexKit API compilation")}
  }
  else->error("Unknown scenario")
 }
 println("PASS: $checks complete preserved hook/selection/store checks ($scenario), with real Python SQLite and explicit platform doubles; no native host discovery or device claim")
}
