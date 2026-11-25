#!/usr/bin/env python3
"""Compile the complete public Channel hook and exercise real Android View lifecycle.

Robolectric API 24/28/34; real current BaseFeature, HookRegistrar, ViewHookDispatcher,
privacy/JID support. Only discovery results and Xposed callback dispatch are controlled.
No private interfaces, source projection, Meta AI replacement, host scan or injection.
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

import android_media_preview_test as framework
from kotlin_compiler import compiler_command

ROOT = Path(__file__).resolve().parents[1]
JAVA = Path('app/src/main/java/com/waenhancer')
CHANNEL = JAVA/'xposed/features/customization/ChannelRecommendationsFilterHook.kt'
SUPPORT = [JAVA/p for p in (
    'xposed/core/BaseFeature.kt', 'xposed/core/HookRegistrar.java',
    'xposed/core/ViewHookDispatcher.java', 'xposed/utils/HookErrors.java',
    'xposed/core/privacy/PrivacyPrefs.java', 'xposed/core/privacy/PrivacyToggle.java',
    'xposed/core/wa/WaJid.java', 'config/DndPreferencePolicy.java')]
FIXTURES = ROOT/'qa/fixtures/channel_visibility'
BASELINE_FAILURES = {
    'channelRecommendationsAreHiddenAfterHostRebind': 3,
    'channelHidingPreservesHostLayoutParameters': 3,
    'missingChannelTargetIsReported': 3,
    'nonViewChannelTargetIsRejected': 3,
}
ANNOTATION_SHA = '1e343917ebf27ba96fe4dc52b1cad7fd32b738fbc6355bb6cd5b3b305d7212d0'
CORE_SHA = 'd1f5a319a77555df7e23858ffb5ed45a95ebb4263fa1ab7a993510ceb53555a0'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--deps', type=Path, required=True)
    parser.add_argument('--dexkit-jar', type=Path, required=True)
    parser.add_argument('--core-api-jar', type=Path, required=True)
    parser.add_argument('--annotation-api-jar', type=Path, required=True)
    parser.add_argument('--sdk-jars', type=Path)
    parser.add_argument('--maven-repo', type=Path)
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--expected-failures', type=Path)
    args = parser.parse_args()
    if args.baseline and args.expected_failures:
        parser.error('Choose one negative-result contract')
    root, out = args.source_root.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    deps = args.deps.resolve()
    dexkit = framework.verify_api(args.dexkit_jar.resolve(), framework.DEXKIT_SHA256, 2*1024*1024)
    core = framework.verify_api(args.core_api_jar.resolve(), CORE_SHA, 4*1024*1024)
    annotation = framework.verify_api(args.annotation_api_jar.resolve(), ANNOTATION_SHA, 1024*1024)
    kotlin_home, compiler = framework.find_kotlin()
    framework.run([*compiler_command(compiler), '-version'], out/'kotlin-version.log', timeout=45)
    if 'kotlinc-jvm 2.0.20 ' not in (out/'kotlin-version.log').read_text():
        raise RuntimeError('Expected exactly Kotlin 2.0.20')
    framework.run(['java', '-version'], out/'java-version.log', timeout=30)
    framework.run(['javac', '-version'], out/'javac-version.log', timeout=30)
    dependencies = sorted(deps.glob('*.jar')) + [dexkit, core, annotation, kotlin_home/'lib/kotlin-stdlib.jar']
    if len({p.name for p in dependencies}) != len(dependencies):
        raise RuntimeError('Duplicate dependency names')
    (out/'dependency-sha256.json').write_text(json.dumps({str(p): sha(p) for p in dependencies}, indent=2)+'\n')
    toolchain = [compiler, kotlin_home/'lib/kotlin-compiler.jar', kotlin_home/'lib/kotlin-stdlib.jar']
    toolchain += [Path(shutil.which(name)).resolve() for name in ('java', 'javac')]
    (out/'toolchain-sha256.json').write_text(json.dumps({str(p): sha(p) for p in toolchain}, indent=2)+'\n')
    paths = [CHANNEL] + SUPPORT
    if not args.baseline:
        paths += [JAVA/'xposed/utils/ViewVisibilityGuard.java', JAVA/'xposed/utils/ViewClassSelector.java']
    stage, classes = out/'sources', out/'classes'
    classes.mkdir()
    sources, identities = [], {}
    for relative in paths:
        src, dst = root/relative, stage/relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        identities[relative.as_posix()] = sha(src)
        sources.append(dst)
    fixture = FIXTURES/'runtime_doubles.py'
    tree = ast.parse(fixture.read_text())
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'STUBS' for t in node.targets))
    doubles = ast.literal_eval(assignment.value)
    if any(name.startswith(('android/', 'androidx/', 'org/luckypray/', 'com/waenhancer/hooking/')) for name in doubles):
        raise RuntimeError('Framework, DexKit and private contracts cannot be fixture replacements')
    ids = sorted(set(re.findall(r'R\.string\.(\w+)', '\n'.join((root/p).read_text() for p in paths))))
    doubles['com/waenhancer/app/R.java'] = ('package com.waenhancer.app; public final class R { public static final class string {'
        + ''.join(f'public static final int {key}={i+1};' for i,key in enumerate(ids)) + '}}')
    boundaries = {}
    for name, contents in doubles.items():
        target = stage/'host-boundaries'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding='utf-8')
        sources.append(target)
        boundaries[name] = sha(target)
    tests = ['ChannelVisibilityBindingTest.java']
    if not args.baseline:
        tests += ['ChannelVisibilityLifecycleTest.java', 'ViewClassSelectorTest.java']
    expected_tests = 0
    for name in tests:
        src, dst = FIXTURES/name, stage/name
        shutil.copyfile(src, dst)
        identities['qa/fixtures/channel_visibility/'+name] = sha(src)
        expected_tests += 3*len(re.findall(r'@Test\b', src.read_text()))
    identities['qa/fixtures/channel_visibility/runtime_doubles.py'] = sha(fixture)
    for name in ['android_channel_visibility_test.py', 'android_media_preview_test.py', 'kotlin_compiler.py']:
        identities['qa/'+name] = sha(ROOT/'qa'/name)
    android = deps/'android-all-14-robolectric-10818077.jar'
    production_cp = os.pathsep.join(map(str, [android, dexkit, core, annotation, kotlin_home/'lib/kotlin-stdlib.jar']))
    cp = str(classes)+os.pathsep+os.pathsep.join(map(str, dependencies))
    framework.run([*compiler_command(compiler), '-jvm-target', '17', '-classpath', production_cp,
                   '-d', str(classes), *map(str, sources)], out/'kotlinc-complete-channel.log', timeout=240)
    framework.run(['javac', '--release', '17', '-encoding', 'UTF-8', '-cp', cp, '-d', str(classes),
                   *[str(p) for p in sources if p.suffix == '.java']], out/'javac-public-support.log', timeout=240)
    framework.run(['javac', '--release', '17', '-encoding', 'UTF-8', '-cp', cp, '-d', str(classes),
                   *[str(stage/name) for name in tests]], out/'javac-tests.log', timeout=180)
    opens = ['java.base/java.lang', 'java.base/java.util', 'java.base/java.util.concurrent',
             'java.base/java.io', 'java.base/java.net', 'java.base/java.security', 'java.base/java.text',
             'java.base/jdk.internal.access', 'java.desktop/java.awt.font', 'jdk.compiler/com.sun.tools.javac.api']
    command = ['java', '-Xmx1g', *['--add-opens='+p+'=ALL-UNNAMED' for p in opens],
               '-Drobolectric.dependency.repo.url=https://repo.maven.apache.org/maven2']
    if args.sdk_jars:
        if len(list(args.sdk_jars.glob('*.jar'))) != 3:
            raise RuntimeError('Require exactly the API24/28/34 instrumented artifacts')
        command += ['-Drobolectric.offline=true', '-Drobolectric.dependency.dir='+str(args.sdk_jars.resolve())]
    if args.maven_repo:
        command += ['-Dmaven.repo.local='+str(args.maven_repo.resolve())]
    command += ['-cp', cp, 'org.junit.runner.JUnitCore']
    command += ['com.waenhancer.xposed.features.customization.'+Path(name).stem for name in tests]
    result = framework.run(command, out/'junit.log', allow_failure=True, timeout=240)
    sdk_root = args.sdk_jars.resolve() if args.sdk_jars else (
        args.maven_repo.resolve() if args.maven_repo else Path.home()/'.m2/repository')/'org/robolectric/android-all-instrumented'
    sdk_jars = sorted(sdk_root.glob('*.jar' if args.sdk_jars else '*/*.jar'))
    (out/'sdk-sha256.json').write_text(json.dumps({str(p): sha(p) for p in sdk_jars}, indent=2)+'\n')
    junit = (out/'junit.log').read_text()
    passed = re.search(r'OK \((\d+) tests?\)', junit)
    failed = re.search(r'Tests run: (\d+),\s+Failures: (\d+)', junit)
    tests_run = int(passed[1]) if passed else int(failed[1]) if failed else 0
    failures = re.findall(r'^\d+\) ([^(\[]+)(?:\[[^\n]*?\])?\([^\n]+\)\n([^\n]+)', junit, re.M)
    observed = {}
    for name, error in failures:
        observed[name] = observed.get(name, 0)+1
    expected = BASELINE_FAILURES if args.baseline else json.loads(args.expected_failures.read_text()) if args.expected_failures else {}
    assertion_only = all(error.startswith(('java.lang.AssertionError', 'org.junit.ComparisonFailure')) for _, error in failures)
    accepted = tests_run == expected_tests and observed == expected and assertion_only
    accepted = accepted and (result != 0 and len(failures) == sum(expected.values()) if expected else result == 0 and passed is not None)
    record = {'mode': 'current-baseline' if args.baseline else 'negative-control' if expected else 'candidate',
              'complete_channel_compilation': True, 'source_projection': False, 'private_contract_doubles': False,
              'tests': tests_run, 'expected_tests': expected_tests, 'failures': len(failures),
              'observed_failures': observed, 'expected_failures': expected, 'assertion_only': assertion_only,
              'junit_exit': result, 'accepted': accepted, 'source_sha256': identities,
              'boundary_sha256': boundaries, 'source_root': str(root), 'scope': __doc__}
    (out/'result.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps({k:record[k] for k in ['mode','tests','failures','observed_failures','accepted']}))
    if not accepted:
        raise RuntimeError('Android behavior differs from the declared exact oracle')

if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, StopIteration, subprocess.SubprocessError) as error:
        print('ERROR:', error, flush=True)
        raise SystemExit(2)
