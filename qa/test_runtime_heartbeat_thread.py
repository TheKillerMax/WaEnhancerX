#!/usr/bin/env python3
"""Current deferred reporting, without the retired heartbeat.

Compile exact MainHook declarations/methods with the complete production dispatcher.
FeatureRegistry's complete reporting method is extracted unchanged as well.
Android/Bundle/JSON and Binder endpoints are strict JVM doubles; the private
registry constructor is not compiled. Wiring is checked separately in source.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MAIN = Path('app/src/main/java/com/waenhancer/xposed/MainHook.java')
QUEUE = Path('app/src/main/java/com/waenhancer/xposed/core/RuntimeReportDispatcher.java')
REGISTRY = Path('app/src/main/java/com/waenhancer/xposed/core/FeatureRegistry.java')
CASES = ['deferred', 'latest_order', 'context_business', 'context_fallback', 'worker',
         'repeated_release', 'later', 'install_once', 'resume', 'late', 'fallback',
         'listener_failure', 'slow', 'failure', 'receiver',
         'blocked_catalog', 'incremental_catalog', 'catalog_failure']


def extract_braced(source, marker):
    if source.count(marker) != 1:
        raise AssertionError('Expected one production declaration: ' + marker)
    start = source.index(marker)
    opening = source.index('{', start)
    depth = 0
    for index in range(opening, len(source)):
        depth += (source[index] == '{') - (source[index] == '}')
        if depth == 0:
            return source[start:index + 1]
    raise AssertionError('Unbalanced declaration: ' + marker)


def extract(source):
    if re.search(r'HEARTBEAT_|scheduleWithFixedDelay|scheduleAtFixedRate', source):
        raise AssertionError('Retired periodic reporting was reintroduced')
    start = source.index('private static final RuntimeReportDispatcher REPORT_DISPATCHER')
    end = source.index('/** Optional observations', start)
    fields = [source[start:end]]
    for name in ('sRuntimeStatus', 'sBridgeStatus', 'sRuntimeError'):
        match = re.search(r'private static volatile String ' + name + r'[^;]*;', source)
        if not match:
            raise AssertionError('Missing runtime state ' + name)
        fields.append(match.group(0))
    permission = re.search(r'public static final String RESTART_PERMISSION\s*=[^;]*;', source)
    if not permission:
        raise AssertionError('Missing report receiver permission')
    fields.append(permission.group(0))
    methods = [extract_braced(source, 'private static void ' + name + '(')
               for name in ('reportTargetRuntime', 'queueDeferred', 'releaseDeferredReporting',
                            'installDeferredReporting', 'registerHookReportReceiver')]
    for kind in ('PACKAGE', 'HEALTH', 'UPDATE_CHECK'):
        if 'queueDeferred(Kind.' + kind not in source:
            raise AssertionError('Production report kind is disconnected: ' + kind)
    return '\n'.join([*fields, *methods])



def validate_wiring(main, registry):
    expected = 'new FeatureRegistry(appContext, lpparam.classLoader, bridgeClient, REPORT_DISPATCHER)'
    if main.count(expected) != 1 or 'queueDeferred(Kind.HOOKS' in main:
        raise AssertionError('MainHook must inject one shared dispatcher without double catalogue enqueue')
    compatible = extract_braced(registry, 'public FeatureRegistry(@NonNull Context context, @NonNull ClassLoader classLoader, @NonNull SharedPreferences prefs)')
    if 'this(context, classLoader, prefs,' not in compatible or 'new RuntimeReportDispatcher(' not in compatible:
        raise AssertionError('Three-argument constructor must retain a bounded default dispatcher')
    if 'this.reportDispatcher = java.util.Objects.requireNonNull(reportDispatcher);' not in registry:
        raise AssertionError('Injected dispatcher is not retained')
    if registry.count('reportInjectedHooks(reportingContext, reportingPackage);') != 3:
        raise AssertionError('Lazy installation/disposal report paths changed')
    if extract_braced(registry, 'private void installLocked(').count('reportInjectedHooks(') != 2:
        raise AssertionError('Incremental installation report paths changed')
    if extract_braced(registry, 'private void disposeLazyEntry(').count('reportInjectedHooks(') != 1:
        raise AssertionError('Incremental disposal report path changed')
    if 'HOOK_REPORT_EXECUTOR' in registry:
        raise AssertionError('Unbounded secondary catalogue sender remains')
    method = extract_braced(registry, 'public void reportInjectedHooks(')
    if method.count('reportDispatcher.submitLatest(RuntimeReportDispatcher.Kind.HOOKS, () -> {') != 1:
        raise AssertionError('Actual catalogue Binder operation is not bounded')
    return method

JAVA = r'''
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import com.waenhancer.xposed.core.RuntimeReportDispatcher;
import com.waenhancer.xposed.core.RuntimeReportDispatcher.Kind;
@interface NonNull {}
class Context {
    static final int RECEIVER_EXPORTED=2;
    Context app=this; BroadcastReceiver receiver; String permission; Integer flags;
    Context getApplicationContext(){return app;}
    Object registerReceiver(BroadcastReceiver r,IntentFilter filter,String p,Object handler){
        receiver=r;permission=p;flags=null;return null;
    }
    Object registerReceiver(BroadcastReceiver r,IntentFilter filter,String p,Object handler,int f){
        registerReceiver(r,filter,p,handler);flags=f;return null;
    }
}
class Intent {final String pkg;Intent(String p){pkg=p;}String getStringExtra(String key){return "PKG".equals(key)?pkg:null;}}
class IntentFilter {IntentFilter(String action){if(!"com.waenhancer.action.REPORT_HOOKS".equals(action))throw new AssertionError("wrong action");}}
abstract class BroadcastReceiver {public abstract void onReceive(Context c,Intent i);}
class Build {static class VERSION {static int SDK_INT=34;}}
class Activity {}
class Looper {static final Looper MAIN=new Looper();static Looper getMainLooper(){return MAIN;}}
class Handler {
    static final List<Runnable> callbacks=new ArrayList<>();
    Handler(Looper looper){if(looper!=Looper.MAIN)throw new AssertionError("wrong looper");}
    boolean postDelayed(Runnable task,long delay){
        if(delay!=5000L)throw new AssertionError("wrong fallback delay");callbacks.add(task);return true;
    }
}
class ActivityTracker {
    interface ActivityListener {void onActivityCreated(Activity a);void onActivityResumed(Activity a);void onActivityStopped(Activity a);void onActivityDestroyed(Activity a);}
    static final List<ActivityListener> listeners=new ArrayList<>();
    static Activity current;static boolean fail;
    static void addListener(ActivityListener listener){if(fail)throw new IllegalStateException("fixture listener");listeners.add(listener);}
    static Activity getCurrentActivity(){return current;}
}
class HookErrors {
    static final List<Throwable> failures=new CopyOnWriteArrayList<>();
    static void swallowed(String site,Throwable error){if(!"MainHook".equals(site))throw new AssertionError("wrong diagnostic owner");failures.add(error);}
}
class XposedBridge {
    static final List<String> logs=new CopyOnWriteArrayList<>();
    static void log(String text){logs.add(text);}
}
class Bundle {
    final Map<String,Object> values=new LinkedHashMap<>();
    void putString(String key,String value){values.put(key,value);}
    void putLong(String key,long value){values.put(key,value);}
    String getString(String key){return (String)values.get(key);}
    long getLong(String key){return (Long)values.get(key);}
}
class JSONObject {
    final Map<String,Object> values=new LinkedHashMap<>();
    JSONObject put(String key,Object value){values.put(key,value);return this;}
    static String quote(Object value){return value==null?"null":"\""+value.toString().replace("\\","\\\\").replace("\"","\\\"")+"\"";}
    public String toString(){List<String> items=new ArrayList<>();values.forEach((k,v)->items.add(quote(k)+":"+quote(v)));return "{"+String.join(",",items)+"}";}
}
class JSONArray {
    final List<JSONObject> values=new ArrayList<>();
    JSONArray put(JSONObject value){values.add(value);return this;}
    public String toString(){List<String> items=new ArrayList<>();values.forEach(v->items.add(v.toString()));return "["+String.join(",",items)+"]";}
}
class FeatureRegistry {
    static void runInline(Runnable task){task.run();} // Compiled inline-I/O mutant only.
    static final ExecutorService LEGACY_EXECUTOR=Executors.newSingleThreadExecutor(task->{
        Thread t=new Thread(task,"fixture-legacy-sender");t.setDaemon(true);return t;
    }); // Used only by the compiled secondary-sender regression.
    static class FeatureEntry {String name="Fixture Hook",className="FixtureHook",category="Privacy",status="ACTIVE",error;}
    private final List<FeatureEntry> features=new ArrayList<>(List.of(new FeatureEntry()));
    private final String hookingMode="fixture-mode";
    private final RuntimeReportDispatcher reportDispatcher;
    FeatureRegistry(RuntimeReportDispatcher dispatcher){reportDispatcher=dispatcher;}
    void state(String value){features.get(0).status=value;}
    void error(String value){features.get(0).error=value;}
    /* REGISTRY_REPORT */
}
class HookProviderIpc {
    record Call(Context context,String method,String pkg,Bundle extras,Thread worker){}
    static final List<Call> reports=new CopyOnWriteArrayList<>();
    static final CountDownLatch entered=new CountDownLatch(1);
    static volatile CountDownLatch hold;static volatile boolean failNext;
    static String status(Call call){
        String json=call.extras().getString("hooks_json"),prefix="\"status\":\"";
        int start=json.indexOf(prefix)+prefix.length();
        if(start<prefix.length())throw new AssertionError("missing captured status");
        return json.substring(start,json.indexOf('"',start));
    }
    static Bundle call(Context context,String method,String pkg,Bundle extras){
        if(!"register_injected_hooks".equals(method))throw new AssertionError("unexpected provider method");
        if(!pkg.equals(extras.getString("package"))||!"fixture-mode".equals(extras.getString("hooking_mode"))
                ||extras.getLong("timestamp")<=0)throw new AssertionError("catalogue payload changed");
        WhatsAppPackageDetector.maxActive.accumulateAndGet(WhatsAppPackageDetector.active.incrementAndGet(),Math::max);
        Call call=new Call(context,method,pkg,extras,Thread.currentThread());reports.add(call);entered.countDown();
        try{
            CountDownLatch gate=hold;
            if(gate!=null&&!gate.await(5,TimeUnit.SECONDS))throw new AssertionError("catalogue Binder gate timed out");
            if(failNext){failNext=false;throw new IllegalStateException("fixture catalogue failure");}
            WhatsAppPackageDetector.order.add("hooks:"+status(call));return new Bundle();
        }catch(InterruptedException interrupted){Thread.currentThread().interrupt();throw new AssertionError(interrupted);}
        finally{WhatsAppPackageDetector.active.decrementAndGet();}
    }
}
class WhatsAppPackageDetector {
    record Report(Context context,String pkg,String state,String bridge,String error,Thread worker){}
    static final List<Report> reports=new CopyOnWriteArrayList<>();
    static final List<String> order=new CopyOnWriteArrayList<>();
    static final AtomicInteger active=new AtomicInteger(),maxActive=new AtomicInteger();
    static final CountDownLatch entered=new CountDownLatch(1);
    static volatile CountDownLatch hold;static volatile boolean failNext;
    static void reportRuntimeHealth(Context context,String pkg,String state,String bridge,String error){
        maxActive.accumulateAndGet(active.incrementAndGet(),Math::max);
        try {
            reports.add(new Report(context,pkg,state,bridge,error,Thread.currentThread()));order.add("health:"+state);entered.countDown();
            CountDownLatch gate=hold;
            if(gate!=null&&!gate.await(5,TimeUnit.SECONDS))throw new AssertionError("provider gate timed out");
            if(failNext){failNext=false;throw new IllegalStateException("fixture provider");}
        } catch(InterruptedException interrupted){Thread.currentThread().interrupt();throw new AssertionError(interrupted);}
        finally {active.decrementAndGet();}
    }
}
class MainHook {
    /* PRODUCTION */
    static void report(Context c,String pkg,String state,String bridge,String error){reportTargetRuntime(c,pkg,state,bridge,error);}
    static void report(String state){report(new Context(),"com.whatsapp",state,"PROVIDER",null);}
    static void release(){releaseDeferredReporting();}
    static void install(){installDeferredReporting(new Context());}
    static void submit(Kind kind,Runnable task){queueDeferred(kind,task);}
    static void hooks(Context c,FeatureRegistry registry){registerHookReportReceiver(c,"com.whatsapp",registry);}
    static FeatureRegistry registry(){return new FeatureRegistry(REPORT_DISPATCHER);}
    static String state(){return sRuntimeStatus+"/"+sBridgeStatus+"/"+sRuntimeError;}
    static void flush()throws Exception{
        CountDownLatch drained=new CountDownLatch(1);queueDeferred(Kind.UPDATE_CHECK,drained::countDown);
        if(!drained.await(3,TimeUnit.SECONDS))throw new AssertionError("released queue did not drain");
    }
}
public final class RuntimeReportingChecks {
    static int checks;
    static final Thread caller=Thread.currentThread();
    static void check(boolean value,String reason){checks++;if(!value)throw new AssertionError(reason);}
    static List<WhatsAppPackageDetector.Report> records(){return WhatsAppPackageDetector.reports;}
    static void awaitEntry()throws Exception{check(WhatsAppPackageDetector.entered.await(2,TimeUnit.SECONDS),"provider never entered");}
    static void run(String name)throws Exception{
        switch(name){
            case "deferred":
                MainHook.report(new Context(),"com.whatsapp","READY","FAILED","type");
                check(MainHook.state().equals("READY/FAILED/type"),"local observation not updated immediately");
                check(!WhatsAppPackageDetector.entered.await(100,TimeUnit.MILLISECONDS),"provider ran before lifecycle release");break;
            case "latest_order":
                MainHook.submit(Kind.PACKAGE,()->WhatsAppPackageDetector.order.add("package"));
                MainHook.report("INITIALIZING");MainHook.registry().reportInjectedHooks(new Context(),"com.whatsapp");MainHook.report("READY");
                MainHook.release();MainHook.flush();
                check(WhatsAppPackageDetector.order.equals(List.of("package","hooks:ACTIVE","health:READY")),"coalesced report lost captured state or causal order");break;
            case "context_business":
                Context owner=new Context(),app=new Context();owner.app=app;
                MainHook.report(owner,"com.whatsapp.w4b","READY","PROVIDER","type");MainHook.release();MainHook.flush();
                var r=records().get(0);check(r.context()==app&&r.pkg().equals("com.whatsapp.w4b")&&r.error().equals("type"),"context or package changed");break;
            case "context_fallback":
                Context fallback=new Context();fallback.app=null;MainHook.report(fallback,"com.whatsapp","READY","PROVIDER",null);
                MainHook.release();MainHook.flush();check(records().get(0).context()==fallback,"null application context lost owner");break;
            case "worker":
                MainHook.release();MainHook.report("FIRST");MainHook.flush();MainHook.report("SECOND");MainHook.flush();
                Thread worker=records().get(0).worker();
                check(worker!=caller&&worker.isDaemon()&&worker.getPriority()==Thread.MIN_PRIORITY&&worker.getName().equals("WAEX-Report"),"report I/O worker contract violated");
                check(records().get(1).worker()==worker,"report worker was not reused");break;
            case "repeated_release":
                MainHook.report("ONCE");for(int i=0;i<10;i++)MainHook.release();MainHook.flush();check(records().size()==1,"release duplicated report");break;
            case "later":
                MainHook.release();MainHook.report("LATER");MainHook.flush();check(records().size()==1&&records().get(0).worker()!=caller,"post-release report missing or inline");break;
            case "install_once":
                MainHook.install();MainHook.install();check(ActivityTracker.listeners.size()==1&&Handler.callbacks.size()==1,"report installation duplicated lifecycle work");break;
            case "resume":
                MainHook.report("RESUME");MainHook.install();var listener=ActivityTracker.listeners.get(0);
                listener.onActivityCreated(new Activity());listener.onActivityStopped(new Activity());listener.onActivityDestroyed(new Activity());
                check(!WhatsAppPackageDetector.entered.await(100,TimeUnit.MILLISECONDS),"non-resume lifecycle released reporting");
                listener.onActivityResumed(new Activity());MainHook.flush();check(records().size()==1,"resume lost report");break;
            case "late":
                MainHook.report("LATE");ActivityTracker.current=new Activity();MainHook.install();MainHook.flush();check(records().size()==1,"late injection stayed deferred");break;
            case "fallback":
                MainHook.report("FALLBACK");MainHook.install();Handler.callbacks.get(0).run();MainHook.flush();
                check(records().size()==1&&records().get(0).worker()!=caller,"fallback lost report or ran I/O inline");break;
            case "listener_failure":
                MainHook.report("RECOVER");ActivityTracker.fail=true;MainHook.install();
                check(HookErrors.failures.size()==1,"listener failure lost diagnostic");Handler.callbacks.get(0).run();MainHook.flush();
                check(records().size()==1,"listener failure disabled fallback");break;
            case "slow":
                WhatsAppPackageDetector.hold=new CountDownLatch(1);MainHook.release();MainHook.report("SLOW");awaitEntry();
                try {for(int i=0;i<1000;i++)MainHook.report("LAST:"+i);check(records().size()==1,"slow provider spawned parallel reporting");}
                finally {WhatsAppPackageDetector.hold.countDown();}
                MainHook.flush();check(records().size()==2&&records().get(1).state().equals("LAST:999")&&WhatsAppPackageDetector.maxActive.get()==1,"blocked report backlog not bounded to latest");break;
            case "failure":
                WhatsAppPackageDetector.failNext=true;MainHook.release();MainHook.report("FAIL");awaitEntry();MainHook.report("RECOVER");MainHook.flush();
                check(records().size()==2&&records().get(1).state().equals("RECOVER")&&HookErrors.failures.size()==1,"provider failure lost subsequent report or diagnostic");break;
            case "receiver":
                Context context=new Context();FeatureRegistry registry=MainHook.registry();MainHook.hooks(context,registry);
                check(context.receiver!=null&&"com.waenhancer.permission.RESTART_TARGET".equals(context.permission)&&Objects.equals(context.flags,Context.RECEIVER_EXPORTED),"report receiver permission or API33 registration changed");
                context.receiver.onReceive(context,new Intent("com.whatsapp.w4b"));
                check(HookProviderIpc.reports.isEmpty(),"foreign package triggered hook report");
                for(int i=0;i<1000;i++){registry.state("LATEST:"+i);context.receiver.onReceive(context,new Intent("com.whatsapp"));}
                registry.state("NOT_SUBMITTED");
                check(HookProviderIpc.reports.isEmpty(),"hook Binder escaped deferred reporting");MainHook.release();MainHook.flush();
                var sent=HookProviderIpc.reports.get(0);
                check(HookProviderIpc.reports.size()==1&&sent.worker()!=caller&&sent.context()==context&&sent.pkg().equals("com.whatsapp")
                    &&HookProviderIpc.status(sent).equals("LATEST:999"),"real catalogue snapshot/recipient/coalescing changed");
                Build.VERSION.SDK_INT=32;Context legacy=new Context();MainHook.hooks(legacy,registry);
                check(legacy.receiver!=null&&legacy.flags==null&&"com.waenhancer.permission.RESTART_TARGET".equals(legacy.permission),"legacy receiver permission changed");break;
            case "blocked_catalog":
                Context catalogContext=new Context();FeatureRegistry catalog=MainHook.registry();MainHook.hooks(catalogContext,catalog);
                HookProviderIpc.hold=new CountDownLatch(1);MainHook.release();
                catalog.state("FIRST");catalogContext.receiver.onReceive(catalogContext,new Intent("com.whatsapp"));
                check(HookProviderIpc.entered.await(2,TimeUnit.SECONDS),"real catalogue Binder never entered");
                try{
                    for(int i=0;i<10000;i++){catalog.state("REPLACED:"+i);catalogContext.receiver.onReceive(catalogContext,new Intent("com.whatsapp"));}
                    MainHook.report("READY");
                    catalog.state("TERMINAL");catalogContext.receiver.onReceive(catalogContext,new Intent("com.whatsapp"));
                    check(HookProviderIpc.reports.size()==1,"blocked catalogue spawned replacement Binder workers");
                    check(!WhatsAppPackageDetector.entered.await(1,TimeUnit.SECONDS),"READY overtook blocked catalogue Binder work");
                }finally{HookProviderIpc.hold.countDown();}
                MainHook.flush();
                check(HookProviderIpc.reports.size()==2&&HookProviderIpc.status(HookProviderIpc.reports.get(1)).equals("TERMINAL"),
                    "blocked catalogue accumulated snapshots instead of keeping latest");
                check(WhatsAppPackageDetector.order.equals(List.of("hooks:FIRST","hooks:TERMINAL","health:READY")),
                    "catalogue replacement moved actual Binder completion behind READY");
                check(WhatsAppPackageDetector.maxActive.get()==1&&HookProviderIpc.reports.get(0).worker()==records().get(0).worker(),
                    "catalogue and health did not share one serial Binder worker");break;
            case "incremental_catalog":
                FeatureRegistry incremental=MainHook.registry();Context current=new Context();
                incremental.state("WAITING");incremental.reportInjectedHooks(current,"com.whatsapp");
                incremental.state("ACTIVE");incremental.reportInjectedHooks(current,"com.whatsapp");
                MainHook.release();MainHook.flush();
                incremental.state("FAILED");incremental.error("BINDING_UNAVAILABLE");incremental.reportInjectedHooks(current,"com.whatsapp");MainHook.flush();
                incremental.state("WAITING");incremental.error(null);incremental.reportInjectedHooks(current,"com.whatsapp");MainHook.flush();
                check(HookProviderIpc.reports.size()==3&&HookProviderIpc.status(HookProviderIpc.reports.get(0)).equals("ACTIVE")
                    &&HookProviderIpc.status(HookProviderIpc.reports.get(1)).equals("FAILED")
                    &&HookProviderIpc.status(HookProviderIpc.reports.get(2)).equals("WAITING"),"incremental catalogue states were lost");
                check(HookProviderIpc.reports.get(1).extras().getString("hooks_json").contains("BINDING_UNAVAILABLE")
                    &&!HookProviderIpc.reports.get(2).extras().getString("hooks_json").contains("\"error\""),"catalogue error snapshot became stale");break;
            case "catalog_failure":
                FeatureRegistry failing=MainHook.registry();HookProviderIpc.failNext=true;
                failing.reportInjectedHooks(new Context(),"com.whatsapp");MainHook.report("READY");MainHook.release();MainHook.flush();
                check(XposedBridge.logs.size()==1&&records().size()==1,"catalogue failure stranded health or lost diagnostic");
                failing.state("RECOVERED");failing.reportInjectedHooks(new Context(),"com.whatsapp");MainHook.flush();
                check(HookProviderIpc.reports.size()==2&&HookProviderIpc.status(HookProviderIpc.reports.get(1)).equals("RECOVERED"),"catalogue failure poisoned future delivery");break;
            default:throw new IllegalArgumentException(name);
        }
    }
    public static void main(String[] args)throws Exception{
        try{run(args[0]);System.out.println("PASS "+args[0]+": "+checks+" checks");}
        finally{if(WhatsAppPackageDetector.hold!=null)WhatsAppPackageDetector.hold.countDown();if(HookProviderIpc.hold!=null)HookProviderIpc.hold.countDown();}
    }
}
'''


def run(source, registry, out, cases):
    out.mkdir(parents=True)
    production = extract(source)
    generated = out / 'RuntimeReportingChecks.java'
    registry_report = extract_braced(registry, 'public void reportInjectedHooks(')
    generated.write_text(JAVA.replace('/* PRODUCTION */', production).replace('/* REGISTRY_REPORT */', registry_report), encoding='utf-8')
    result = subprocess.run(['javac', '--release', '17', '-d', str(out),
        str(ROOT / QUEUE), str(generated)], text=True, capture_output=True, timeout=30)
    (out / 'compile.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    if result.returncode:
        raise RuntimeError('Compilation failed, not behavioral evidence: ' + str(out))
    rows = []
    for case in cases:
        result = subprocess.run(['java', '-cp', str(out), 'RuntimeReportingChecks', case],
                                text=True, capture_output=True, timeout=12)
        output = result.stdout + result.stderr
        (out / (case + '.log')).write_text(output, encoding='utf-8')
        rows.append({'case': case, 'exit': result.returncode, 'output': output})
    return {'cases': rows, 'extracted_sha256': hashlib.sha256(production.encode()).hexdigest(),
            'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'registry_method_sha256': hashlib.sha256(registry_report.encode()).hexdigest(),
            'registry_source_sha256': hashlib.sha256(registry.encode()).hexdigest()}


def execute(out):
    source = (ROOT / MAIN).read_text(encoding='utf-8')
    registry = (ROOT / REGISTRY).read_text(encoding='utf-8')
    validate_wiring(source, registry)
    candidate = run(source, registry, out / 'candidate', CASES)
    if any(row['exit'] for row in candidate['cases']):
        print(json.dumps(candidate, indent=2));raise AssertionError('Current reporting contract failed')
    mutants = []
    for label, before, after, case, expected in (
        ('premature-release', 'HookErrors.swallowed("MainHook", failure), false);',
         'HookErrors.swallowed("MainHook", failure), true);', 'deferred', 'provider ran before lifecycle release'),
        ('inline-io', 'REPORT_DISPATCHER.submitLatest(kind, task);', 'task.run();',
         'worker', 'report I/O worker contract violated'),
        ('missing-release', 'REPORT_DISPATCHER.release();', '/* lost release */',
         'fallback', 'released queue did not drain'),
    ):
        if source.count(before) != 1:
            raise AssertionError('Mutation anchor changed: ' + label)
        result = run(source.replace(before, after), registry, out / label, [case])
        row = result['cases'][0]
        if row['exit'] == 0 or 'AssertionError: ' + expected not in row['output']:
            raise AssertionError('Mutation was not rejected at its intended assertion: ' + label)
        mutants.append({'label': label, 'result': result})
    registry_mutants = []
    for label, replacement, case, expected in (
        ('secondary-catalogue-sender', 'LEGACY_EXECUTOR.execute(() -> {', 'blocked_catalog',
         'READY overtook blocked catalogue Binder work'),
        ('inline-catalogue-binder', 'runInline(() -> {', 'receiver',
         'hook Binder escaped deferred reporting'),
    ):
        before = 'reportDispatcher.submitLatest(RuntimeReportDispatcher.Kind.HOOKS, () -> {'
        if registry.count(before) != 1:
            raise AssertionError('Catalogue mutation anchor changed')
        modified = registry.replace(before, replacement)
        result = run(source, modified, out / label, [case])
        row = result['cases'][0]
        if row['exit'] == 0 or 'AssertionError: ' + expected not in row['output']:
            raise AssertionError('Catalogue mutation did not fail behaviorally: ' + label)
        registry_mutants.append({'label': label, 'result': result})
    source_controls = []
    for label, modified_main, modified_registry in (
        ('unshared-constructor', source.replace('bridgeClient, REPORT_DISPATCHER)', 'bridgeClient)'), registry),
        ('lost-incremental-report', source, registry.replace('reportInjectedHooks(reportingContext, reportingPackage);', '/* missing incremental report */', 1)),
    ):
        try:
            validate_wiring(modified_main, modified_registry)
        except AssertionError as expected:
            source_controls.append({'label': label, 'rejected': str(expected), 'scope': 'source wiring control, not compiled behavior'})
        else:
            raise AssertionError('Wiring control was not rejected: ' + label)
    report = {'candidate': candidate, 'mutants': mutants, 'registry_mutants': registry_mutants, 'source_controls': source_controls,
              'dispatcher_sha256': hashlib.sha256((ROOT / QUEUE).read_bytes()).hexdigest(),
              'fixture_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'scope': 'Exact MainHook reporting/receiver methods + exact FeatureRegistry reporting method + complete dispatcher. Android/Bundle/JSON/provider are strict JVM substitutes. Private registry construction is not compiled; three-argument compatibility, shared injection and incremental callers are source-checked.'}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('PASS: 18 reporting scenarios including actual catalogue sender; 5 compiled causal mutants; 2 source wiring controls')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.out:
        args.out.mkdir(parents=True)
        execute(args.out)
    else:
        with tempfile.TemporaryDirectory(prefix='waex-deferred-reporting-') as directory:
            execute(Path(directory))


if __name__ == '__main__':
    main()
