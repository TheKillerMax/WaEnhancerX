#!/usr/bin/env python3
"""Compile real WaTargets/WaMessage/WaJid against DexKit 2.2, then test exact setter selection.

DEX discovery and persisted-cache transport are explicit controlled boundaries;
the helper, public message code and WaTargets cache validation execute unchanged.
No WhatsApp DEX, private licensing code, LSPosed or Android injection is executed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
JAVA = Path('app/src/main/java/com/waenhancer')
SOURCES = [JAVA / ('xposed/core/wa/' + name + '.java') for name in
           ('ViewOnceSetterContract', 'WaTargets', 'WaMessage', 'WaJid')]
SOURCES += [JAVA / 'xposed/utils/HookErrors.java']

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--android-api', type=Path, required=True)
    p.add_argument('--dexkit-jar', type=Path, required=True)
    p.add_argument('--mutations', action='store_true')
    a = p.parse_args(); root = a.root.resolve(); out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    if hashlib.sha256(a.dexkit_jar.read_bytes()).hexdigest() != '195979d9576ba6d68a1c60bdd3e38cd3aed068d4e0c5c6c99caa50bc25fcb9f1':
        raise RuntimeError('Unexpected DexKit API identity')
    kotlin = Path(os.environ['KOTLIN_HOME']) / 'lib/kotlin-stdlib.jar'
    dependencies = [a.android_api.resolve(), a.dexkit_jar.resolve(), kotlin]
    classpath = os.pathsep.join(map(str, dependencies))
    stubs = {
        'com/waenhancer/utils/ContactNameResolver.java': '''package com.waenhancer.utils;
public final class ContactNameResolver {
 public static final ContactNameResolver INSTANCE = new ContactNameResolver();
 public String resolveLidToPhone(android.content.Context c, String value) { throw new AssertionError("Contact lookup is outside this selector fixture"); }
 public String resolvePhoneToLid(android.content.Context c, String value) { throw new AssertionError("Contact lookup is outside this selector fixture"); }
}''',
        'androidx/annotation/NonNull.java': 'package androidx.annotation; public @interface NonNull {}',
        'androidx/annotation/Nullable.java': 'package androidx.annotation; public @interface Nullable {}',
        'androidx/annotation/VisibleForTesting.java': 'package androidx.annotation; public @interface VisibleForTesting {}',
        'de/robv/android/xposed/XposedBridge.java': 'package de.robv.android.xposed; public final class XposedBridge { public static void log(String text) { throw new AssertionError("Unexpected diagnostic failure: " + text); } }',
        'com/waenhancer/xposed/core/devkit/DexCacheManager.java': '''package com.waenhancer.xposed.core.devkit;
public final class DexCacheManager {
 public interface Resolver<T> { T resolve() throws Throwable; }
 public static DexCacheManager getInstance(android.content.Context context) { throw new AssertionError("Field-cache boundary was not configured"); }
 public java.lang.reflect.Field getField(ClassLoader loader,String key,Resolver<java.lang.reflect.Field> resolver) { throw new AssertionError("Field-cache boundary was not configured"); }
}''',
        'com/waenhancer/xposed/core/devkit/DexSearchEngine.java': '''package com.waenhancer.xposed.core.devkit;
import java.lang.reflect.Method;
import org.luckypray.dexkit.DexKitBridge;
public final class DexSearchEngine {
 public static Class<?> messageClass; public static Method[] cachedMethods; public static String lastCacheKey;
 public interface CQ { Class<?> run(DexKitBridge bridge,ClassLoader loader) throws Throwable; }
 public interface MQ { Method run(DexKitBridge bridge,ClassLoader loader) throws Throwable; }
 public interface MSQ { Method[] run(DexKitBridge bridge,ClassLoader loader) throws Throwable; }
 public static DexSearchEngine getInstance() { return new DexSearchEngine(); }
 public Class<?> findClassWithCache(android.content.Context c,ClassLoader l,String key,CQ q) {
  if (!"waex_fmessage_class".equals(key)) throw new AssertionError("Unconfigured class cache " + key);
  return messageClass;
 }
 public Method[] findMethodsWithCache(android.content.Context c,ClassLoader l,String key,MSQ q) { lastCacheKey=key; return cachedMethods; }
 public Method findMethodWithCache(android.content.Context c,ClassLoader l,String key,MQ q) { throw new AssertionError("Unconfigured method cache"); }
 public DexKitBridge getBridge() { throw new AssertionError("No WhatsApp DEX fixture"); }
 public void initialize(android.content.Context c) { throw new AssertionError("No WhatsApp DEX fixture"); }
}'''
    }
    source = (root / SOURCES[0]).read_text()
    variants = {'current': source}
    if a.mutations:
        variants.update({
            'foreign-type': source.replace('!messageClass.isAssignableFrom(candidate)', 'false').replace('messageClass.isAssignableFrom(method.getDeclaringClass())', 'true'),
            'ambiguous-interface': source.replace('if (selected != null && !selected.equals(candidate)) return null;', 'if (selected != null && !selected.equals(candidate)) continue;'),
            'native-cache': source.replace(' && !Modifier.isNative(flags)', ''),
            'wrong-cache-name': source.replace('|| !setter.getName().equals(method.getName())', ''),
            'all-int-setters': source.replace('if (isMessageSetter(implementation, messageClass)) methods.add(implementation);', 'for (Method member : candidate.getDeclaredMethods()) if (isMessageSetter(member, messageClass)) methods.add(member);'),
        })
        if any(value == source for name, value in variants.items() if name != 'current'):
            raise RuntimeError('Mutation did not apply')
    results = []
    for name, variant in variants.items():
        stage = out/name/'sources'; classes = out/name/'classes'; classes.mkdir(parents=True)
        paths = []
        for relative in SOURCES:
            dest = stage/relative; dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(variant if relative == SOURCES[0] else (root/relative).read_text()); paths.append(dest)
        for relative, text in stubs.items():
            dest = stage/'boundaries'/relative; dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text); paths.append(dest)
        fixture = ROOT/'qa/fixtures/ViewOnceSetterContractChecks.java'
        staged_fixture = stage/fixture.name; shutil.copyfile(fixture, staged_fixture); paths.append(staged_fixture)
        compile_run = subprocess.run(['javac','--release','17','-cp',classpath,'-d',str(classes),*map(str,paths)], capture_output=True, text=True, timeout=90)
        (out/name/'compile.log').write_text(compile_run.stdout+compile_run.stderr)
        if compile_run.returncode: raise RuntimeError('Compilation failed: '+name+'\n'+compile_run.stderr)
        run = subprocess.run(['java','-cp',str(classes)+os.pathsep+classpath,'com.waenhancer.xposed.core.wa.ViewOnceSetterContractChecks'],capture_output=True,text=True,timeout=30)
        (out/name/'run.log').write_text(run.stdout+run.stderr)
        match = re.search(r'CHECKS=(\d+) FAILURES=(\d+)',run.stdout)
        valid = match is not None and int(match[1]) == 38 and ((run.returncode == 0 and int(match[2]) == 0) if name == 'current' else (run.returncode != 0 and int(match[2]) > 0 and 'java.lang.AssertionError' in run.stderr))
        results.append({'variant':name,'compile_exit':compile_run.returncode,'run_exit':run.returncode,'checks':int(match[1]) if match else None,'assertion_failures':int(match[2]) if match else None,'accepted':valid})
        print(results[-1], flush=True)
    summary = {'source_sha256':{str(p):hashlib.sha256((root/p).read_bytes()).hexdigest() for p in SOURCES},'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),'dependency_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in dependencies},'scope':__doc__,'results':results,'accepted':all(r['accepted'] for r in results)}
    (out/'result.json').write_text(json.dumps(summary,indent=2)+'\n')
    if not summary['accepted']: raise RuntimeError('Unexpected selector result')

if __name__ == '__main__': main()
