package com.waenhancer.utils

import android.content.pm.PackageManager
import android.app.Activity
import de.robv.android.xposed.XposedBridge

import android.content.*
import android.content.res.Resources
import android.os.SystemClock
import com.waenhancer.app.R
import com.waenhancer.utils.UniversalVersionValidator.Decision as D
import com.waenhancer.utils.TargetRuntimePresentation.Severity as S
import com.waenhancer.xposed.utils.AppRestartHelper as Root
import com.waenhancer.xposed.core.VersionGuard
import com.waenhancer.xposed.core.components.WaexBottomSheet
import java.io.File

class Prefs:SharedPreferences,SharedPreferences.Editor {
    val values=mutableMapOf<String,Any>();var fail=false
    override fun getBoolean(k:String,d:Boolean):Boolean{if(fail)throw ClassCastException("private value");return values[k] as? Boolean?:d}
    override fun getString(k:String,d:String?)=values[k] as? String?:d
    override fun getStringSet(k:String,d:Set<String>?)=values[k] as? Set<String>?:d
    override fun edit():SharedPreferences.Editor=this
    override fun putBoolean(k:String,v:Boolean)=apply{values[k]=v}
    override fun putString(k:String,v:String?)=apply{if(v!=null)values[k]=v}
    override fun putStringSet(k:String,v:Set<String>)=apply{values[k]=v}
    override fun apply(){}
}
var checks=0
fun ck(label:String,a:Any?,b:Any?){check(a==b){"ASSERTION|$label actual=$a expected=$b"};checks++}
fun main(args:Array<String>){
    val names=mapOf("universal_supported_versions" to R.array.universal_supported_versions)
    val rules=arrayOf(/*BUILTIN_RULES*/)
    fun module(rules:Array<String>, name:String?=null, namesArg:Map<String,Int> = names)=Context("com.waenhancer",Resources("com.waenhancer",namesArg,mapOf(R.array.universal_supported_versions to rules),name))
    val mod=module(rules);val prefs=Prefs()
    val host=Context("com.whatsapp",Resources("com.whatsapp",emptyMap(),emptyMap()),mod)
    for(v in listOf("2.26.46.9","2.26.45.1","2.26.44.1","2.26.43.1","2.26.42.9","2.26.41.1","2.26.40.76"," v2.26.40.76 ")){
        ck("module admits $v",UniversalVersionValidator.evaluate(mod,v,prefs),D.BUILTIN_RULE)
        ck("host uses own module resources $v",UniversalVersionValidator.evaluate(host,v,prefs),D.BUILTIN_RULE)
        ck("Boolean API compatible $v",UniversalVersionValidator.isSupported(host,v,prefs),true)
    }
    ck("host table not consulted",host.resources.reads.size,0)
    ck("module context requested by exact package",host.contextRequests.isNotEmpty() && host.contextRequests.all{it.first=="com.waenhancer"},true)
    ck("resource access never requests application code",host.contextRequests.all{it.second and Context.CONTEXT_INCLUDE_CODE==0},true)
    val hidden=Context("com.whatsapp",Resources("com.whatsapp",emptyMap(),mapOf(R.array.universal_supported_versions to arrayOf("9.99.1"))))
    ck("hidden module has no version rules",UniversalVersionValidator.evaluate(hidden,"2.26.40.76",prefs),D.RULES_UNAVAILABLE)
    ck("reject foreign matching numeric table",UniversalVersionValidator.isSupported(hidden,"9.99.1",prefs),false)
    ck("never read foreign resource ID",hidden.resources.reads.size,0)
    ck("null context has no built-in rules",UniversalVersionValidator.evaluate(null,"2.26.40.76",prefs),D.RULES_UNAVAILABLE)
    ck("no-context bool cannot infer support",UniversalVersionValidator.isSupported("2.26.40.76",prefs),false)
    ck("no-context built-in list is empty",UniversalVersionValidator.getBuiltinSupportedVersions(null),emptyList<String>())
    ck("no-context rejects unknown versions",UniversalVersionValidator.isSupported(null,"9.99.1",prefs),false)
    ck("wrong context has no module rules",UniversalVersionValidator.evaluate(Context("com.whatsapp",hidden.resources,hidden),"2.26.40.76",prefs),D.RULES_UNAVAILABLE)
    val foreignMatching=Context("com.whatsapp",Resources("com.whatsapp",names,mapOf(R.array.universal_supported_versions to rules)))
    ck("wrong context cannot supply module rules",UniversalVersionValidator.evaluate(Context("com.whatsapp",hidden.resources,foreignMatching),"2.26.40.76",prefs),D.RULES_UNAVAILABLE)
    ck("wrong context rejected before its array read",foreignMatching.resources.reads.size,0)
    val misplacedModuleResources=Resources("com.waenhancer",names,mapOf(R.array.universal_supported_versions to rules))
    val wrongPackageContext=Context("com.whatsapp",misplacedModuleResources)
    ck("wrong package cannot supply module rules",UniversalVersionValidator.evaluate(Context("com.whatsapp",hidden.resources,wrongPackageContext),"2.26.40.76",prefs),D.RULES_UNAVAILABLE)
    ck("unexpected context is rejected before reading even matching arrays",misplacedModuleResources.reads.size,0)
    ck("foreign owner is unavailable",UniversalVersionValidator.evaluate(module(rules,"com.whatsapp:array/universal_supported_versions"),"2.26.40.76",prefs),D.RULES_UNAVAILABLE)
    ck("foreign array name is unavailable",UniversalVersionValidator.evaluate(module(rules,"com.waenhancer:array/another_array"),"2.26.40.76",prefs),D.RULES_UNAVAILABLE)
    ck("own numeric fallback verified by full name",UniversalVersionValidator.evaluate(module(rules,"com.waenhancer:array/universal_supported_versions",emptyMap()),"2.26.40.76",prefs),D.BUILTIN_RULE)
    for(failure in listOf(SecurityException("blocked"),PackageManager.NameNotFoundException(),NoClassDefFoundError("unavailable"))){
        val inaccessible=Context("com.whatsapp",hidden.resources,mod).apply{contextFailure=failure}
        ck("resource access failure has no rules ${failure.javaClass.simpleName}",UniversalVersionValidator.evaluate(inaccessible,"2.26.40.76",prefs),D.RULES_UNAVAILABLE)
    }
    for(failure in listOf(AssertionError("controlled assertion"),OutOfMemoryError("controlled VM failure"),ThreadDeath())){
        val broken=Context("com.whatsapp",hidden.resources,mod).apply{contextFailure=failure}
        var caught:Throwable?=null
        try { UniversalVersionValidator.evaluate(broken,"2.26.40.76",prefs) } catch(t:Throwable){caught=t}
        ck("fatal or assertion error is not a rules result ${failure.javaClass.simpleName}",caught===failure,true)
    }
    for(list in listOf(emptyArray<String>(),arrayOf("bad"),arrayOf(""),arrayOf("2.26.40.xx",""),arrayOf("*.xx"))){
        ck("invalid array is unavailable",UniversalVersionValidator.evaluate(module(list),"2.26.40.76",prefs),D.RULES_UNAVAILABLE)
    }
    // A future 2.26.x branch can become supported as arrays.xml changes. Keep the
    // synthetic major-zero version outside that range and test 2.26.42 above.
    for(v in listOf("2.26.39.74","2.26.39.72","2.26.35.90","0.0.0.0","9.99.1"))ck("true rejected version $v",UniversalVersionValidator.evaluate(mod,v,prefs),D.UNSUPPORTED)
    for(v in listOf(null,""," ","v"))ck("version unavailable",UniversalVersionValidator.evaluate(mod,v,prefs),D.VERSION_UNAVAILABLE)
    val custom=Prefs().apply{values["customize_supported_versions"]=true;values["custom_supported_versions"]=setOf("9.99.1")}
    ck("intentional custom permission preserved",UniversalVersionValidator.evaluate(hidden,"9.99.1",custom),D.CUSTOM_RULE)
    ck("custom does not invent unavailable built-ins",UniversalVersionValidator.evaluate(hidden,"9.99.2",custom),D.RULES_UNAVAILABLE)
    ck("built-in rule retains precedence",UniversalVersionValidator.evaluate(host,"2.26.40.76",custom),D.BUILTIN_RULE)
    custom.values["customize_supported_versions"]=false
    ck("disabled custom does not replace missing rules",UniversalVersionValidator.evaluate(hidden,"9.99.1",custom),D.RULES_UNAVAILABLE)
    val bypass=Prefs().apply{values["bypass_version_check"]=true}
    ck("explicit existing bypass preserved",UniversalVersionValidator.evaluate(hidden,"99.8.7",bypass),D.EXPLICIT_BYPASS)
    ck("even bypass needs version",UniversalVersionValidator.evaluate(hidden,"",bypass),D.VERSION_UNAVAILABLE)
    ck("unreadable preferences named honestly",UniversalVersionValidator.evaluate(mod,"2.26.40.76",Prefs().apply{fail=true}),D.PREFERENCES_UNAVAILABLE)
    ck("evaluating did not change preferences",prefs.values.size,0)
    val loader=VersionGuard.javaClass.classLoader
    ck("guard accepts only array-declared rules",VersionGuard.verifyAndGuard(host,loader,prefs),true)
    val unavailablePrefs=Prefs().apply{fail=true}
    ck("guard pauses on unreadable settings",VersionGuard.verifyAndGuard(hidden,loader,unavailablePrefs),false)
    ck("guard forwards unavailable decision",VersionGuard.runtimeStatus(),"COMPATIBILITY_UNAVAILABLE")
    VersionGuard.onTargetActivityResumed(Activity())
    ck("settings access error notice",WaexBottomSheet.lastMessage.contains("compatibility settings"),true)
    ck("dialog shown once",WaexBottomSheet.shows,1)
    VersionGuard.onTargetActivityResumed(Activity());ck("no duplicate dialog",WaexBottomSheet.shows,1)
    ck("guard recovery after fresh verification",VersionGuard.verifyAndGuard(host,loader,prefs),true)
    VersionGuard.onTargetActivityResumed(Activity());ck("successful guard clears pending warning",WaexBottomSheet.shows,1)
    host.packageManager.version="9.99.1"
    ck("guard truly unsupported",VersionGuard.verifyAndGuard(host,loader,prefs),false)
    ck("precise unsupported status",VersionGuard.runtimeStatus(),"UNSUPPORTED_VERSION")
    host.packageManager.fail=true
    ck("version lookup failure pauses",VersionGuard.verifyAndGuard(host,loader,prefs),false)
    ck("lookup error doesn't reuse earlier rejection",VersionGuard.runtimeStatus(),"COMPATIBILITY_UNAVAILABLE")
    host.packageManager.fail=false;host.packageManager.version="2.26.40.76"
    ck("settings failure pauses",VersionGuard.verifyAndGuard(host,loader,Prefs().apply{fail=true}),false)
    ck("failure notice reason",VersionGuard.noticeMessage("v",D.PREFERENCES_UNAVAILABLE).contains("compatibility settings"),true)
    ck("no missing-resource mislabel",VersionGuard.noticeMessage("2.26.40.76",D.RULES_UNAVAILABLE).contains("not match"),false)
    ck("guard logs exclude raw preferences",XposedBridge.logs.any{it.contains("private value")},false)
    VersionGuard.verifyAndGuard(hidden,loader,unavailablePrefs)
    WaexBottomSheet.fail=true;VersionGuard.onTargetActivityResumed(Activity())
    WaexBottomSheet.fail=false;VersionGuard.onTargetActivityResumed(Activity())
    ck("warning can recover after failed show",WaexBottomSheet.shows,2)
    fun evidence(pids:Set<Int>?=setOf(123),t:Long=10000,boot:Int=7,recorded:Int=7,pid:Int=123,active:Boolean=true)=classifyInjection(active,recorded,boot,pid,pids,t)
    ck("current",evidence(),InjectionEvidence.CURRENT)
    ck("missing root observation",evidence(null),InjectionEvidence.PROCESS_OBSERVATION_UNAVAILABLE)
    ck("completed empty result",evidence(emptySet()),InjectionEvidence.PROCESS_STOPPED)
    ck("changed PID",evidence(setOf(456)),InjectionEvidence.PROCESS_CHANGED)
    ck("unreadable boot",evidence(boot=-1),InjectionEvidence.BOOT_UNKNOWN)
    ck("other negative boot",evidence(boot=-2),InjectionEvidence.BOOT_UNKNOWN)
    ck("other boot",evidence(recorded=6),InjectionEvidence.PREVIOUS_BOOT)
    ck("missing report",evidence(pid=0),InjectionEvidence.NO_REPORT)
    ck("negative pid",evidence(pid=-1),InjectionEvidence.NO_REPORT)
    ck("inactive",evidence(active=false),InjectionEvidence.MODULE_INACTIVE)
    for(timestamp in listOf(1L,10000L,Long.MAX_VALUE))
        ck("current boot/PID independent of report age $timestamp",evidence(t=timestamp),InjectionEvidence.CURRENT)
    for(timestamp in listOf(0L,-1L,Long.MIN_VALUE))
        ck("non-positive report is absent $timestamp",evidence(t=timestamp),InjectionEvidence.NO_REPORT)
    ck("compat helper preserves PID proof",hasCurrentInjection(true,7,7,123,setOf(123),1L),true)
    ck("compat helper rejects different PID",hasCurrentInjection(true,7,7,123,setOf(456),10000L),false)
    val snap=parseProcessList("PID NAME\n123 com.whatsapp\n456 com.whatsapp\n12 com.whatsapp.w4b\n",1000)
    ck("PID values",snap.pidsFor("com.whatsapp"),setOf(123,456))
    ck("exhaustive missing target stopped",snap.pidsFor("com.gbwhatsapp"),emptySet<Int>())
    ck("partial missing target unknown",snap.copy(exhaustive=false).pidsFor("com.gbwhatsapp"),null)
    ck("incomplete known target unknown",snap.copy(complete=false).pidsFor("com.whatsapp"),null)
    ck("timestamp records collection start",snap.observedAtElapsed,1000L)
    val legacy=parseProcessList("USER PID PPID VSIZE RSS WCHAN PC NAME\nu0_a1 41 1 20 30 S 0 com.whatsapp\n",1111)
    ck("legacy ps PID",legacy.pidsFor("com.whatsapp"),setOf(41))
    ck("duplicate rows deduplicated",parseProcessList("42 com.whatsapp\n42 com.whatsapp\n").pidsFor("com.whatsapp"),setOf(42))
    for(line in listOf("", "bad", "0 com.whatsapp", "-1 com.whatsapp", "abc com.whatsapp",
            "2147483648 com.whatsapp", "12 com.whatsapp:service", "12 com.whatsapp;id",
            "12 single", "12 1invalid.name", "12 "+"a".repeat(250)+".whatsapp"))
        ck("malformed process row ignored: $line",parseProcessList(line).runningPids.size,0)
    var immutable=false
    try{(snap.runningPids as MutableMap).clear()}catch(_:UnsupportedOperationException){immutable=true}
    ck("observations immutable",immutable,true)
    immutable=false
    try{(snap.pidsFor("com.whatsapp") as MutableSet).clear()}catch(_:UnsupportedOperationException){immutable=true}
    ck("PID sets immutable",immutable,true)
    val noScope=LsposedScopeSnapshot("com.waenhancer",emptySet(),false,LsposedScopeSnapshot.Source.UNAVAILABLE)
    val liveScope=noScope.copy(packages=setOf("com.whatsapp"),frameworkReachable=true,source=LsposedScopeSnapshot.Source.DATABASE)
    val cachedScope=liveScope.copy(frameworkReachable=false,source=LsposedScopeSnapshot.Source.CACHE)
    ck("live membership",classifyScope("com.whatsapp",liveScope,false),TargetScopeState.IN_SCOPE)
    ck("live absence",classifyScope("com.whatsapp.w4b",liveScope,false),TargetScopeState.NOT_IN_SCOPE)
    ck("injection beats live absence",classifyScope("com.whatsapp.w4b",liveScope,true),TargetScopeState.INJECTED)
    ck("cache membership",classifyScope("com.whatsapp",cachedScope,false),TargetScopeState.IN_SCOPE)
    ck("cache absence unverified",classifyScope("com.whatsapp.w4b",cachedScope,false),TargetScopeState.UNVERIFIED)
    ck("unavailable scope unverified",classifyScope("com.whatsapp",noScope,false),TargetScopeState.UNVERIFIED)
    val beforeUnconfigured=Root.calls
    var scopeBoundaryRejected=false
    try{RootProbe.run(mod)}catch(_:AssertionError){scopeBoundaryRejected=true}
    ck("unconfigured scope boundary fails closed",scopeBoundaryRejected,true)
    ck("unconfigured scope never calls root",Root.calls,beforeUnconfigured)
    LsposedScopeReader.configured=liveScope
    Root.failure=null;Root.advance=4000;SystemClock.time=1000
    Root.output="WAEX_LSPOSED_DB_OK\nWAEX_PS_BEGIN\n123 com.whatsapp\n1 com.waenhancer\nWAEX_PS_END\n"
    val observed=RootProbe.run(mod)
    ck("actual root probe preserves current PID",observed.runtime!!.pidsFor("com.whatsapp"),setOf(123))
    ck("root observation starts before collection",observed.runtime.observedAtElapsed,1000L)
    ck("scope result passed through exactly",observed.scope===liveScope,true)
    ck("scope success marker passed to boundary",LsposedScopeReader.parsedStaged,true)
    ck("one shared root invocation",Root.calls,beforeUnconfigured+1)
    File(args.single()).writeText(RootProbe.processListCommand())
    ck("command wraps process output",Root.lastCommand.contains("\necho WAEX_PS_BEGIN\n")&&Root.lastCommand.endsWith("\necho WAEX_PS_END"),true)
    Root.advance=0
    for(output in listOf(null,"","bad","WAEX_PS_BEGIN\n42 com.whatsapp","WAEX_PS_END\nWAEX_PS_BEGIN\n42 com.whatsapp",
            "WAEX_PS_BEGIN\n\nWAEX_PS_END","WAEX_PS_BEGIN\ninvalid output\nWAEX_PS_END")){
        Root.output=output
        ck("unavailable/truncated process probe stays unknown",RootProbe.run(mod).runtime,null)
        ck("missing DB success marker reported",LsposedScopeReader.parsedStaged,false)
    }
    for(failure in listOf(SecurityException("fixture root denied"),NoClassDefFoundError("fixture root unavailable"))){
        Root.failure=failure
        ck("root failure stays unknown",RootProbe.run(mod).runtime,null)
    }
    val fatal=AssertionError("fixture root assertion");Root.failure=fatal
    var escaped:Throwable?=null
    try{RootProbe.run(mod)}catch(t:Throwable){escaped=t}
    ck("unexpected root assertion propagates",escaped===fatal,true)
    Root.failure=null
    Root.output="WAEX_PS_BEGIN\n1 com.waenhancer\nWAEX_PS_END"
    ck("manager present makes target absence observed",RootProbe.run(mod).runtime!!.pidsFor("com.whatsapp"),emptySet<Int>())
    val app=HookedAppInfo("com.whatsapp","WhatsApp","2.26.40.76",true,true,lastActiveTime=10000,runtimeStatus="READY",bridgeStatus="PROVIDER",processObservedAtElapsed=1000,scopeState=TargetScopeState.IN_SCOPE)
    val stopped=app.copy(isHooked=false,injectionEvidence=InjectionEvidence.PROCESS_STOPPED)
    ck("manager sentinel establishes module",ModuleActivation.resolve(true,emptyList()).signal,ModuleSignal.MANAGER_HOOK)
    ck("target injection establishes module",ModuleActivation.resolve(false,listOf(app)).signal,ModuleSignal.TARGET_INJECTION)
    ck("stopped target does not establish module",ModuleActivation.resolve(false,listOf(stopped)),ModuleActivation.INACTIVE)
    fun card(a:HookedAppInfo,d:D=D.BUILTIN_RULE)=TargetRuntimePresentation.card(a,true,d)
    ck("current complete",card(app).severity,S.OK)
    for(state in listOf("UNSUPPORTED_VERSION","COMPATIBILITY_UNAVAILABLE","INITIALIZATION_FAILED","READY_WITH_ERRORS")){
        for(d in listOf(D.BUILTIN_RULE,D.CUSTOM_RULE,D.EXPLICIT_BYPASS))ck("target state wins over local rule $state $d",card(app.copy(runtimeStatus=state),d).severity,S.REVIEW)
    }
    for(state in listOf("INJECTED","INITIALIZING","future-state"))ck("not ready",card(app.copy(runtimeStatus=state)).severity,S.UNKNOWN)
    ck("unknown bridge isn't ready",card(app.copy(bridgeStatus="PENDING")).severity,S.UNKNOWN)
    ck("failed bridge",card(app.copy(bridgeStatus="FAILED")).severity,S.REVIEW)
    ck("fallback bridge",card(app.copy(bridgeStatus="DISK_FALLBACK")).severity,S.REVIEW)
    ck("bypass not certification",card(app,D.EXPLICIT_BYPASS).severity,S.REVIEW)
    ck("custom allowance current upstream presentation",card(app,D.CUSTOM_RULE).severity,S.OK)
    ck("stopped target card unconfirmed",card(stopped).severity,S.UNKNOWN)
    ck("bridge historical",TargetRuntimePresentation.bridge(stopped),"Last report (not current): Connected directly")
    ck("init historical",TargetRuntimePresentation.initialization(stopped),"Last report (not current): Completed")
    ck("current bridge no historical label",TargetRuntimePresentation.bridge(app),"Connected directly")
    fun sum(apps:List<HookedAppInfo>,d:D=D.BUILTIN_RULE)=TargetRuntimePresentation.summarize(apps,apps.associate{it.packageName to d})
    ck("empty targets not supported",sum(emptyList()).healthy,null)
    ck("uninstalled not supported",sum(listOf(app.copy(isInstalled=false))).healthy,null)
    ck("no injection no false supported",sum(listOf(stopped)).healthy,null)
    ck("unsupported target matters without injection",sum(listOf(stopped),D.UNSUPPORTED).healthy,false)
    ck("target pause aggregate",sum(listOf(app.copy(runtimeStatus="UNSUPPORTED_VERSION"))).healthy,false)
    ck("bypass aggregate warning",sum(listOf(app),D.EXPLICIT_BYPASS).healthy,false)
    ck("complete reported",sum(listOf(app)).healthy,true)
    ck("closed target does not downgrade current ready target",sum(listOf(app,stopped.copy(packageName="com.whatsapp.w4b"))).healthy,true)
    ck("running incomplete target still matters",sum(listOf(app,app.copy(packageName="com.whatsapp.w4b",runtimeStatus="INITIALIZING"))).healthy,null)
    ck("summary says not all feature acceptance",sum(listOf(app)).text,"Rules accepted; initialization reported")
    ck("custom allowance summary follows current upstream",sum(listOf(app),D.CUSTOM_RULE).healthy,true)
    val delayed=Activity();delayed.defer=true
    prefs.values.clear();prefs.fail=false;host.packageManager.fail=false;host.packageManager.version="99.99.99.99"
    ck("queue scenario paused",VersionGuard.verifyAndGuard(host,host.javaClass.classLoader,prefs),false)
    VersionGuard.onTargetActivityResumed(delayed)
    val before=WaexBottomSheet.shows
    host.packageManager.version="2.26.40.76"
    ck("queue scenario subsequently admitted",VersionGuard.verifyAndGuard(host,host.javaClass.classLoader,prefs),true)
    delayed.flush()
    ck("obsolete pause callback does not render",WaexBottomSheet.shows,before)
    host.packageManager.version="99.99.99.99"
    VersionGuard.verifyAndGuard(host,host.javaClass.classLoader,prefs);VersionGuard.onTargetActivityResumed(delayed)
    host.packageManager.version=null
    VersionGuard.verifyAndGuard(host,host.javaClass.classLoader,prefs);VersionGuard.onTargetActivityResumed(delayed)
    delayed.flush()
    ck("only latest failed decision renders",WaexBottomSheet.shows,before+1)
    ck("latest message uses latest decision",WaexBottomSheet.lastMessage.contains("determine the installed WhatsApp version"),true)

    println("PASS: $checks runtime compatibility/evidence/queue presentation checks. Explicit Android and root doubles.")
}
