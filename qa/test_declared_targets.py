#!/usr/bin/env python3
"""Exact target selection before/after Context, including cached discovery.
Runs production Java and extracted Kotlin bodies with explicit Android doubles.
Does not authenticate installed APKs or exercise Xposed/Binder.
"""
from pathlib import Path
import hashlib, json, shutil, subprocess, tempfile, xml.etree.ElementTree as ET
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'app/src/main/java/com/waenhancer'

def body(text, marker):
    start = text.index(marker)
    p = text.index('{', start); depth = 0
    for i in range(p, len(text)):
        depth += (text[i] == '{') - (text[i] == '}')
        if depth == 0: return text[start:i+1]
    raise AssertionError('Unterminated ' + marker)

def main():
    for tool in ('javac', 'java', 'kotlinc'):
        if not shutil.which(tool): raise SystemExit('Required tool missing: ' + tool)
    scope = [x.text for x in ET.parse(ROOT/'app/src/main/res/values/arrays.xml').find("string-array[@name='xposed_scope']") if x.tag == 'item' and x.text != 'com.waenhancer']
    assert len(scope) == len(set(scope)), 'Duplicate declared scope'
    detector = (SRC/'utils/WhatsAppPackageDetector.kt').read_text()
    first = detector.index('    /** Declared targets')
    last = detector.index('    /**\n     * Registers a hooked', first)
    selection = detector[first:last]
    discover = detector[detector.index('        val pm = context.packageManager', detector.index('fun detectWhatsAppApps(')):detector.index('        val result = mutableListOf<HookedAppInfo>()')]
    assert 'WhatsAppPackageDetector.isWhatsAppPackageName(packageName)' in (SRC/'xposed/MainHook.java').read_text()
    with tempfile.TemporaryDirectory(prefix='waex-targets-') as folder:
        out=Path(folder); classes=out/'classes'; classes.mkdir()
        policy=SRC/'utils/DeclaredWhatsAppTargets.java'
        subprocess.run(['javac','--release','17','-d',str(classes),str(policy)],check=True)
        (out/'Context.kt').write_text('''package android.content
class Context { val packageManager=Any() }
''')
        (out/'Selection.kt').write_text('''package com.waenhancer.utils
import android.content.Context
object ModuleStatus { fun isModuleActive() = true }
object PreferenceStores { var reports:Set<String>?=null; fun publicStore(context:Context)=this
fun getStringSet(key:String,default:Set<String>?)=reports?:default }
object WhatsAppPackageDetector {
private const val MODULE_PACKAGE="com.waenhancer"
'''+selection+'''fun discover(context:Context):Set<String> {
'''+discover+'''return discoveredPackages
}}
''')
        tests='''package com.waenhancer.utils
import android.content.Context
fun main() {
 var n=0
 fun ck(label:String,value:Boolean) {check(value){label};n++}
 val declared=listOf(SCOPE)
 val context=Context()
 ck("scope exact",DeclaredWhatsAppTargets.packages().toList()==declared)
 for (pkg in declared) {
  ck("context $pkg",WhatsAppPackageDetector.isWhatsAppPackageName(context,pkg))
  ck("no context $pkg",WhatsAppPackageDetector.isWhatsAppPackageName(pkg))
  ck("case $pkg",!WhatsAppPackageDetector.isWhatsAppPackageName(pkg.uppercase()))
  ck("suffix $pkg",!WhatsAppPackageDetector.isWhatsAppPackageName(pkg+".scanner.fixture"))
 }
 for (pkg in listOf<String?>(null,"","com.waenhancer","android.whatsapp","com.android.whatsapp","org.example.delight.reader","com.whatsapp.web.dual.app.scanner","whatsapprecovery.deletedphotos.recover.fixture","whatsapp.web.whatscan.fixture","com.whatsapp:worker"," com.whatsapp","com.whatsapp ","com.whatsаpp","com.whatsapp\\n")) {
  ck("reject $pkg",!WhatsAppPackageDetector.isWhatsAppPackageName(pkg))
  ck("reject with context $pkg",!WhatsAppPackageDetector.isWhatsAppPackageName(context,pkg))
 }
 ck("null context retains declared scope",WhatsAppPackageDetector.getSupportedPackages(null).toList()==declared)
 ck("context agrees",WhatsAppPackageDetector.getSupportedPackages(context)==DeclaredWhatsAppTargets.packages())
 try { (DeclaredWhatsAppTargets.packages() as MutableSet<String>).clear(); error("mutable allowlist") } catch (expected:UnsupportedOperationException) {n++}
 ck("immutable after caller attempt",DeclaredWhatsAppTargets.packages().size==declared.size)
 PreferenceStores.reports=setOf("com.whatsapp.web.dual.app.scanner","com.waenhancer","com.aero","org.example.injected")
 ck("historical reports do not expand targets",WhatsAppPackageDetector.discover(context).toList()==declared)
 PreferenceStores.reports=null
 ck("absent reports do not narrow declared scope",WhatsAppPackageDetector.discover(context).toList()==declared)
 println("PASS: $n declared-target behavior checks; ${declared.size} exact scope entries, no Context/substring authorization")
}
'''.replace('SCOPE',','.join(json.dumps(x) for x in scope))
        (out/'Test.kt').write_text(tests)
        cmd=['kotlinc','-language-version','2.0','-jvm-target','17','-cp',str(classes),*[str(p) for p in sorted(out.glob('*.kt'))],'-include-runtime','-d',str(out/'test.jar')]
        subprocess.run(cmd,check=True,timeout=120)
        subprocess.run(['java','-cp',str(out/'test.jar')+':'+str(classes),'com.waenhancer.utils.TestKt'],check=True,timeout=60)
    print('PASS: same selector at pre-Context entry; cached package discovery filtered, no installed-name scan')
if __name__=='__main__':main()
