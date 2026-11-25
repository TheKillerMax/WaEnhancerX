#!/usr/bin/env python3
"""Build one isolated x86_64 JNI-constants APK on a disposable Linux runner."""
import argparse
import datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile

import validate_native_constants_probe as validate

HELPER_PINS = {
    'native_diagnostics_ndk27_lab.py': '23af81cfd5800470676f2075df267daa2099e8428a464c7ae7e1bc1acb9e5235',
    'android_emulator_lab_preflight.py': '095e06cc348e6d6cd895a8f4ee1bbec7770cb2b9c1fee5822002e1cf11c99923',
}
AUDIT_REVISION = '1c50db163ee1b8127288ea27a055242c9899541f'
AUDITOR_SHA256 = 'e9d840a160943cf10cd766977a341e256a1815a0e87f5a9cb89bb31d2094faa1'
FIXTURE = Path(__file__).parent / 'native_constants_probe'
require = validate.require


def verify_badging(text):
    """Accept the two observed/documented minimum-SDK field spellings, without ambiguity."""
    lines = [line.strip() for line in text.splitlines()]
    minima = [line for line in lines if line.startswith(('sdkVersion:', 'minSdkVersion:'))]
    require(len(minima) == 1, 'Missing or ambiguous minimum-SDK field')
    match = re.fullmatch(r"(sdkVersion|minSdkVersion):'24'", minima[0])
    require(match is not None, 'Minimum SDK must be exactly 24')
    require([line for line in lines if line.startswith('targetSdkVersion:')]
            == ["targetSdkVersion:'36'"], 'Target SDK must occur once and equal 36')
    packages = [line for line in lines if line.startswith('package:')]
    require(len(packages) == 1 and re.match(
        r"^package: name='" + re.escape(validate.PACKAGE) + r"'(?:\s|$)", packages[0]),
        'Unexpected package identity')
    require([line for line in lines if line.startswith('native-code:')] == ["native-code: 'x86_64'"],
            'Expected only x86_64 native code')
    require(not any(line.startswith('uses-permission') for line in lines), 'Unexpected APK permission')
    return {'package': validate.PACKAGE, 'minimum_sdk': 24, 'minimum_field_observed': match.group(1),
            'target_sdk': 36, 'native_abis': ['x86_64'], 'permissions': []}


def verify_manifest(path):
    root = ET.parse(path).getroot()
    a = '{http://schemas.android.com/apk/res/android}'
    require(root.tag == 'manifest' and root.get('package') == validate.PACKAGE, 'Source manifest package')
    require([node.tag for node in root] == ['uses-sdk', 'application', 'instrumentation'],
            'Unexpected manifest components/permissions')
    sdk, app, instrumentation = list(root)
    require(sdk.get(a + 'minSdkVersion') == '24' and sdk.get(a + 'targetSdkVersion') == '36',
            'Source manifest SDK')
    require(not list(app) and all(app.get(a + key) == expected for key, expected in {
        'testOnly': 'true', 'debuggable': 'false', 'allowBackup': 'false',
        'usesCleartextTraffic': 'false', 'extractNativeLibs': 'false'}.items()), 'Application flags')
    require(instrumentation.get(a + 'name') == '.NativeConstantsInstrumentation'
            and instrumentation.get(a + 'targetPackage') == validate.PACKAGE, 'Instrumentation identity')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-repo', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = {'status': 'BLOCKED', 'schema': 'WAEXDIAG_PROBE_BUILD_V2',
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'jni_executed': False, 'android_booted': False, 'licenses_accepted_by_this_run': False,
              'scope': validate.SCOPE, 'package': validate.PACKAGE,
              'source_revision': validate.SOURCE_REVISION, 'source_sha256': validate.SOURCE_SHA256,
              'cmake_sha256': validate.CMAKE_SHA256, 'contract_sha256': validate.CONTRACT_SHA256}
    key = sdk = before_licenses = None
    env = dict(os.environ)
    native = lab = None
    try:
        require(sys.platform == 'linux', 'This builder is only for a disposable Linux runner')
        for name, expected in HELPER_PINS.items():
            require(validate.digest((Path(__file__).parent / name).read_bytes()) == expected, 'Helper identity: ' + name)
        import native_diagnostics_ndk27_lab as native
        lab = native.lab
        lab.context_check(env)
        temp = Path(env['RUNNER_TEMP']).resolve()
        require(out.is_relative_to(temp), 'Reports must be inside RUNNER_TEMP')
        work = temp / 'waex-native-constants-v2-work'
        work.mkdir(exist_ok=False)
        logs = out / 'logs'
        logs.mkdir()
        result['input_files'] = before = validate.source_inventory()
        verify_manifest(FIXTURE / 'AndroidManifest.xml')
        validate.contract()
        for name in ('CC', 'CXX', 'CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS',
                     'CMAKE_GENERATOR', 'CMAKE_TOOLCHAIN_FILE'):
            env.pop(name, None)
        sdk = Path(env.get('ANDROID_HOME', env.get('ANDROID_SDK_ROOT', ''))).resolve()
        jdk = Path(env.get('JAVA_HOME', '')).resolve()
        tools = {name: jdk / 'bin' / name for name in ('java', 'javac', 'keytool')}
        bt = sdk / 'build-tools/36.0.0'
        tools.update(android_jar=sdk / 'platforms/android-36/android.jar',
                     aapt2=bt / 'aapt2', zipalign=bt / 'zipalign', d8_jar=bt / 'lib/d8.jar',
                     apksigner_jar=bt / 'lib/apksigner.jar')
        require(all(path.is_file() for path in tools.values()) and shutil.which('unzip'), 'Required SDK/JDK tools missing')
        require(re.search(r'^Pkg.Revision\s*=\s*36\.0\.0\s*$', (bt / 'source.properties').read_text(), re.M),
                'Build tools are not the exact existing 36.0.0 package')
        require(re.search(r'^AndroidVersion.ApiLevel\s*=\s*36\s*$',
                          (sdk / 'platforms/android-36/source.properties').read_text(), re.M), 'SDK platform differs')
        run = lambda name, command, timeout=120: native.command(logs, name, command, env, timeout)
        require(run('javac-version', [tools['javac'], '-version']).strip().startswith('javac 17.'),
                'Reviewed JDK17 is required')
        result['tools'] = {name: {'path': str(path), 'sha256': lab.sha256_file(path)}
                           for name, path in tools.items()}
        audit = args.audit_repo.resolve()
        require(run('audit-head', ['git', '-C', audit, 'rev-parse', 'HEAD']).strip() == AUDIT_REVISION,
                'Audit/source checkout revision differs')
        source = audit / 'app/src/main/cpp/waex_diag.c'
        auditor_file = audit / 'qa/audit_native_alignment.py'
        cmake_input = Path(__file__).parent / 'fixtures/native_diag_16kb_CMakeLists.txt'
        for path, expected in ((source, validate.SOURCE_SHA256), (auditor_file, AUDITOR_SHA256),
                               (cmake_input, validate.CMAKE_SHA256)):
            require(lab.sha256_file(path) == expected, 'Frozen native input changed: ' + path.name)
        before_licenses = lab.license_files(sdk)
        with native.open_official(native.METADATA_URL) as response:
            metadata = response.read(4 * 1024**2 + 1)
        require(len(metadata) <= 4 * 1024**2 and b'<!DOCTYPE' not in metadata.upper()
                and b'<!ENTITY' not in metadata.upper(), 'Unsafe repository metadata')
        result['packages'] = native.confirm_metadata(ET.fromstring(metadata), before_licenses)
        result['metadata_sha256'] = validate.digest(metadata)
        result['license_registry_before'] = before_licenses
        destinations = {}
        for package in native.PACKAGES:
            destination, receipt = native.acquire(package, work, logs, env)
            destinations[package['name']] = destination
        ndk = destinations['ndk'] / 'android-ndk-r27'
        require(re.search(r'^Pkg.Revision\s*=\s*27\.0\.12077973\s*$',
                          (ndk / 'source.properties').read_text(), re.M), 'NDK revision differs')
        cmakes = list(destinations['cmake'].rglob('bin/cmake'))
        require(len(cmakes) == 1, 'Expected exactly one CMake executable')
        cmake, ninja = cmakes[0], cmakes[0].with_name('ninja')
        require(run('cmake-version', [cmake, '--version']).splitlines()[0]
                == 'cmake version 3.22.1-g37088a8', 'CMake banner differs')
        toolbin = ndk / 'toolchains/llvm/prebuilt/linux-x86_64/bin'
        project, build = work / 'native-source', work / 'native-build'
        project.mkdir()
        shutil.copyfile(source, project / 'waex_diag.c')
        shutil.copyfile(cmake_input, project / 'CMakeLists.txt')
        run('native-configure', [cmake, '-S', project, '-B', build, '-G', 'Ninja',
             '-DCMAKE_MAKE_PROGRAM=' + str(ninja),
             '-DCMAKE_TOOLCHAIN_FILE=' + str(ndk / 'build/cmake/android.toolchain.cmake'),
             '-DANDROID_ABI=x86_64', '-DANDROID_PLATFORM=android-24',
             '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON'])
        build_log = run('native-build', [cmake, '--build', build, '--parallel', '2', '--verbose'])
        require(all(flag in build_log for flag in ('-Wl,-z,max-page-size=16384', '-Wl,-z,common-page-size=16384')),
                'Reviewed linker flags missing')
        commands = json.loads((build / 'compile_commands.json').read_text())
        require(len(commands) == 1 and Path(commands[0]['file']).resolve() == project / 'waex_diag.c',
                'Unexpected compiled source')
        tokens = shlex.split(commands[0]['command'])
        require(Path(tokens[0]).resolve() == (toolbin / 'clang').resolve(), 'Compiler is not the exact NDK clang')
        targets = [token.split('=', 1)[1] for token in tokens if token.startswith('--target=')]
        targets += [tokens[i+1] for i, token in enumerate(tokens[:-1]) if token in ('-target', '--target')]
        require(len(targets) == 1 and re.fullmatch(r'x86_64(?:-none)?-linux-android24', targets[0]), 'Native ABI/API')
        library = build / 'libwaexdiag.so'
        require(0 < library.stat().st_size < 1024**2, 'Native library size')
        spec = importlib.util.spec_from_file_location('pinned_jni_auditor', auditor_file)
        auditor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(auditor)
        elf = auditor.inspect_elf(library.read_bytes())
        require(elf['elf_bits'] == 64 and elf['machine'] == 62 and elf['relro_segments']
                and not elf['issues'], 'Native ELF alignment/ABI issue')
        native.crosscheck_readelf(run('native-readelf', [toolbin / 'llvm-readelf', '--wide', '--program-headers', library]), elf)
        exports = native.jni_exports(run('native-exports', [toolbin / 'llvm-readelf', '--wide', '--dyn-syms', library]))
        elf_sha = lab.sha256_file(library)
        result['native'] = {'elf_sha256': elf_sha, 'bytes': library.stat().st_size,
                            'elf': elf, 'jni_exports': exports, 'api': 24, 'abi': 'x86_64',
                            'compiler_target': targets[0], 'compiler_path': str(Path(tokens[0]).resolve())}
        lab.save(logs, 'native-compile-commands.json', commands)
        generated = work / 'BuildIdentity.java'
        fields = {'SOURCE_REVISION': validate.SOURCE_REVISION, 'SOURCE_SHA256': validate.SOURCE_SHA256,
                  'CMAKE_SHA256': validate.CMAKE_SHA256, 'CONTRACT_SHA256': validate.CONTRACT_SHA256, 'ELF_SHA256': elf_sha}
        generated.write_text('package org.lab.waex.qa.nativeconstants;\nfinal class BuildIdentity {\n'
                             + ''.join(' static final String ' + key + ' = "' + value + '";\n'
                                       for key, value in fields.items()) + '}\n', encoding='utf-8')
        classes, dex, assets = work / 'classes', work / 'dex', work / 'assets'
        for directory in (classes, dex, assets):
            directory.mkdir()
        shutil.copyfile(FIXTURE / 'expected_constants.json', assets / 'expected_constants.json')
        run('javac', [tools['javac'], '--release', '8', '-g:none', '-encoding', 'UTF-8',
             '-classpath', tools['android_jar'], '-d', classes, generated,
             FIXTURE / 'NativeDiagPaths.java', FIXTURE / 'NativeConstantsInstrumentation.java'])
        class_files = sorted(classes.rglob('*.class'))
        require(len(class_files) == 3, 'Unexpected Java class inventory')
        run('d8', [tools['java'], '-cp', tools['d8_jar'], 'com.android.tools.r8.D8', '--release',
             '--min-api', '24', '--lib', tools['android_jar'], '--output', dex, *class_files])
        unsigned, aligned, apk = work / 'unsigned.apk', work / 'aligned.apk', out / 'native-constants-probe.apk'
        run('aapt-link', [tools['aapt2'], 'link', '-I', tools['android_jar'], '--manifest',
             FIXTURE / 'AndroidManifest.xml', '-A', assets, '-o', unsigned])
        with zipfile.ZipFile(unsigned, 'a') as archive:
            for name, data, compression in (('classes.dex', (dex / 'classes.dex').read_bytes(), zipfile.ZIP_DEFLATED),
                                             (validate.ELF_ENTRY, library.read_bytes(), zipfile.ZIP_STORED)):
                entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.compress_type = compression
                archive.writestr(entry, data)
        run('zipalign', [tools['zipalign'], '-P', '16', '-f', '4', unsigned, aligned])
        key = work / 'disposable-qa.p12'
        env['WAEX_NATIVE_QA_KEY_PASS'] = secrets.token_hex(32)
        run('keytool', [tools['keytool'], '-genkeypair', '-alias', 'qa', '-keyalg', 'RSA', '-keysize', '2048',
             '-validity', '1', '-storetype', 'PKCS12', '-dname', 'CN=DisposableNativeConstantsQA',
             '-keystore', key, '-storepass:env', 'WAEX_NATIVE_QA_KEY_PASS',
             '-keypass:env', 'WAEX_NATIVE_QA_KEY_PASS', '-noprompt'])
        signer = [tools['java'], '-jar', tools['apksigner_jar']]
        run('apk-sign', [*signer, 'sign', '--ks', key, '--ks-pass', 'env:WAEX_NATIVE_QA_KEY_PASS',
             '--key-pass', 'env:WAEX_NATIVE_QA_KEY_PASS', '--v1-signing-enabled', 'true',
             '--v2-signing-enabled', 'true', '--v3-signing-enabled', 'true', '--v4-signing-enabled', 'false',
             '--out', apk, aligned])
        signed = run('apk-signature', [*signer, 'verify', '--verbose', '--print-certs', '--min-sdk-version', '24', apk])
        require('Verified using v2 scheme (APK Signature Scheme v2): true' in signed, 'Missing v2 signature')
        result['badging'] = verify_badging(run('apk-badging', [tools['aapt2'], 'dump', 'badging', apk]))
        run('apk-manifest', [tools['aapt2'], 'dump', 'xmltree', apk, '--file', 'AndroidManifest.xml'])
        run('apk-alignment', [tools['zipalign'], '-c', '-P', '16', '4', apk])
        result['apk'] = validate.inspect_apk(apk, lab.sha256_file(apk), elf_sha)
        require(validate.source_inventory() == before, 'Probe source changed during build')
        require(lab.sha256_file(source) == validate.SOURCE_SHA256
                and lab.sha256_file(cmake_input) == validate.CMAKE_SHA256, 'Native source changed')
        native.space(work)
        result['status'] = 'PASS_BUILD_ONLY'
    except Exception as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        if key is not None and key.exists():
            key.unlink()
        env.pop('WAEX_NATIVE_QA_KEY_PASS', None)
        result['ephemeral_key_absent'] = key is None or not key.exists()
        if before_licenses is not None:
            result['license_registry_unchanged'] = lab.license_files(sdk) == before_licenses
            if not result['license_registry_unchanged']:
                result['status'] = 'BLOCKED'
        result['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (out / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result.get(key) for key in ('status', 'apk', 'ephemeral_key_absent', 'error')}))
    return 0 if result['status'] == 'PASS_BUILD_ONLY' and result['ephemeral_key_absent'] else 1


if __name__ == '__main__':
    sys.exit(main())
