#!/usr/bin/env python3
"""Exercise the verbatim registry predicate and hook reader with the real bridge.

The BaseFeature.isEnabled Kotlin method is also compiled verbatim for A/B runs.
Platform IPC/Context are explicit endpoint fixtures. This does not install hooks,
compile licensing, send statuses or prove preservation of an actual WhatsApp status.
The platform fixtures come from the existing bridge contract test.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def body(source, signature):
    if source.count(signature) != 1:
        raise AssertionError('Expected one source method: ' + signature)
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 0
    for i in range(opening, len(source)):
        if source[i] == '{': depth += 1
        if source[i] == '}':
            depth -= 1
            if depth == 0: return source[start:i+1]
    raise AssertionError('Unterminated source method')


HARNESS = r'''package test;
import android.content.*;
import android.database.ContentObserver;
import android.net.Uri;
import android.os.Bundle;
import com.waenhancer.xposed.bridge.client.PreferenceBridgeClient;
POLICY_IMPORT
import java.lang.reflect.Proxy;
import java.util.*;
public final class StatusActivationChecks {
    static int checks, failures, unexpectedEndpointCalls, unexpectedPreferenceCalls;
    static void check(boolean ok, String label) {
        checks++;
        if (!ok) { failures++; System.out.println("FAIL: " + label); }
    }
    static class Resolver extends ContentResolver {
        final Map<String,Object> values = new HashMap<>();
        boolean unavailable;
        public void registerContentObserver(Uri uri, boolean descendants, ContentObserver observer) {
            if (!"content://com.waenhancer.hookprovider/preferences".equals(uri.path) || !descendants || observer == null)
                { unexpectedEndpointCalls++; throw new AssertionError("Unexpected observer registration"); }
        }
        public Bundle call(Uri uri, String method, String arg, Bundle extras) {
            if (!"content://com.waenhancer.hookprovider".equals(uri.path)
                    || !"get_all_preferences".equals(method) || arg != null || extras != null)
                { unexpectedEndpointCalls++; throw new AssertionError("Unexpected provider operation"); }
            if (unavailable) throw new SecurityException("Synthetic provider unavailable");
            Bundle result = new Bundle(), data = new Bundle();
            for (Map.Entry<String,Object> e: values.entrySet()) {
                Object v=e.getValue(); String k=e.getKey();
                if (v instanceof String) data.putString(k,(String)v);
                else if (v instanceof Boolean) data.putBoolean(k,(Boolean)v);
                else if (v instanceof Integer) data.putInt(k,(Integer)v);
                else if (v instanceof Long) data.putLong(k,(Long)v);
                else if (v instanceof Float) data.putFloat(k,(Float)v);
                else { unexpectedEndpointCalls++; throw new AssertionError("Unsupported provider fixture type"); }
            }
            result.putBundle("values",data); return result;
        }
    }
    static class Ctx extends Context {
        final String pkg; final Resolver resolver;
        Ctx(String pkg, Map<String,Object> values) { this.pkg=pkg; resolver=new Resolver(); resolver.values.putAll(values); }
        public String getPackageName() { return pkg; }
        public ContentResolver getContentResolver() { return resolver; }
    }
    static class Reader extends BaseFeatureProbe {
        Reader(Context context, SharedPreferences prefs) { super(context,prefs); }
        STATUS_METHOD
    }
    static boolean predicate(SharedPreferences prefs) { return REGISTRY_EXPRESSION; }
    static boolean registered(SharedPreferences prefs) {
        // FeatureRegistry.isEntryEnabled catches getter failures and returns false.
        try { return predicate(prefs); } catch (Throwable failure) { return false; }
    }
    static SharedPreferences strict(Map<String,Object> values) {
        return (SharedPreferences)Proxy.newProxyInstance(StatusActivationChecks.class.getClassLoader(),
            new Class<?>[]{SharedPreferences.class}, (proxy,method,args)-> {
                String name=method.getName();
                if (name.equals("getAll")) return Collections.unmodifiableMap(new HashMap<>(values));
                if (name.equals("contains")) return values.containsKey((String)args[0]);
                if (name.equals("getBoolean") || name.equals("getString")) {
                    Object v=values.get((String)args[0]); if(v==null) return args[1];
                    if(name.equals("getBoolean") && v instanceof Boolean) return v;
                    if(name.equals("getString") && v instanceof String) return v;
                    throw new ClassCastException("Synthetic strict preferences mismatch");
                }
                unexpectedPreferenceCalls++; throw new AssertionError("Unexpected strict preference call: "+name);
            });
    }
    static Map<String,Object> values(Object raw) {
        Map<String,Object> m=new HashMap<>(); m.put("anti_revoke",false); m.put("preserve_own_revoke",false);
        if(raw!=null)m.put("antirevokestatus",raw);return m;
    }
    static void both(Ctx ctx, SharedPreferences prefs, boolean expected, String label) {
        check(registered(prefs)==expected,label+"/registry");
        try {check(new Reader(ctx,prefs).isAntiRevokeStatusEnabled()==expected,label+"/hook-reader");}
        catch(Throwable failure) {check(false,label+"/hook-reader-threw-"+failure.getClass().getSimpleName());}
    }
    static void bridgeCase(Map<String,Object> data,String pkg,boolean expected,String label) {
        Ctx ctx=new Ctx(pkg,data); PreferenceBridgeClient bridge=new PreferenceBridgeClient(ctx,null);
        check("PROVIDER".equals(bridge.getLastSyncSource()),label+"/provider");
        both(ctx,bridge,expected,label);
    }
    public static void main(String[] args) {
        Object[] raw={null,"0","1",false,true,"false","TRUE",0,1,-1,2,0L,1L,4294967296L,0.5f,1.5f,"","bad","2"," true "};
        boolean[] expected={false,false,true,false,true,false,true,false,true,true,true,false,true,false,false,true,false,false,false,false};
        for(int i=0;i<raw.length;i++) {
            String label=(i==2?"canonical-one":"value-"+i);
            Map<String,Object> data=values(raw[i]);Ctx ctx=new Ctx("com.whatsapp",data);
            both(ctx,strict(data),expected[i],label+"/strict");
            bridgeCase(data,"com.whatsapp",expected[i],label+"/bridge");
        }
        // Other activation controls retain their own independent Boolean contract.
        for(boolean anti:new boolean[]{false,true})for(boolean own:new boolean[]{false,true})for(String status:new String[]{"0","1"}) {
            Map<String,Object> data=values(status);data.put("anti_revoke",anti);data.put("preserve_own_revoke",own);
            Ctx ctx=new Ctx("com.whatsapp",data);PreferenceBridgeClient bridge=new PreferenceBridgeClient(ctx,null);
            check(registered(bridge)==(anti||own||status.equals("1")),"independent-activation-controls");
        }
        Map<String,Object> data=values("1");data.put("module_config_mode","Per Target App");
        data.put("com.whatsapp:antirevokestatus","0");data.put("com.whatsapp.w4b:antirevokestatus","1");
        bridgeCase(data,"com.whatsapp",false,"per-target-explicit-off");
        bridgeCase(data,"com.whatsapp.w4b",true,"per-target-business-on");
        bridgeCase(data,"example.clone",true,"per-target-missing-override-inherits-universal");
        data.put("com.whatsapp:antirevokestatus","bad");
        bridgeCase(data,"com.whatsapp",false,"invalid-own-value-does-not-revive-universal");
        data.remove("antirevokestatus");data.put("module_config_mode","Universal");
        bridgeCase(data,"com.whatsapp",false,"universal-missing-key-does-not-borrow-business");
        data=values(null);data.put("module_config_mode","Universal");
        data.put("com.whatsapp.w4b:antirevokestatus",true);data.put("anti_revoke",true);
        Ctx borrowedCtx=new Ctx("com.whatsapp",data);PreferenceBridgeClient borrowed=new PreferenceBridgeClient(borrowedCtx,null);
        check(registered(borrowed),"separate-message-control-still-registers");
        check(!new Reader(borrowedCtx,borrowed).isAntiRevokeStatusEnabled(),"message-control-does-not-enable-business-status-setting");
        data=values("1");Ctx ctx=new Ctx("com.whatsapp",data);PreferenceBridgeClient bridge=new PreferenceBridgeClient(ctx,null);
        both(ctx,bridge,true,"before-refresh");ctx.resolver.values.put("antirevokestatus","0");bridge.syncPreferences();
        both(ctx,bridge,false,"after-disable-refresh");
        both(ctx,new PreferenceBridgeClient(ctx,null),false,"recreated-bridge-stays-off");
        ctx.resolver.values.put("module_config_mode","Per Target App");ctx.resolver.values.put("com.whatsapp:antirevokestatus","1");bridge.syncPreferences();
        both(ctx,bridge,true,"mode-change-resolves-own-on");
        ctx.resolver.values.put("module_config_mode","Universal");bridge.syncPreferences();
        both(ctx,bridge,false,"mode-change-restores-universal-off");
        Map<String,Object> disk=values("1");disk.put("module_config_mode","Per Target App");disk.put("com.whatsapp:antirevokestatus","0");
        Ctx unavailable=new Ctx("com.whatsapp",Collections.emptyMap());unavailable.resolver.unavailable=true;
        PreferenceBridgeClient fallback=new PreferenceBridgeClient(unavailable,strict(disk));
        check("DISK_FALLBACK".equals(fallback.getLastSyncSource()),"disk-fallback-source");
        both(unavailable,fallback,false,"disk-fallback-retains-own-off");
        check(unexpectedEndpointCalls==0,"no-swallowed-unexpected-endpoint-calls");
        check(unexpectedPreferenceCalls==0,"no-swallowed-unexpected-preference-calls");
        System.out.println("STATUS_ACTIVATION checks="+checks+" failures="+failures);
        if(failures!=0)throw new AssertionError("Status activation acceptance failed: "+failures);
    }
}
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--platform-fixture',type=Path)
    p.add_argument('--out',type=Path)
    args=p.parse_args();root=args.repo.resolve();src=root/'app/src/main/java/com/waenhancer'
    fixture=args.platform_fixture or root/'qa/test_bridge_contract.py'
    paths={'registry':src/'xposed/core/FeatureRegistry.java','hook':src/'xposed/features/privacy/AntiRevokeHook.java',
           'base':src/'xposed/core/BaseFeature.kt','bridge':src/'xposed/bridge/client/PreferenceBridgeClient.java',
           'policy':src/'config/StatusAntiRevokePolicy.java','fixture':fixture}
    texts={k:v.read_text(encoding='utf-8') for k,v in paths.items() if v.exists()}
    match=re.search(r'registerFeature\(AntiRevokeHook\.class, "Privacy",\s*\(\) -> (.*?),\s*\(\) -> new AntiRevokeHook',texts['registry'],re.S)
    if not match:raise AssertionError('One AntiRevoke registry predicate required')
    stubs=None
    for node in ast.parse(texts['fixture']).body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='STUBS' for t in node.targets):stubs=ast.literal_eval(node.value)
    if stubs is None:raise AssertionError('Missing explicit platform fixtures')
    stubs={k:v for k,v in stubs.items() if not k.startswith('test/')}
    # Compile the existing full method; do not substitute a permissive Boolean adapter.
    base_method=body(texts['base'],'protected fun isEnabled(key: String, def: Boolean = false): Boolean')
    kotlin='package test\nimport android.content.*\nopen class BaseFeatureProbe(@JvmField protected val context:Context,@JvmField protected val prefs:SharedPreferences) {\n'+base_method+'\n}\n'
    harness=HARNESS.replace('POLICY_IMPORT','import com.waenhancer.config.StatusAntiRevokePolicy;' if 'policy' in texts else '')
    harness=harness.replace('STATUS_METHOD',body(texts['hook'],'private boolean isAntiRevokeStatusEnabled()')).replace('REGISTRY_EXPRESSION',match.group(1))
    java=shutil.which('java');javac=shutil.which('javac');kotlinc=shutil.which('kotlinc')
    if not java or not javac or not kotlinc:raise RuntimeError('JDK17+ and Kotlin compiler required')
    kotlin_home=Path(os.environ['KOTLIN_HOME']) if os.environ.get('KOTLIN_HOME') else Path(kotlinc).resolve().parents[1]
    runtime=kotlin_home/'lib/kotlin-stdlib.jar'
    if not runtime.is_file():raise RuntimeError('Explicit KOTLIN_HOME stdlib required')
    receipt={'scope':'Verbatim registry predicate, hook reader and Kotlin BaseFeature method; actual PreferenceBridgeClient; controlled IPC/platform endpoints; no hook installation',
             'source_sha256':{k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in paths.items() if v.exists()},'runs':[]}
    if args.out:args.out.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='waex-status-activation-') as folder:
        temp=Path(folder);classes=temp/'classes';classes.mkdir();files=[]
        for name,source in stubs.items():
            f=temp/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(source,encoding='utf-8');files.append(str(f))
        kt=temp/'BaseFeatureProbe.kt';kt.write_text(kotlin,encoding='utf-8');j=temp/'StatusActivationChecks.java';j.write_text(harness,encoding='utf-8')
        cp=os.pathsep.join([str(classes),str(runtime)])
        commands=[('platform',[javac,'--release','17','-d',str(classes),*files]),
                  ('base-method',[kotlinc,str(kt),'-classpath',str(classes),'-d',str(classes)]),
                  ('production-readers',[javac,'--release','17','-cp',cp,'-d',str(classes),str(j),str(paths['bridge']),*([str(paths['policy'])] if 'policy' in texts else [])]),
                  ('behavior',[java,'-cp',cp,'test.StatusActivationChecks'])]
        exit_code=0
        for name,command in commands:
            result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
            output=result.stdout+result.stderr;print(output,end='')
            receipt['runs'].append({'id':name,'command':command,'exit':result.returncode,'output_sha256':hashlib.sha256(output.encode()).hexdigest()})
            if args.out:(args.out/(name+'.log')).write_text(output,encoding='utf-8')
            if result.returncode:exit_code=result.returncode;break
    receipt['status']='PASS' if exit_code==0 else 'FAIL'
    if args.out:(args.out/'result.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':receipt['status'],'scope':receipt['scope']}))
    raise SystemExit(exit_code)


if __name__=='__main__':main()
