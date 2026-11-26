#!/usr/bin/env python3
"""Exercise actual profile-owner resolution, process parser and extracted complete RootProbe.

Android Context/PackageManager/Process run on Robolectric API 24/28/34. Only root
execution and the LSPosed database are controlled boundaries. The exact production
ps command also executes against a controlled executable; no root or real ps runs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
JAVA=Path('app/src/main/java/com/waenhancer/utils')
SOURCES=[JAVA/p for p in ['ProfileProcessSnapshot.kt','XposedRuntimeInspector.kt','AndroidUserScope.java','DeclaredWhatsAppTargets.java']]
IDENTITIES=SOURCES+[JAVA/'TargetAppManager.kt',JAVA/'LsposedScopeReader.kt']

def run(cmd,log):
    with log.open('w') as stream:result=subprocess.run(cmd,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
    print(log.name,'exit='+str(result.returncode),flush=True);return result.returncode

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--deps',type=Path,required=True);p.add_argument('--sdk-jars',type=Path,required=True)
    p.add_argument('--mutations',action='store_true');a=p.parse_args();root=a.root.resolve();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    kotlin=Path(os.environ['KOTLIN_HOME']);deps=sorted(a.deps.resolve().glob('*.jar'))+[kotlin/'lib/kotlin-stdlib.jar']
    cp=os.pathsep.join(map(str,deps));android=next(p for p in deps if p.name=='android-all-14-robolectric-10818077.jar')
    # The fixture does not use test-parameter-injector (compiled with Kotlin2.2).
    # Keep it at runtime for Robolectric; do not bypass Kotlin metadata validation.
    compile_cp=os.pathsep.join(str(p) for p in deps if not p.name.startswith('test-parameter-injector-'))
    manager=(root/JAVA/'TargetAppManager.kt').read_text()
    probe=manager[manager.index('internal data class RootProbeResult'):manager.index('/**\n * Universal source of truth')]
    probe='package com.waenhancer.utils\nimport android.content.Context\nimport android.os.Process\nimport android.os.SystemClock\nimport com.waenhancer.xposed.utils.AppRestartHelper\n'+probe
    scope=(root/JAVA/'LsposedScopeReader.kt').read_text()
    scope=scope[scope.index('data class LsposedScopeSnapshot('):scope.index('/**\n * Reads the module')]
    scope='package com.waenhancer.utils\n'+scope+'''
object LsposedScopeReader {
 const val STAGED_OK_MARKER="WAEX_LSPOSED_DB_OK"
 var calls=0
 fun stageCommand(context:android.content.Context):String { calls++;return "fixture_scope_stage" }
 fun parseStaged(context:android.content.Context,staged:Boolean)=LsposedScopeSnapshot(context.packageName,
  DeclaredWhatsAppTargets.packages(),staged,if(staged)LsposedScopeSnapshot.Source.DATABASE else LsposedScopeSnapshot.Source.UNAVAILABLE)
}
'''
    boundary='''package com.waenhancer.xposed.utils
object AppRestartHelper {
 var output:String?="";var calls=0;var lastCommand="";var failure:Throwable?=null
 fun runRootCommand(command:String):String? { calls++;lastCommand=command;failure?.let{throw it};return output }
}
'''
    originals={path:(root/path).read_text() for path in SOURCES}
    variants={'current':{}}
    if a.mutations:
        parser=SOURCES[0]
        variants.update({
            'ignore-uid':{parser:originals[parser].replace('if (owners[name] == uid)','if (name in owners)')},
            'accept-other-user':{parser:originals[parser].replace('require(app.packageName == name && AndroidUserScope.userIdForUid(app.uid) == user)','require(app.packageName == name)')},
            'ignore-context-uid':{parser:originals[parser].replace('require(own.uid == Process.myUid() && own.packageName == context.packageName)','require(own.packageName == context.packageName)')},
            'any-manager-pid':{'probe':probe.replace('managerPid in it.pidsFor(managerPackage).orEmpty()','it.pidsFor(managerPackage).orEmpty().isNotEmpty()')},
        })
    fixtures=ROOT/'qa/fixtures/ProfileProcessProbeTest.kt';expected=len(re.findall(r'@Test\b',fixtures.read_text()))*3
    results=[]
    for name,changes in variants.items():
        case=out/name;stage=case/'sources';classes=case/'classes';classes.mkdir(parents=True)
        paths=[]
        for relative,content in originals.items():
            destination=stage/relative;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(changes.get(relative,content));paths.append(destination)
        for filename,content in [('RootProbe.kt',changes.get('probe',probe)),('ScopeBoundary.kt',scope),('RootBoundary.kt',boundary),('ProfileProcessProbeTest.kt',fixtures.read_text())]:
            destination=stage/filename;destination.write_text(content);paths.append(destination)
        if run(['javac','--release','17','-cp',str(android),'-d',str(classes),*[str(path) for path in paths if path.suffix=='.java']],case/'compile-java.log'):raise RuntimeError('Java failed')
        if run([str(kotlin/'bin/kotlinc'),'-jvm-target','17','-cp',str(classes)+os.pathsep+compile_cp,'-d',str(classes),*[str(path) for path in paths if path.suffix=='.kt']],case/'compile-kotlin.log'):raise RuntimeError('Kotlin failed')
        command=['java','-Xmx1g','--add-opens=java.base/java.lang=ALL-UNNAMED','--add-opens=java.base/java.util=ALL-UNNAMED','-Drobolectric.offline=true','-Drobolectric.dependency.dir='+str(a.sdk_jars.resolve()),'-Dwaex.commandfile='+str(case/'command.sh'),'-cp',str(classes)+os.pathsep+cp,'org.junit.runner.JUnitCore','com.waenhancer.utils.ProfileProcessProbeTest']
        code=run(command,case/'junit.log');log=(case/'junit.log').read_text();good=re.search(r'OK \((\d+) tests?\)',log);bad=re.search(r'Tests run: (\d+),\s+Failures: (\d+)',log)
        tests=int(good[1]) if good else int(bad[1]) if bad else 0;failures=int(bad[2]) if bad else 0;assertions=len(re.findall(r'(?m)^java\.lang\.AssertionError(?::.*)?$',log))
        accepted=tests==expected and ((code==0 and good is not None) if name=='current' else code!=0 and failures>0 and failures==assertions)
        results.append({'variant':name,'tests':tests,'failures':failures,'assertion_failures':assertions,'accepted':accepted});print(results[-1],flush=True)
    # Real emitted command, fixture ps only. Unknown output cannot execute shell fragments.
    binary=out/'bin';binary.mkdir();fake=binary/'ps'
    fake.write_text('#!/bin/sh\nif [ "$#" -gt 0 ]; then printf "%s\\n" "$FIXTURE_PS";exit "$FIXTURE_PS_EXIT";fi\nprintf "%s\\n" "$FIXTURE_LEGACY";exit "$FIXTURE_LEGACY_EXIT"\n');fake.chmod(0o700)
    shell=[];command=(out/'current/command.sh').read_text()
    cases=[('modern',0,'UID PID NAME\n10123 44 com.whatsapp\n10000 99 com.waenhancer\n12 77 com.foreign',0,'',['10123 44 com.whatsapp','10000 99 com.waenhancer']),('legacy',127,'',0,'u10_a123 44 1 0 S com.whatsapp',['u10_a123 44 1 0 S com.whatsapp']),('exact-name',0,'10123 44 com.whatsapp:push\n10123 45 com.whatsapp.attacker\n10123 46 comXwhatsapp\n10123 47 com.whatsapp;id',0,'',[]),('no-process-command',127,'',127,'',[]),('failed-producers-with-partial-output',1,'10000 99 com.waenhancer',1,'u0_a0 99 1 0 S com.waenhancer',[])]
    for name,code,text,fallback_code,fallback,expected_lines in cases:
        env=dict(os.environ,PATH=str(binary)+os.pathsep+os.environ['PATH'],FIXTURE_PS=text,FIXTURE_PS_EXIT=str(code),FIXTURE_LEGACY=fallback,FIXTURE_LEGACY_EXIT=str(fallback_code))
        result=subprocess.run(['sh','-c',command],capture_output=True,text=True,env=env,timeout=5)
        accepted=result.stdout.splitlines()==expected_lines and result.returncode==(0 if expected_lines else 1)
        shell.append({'case':name,'exit':result.returncode,'accepted':accepted})
    summary={'scope':__doc__,'source_root':str(root),'source_sha256':{str(path):hashlib.sha256((root/path).read_bytes()).hexdigest() for path in IDENTITIES},'fixture_sha256':hashlib.sha256(fixtures.read_bytes()).hexdigest(),'results':results,'shell':shell,'accepted':all(r['accepted'] for r in results+shell)}
    (out/'result.json').write_text(json.dumps(summary,indent=2)+'\n')
    if not summary['accepted']:raise RuntimeError('Unexpected profile result')

if __name__=='__main__':main()
