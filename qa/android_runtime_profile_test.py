#!/usr/bin/env python3
"""Run current profile UID contracts on cached Robolectric API24/28/34 and both unit consumers.

The complete UID parser/probe helper and public models are compiled against Android-all.
RootProbe and detector model/selection members are literal slices with byte-span receipts.
PackageManager/ApplicationInfo/Process are Android framework APIs with standard Robolectric
shadows; root output and SQLite staging are explicit boundaries. No device or real su is used.
Use --deps and --sdk-jars together for a fully offline run. Without them, the pinned
Robolectric graph is resolved by the shared Maven helper and SDKs by Robolectric.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tomllib
import zipfile
from kotlin_compiler import compiler_command
from runtime_source_slices import runtime_model_slices

ROOT = Path(__file__).resolve().parents[1]
BASE = Path('app/src/main/java/com/waenhancer/utils')
FULL = ('AndroidUserScope.java', 'DeclaredWhatsAppTargets.java', 'InjectionEvidence.kt', 'XposedRuntimeInspector.kt')
UNITS = ('WhatsAppPackageDetectorTest.kt', 'TargetScopeStateTest.kt')
FRAMEWORK_TESTS = 36
UNIT_TESTS = 26


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(command, log, timeout=90, cwd=None):
    with log.open('w', encoding='utf-8') as stream:
        result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout, cwd=cwd)
    print(log.name + ' exit=' + str(result.returncode), flush=True)
    return result.returncode


def resource_tools(sdk):
    """Use an installed SDK only; this fixture never downloads or licenses SDK tools."""
    if sdk is None or not sdk.is_dir():
        raise RuntimeError('An existing Android SDK is required for the resource-only test APK')
    executable = 'aapt2.exe' if os.name == 'nt' else 'aapt2'
    tools = []
    for path in (sdk/'build-tools').glob('*/'+executable):
        if re.fullmatch(r'\d+\.\d+\.\d+', path.parent.name):
            tools.append((tuple(map(int, path.parent.name.split('.'))), path))
    platforms = []
    for path in (sdk/'platforms').glob('android-*/android.jar'):
        match = re.fullmatch(r'android-(\d+)', path.parent.name)
        if match and int(match[1]) >= 34:
            platforms.append((int(match[1]), path))
    if not tools or not platforms:
        raise RuntimeError('Installed aapt2 and stable Android platform 34 or newer required')
    tools.sort();platforms.sort()
    aapt = next((p for version, p in tools if version == (34, 0, 0)), tools[-1][1])
    android = platforms[0][1]
    return aapt, android


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--deps', type=Path)
    parser.add_argument('--sdk-jars', type=Path)
    parser.add_argument('--maven', default='mvn')
    parser.add_argument('--maven-repo', type=Path)
    parser.add_argument('--android-sdk', type=Path,
                        default=os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root, out = args.source_root.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    stage, classes, units = out/'sources', out/'classes', out/'unit-classes'
    stage.mkdir(); classes.mkdir(); units.mkdir()
    compiler = os.environ.get('KOTLINC') or shutil.which('kotlinc')
    if not compiler:
        raise RuntimeError('Kotlin compiler is required')
    stdlib = Path(compiler).resolve().parents[1]/'lib/kotlin-stdlib.jar'
    deps = args.deps.resolve() if args.deps else out/'deps'
    if not args.deps:
        deps.mkdir()
        kotlin = tomllib.loads((root/'gradle/libs.versions.toml').read_text())['versions']['kotlin']
        pom = '''<project xmlns="http://maven.apache.org/POM/4.0.0">
<modelVersion>4.0.0</modelVersion><groupId>org.waex.qa</groupId><artifactId>runtime-profile-qa</artifactId><version>1</version>
<repositories><repository><id>google</id><url>https://dl.google.com/dl/android/maven2/</url></repository></repositories>
<dependencies>
<dependency><groupId>org.robolectric</groupId><artifactId>robolectric</artifactId><version>4.17</version></dependency>
<dependency><groupId>org.robolectric</groupId><artifactId>android-all</artifactId><version>14-robolectric-10818077</version></dependency>
<dependency><groupId>junit</groupId><artifactId>junit</artifactId><version>4.13.2</version></dependency>
<dependency><groupId>org.jetbrains.kotlin</groupId><artifactId>kotlin-stdlib</artifactId><version>KOTLIN</version></dependency>
</dependencies></project>
'''.replace('KOTLIN', kotlin)
        (out/'pom.xml').write_bytes(pom.encode('utf-8'))
        from maven_dependencies import resolve_dependencies, DEPENDENCY_GOAL
        command = [args.maven, '-B', '-f', str(out/'pom.xml'), DEPENDENCY_GOAL, '-DoutputDirectory='+str(deps)]
        if args.maven_repo:
            command.append('-Dmaven.repo.local='+str(args.maven_repo.resolve()))
        resolve_dependencies(command, out/'dependencies.log', timeout=600)
        for archive in deps.glob('*.aar'):
            with zipfile.ZipFile(archive) as bundle:
                for name in bundle.namelist():
                    if name == 'classes.jar' or (name.startswith('libs/') and name.endswith('.jar')):
                        (deps/(archive.stem+'-'+name.replace('/', '_'))).write_bytes(bundle.read(name))
    jars = sorted(deps.glob('*.jar'))
    android = [p for p in jars if p.name == 'android-all-14-robolectric-10818077.jar']
    if len(android) != 1 or not stdlib.is_file():
        raise RuntimeError('Pinned Android-all 14 compile jar and Kotlin distribution stdlib required')
    if not any(p.name == 'robolectric-4.17.jar' for p in jars):
        raise RuntimeError('Robolectric 4.17 required')
    if not any(p.name.startswith('kotlin-stdlib-') for p in jars):
        jars.append(stdlib)
    (out/'dependency-sha256.json').write_bytes((json.dumps({str(p): digest(p) for p in jars}, indent=2)+'\n').encode())
    identities = {}
    for name in FULL:
        path = root/BASE/name
        shutil.copyfile(path, stage/name)
        identities[str(BASE/name)] = digest(path)
    model_sources, extraction_receipts = runtime_model_slices(root)
    for name, content in model_sources.items():
        (stage/name).write_bytes(content.encode('utf-8'))
    fixture_root = ROOT/'qa/fixtures/runtime_profile'
    fixture_hashes = {}
    for name in ('AppRestartHelper.java', 'RuntimeProfileInspectorTest.java'):
        path = fixture_root/name
        shutil.copyfile(path, stage/name)
        fixture_hashes[str(path.relative_to(ROOT))] = digest(path)
    manifest = fixture_root/'AndroidManifest.xml'
    manifest_resource = classes/'qa/fixtures/runtime_profile/AndroidManifest.xml'
    manifest_resource.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(manifest, manifest_resource)
    fixture_hashes[str(manifest.relative_to(ROOT))] = digest(manifest)
    aapt, platform = resource_tools(args.android_sdk)
    resource_inputs = {str(p): digest(p) for p in (aapt, platform)}
    resource_apk = out/'runtime-profile-resources.apk'
    resource_command = [str(aapt), 'link', '-o', str(resource_apk),
                        '--manifest', str(manifest_resource), '-I', str(platform)]
    if execute(resource_command, out/'aapt2-link.log'):
        raise RuntimeError('INFRASTRUCTURE_FAILURE: resource-only manifest compilation')
    if not resource_apk.is_file():
        raise RuntimeError('aapt2 did not create the resource-only test APK')
    fixture_hashes['generated/runtime-profile-resources.apk'] = digest(resource_apk)
    build_properties = classes/'com/android/tools/test_config.properties'
    build_properties.parent.mkdir(parents=True, exist_ok=True)
    build_properties.write_bytes(('android_custom_package=com.waenhancer\n'
                                  'android_merged_manifest='+manifest_resource.as_uri()+'\n'
                                  'android_resource_apk='+resource_apk.as_uri()+'\n').encode('utf-8'))
    fixture_hashes['generated/test_config.properties'] = digest(build_properties)
    unit_paths = []
    for name in UNITS:
        path = root/'app/src/test/java/com/waenhancer/utils'/name
        shutil.copyfile(path, stage/name);unit_paths.append(stage/name)
        fixture_hashes[str(path.relative_to(root))] = digest(path)
    android_cp = os.pathsep.join(map(str, [*android, stdlib]))
    runtime_cp = os.pathsep.join(map(str, [classes, *jars]))
    unit_cp = os.pathsep.join(map(str, [classes, *android, stdlib, *[
        p for p in jars if p.name.startswith(('junit-', 'hamcrest-'))]]))
    commands = [
        ['javac', '--release', '17', '-cp', android_cp, '-d', str(classes),
         *[str(stage/name) for name in ('AndroidUserScope.java', 'DeclaredWhatsAppTargets.java', 'AppRestartHelper.java')]],
        [*compiler_command(compiler), '-language-version', '2.0', '-jvm-target', '17',
         '-classpath', os.pathsep.join([str(classes), android_cp]), '-d', str(classes),
         *[str(stage/name) for name in ('InjectionEvidence.kt', 'XposedRuntimeInspector.kt', *model_sources)]],
        ['javac', '--release', '17', '-cp', runtime_cp, '-d', str(classes), str(stage/'RuntimeProfileInspectorTest.java')],
        [*compiler_command(compiler), '-language-version', '2.0', '-jvm-target', '17',
         '-classpath', unit_cp, '-Xfriend-paths='+str(classes), '-d', str(units), *map(str, unit_paths)],
    ]
    for command, name in zip(commands, ('javac-production.log', 'kotlinc-production.log', 'javac-framework.log', 'kotlinc-units.log')):
        if execute(command, out/name):
            print((out/name).read_text(encoding='utf-8'))
            raise RuntimeError('INFRASTRUCTURE_FAILURE: ' + name)
    print('COMPILE_OK: Android profile contracts and both current unit consumers', flush=True)
    sdk_hashes = {}
    sdk_arguments = []
    if args.sdk_jars:
        sdk = out/'sdk-cache';sdk.mkdir()
        for jar in args.sdk_jars.resolve().rglob('android-all-instrumented-*.jar'):
            target = sdk/jar.name
            if not target.exists():
                os.link(jar, target)  # Immutable cache inputs on the same volume; no duplicate SDK data.
            sdk_hashes[jar.name] = digest(jar)
        if not sdk_hashes:
            raise RuntimeError('Instrumented SDK jars absent')
        sdk_arguments = ['-Drobolectric.offline=true', '-Drobolectric.dependency.dir='+str(sdk)]
        (out/'sdk-sha256.json').write_bytes((json.dumps(sdk_hashes, indent=2)+'\n').encode())
    else:
        sdk_arguments = ['-Drobolectric.dependency.repo.url=https://repo.maven.apache.org/maven2']
    if args.maven_repo:
        sdk_arguments.append('-Dmaven.repo.local='+str(args.maven_repo.resolve()))
    opens = ['java.base/java.lang', 'java.base/java.util', 'java.base/java.io', 'java.base/java.net',
             'java.base/java.security', 'java.base/java.text', 'java.base/jdk.internal.access',
             'java.desktop/java.awt.font', 'jdk.compiler/com.sun.tools.javac.api']
    framework = ['java', '-Xmx1g', *['--add-opens='+item+'=ALL-UNNAMED' for item in opens],
                 *sdk_arguments, '-cp', runtime_cp,
                 'org.junit.runner.JUnitCore', 'com.waenhancer.utils.RuntimeProfileInspectorTest']
    unit = ['java', '-cp', os.pathsep.join([str(units), unit_cp]), 'org.junit.runner.JUnitCore',
            'com.waenhancer.utils.WhatsAppPackageDetectorTest', 'com.waenhancer.utils.TargetScopeStateTest']
    results = []
    for name, command, expected in [('framework', framework, FRAMEWORK_TESTS), ('units', unit, UNIT_TESTS)]:
        code = execute(command, out/(name+'.log'), timeout=120, cwd=root)
        output = (out/(name+'.log')).read_text(encoding='utf-8')
        passed = re.search(r'OK \((\d+) tests?\)', output)
        accepted = code == 0 and passed is not None and int(passed[1]) == expected
        results.append({'suite': name, 'command': command, 'exit': code, 'expected_tests': expected,
                        'actual_tests': int(passed[1]) if passed else None, 'accepted': accepted})
        if not accepted:
            print(output[-12000:])
    summary = {'full_production_sha256': identities, 'extractions': extraction_receipts,
               'fixture_sha256': fixture_hashes, 'commands': commands, 'results': results,
               'resource_command': resource_command, 'resource_tool_sha256': resource_inputs,
               'harness_sha256': digest(Path(__file__)), 'existing_unit_consumers_executed': True,
               'limits': 'Robolectric API24/28/34 framework APIs; standard UID/package shadows; controlled root output and unavailable scope staging. No actual work profile, root, kernel, LSPosed, device or whole app acceptance.'}
    (out/'result.json').write_bytes((json.dumps(summary, indent=2)+'\n').encode())
    if any(digest(Path(path)) != expected for path, expected in resource_inputs.items()):
        raise RuntimeError('Installed resource compiler inputs changed during validation')
    print(json.dumps(results), flush=True)
    if not all(row['accepted'] for row in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
