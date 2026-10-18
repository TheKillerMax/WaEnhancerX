package com.waenhancer.xposed.features.conversation

import android.content.Context
import android.content.SharedPreferences
import com.waenhancer.xposed.core.devkit.DexSearchEngine
import de.robv.android.xposed.XposedBridge
import java.io.File
import java.lang.reflect.Method
import org.luckypray.dexkit.DexKitBridge
import org.luckypray.dexkit.query.enums.StringMatchType
import org.luckypray.dexkit.result.MethodData

private class ActionOne {fun local(messages:Collection<Any>,first:Boolean,second:Boolean){}}
private class ActionTwo {fun local(messages:Collection<Any>,first:Boolean,second:Boolean){}}
private class UnrelatedAction {
 fun wrong(messages:Set<Any>,first:Boolean,second:Boolean){}
 fun wrongResult(messages:Collection<Any>,first:Boolean,second:Boolean)=true
 companion object {@JvmStatic fun global(messages:Collection<Any>,first:Boolean,second:Boolean){}}
}

/** The production resolver runs against controlled DexKit result data, not copied selector logic. */
fun selectorChecks(root:File){
 val literals=listOf("UserActionsMessageDeletion/userActionDeleteMessages ",
  "UserActionsMessageDeletion/userActionDeleteMessages messagesToDeleteIncludingAssociatedMessages=")
 val first=ActionOne::class.java.declaredMethods.single()
 val second=ActionTwo::class.java.declaredMethods.single()
 fun candidate(method:Method,text:List<String> = literals)=MethodData(
  name=method.name,paramTypeNames=method.parameterTypes.map{it.name},returnTypeName=method.returnType.name,
  reflected=method,literals=text)
 val context=Context(File(root,"resolver").apply{mkdirs()})
 val preferences=object:SharedPreferences{override fun getBoolean(key:String,default:Boolean)=true}
 var checks=0
 fun checkCase(label:String,candidates:List<MethodData>,expected:Method?){
  val bridge=DexKitBridge(candidates)
  DexSearchEngine.selected=null;DexSearchEngine.dedicated=null;DexSearchEngine.lookupBridge=bridge
  XposedBridge.methodHooks.clear();XposedBridge.databaseHooks.clear()
  PreserveDeleteForMeHook(context,ActionOne::class.java.classLoader,preferences).hook()
  val actual=XposedBridge.methodHooks.singleOrNull()?.first
  check(actual==expected){"ASSERTION|selector $label actual=$actual expected=$expected"};checks++
  check(bridge.queries.single().value.strings==literals.map{it to StringMatchType.Equals}){"Exact two-literal contract changed"};checks++
 }
 try {
  checkCase("unique dedicated action",listOf(candidate(first)),first)
  checkCase("ambiguous dedicated actions",listOf(candidate(first),candidate(second)),null)
  checkCase("no action",emptyList(),null)
  checkCase("only first anchor",listOf(candidate(first,literals.take(1))),null)
  checkCase("only second anchor",listOf(candidate(first,literals.drop(1))),null)
  checkCase("trailing-space literal remains exact",listOf(candidate(first,listOf(literals[0].trimEnd(),literals[1]))),null)
  checkCase("prefix is not exact anchor",listOf(candidate(first,listOf("prefix"+literals[0],literals[1]))),null)
  for(name in listOf("wrong","wrongResult","global")){
   checkCase(name,listOf(candidate(UnrelatedAction::class.java.declaredMethods.single{it.name==name})),null)
  }
  checkCase("invalid neighbor does not replace unique valid action",listOf(candidate(UnrelatedAction::class.java.declaredMethods.single{it.name=="global"}),candidate(first)),first)
 } finally {DexSearchEngine.lookupBridge=null}
 println("PASS: $checks production dedicated-delete resolver checks using explicit DexKit results; actual host discovery remains a separate check")
}
