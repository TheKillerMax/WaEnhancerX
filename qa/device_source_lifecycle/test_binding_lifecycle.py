#!/usr/bin/env python3
"""Execute exact getView callback/bind pipeline with explicit controlled dependencies."""
from pathlib import Path
from datetime import datetime, timezone
import argparse,hashlib,json,re,shutil,subprocess,sys
import test_listener_ownership as common

ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT.parents[1]

def build(raw):
    text=raw.decode();header=(ROOT/"ListenerOwnershipProbe.java.template").read_text().split("/* EXACT_SOURCE_FRAGMENTS */")[0]
    header=header.replace("ListenerOwnershipProbe","BindingLifecycleProbe")
    header=header.replace("import java.util.*;","import java.util.*;\nimport java.lang.reflect.*;\nimport java.util.function.Consumer;\nimport java.util.regex.Pattern;")
    header=header.replace("static final class Context {}",'''static final class Context {
        final Resources resources=new Resources();Resources getResources(){return resources;}String getPackageName(){return "com.whatsapp";}
    }
    static final class Resources {
        int getIdentifier(String name,String kind,String owner){return name.equals("date")?91:name.equals("date_wrapper")?92:0;}
        String getResourceEntryName(int id){return id==91?"date":id==92?"date_wrapper":"other";}
    }
    static final class TextUtils {static boolean isEmpty(String text){return text==null||text.isEmpty();}}
    static final class ViewGroup extends View {
        final List<View> children=new ArrayList<>();void add(View view){children.add(view);}int getChildCount(){return children.size();}View getChildAt(int i){return children.get(i);}
        @Override View findViewById(int value){if(getId()==value)return this;for(View v:children){View found=v.findViewById(value);if(found!=null)return found;}return null;}
    }''')
    header=header.replace("static class View {",'''static class View {
        static final int NO_ID=-1;private int id=NO_ID;
        int getId(){return id;}void setId(int value){id=value;}Resources getResources(){return context.resources;}
        View findViewById(int value){return id==value?this:null;}''')
    header=header.replace("static final class XposedHelpers {",'''static final class XposedHelpers {
        static Object callMethod(Object object,String name,Object...args) throws Exception {
            if(args.length!=0)throw new AssertionError("Unexpected reflective method arguments");
            Method method=object.getClass().getMethod(name);method.setAccessible(true);return method.invoke(object);
        }''')
    fragments,intervals=common.fragments(raw)
    for i,line in enumerate(text.splitlines(keepends=True),1):
        if re.search(r"private static (?:final String FIELD_DEVICE_(?:GUARD|MSG_ID)\b|volatile int sDate(?:Wrapper)?ResId\b)",line) and line.strip() not in fragments:
            fragments+="\n"+line;intervals.append([i,i])
    names=["bindMessageRow","trackDeviceSourceTarget","invalidateDeviceSourceRow","findDateTextView","findChildByResourceName","getResourceEntryName","resolveMessageDeviceId","applyDeviceSourceToMatchingViews","forEachTextView","extractMessageId","extractIdFromKeyObj","extractDeviceId","getDeviceJidObject"]
    for name in names:
        match=re.search(r"^    private [^\n]*\b"+name+r"\(",text,re.M)
        if not match and name in ("trackDeviceSourceTarget", "invalidateDeviceSourceRow"): continue
        block,interval=common.extract_block(text,match.group(0));fragments+="\n"+block;intervals.append(interval)
    for marker in ["    private Object findFMessage(Object candidate)","    static int parseDeviceIdFromRawString(String raw, boolean isDeviceJid)"]:
        block,interval=common.extract_block(text,marker);fragments+="\n"+block;intervals.append(interval)
    # #111 replaced the ad-hoc parsing method with a production JID parser.
    # Extract that implementation rather than providing a permissive fake.
    parser_file=WORKSPACE/"app/src/main/java/com/waenhancer/xposed/features/conversation/DeviceJidParser.java"
    parser=parser_file.read_text(encoding="utf-8")
    parser_body,_=common.extract_block(parser,"final class DeviceJidParser")
    fragments+="\n"+parser_body.replace("final class DeviceJidParser", "static final class DeviceJidParser",1)
    bind_callbacks=""
    before_marker="protected void beforeHookedMethod(MethodHookParam p)"
    if before_marker in text:
        callback,interval=common.extract_block(text,before_marker)
        bind_callbacks+="\n@Override\n"+callback;intervals.append(interval)
    callback,interval=common.extract_block(text,"protected void afterHookedMethod(MethodHookParam p)")
    bind_callbacks+="\n@Override\n"+callback;intervals.append(interval)
    fragments+="\nprivate final class BindObserver extends XC_MethodHook {"+bind_callbacks+"\n}\n"
    text_set_start=text.index("    private void hookTextViewSetText()")
    callback,interval=common.extract_block(text,"protected void afterHookedMethod(MethodHookParam param)",text_set_start)
    fragments+="\nprivate final class TextObserver extends XC_MethodHook {\n@Override\n"+callback+"\n}\n";intervals.append(interval)
    return header+fragments+"\n"+(ROOT/"BindingLifecycleCases.java.fragment").read_text()+"\n}\n",intervals

def execute(label,source,output,release=17):
    raw=source.read_bytes();generated,intervals=build(raw);work=output/label;work.mkdir(parents=True,exist_ok=True)
    java_file=work/"BindingLifecycleProbe.java";java_file.write_text(generated)
    java=shutil.which("java");javac=shutil.which("javac")
    has_symbols=(Path(java).resolve().parents[1]/"lib/ct.sym").exists()
    flags=(["--release",str(release)] if has_symbols else ["-source",str(release),"-target",str(release)])
    command=([javac] if javac else [java,"-m","jdk.compiler/com.sun.tools.javac.Main"])+flags+[java_file.name]
    result=subprocess.run(command,cwd=work,text=True,capture_output=True,timeout=60);(work/"compile.stdout.txt").write_text(result.stdout);(work/"compile.stderr.txt").write_text(result.stderr)
    if result.returncode:raise RuntimeError(result.stderr)
    executed=subprocess.run([java,"BindingLifecycleProbe"],cwd=work,text=True,capture_output=True,timeout=30);(work/"run.stdout.txt").write_text(executed.stdout);(work/"run.stderr.txt").write_text(executed.stderr)
    if executed.returncode:raise RuntimeError(executed.stderr)
    cases=[dict(zip(["name","status","detail"],line.split("\t",2))) for line in executed.stdout.splitlines()]
    if len(cases)!=30:raise RuntimeError("Expected30 completed scenarios")
    return {"label":label,"source":str(source),"source_sha256":hashlib.sha256(raw).hexdigest(),"extracted_intervals":intervals,
            "fixture_sha256":hashlib.sha256(java_file.read_bytes()).hexdigest(),"compile_command":command,"compile_exit_code":result.returncode,
            "run_exit_code":executed.returncode,"cases":cases,"pass_count":sum(c["status"]=="PASS" for c in cases),"fail_count":sum(c["status"]=="FAIL" for c in cases)}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",type=Path,default=WORKSPACE/common.RELATIVE)
    parser.add_argument("--label",default="candidate")
    parser.add_argument("--out",type=Path,default=ROOT/"binding-lifecycle-results")
    parser.add_argument("--release",type=int,default=17)
    parser.add_argument("--allow-behavior-failures",action="store_true")
    args=parser.parse_args()
    results=[execute(args.label,args.source,args.out.resolve(),args.release)]
    doc={"schema":"WAEX_DEVICE_SOURCE_BIND_LIFECYCLE_PROBE_V1","created_utc":datetime.now(timezone.utc).isoformat(),
         "source_methods":"Exact current main/candidate getView after-hook callback, bindMessageRow, matching-view propagation, identity extraction and listener methods",
         "controlled_dependencies":["Android Views/resources/listeners","Xposed metadata and MethodHookParam","Host adapter/message/JID shape","In-memory DeviceSource store","Explicit CompletableFuture/Executor schedule and feature setting"],
         "limits":["Not full class or APK compilation","No real Android/LSPosed","No actual WhatsApp adapter or native DEX selector","No physical scheduling/performance measurement"],"variants":results}
    dest=args.out.resolve()/"RESULTS.json";dest.write_text(json.dumps(doc,indent=2)+"\n")
    for r in results:print(r["label"],r["pass_count"],"PASS",r["fail_count"],"FAIL")
    print(dest)
    if not args.allow_behavior_failures and any(r["fail_count"] for r in results):sys.exit(1)

if __name__=="__main__":main()
