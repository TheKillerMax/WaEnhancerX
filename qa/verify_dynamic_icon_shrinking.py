#!/usr/bin/env python3
"""Build an isolated AGP 9.0.1 fixture with the production dynamic icon resources.

Requires Java, the reviewed Gradle wrapper, Android SDK 36/Build Tools 36.0.0 and
network access to Gradle/Maven dependencies. Produces temporary fixture APKs, NOT
WaEnhancerX APKs. Does not load private licensing code, install anything or run
LSPosed. Only text evidence belongs in artifacts or pull requests.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from test_dynamic_menu_resources import validate

SETTINGS = '''pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }
dependencyResolutionManagement { repositories { google(); mavenCentral() } }
rootProject.name="icon-fixture"
'''
BUILD = '''plugins { id "com.android.application" version "9.0.1" }
android { namespace "org.waex.qa.fixture"; compileSdk 36;
 defaultConfig { applicationId "org.waex.qa.fixture"; minSdk 24; targetSdk 36; versionCode 1; versionName "qa" }
 buildTypes { release { minifyEnabled true; shrinkResources true; proguardFiles getDefaultProguardFile("proguard-android-optimize.txt") } }
}
'''
ACTIVITY = '''package org.waex.qa.fixture;
public class ProbeActivity extends android.app.Activity {
 public void onCreate(android.os.Bundle state) {
  super.onCreate(state);
  android.view.View v=new android.view.View(this);
  v.setBackgroundResource(R.drawable.ic_waex_download); setContentView(v);
  try {
   java.io.InputStream in=getAssets().open("icons.json");
   java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream();
   byte[] b=new byte[1024];int n;while((n=in.read(b))>=0)out.write(b,0,n);in.close();
   org.json.JSONArray list=new org.json.JSONArray(out.toString("UTF-8"));
   for(int i=0;i<list.length();i++) android.util.Log.i("ResourceQA",
    Integer.toString(getResources().getIdentifier(list.getString(i),"drawable",getPackageName())));
  } catch(Exception e) { throw new RuntimeException(e); }
 }
}
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();root=args.root.resolve();base=args.out.resolve()
    if base.exists():raise ValueError('Use a new output directory; do not reuse old build evidence')
    versions=(root/'gradle/libs.versions.toml').read_text()
    if 'androidGradlePlugin = "9.0.1"' not in versions:
        raise ValueError('Review the fixture toolchain after an AGP version change')
    names=validate(root)
    sdk=os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
    if not sdk:raise ValueError('Android SDK is required')
    aapt=Path(sdk)/'build-tools/36.0.0/aapt2'
    if not aapt.is_file():raise ValueError('Build Tools 36.0.0 aapt2 required')
    base.mkdir(parents=True);out=base/'evidence';out.mkdir();fixture=base/'fixture';fixture.mkdir()
    src=fixture/'src/main';(src/'java/org/waex/qa/fixture').mkdir(parents=True)
    (src/'assets').mkdir();(src/'res/drawable').mkdir(parents=True);(src/'res/raw').mkdir()
    (fixture/'settings.gradle').write_text(SETTINGS)
    (fixture/'build.gradle').write_text(BUILD)
    (fixture/'gradle.properties').write_text('org.gradle.jvmargs=-Xmx3g\nandroid.useAndroidX=true\n')
    (src/'AndroidManifest.xml').write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application android:label="Resource QA"><activity android:name=".ProbeActivity" android:exported="true"><intent-filter><action android:name="android.intent.action.MAIN"/><category android:name="android.intent.category.LAUNCHER"/></intent-filter></activity></application></manifest>')
    (src/'assets/icons.json').write_text(json.dumps(names))
    (src/'java/org/waex/qa/fixture/ProbeActivity.java').write_text(ACTIVITY)
    sources={}
    for name in names:
        p=root/'app/src/main/res/drawable'/(name+'.xml')
        shutil.copy2(p,src/'res/drawable'/p.name)
        sources[str(p.relative_to(root))]=hashlib.sha256(p.read_bytes()).hexdigest()
    keep=root/'app/src/main/res/raw/waex_dynamic_menu_icons_keep.xml'
    sources[str(keep.relative_to(root))]=hashlib.sha256(keep.read_bytes()).hexdigest()
    (out/'source-sha256.json').write_text(json.dumps(sources,indent=2))
    for p in ['build.gradle','settings.gradle','gradle.properties']:shutil.copy2(fixture/p,out/p)
    (out/'ProbeActivity.java').write_text(ACTIVITY)
    results={}
    for label in ['baseline','retained']:
        if label=='retained':shutil.copy2(keep,src/'res/raw'/keep.name)
        cmd=['bash',str(root/'gradlew'),'--no-daemon','-p',str(fixture),'clean','assembleRelease']
        with (out/(label+'-build.log')).open('w') as log:
            proc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=600)
        if proc.returncode:
            print((out/(label+'-build.log')).read_text()[-18000:])
            raise RuntimeError('Fixture build failed: '+label)
        apks=list((fixture/'build/outputs/apk/release').glob('*.apk'))
        if len(apks)!=1:raise RuntimeError('Expected one fixture APK')
        proc=subprocess.run([str(aapt),'dump','resources',str(apks[0])],capture_output=True,text=True,check=True,timeout=60)
        (out/(label+'-resources.txt')).write_text(proc.stdout)
        present=set(re.findall(r'\sresource 0x[0-9a-fA-F]{8} drawable/(\S+)',proc.stdout))
        results[label]={'present':[n for n in names if n in present], 'missing':[n for n in names if n not in present],
                        'fixture_apk_sha256':hashlib.sha256(apks[0].read_bytes()).hexdigest()}
        (out/'results.json').write_text(json.dumps(results,indent=2))
    if results['baseline']['present']!=['ic_waex_download']:
        raise AssertionError('Baseline did not reproduce the reviewed removal: '+str(results))
    if len(results['retained']['present'])!=len(names) or results['retained']['missing']:
        raise AssertionError('Retention failed: '+str(results))
    print('AGP 9.0.1 optimized fixture: 1 ->',len(names),'of',len(names),
          'drawables. Not a WAEX build, installation or LSPosed test.')

if __name__=='__main__':main()
