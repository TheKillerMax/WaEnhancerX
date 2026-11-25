#!/usr/bin/env python3
"""Build a neutral SQLite instrumentation APK from an existing official SDK.

No SDK install, license acceptance, network access, adb or emulator commands.
Build once, then use the resulting APK/hash unchanged across the isolated lab.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

PACKAGE = 'org.lab.waex.qa.sqlite'
COMPONENT = PACKAGE + '/.SqliteProbeInstrumentation'
MIN_SDK, TARGET_SDK, BUILD_TOOLS = 24, 36, '36.0.0'
ANDROID = '{http://schemas.android.com/apk/res/android}'
SOURCE = Path(__file__).resolve().parent / 'android_sqlite_probe'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def verify_source_manifest(path):
    root = ET.fromstring(path.read_bytes())
    if root.tag != 'manifest' or root.get('package') != PACKAGE:
        raise ValueError('Unexpected probe identity')
    if sorted(child.tag for child in root) != ['application', 'instrumentation', 'uses-sdk']:
        raise ValueError('Only the minimal self-instrumenting manifest is permitted')
    sdk = root.find('uses-sdk')
    app = root.find('application')
    inst = root.find('instrumentation')
    if (sdk.get(ANDROID + 'minSdkVersion'), sdk.get(ANDROID + 'targetSdkVersion')) != ('24', '36'):
        raise ValueError('Unexpected SDK contract')
    for key, expected in {'testOnly': 'true', 'allowBackup': 'false',
                          'usesCleartextTraffic': 'false', 'debuggable': 'false'}.items():
        if app.get(ANDROID + key) != expected:
            raise ValueError('Unexpected application flag: ' + key)
    if len(app) or inst.get(ANDROID + 'name') != '.SqliteProbeInstrumentation' or inst.get(ANDROID + 'targetPackage') != PACKAGE:
        raise ValueError('Unexpected component or instrumentation target')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--java-home', type=Path, default=Path(os.environ['JAVA_HOME']) if os.environ.get('JAVA_HOME') else None)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.java_home is None:
        raise SystemExit('An existing JDK 17+ is required via --java-home or JAVA_HOME')
    sdk, java_home, out = args.sdk.resolve(), args.java_home.resolve(), args.out.resolve()
    if out.exists():
        raise SystemExit('A new output directory is required; existing evidence is never overwritten')
    if not out.parent.is_dir():
        raise SystemExit('Output parent must already exist')
    # Retain the shared Windows lab reserve; Linux CI also keeps a bounded build margin.
    reserve = 20 * 1024**3 if os.name == 'nt' else 2 * 1024**3
    if shutil.disk_usage(out.parent).free < reserve + 256 * 1024**2:
        raise SystemExit('Insufficient build space above the reserve')
    os.umask(0o077)
    out.mkdir(mode=0o700)
    logs = out / 'logs'
    logs.mkdir(mode=0o700)
    exe = '.exe' if os.name == 'nt' else ''
    bt = sdk / 'build-tools' / BUILD_TOOLS
    tools = {'java': java_home / ('bin/java' + exe), 'javac': java_home / ('bin/javac' + exe),
             'keytool': java_home / ('bin/keytool' + exe), 'aapt2': bt / ('aapt2' + exe),
             'zipalign': bt / ('zipalign' + exe), 'd8_jar': bt / 'lib/d8.jar',
             'apksigner_jar': bt / 'lib/apksigner.jar',
             'android_jar': sdk / 'platforms/android-36/android.jar'}
    key = out / 'ephemeral-signing.p12'
    result = {'schema': 'WAEX_SQLITE_PROBE_BUILD_V1', 'status': 'FAILED',
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'package': PACKAGE, 'instrumentation_component': COMPONENT,
              'min_sdk': MIN_SDK, 'target_sdk': TARGET_SDK, 'build_tools_revision': BUILD_TOOLS,
              'permissions': [], 'native_libraries': [], 'phone_or_emulator_accessed': False,
              'sdk_installed_or_license_accepted': False, 'commands': []}
    env = os.environ.copy()
    env['WAEX_PROBE_KS_PASS'] = secrets.token_urlsafe(32)

    def run(name, command, timeout=120):
        argv = [str(x) for x in command]
        started = time.monotonic()
        completed = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, env=env, timeout=timeout)
        output = completed.stdout
        if len(output) > 512 * 1024:
            raise RuntimeError('Unexpected build output size: ' + name)
        (logs / (name + '.log')).write_bytes(output)
        result['commands'].append({'name': name, 'command': argv, 'returncode': completed.returncode,
                                   'elapsed_seconds': round(time.monotonic() - started, 3)})
        if completed.returncode:
            raise RuntimeError('Build command failed: ' + name)
        return output.decode('utf-8', errors='replace')

    try:
        for label, path in tools.items():
            if not path.is_file():
                raise FileNotFoundError('Existing SDK/JDK tool missing: ' + str(path))
        result['tools'] = {label: {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest(path)}
                           for label, path in tools.items()}
        inputs = [SOURCE / 'SqliteProbeInstrumentation.java', SOURCE / 'AndroidManifest.xml']
        verify_source_manifest(inputs[1])
        before = {p.name: digest(p) for p in inputs}
        result['source_sha256'] = before
        result['builder_sha256'] = digest(__file__)
        result['sdk_metadata'] = {}
        for relative in ('platforms/android-36/package.xml', 'platforms/android-36/source.properties',
                         'build-tools/36.0.0/package.xml', 'build-tools/36.0.0/source.properties'):
            path = sdk / relative
            if path.is_file():
                result['sdk_metadata'][relative] = digest(path)
        run('java-version', [tools['java'], '-version'])
        classes, dex = out / 'classes', out / 'dex'
        classes.mkdir(); dex.mkdir()
        run('javac', [tools['javac'], '--release', '8', '-g:none', '-encoding', 'UTF-8',
                      '-classpath', tools['android_jar'], '-d', classes, inputs[0]])
        class_files = sorted(classes.rglob('*.class'))
        if len(class_files) != 1:
            raise ValueError('Unexpected compiled class inventory')
        run('d8', [tools['java'], '-cp', tools['d8_jar'], 'com.android.tools.r8.D8', '--release',
                   '--min-api', '24', '--lib', tools['android_jar'], '--output', dex, *class_files])
        unsigned, aligned, apk = out / 'unsigned.apk', out / 'aligned.apk', out / 'sqlite-probe.apk'
        run('aapt2-link', [tools['aapt2'], 'link', '-I', tools['android_jar'], '--manifest', inputs[1], '-o', unsigned])
        with zipfile.ZipFile(unsigned, 'a', compression=zipfile.ZIP_DEFLATED) as archive:
            entry = zipfile.ZipInfo('classes.dex', date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, (dex / 'classes.dex').read_bytes())
        run('zipalign', [tools['zipalign'], '-f', '4', unsigned, aligned])
        run('keytool', [tools['keytool'], '-genkeypair', '-alias', 'fixture', '-keyalg', 'RSA',
                        '-keysize', '2048', '-validity', '1', '-storetype', 'PKCS12',
                        '-dname', 'CN=WAEXLabNeutralSQLiteOnly', '-keystore', key,
                        '-storepass:env', 'WAEX_PROBE_KS_PASS', '-keypass:env', 'WAEX_PROBE_KS_PASS', '-noprompt'])
        signer = [tools['java'], '-jar', tools['apksigner_jar']]
        run('sign', [*signer, 'sign', '--ks', key, '--ks-pass', 'env:WAEX_PROBE_KS_PASS',
                     '--key-pass', 'env:WAEX_PROBE_KS_PASS', '--v1-signing-enabled', 'true',
                     '--v2-signing-enabled', 'true', '--v3-signing-enabled', 'true',
                     '--v4-signing-enabled', 'false', '--out', apk, aligned])
        verification = run('signature-verify', [*signer, 'verify', '--verbose', '--print-certs',
                                               '--min-sdk-version', '24', apk])
        if 'Verified using v2 scheme (APK Signature Scheme v2): true' not in verification:
            raise ValueError('APK v2 signature verification missing')
        badging = run('apk-badging', [tools['aapt2'], 'dump', 'badging', apk])
        if (f"package: name='{PACKAGE}'" not in badging or "minSdkVersion:'24'" not in badging or
                "targetSdkVersion:'36'" not in badging or 'uses-permission:' in badging):
            raise ValueError('Built APK identity/SDK/permission mismatch')
        run('apk-manifest', [tools['aapt2'], 'dump', 'xmltree', apk, '--file', 'AndroidManifest.xml'])
        run('alignment-check', [tools['zipalign'], '-c', '4', apk])
        with zipfile.ZipFile(apk) as archive:
            names = archive.namelist()
            if archive.testzip() is not None or len(names) != len(set(names)) or 'classes.dex' not in names or any(n.startswith('lib/') for n in names):
                raise ValueError('Invalid or unexpected APK archive')
        if before != {p.name: digest(p) for p in inputs}:
            raise ValueError('Source changed during build')
        result.update(status='PASS_BUILD_ONLY', apk={'file': apk.name, 'bytes': apk.stat().st_size,
                                                    'sha256': digest(apk)},
                      dex_sha256=digest(dex / 'classes.dex'), unsigned_sha256=digest(aligned),
                      runtime_tested=False, signing='ephemeral nonproduction key; one APK per matrix')
    except Exception as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        if key.exists():
            key.unlink()
        env.pop('WAEX_PROBE_KS_PASS', None)
        result['ephemeral_key_absent'] = not key.exists()
        result['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save(out / 'build-result.json', result)
    print(json.dumps({key: result.get(key) for key in ('status', 'apk', 'ephemeral_key_absent', 'error')}))
    return 0 if result['status'] == 'PASS_BUILD_ONLY' and result['ephemeral_key_absent'] else 1


if __name__ == '__main__':
    sys.exit(main())
