#!/usr/bin/env python3
"""Compile complete SystemDiagnostics.kt; exercise SELinux evidence and refresh.

Android metadata, the hidden Boolean API and root-command execution are explicit
configured boundaries. No device, root command or SELinux policy is exercised.
The production absolute file path is unchanged and must be unreadable on this
host JVM, which lets the real fallback/caching code execute without path edits.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('app/src/main/java/com/waenhancer/utils/SystemDiagnostics.kt')
FIXTURE = Path('qa/fixtures/SystemDiagnosticsSelinuxChecks.kt')
STUBS = {
    'Context.kt': '''package android.content
class Context(val packageName:String="com.waenhancer") {
 val packageManager=android.content.pm.PackageManager(packageName)
}
''',
    'PackageManager.kt': '''package android.content.pm
class ApplicationInfo
class PackageInfo { val versionName="fixture"; val versionCode=1; val longVersionCode=1L; val applicationInfo:ApplicationInfo?=ApplicationInfo() }
class PackageManager(val own:String) {
 val lookups=mutableListOf<String>()
 fun getPackageInfo(name:String, flags:Int):PackageInfo {
  lookups.add(name); if(name!=own) throw IllegalArgumentException("fixture manager absent")
  return PackageInfo()
 }
 fun getApplicationLabel(info:ApplicationInfo):CharSequence="fixture"
}
''',
    'Build.kt': '''package android.os
object Build {
 val MANUFACTURER="fixture"; val MODEL="host JVM"; val SUPPORTED_ABIS=arrayOf("fixture")
 object VERSION { const val SDK_INT=30; const val RELEASE="11" }
}
object SELinux {
 var enforced=false; var failure:Throwable?=null; var calls=0
 @JvmStatic fun isSELinuxEnforced():Boolean { calls++; failure?.let { throw it }; return enforced }
}
''',
    'BuildConfig.kt': '''package com.waenhancer.app
object BuildConfig { const val VERSION_NAME="fixture"; const val VERSION_CODE=1; const val GIT_SHA="fixture"; const val MAPPING_ID="fixture" }
''',
    'PreferenceStores.kt': '''package com.waenhancer.config
object PreferenceStores { fun publicStore(context:android.content.Context)=Store() }
class Store {
 fun getInt(key:String, fallback:Int)=fallback
 fun getString(key:String, fallback:String?)=fallback
 fun getStringSet(key:String, fallback:Set<String>?):Set<String>?=fallback
}
''',
    'TargetAppManager.kt': '''package com.waenhancer.utils
object TargetAppManager { fun isModuleActive()=false }
''',
    'UpdateDownloader.kt': '''package com.waenhancer.update
object UpdateDownloader {
 var allowed=false; val requests=mutableListOf<Boolean>()
 fun hasCachedRootAccess():Boolean?=allowed
 fun hasRootAccess(force:Boolean):Boolean { requests.add(force); return allowed }
}
''',
    'AppRestartHelper.kt': '''package com.waenhancer.xposed.utils
object AppRestartHelper {
 var output:String?=null; var failure:Throwable?=null; val commands=mutableListOf<String>()
 fun runRootCommand(command:String):String? {
  commands.add(command)
  if(command!="getenforce") throw AssertionError("Only a read-only SELinux observation is allowed")
  failure?.let { throw it }; return output
 }
}
''',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    compiler = shutil.which('kotlinc')
    if compiler is None or shutil.which('java') is None:
        raise RuntimeError('Kotlin compiler and Java are required')
    origin = args.source_root.resolve() / SOURCE
    with tempfile.TemporaryDirectory(prefix='waex_selinux_diagnostics_') as temporary:
        out = (args.out or Path(temporary)).resolve(); out.mkdir(parents=True, exist_ok=True)
        src = out / 'sources'; src.mkdir(exist_ok=True)
        target = src / SOURCE.name; target.write_bytes(origin.read_bytes())
        fixture = src / FIXTURE.name; fixture.write_bytes((ROOT / FIXTURE).read_bytes())
        for name, body in STUBS.items():
            (src / name).write_text(body, encoding='utf-8')
        record = {'source': str(origin), 'source_sha256': sha(origin),
                  'fixture_sha256': sha(ROOT / FIXTURE), 'runner_sha256': sha(Path(__file__)),
                  'complete_production_class': True, 'production_paths_rewritten': False,
                  'android_or_root_executed': False,
                  'explicit_fixture_sha256': {name: sha(src / name) for name in STUBS}}
        jar = out / 'checks.jar'
        command = [compiler, '-nowarn', '-language-version', '2.0', '-jvm-target', '17',
                   *map(str, sorted(src.glob('*.kt'))), '-include-runtime', '-d', str(jar)]
        with (out / 'compile.log').open('w') as stream:
            compiled = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=90)
        record['compile_exit_code'] = compiled.returncode
        if compiled.returncode == 0:
            with (out / 'behavior.log').open('w') as stream:
                run = subprocess.run(['java', '-cp', str(jar), 'com.waenhancer.utils.SystemDiagnosticsSelinuxChecksKt'],
                                     stdout=stream, stderr=subprocess.STDOUT, timeout=30)
            match = re.search(r'SELINUX_DIAGNOSTICS scenarios=(\d+) checks=(\d+) failures=(\d+)',
                              (out / 'behavior.log').read_text())
            record.update(behavior_exit_code=run.returncode,
                          scenarios=int(match[1]) if match else 0,
                          checks=int(match[2]) if match else 0,
                          failures=int(match[3]) if match else None)
        record['accepted'] = (compiled.returncode == 0 and record.get('behavior_exit_code') == 0
                              and record.get('scenarios') == 20 and record.get('failures') == 0)
        (out / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
        print(json.dumps(record), flush=True)
        if not record['accepted']:
            for name in ('compile.log', 'behavior.log'):
                if (out / name).exists():
                    print((out / name).read_text())
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
