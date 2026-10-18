#!/usr/bin/env python3
"""Type-check verbatim receipt selectors against a supplied real DexKit classes.jar.

Android context, DexSearchEngine and Xposed are explicit compile-only stubs.
DexKit query, matcher and result types come exclusively from the supplied jar.
The native bridge and WhatsApp are not executed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from test_receipt_observation import extract


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dexkit-jar', required=True, type=Path)
    parser.add_argument('--kotlin-stdlib', required=True, type=Path)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.source_root.resolve()
    for path in (args.dexkit_jar, args.kotlin_stdlib):
        if not path.is_file(): parser.error('Required dependency missing: ' + str(path))
    area = root / 'app/src/main/java/com/waenhancer/xposed/features/automation'
    source = (area / 'PresenceToastsHook.java').read_text()
    declarations = '\n'.join(extract(source, marker) for marker in (
        '    private ReceiptTypes resolveReceiptTypes()', '    private static final class ReceiptTypes',
        '    private void hookStatusViewedReceipt()', '    private void hookOnInsertReceipt()'))
    wrapper = '''package com.waenhancer.xposed.features.automation;
import java.lang.reflect.*; import java.util.*;
import org.luckypray.dexkit.DexKitBridge;
import org.luckypray.dexkit.query.FindMethod;
import org.luckypray.dexkit.query.enums.StringMatchType;
import org.luckypray.dexkit.query.matchers.MethodMatcher;
import org.luckypray.dexkit.result.MethodData;
import org.luckypray.dexkit.result.MethodDataList;
import org.luckypray.dexkit.result.UsingFieldData;
public final class ReceiptDexKitApiCompile {
 static final String TAG="compile-only", STATUS_SNAPSHOT="status", MESSAGE_SNAPSHOT="message";
 final Object context = null; final ClassLoader classLoader = null;
 boolean receiptTypesResolved; ReceiptTypes receiptTypes;
 boolean isStatusViewedToastEnabled(){return false;} boolean isMessageViewedToastEnabled(){return false;}
 void emitReceiptObservation(ReceiptObservationPolicy.Observation event){}
 static class DexSearchEngine {
  static DexSearchEngine getInstance(){return null;}
  void initialize(Object context){} DexKitBridge getBridge(){return null;}
 }
 static class XposedBridge { static void hookMethod(Method method,XC_MethodHook callback){} static void log(String value){} }
 static class XC_MethodHook {
  protected void beforeHookedMethod(MethodHookParam param){} protected void afterHookedMethod(MethodHookParam param){}
  static class MethodHookParam { Object thisObject; Object[] args;
   boolean hasThrowable(){return false;} Object getObjectExtra(String key){return null;}
   void setObjectExtra(String key,Object value){} }
 }
''' + declarations + '\n}\n'
    with tempfile.TemporaryDirectory(prefix='waex_receipt_dexkit_api_') as directory:
        dest = Path(directory)
        fixture = dest / 'ReceiptDexKitApiCompile.java'
        fixture.write_text(wrapper)
        run = subprocess.run(['javac', '--release', '17', '-cp', str(args.dexkit_jar.resolve()) + ':' + str(args.kotlin_stdlib.resolve()),
                              '-d', str(dest), str(area / 'ReceiptObservationPolicy.java'),
                              str(area / 'ReceiptObservationContract.java'), str(fixture)],
                             text=True, capture_output=True, timeout=60)
        if run.returncode:
            raise SystemExit(run.stdout + run.stderr)
        result = {'result': 'PASS', 'declarations_compiled': 4, 'dexkit_types_stubbed': False,
                  'dexkit_jar_sha256': hashlib.sha256(args.dexkit_jar.read_bytes()).hexdigest(),
                  'kotlin_stdlib_sha256': hashlib.sha256(args.kotlin_stdlib.read_bytes()).hexdigest(),
                  'production_declarations_sha256': hashlib.sha256(declarations.encode()).hexdigest(),
                  'compiler_output': run.stdout + run.stderr,
                  'scope': 'Real DexKit API type-check, not native matching, Android compilation or device acceptance'}
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
