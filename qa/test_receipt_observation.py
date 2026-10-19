#!/usr/bin/env python3
"""Execute production receipt models, dispatch and verbatim installer/callback methods.

The fixture provides explicit Android, Xposed, DexKit and host doubles. It does
not execute WhatsApp, its SQL writes/transactions, Android UI or LSPosed.
"""
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET


def extract(text, marker):
    start = text.index(marker)
    opening = text.index('{', start)
    state, depth, i = 'code', 0, opening
    while i < len(text):
        char, pair = text[i], text[i:i + 2]
        if state == 'line':
            if char == '\n': state = 'code'
        elif state == 'comment':
            if pair == '*/': state = 'code'; i += 1
        elif state in ('string', 'char'):
            if char == '\\': i += 1
            elif char == ('"' if state == 'string' else "'"): state = 'code'
        elif pair == '//': state = 'line'; i += 1
        elif pair == '/*': state = 'comment'; i += 1
        elif char == '"': state = 'string'
        elif char == "'": state = 'char'
        elif char == '{': depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0: return text[start:i + 1]
        i += 1
    raise ValueError('Unclosed production declaration: ' + marker)


def check_receipt_text(root, area):
    """Compile the production resource/cache helper using explicit Android API doubles."""
    texts = {}
    for folder, locale in [('values', 'en'), ('values-es', 'es'), ('values-b+es+419', 'es-419')]:
        entries = {e.attrib['name']: e.text for e in ET.parse(root / 'app/src/main/res' / folder / 'receipt_toasts.xml').getroot()}
        texts[locale] = [entries[key] for key in ('receipt_observed_message', 'receipt_observed_status')]
        for value in texts[locale]:
            assert value.count('%1$s') == 1 and value.count('%') == 1, 'Exactly one contact placeholder is required'
    sources = {
        'android/content/pm/PackageManager.java': 'package android.content.pm; public class PackageManager { public static class NameNotFoundException extends Exception {} }',
        'android/content/res/Configuration.java': '''package android.content.res;
public class Configuration { public String locale="en"; public Configuration() {} public Configuration(Configuration c){locale=c.locale;}
 public boolean equals(Object o){return o instanceof Configuration && locale.equals(((Configuration)o).locale);} public int hashCode(){return locale.hashCode();} }''',
        'android/content/res/Resources.java': '''package android.content.res;
public class Resources { public final Configuration config=new Configuration(); public String owner="com.waenhancer"; public boolean swapped;
 public Configuration getConfiguration(){return config;}
 public String getResourceName(int id){return owner+":string/"+((id==1)!=swapped?"receipt_observed_message":"receipt_observed_status");}
 public static class NotFoundException extends RuntimeException {} }''',
        'android/content/Context.java': '''package android.content;
import android.content.res.*; import android.content.pm.PackageManager; import java.util.*;
public class Context {
 public static Map<String,String[]> texts=new HashMap<>(); public static int stringsRead;
 public final Resources resources=new Resources(); public String packageName="com.waenhancer";
 public Context module; public int packages,configurations; public boolean missing, denied, missingString;
 public Resources getResources(){return resources;}
 public String getPackageName(){return packageName;}
 public Context createPackageContext(String p,int flags) throws PackageManager.NameNotFoundException {
  if(!p.equals("com.waenhancer") || flags!=0) throw new AssertionError("Wrong package or unsafe flags");
  packages++; if(missing)throw new PackageManager.NameNotFoundException(); if(module==null)module=new Context();return module;
 }
 public Context createConfigurationContext(Configuration next){configurations++;if(denied)throw new SecurityException();
  Context c=new Context();c.resources.config.locale=next.locale;c.resources.owner=resources.owner;c.resources.swapped=resources.swapped;
  c.packageName=packageName;c.missingString=missingString;return c;}
 public String getString(int id,Object... args){stringsRead++;if(missingString)throw new Resources.NotFoundException();
  return String.format(Locale.ROOT,texts.get(resources.config.locale)[id-1],args);}
}''',
        'com/waenhancer/app/R.java': 'package com.waenhancer.app; public final class R { public static final class string { public static final int receipt_observed_message=1,receipt_observed_status=2; } }',
        'com/waenhancer/xposed/features/automation/ReceiptTextFixture.java': '''package com.waenhancer.xposed.features.automation;
import android.content.Context;
public final class ReceiptTextFixture {
 static int checks; static void check(boolean b,String m){checks++;if(!b)throw new AssertionError(m);}
 public static void main(String[] args){
  /* RESOURCE_TEXTS */
  Context host=new Context(); ReceiptToastText text=new ReceiptToastText(host);
  check(text.format(ReceiptObservationPolicy.Kind.MESSAGE,"Alex").equals("Alex just read your message"),"English message observation");
  check(text.format(ReceiptObservationPolicy.Kind.STATUS,"Alex").equals("Alex just viewed your status"),"Status has own resource");
  check(host.packages==1 && host.module.configurations==1,"Contexts reused for unchanged configuration");
  host.resources.config.locale="es";
  check(text.format(ReceiptObservationPolicy.Kind.MESSAGE,"Alex").equals(String.format(Context.texts.get("es")[0],"Alex")),"Spanish configuration applied");
  check(host.module.configurations==2 && host.packages==1,"Locale change replaces only configured context");
  host.resources.config.locale="es-419"; host.module.denied=true;
  check(text.format(ReceiptObservationPolicy.Kind.STATUS,"Alex").equals("Alex just viewed your status"),"Unavailable configuration uses explicit fallback");
  host.module.denied=false;
  check(text.format(ReceiptObservationPolicy.Kind.STATUS,"Alex").equals(String.format(Context.texts.get("es-419")[1],"Alex")),"Failed configuration change is retried, never cached as applied");
  check(host.module.configurations==4,"Failed configuration is not consumed");
  Context missing=new Context();missing.missing=true;
  check(new ReceiptToastText(missing).format(ReceiptObservationPolicy.Kind.MESSAGE,null).equals("A contact just read your message"),"Missing package/null name fallback");
  missing.missing=false;missing.module=new Context();missing.module.missingString=true;
  check(new ReceiptToastText(missing).format(ReceiptObservationPolicy.Kind.STATUS,"").equals("A contact just viewed your status"),"Missing resource/empty name fallback");
  Context foreignPackage=new Context();foreignPackage.module=new Context();foreignPackage.resources.config.locale="es";
  foreignPackage.module.packageName="com.example.foreign"; int before=Context.stringsRead;
  check(new ReceiptToastText(foreignPackage).format(ReceiptObservationPolicy.Kind.MESSAGE,"Alex").equals("Alex just read your message"),"Foreign context with valid numeric string ID uses honest fallback");
  check(Context.stringsRead==before,"Foreign package string is not read");
  Context foreignTable=new Context();foreignTable.module=new Context();foreignTable.resources.config.locale="es";
  foreignTable.module.resources.owner="com.example.foreign";before=Context.stringsRead;
  check(new ReceiptToastText(foreignTable).format(ReceiptObservationPolicy.Kind.STATUS,"Alex").equals("Alex just viewed your status"),"Foreign table with valid numeric string ID uses honest fallback");
  check(Context.stringsRead==before,"Foreign table string is not read");
  Context wrongName=new Context();wrongName.module=new Context();wrongName.resources.config.locale="es";
  wrongName.module.resources.swapped=true;before=Context.stringsRead;
  check(new ReceiptToastText(wrongName).format(ReceiptObservationPolicy.Kind.MESSAGE,"Alex").equals("Alex just read your message"),"Same package with a different resource name uses fallback");
  check(Context.stringsRead==before,"Wrong named resource is not read despite a valid numeric ID and module package");
  System.out.println("TEXT_CHECKS="+checks+"; production ReceiptToastText and XML strings with Android API doubles");
 }
}'''
    }
    fixtures = '\n'.join('Context.texts.put(' + json.dumps(locale) + ',new String[]{' + ','.join(json.dumps(s) for s in values) + '});' for locale, values in texts.items())
    sources['com/waenhancer/xposed/features/automation/ReceiptTextFixture.java'] = sources['com/waenhancer/xposed/features/automation/ReceiptTextFixture.java'].replace('/* RESOURCE_TEXTS */', fixtures)
    with tempfile.TemporaryDirectory(prefix='waex_receipt_text_') as directory:
        dest = Path(directory)
        files = []
        for relative, source in sources.items():
            target = dest / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source)
            files.append(target)
        subprocess.run(['javac', '--release', '17', '-d', str(dest), str(area / 'ReceiptToastText.java'),
                        str(area / 'ReceiptObservationPolicy.java'), *map(str, files)], check=True, timeout=60)
        subprocess.run(['java', '-cp', str(dest), 'com.waenhancer.xposed.features.automation.ReceiptTextFixture'], check=True, timeout=60)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.source_root.resolve()
    area = root / 'app/src/main/java/com/waenhancer/xposed/features/automation'
    for tool in ('javac', 'java'):
        if not shutil.which(tool): raise SystemExit('Required tool missing: ' + tool)
    source = (area / 'PresenceToastsHook.java').read_text()
    markers = ['    private ReceiptTypes resolveReceiptTypes()', '    private static final class ReceiptTypes',
               '    private void hookStatusViewedReceipt()', '    private void hookOnInsertReceipt()',
               '    private boolean isReceiptToastEnabled(', '    private void emitReceiptObservation(']
    declarations = '\n'.join(extract(source, marker) for marker in markers)
    for forbidden in ('setResult(', 'setThrowable(', 'SQLiteDatabase', 'processReceiptItem('):
        assert forbidden not in declarations, 'Receipt observation must not mutate host or guess SQL outcomes: ' + forbidden
    assert 'ReceiptToastDispatch::discardOldest' in source, 'The bounded queue must cancel displaced receipt reservations'
    template = (Path(__file__).resolve().parent / 'fixtures/receipt_observation/ReceiptObservationFixture.java.in').read_text()
    assert template.count('/* PRODUCTION_DECLARATIONS */') == 1
    body = template.replace('/* PRODUCTION_DECLARATIONS */', declarations)
    with tempfile.TemporaryDirectory(prefix='waex_receipt_observation_') as directory:
        dest = Path(directory)
        fixture = dest / 'ReceiptObservationFixture.java'
        fixture.write_text(body)
        production = [area / name for name in ('ReceiptObservationPolicy.java', 'ReceiptObservationContract.java',
                                               'ReceiptToastDispatch.java', 'ToastThrottle.java')]
        subprocess.run(['javac', '--release', '17', '-d', str(dest), *map(str, production), str(fixture)],
                       check=True, timeout=60)
        subprocess.run(['java', '-cp', str(dest), 'com.waenhancer.xposed.features.automation.ReceiptObservationFixture'],
                       check=True, timeout=60)
    check_receipt_text(root, area)
    print('PASS: production receipt models/dispatch and six verbatim declarations; explicit JVM doubles, not device/SQL')


if __name__ == '__main__': main()
