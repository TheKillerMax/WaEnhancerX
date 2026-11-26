#!/usr/bin/env python3
"""Compile complete current appearance hooks and public lifecycle helpers on Android API 24/28/34.

Robolectric executes Views, Drawables and layouts. DexKit/AndroidX Core APIs are
real pinned JARs. Xposed, host discovery and the private ScreenScopedFeature
declaration are explicit test boundaries; private engine policies never execute.
No WhatsApp DEX, real-device injection, GPU output or hook-mode coverage is claimed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
JAVA=Path('app/src/main/java/com/waenhancer')
SOURCES=[JAVA/p for p in ['xposed/core/BaseFeature.kt','xposed/core/HookRegistrar.java','xposed/core/ViewHookDispatcher.java',
    'xposed/utils/HookErrors.java','xposed/utils/HostClassNames.java','xposed/utils/HostResourceIds.java',
    'xposed/utils/ViewClassSelector.java','xposed/features/customization/FloatingBottomBarHook.java',
    'xposed/features/customization/ChannelRecommendationsFilterHook.kt','xposed/features/homescreen/ChatListCustomizationsHook.java']]
FIXTURES=ROOT/'qa/fixtures/appearance_current'

def run(command,log):
    with log.open('w') as stream:
        result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
    print(log.name,'exit='+str(result.returncode),flush=True)
    return result.returncode

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--deps',type=Path,required=True);p.add_argument('--sdk-jars',type=Path,required=True)
    p.add_argument('--dexkit-jar',type=Path,required=True);p.add_argument('--core-api-jar',type=Path,required=True)
    p.add_argument('--mutations',action='store_true');a=p.parse_args();root=a.root.resolve();out=a.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    for path,digest in [(a.dexkit_jar,'195979d9576ba6d68a1c60bdd3e38cd3aed068d4e0c5c6c99caa50bc25fcb9f1'),(a.core_api_jar,'d1f5a319a77555df7e23858ffb5ed45a95ebb4263fa1ab7a993510ceb53555a0')]:
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise RuntimeError('Pinned API mismatch: '+str(path))
    kotlin=Path(os.environ['KOTLIN_HOME'])
    dependencies=sorted(a.deps.resolve().glob('*.jar'))+[a.dexkit_jar.resolve(),a.core_api_jar.resolve(),kotlin/'lib/kotlin-stdlib.jar']
    cp=os.pathsep.join(map(str,dependencies))
    android=next(p for p in dependencies if p.name=='android-all-14-robolectric-10818077.jar')
    production_cp=os.pathsep.join(map(str,[android,a.dexkit_jar.resolve(),a.core_api_jar.resolve(),kotlin/'lib/kotlin-stdlib.jar']))
    fixtures=sorted(FIXTURES.glob('*Test.java'))
    expected=sum(len(re.findall(r'@Test\b',f.read_text())) for f in fixtures)*3
    originals={p:(root/p).read_text() for p in SOURCES}
    variants={'current':{}}
    if a.mutations:
        floating=SOURCES[7];channel=SOURCES[8];chat=SOURCES[9]
        variants.update({
            'fab-poll':{floating:originals[floating].replace('awaitFabLayout(rootView, container);','final ViewGroup pending = container; rootView.postDelayed(() -> positionFabsAboveBar(rootView,pending),100L);')},
            'nested-transition':{floating:originals[floating].replace('from = previous.getDrawable(previous.getNumberOfLayers() - 1);','from = previous;')},
            'channel-resize':{channel:originals[channel].replace('view.visibility = View.GONE','view.visibility = View.GONE\n                view.layoutParams?.let { it.width=0; it.height=0; view.layoutParams=it }')},
            'meta-switch':{chat:originals[chat].replace('return isMetaAiDisabled() && prefs.getBoolean("metaai_block_chat", true);','return prefs.getBoolean("metaai_block_chat", true);')},
            'channel-rebind':{channel:originals[channel].replace('(flags and visibilityMask.inv()) or View.GONE','flags')},
        })
        for name,changes in variants.items():
            if name!='current' and any(value==originals[path] for path,value in changes.items()):raise RuntimeError('Mutation not applied')
    results=[]
    for name,changes in variants.items():
        case=out/name;stage=case/'sources';classes=case/'classes';classes.mkdir(parents=True)
        for relative,content in originals.items():
            destination=stage/relative;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(changes.get(relative,content))
        stubs=runpy.run_path(str(FIXTURES/'boundaries.py'))['STUBS']
        ids=sorted(set(re.findall(r'R\.string\.(\w+)','\n'.join(originals.values()))))
        stubs['com/waenhancer/app/R.java']='package com.waenhancer.app; public final class R { public static final class string {'+''.join('public static final int '+value+'='+str(index+1)+';' for index,value in enumerate(ids))+'}}'
        adapters=[]
        for relative,content in stubs.items():
            destination=stage/'boundaries'/relative;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(content);adapters.append(destination)
        if run(['javac','--release','17','-cp',production_cp,'-d',str(classes),*map(str,adapters)],case/'compile-boundaries.log'):raise RuntimeError('Boundary compilation failed')
        if run([str(kotlin/'bin/kotlinc'),'-jvm-target','17','-cp',str(classes)+os.pathsep+production_cp,'-d',str(classes),*[str(stage/p) for p in SOURCES]],case/'compile-kotlin.log'):raise RuntimeError('Production Kotlin failed')
        if run(['javac','--release','17','-cp',str(classes)+os.pathsep+production_cp,'-d',str(classes),*[str(stage/p) for p in SOURCES if p.suffix=='.java']],case/'compile-java.log'):raise RuntimeError('Production Java failed')
        staged_tests=[]
        for fixture in fixtures:
            destination=stage/fixture.name;shutil.copyfile(fixture,destination);staged_tests.append(destination)
        if run(['javac','--release','17','-cp',str(classes)+os.pathsep+cp,'-d',str(classes),*map(str,staged_tests)],case/'compile-tests.log'):raise RuntimeError('Fixture compilation failed')
        command=['java','-Xmx1g','--add-opens=java.base/java.lang=ALL-UNNAMED','--add-opens=java.base/java.util=ALL-UNNAMED','-Drobolectric.offline=true','-Drobolectric.dependency.dir='+str(a.sdk_jars.resolve()),'-cp',str(classes)+os.pathsep+cp,'org.junit.runner.JUnitCore',*['com.waenhancer.xposed.features.customization.'+f.stem for f in fixtures]]
        code=run(command,case/'junit.log');log=(case/'junit.log').read_text()
        good=re.search(r'OK \((\d+) tests?\)',log);bad=re.search(r'Tests run: (\d+),\s+Failures: (\d+)',log)
        tests=int(good[1]) if good else int(bad[1]) if bad else 0
        failures=int(bad[2]) if bad else 0;assertions=len(re.findall(r'(?m)^java\.lang\.AssertionError(?::.*)?$',log))
        accepted=tests==expected and ((code==0 and good is not None) if name=='current' else (code!=0 and failures>0 and failures==assertions))
        results.append({'variant':name,'tests':tests,'failures':failures,'assertion_failures':assertions,'exit':code,'accepted':accepted})
        print(results[-1],flush=True)
    summary={'source_root':str(root),'scope':__doc__,'source_sha256':{str(p):hashlib.sha256((root/p).read_bytes()).hexdigest() for p in SOURCES},'fixture_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*fixtures,FIXTURES/'boundaries.py',Path(__file__)]},'dependency_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in dependencies},'results':results,'accepted':all(r['accepted'] for r in results)}
    (out/'result.json').write_text(json.dumps(summary,indent=2)+'\n')
    if not summary['accepted']:raise RuntimeError('Unexpected appearance result')

if __name__=='__main__':main()
