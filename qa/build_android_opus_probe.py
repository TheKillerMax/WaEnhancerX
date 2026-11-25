#!/usr/bin/env python3
"""Build one synthetic Opus APK with fixed public inputs and an existing SDK/JDK.

This command never installs an SDK, accepts licenses, or accesses ADB/devices.
It retains the original AAR/JAR inputs and packages their notices in the APK.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from validate_android_opus_probe import write_pcm_assets

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'qa/android_opus_probe'
LOCK = SOURCE / 'dependency-lock.json'
PACKAGE = 'org.lab.waex.qa.opus'
COMPONENT = PACKAGE + '/.OpusProbeInstrumentation'
ANDROID = '{http://schemas.android.com/apk/res/android}'
MAX_APK = 4 * 1024**2


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf8')


def source_pins():
    paths = [Path(__file__), ROOT / 'qa/validate_android_opus_probe.py', LOCK,
             SOURCE / 'OpusProbeInstrumentation.java', SOURCE / 'AndroidManifest.xml',
             *sorted((SOURCE / 'licenses').glob('*.txt'))]
    require(len(paths) >= 10, 'Third-party notice set is incomplete')
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in paths}


def verify_manifest(path):
    root = ET.fromstring(path.read_bytes())
    require(root.tag == 'manifest' and root.get('package') == PACKAGE, 'Wrong APK package')
    require(sorted(x.tag for x in root) == ['application', 'instrumentation', 'uses-sdk'],
            'Only the minimal self-instrumenting manifest is allowed')
    sdk, app, instrument = root.find('uses-sdk'), root.find('application'), root.find('instrumentation')
    require(sdk.get(ANDROID + 'minSdkVersion') == '24' and sdk.get(ANDROID + 'targetSdkVersion') == '36',
            'Wrong SDK contract')
    for key, expected in {'testOnly': 'true', 'debuggable': 'false', 'allowBackup': 'false',
                          'usesCleartextTraffic': 'false', 'extractNativeLibs': 'false'}.items():
        require(app.get(ANDROID + key) == expected, 'Wrong application flag: ' + key)
    require(len(app) == 0 and instrument.get(ANDROID + 'name') == '.OpusProbeInstrumentation'
            and instrument.get(ANDROID + 'targetPackage') == PACKAGE, 'Unexpected APK component')


def elf_identity(raw):
    require(len(raw) >= 64 and raw[:7] == b'\x7fELF\x02\x01\x01', 'Expected ELF64 little endian')
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    require(h[1:4] == (3, 62, 1) and h[8] == 64 and h[9] == 56 and 1 <= h[10] <= 64,
            'Unexpected x86_64 shared-library header')
    require(h[5] + h[9] * h[10] <= len(raw), 'Truncated ELF program table')
    segments = []
    for index in range(h[10]):
        kind, flags, offset, address, _, file_size, memory_size, alignment = struct.unpack_from(
            '<IIQQQQQQ', raw, h[5] + index * h[9])
        require(offset + file_size <= len(raw) and file_size <= memory_size, 'Invalid ELF segment')
        segments.append({'type': kind, 'flags': flags, 'offset': offset, 'vaddr': address,
                         'filesz': file_size, 'memsz': memory_size, 'align': alignment})
    loads = [s for s in segments if s['type'] == 1]
    require(loads and all(s['align'] >= 16384 and s['align'] & (s['align'] - 1) == 0
                         and (s['offset'] - s['vaddr']) % s['align'] == 0 for s in loads),
            'ELF LOAD segments do not support 16 KiB alignment')
    relro = [s for s in segments if s['type'] == 0x6474e552]
    require(len(relro) == 1, 'Expected a GNU_RELRO segment')
    stacks = [s for s in segments if s['type'] == 0x6474e551]
    require(len(stacks) == 1 and not stacks[0]['flags'] & 1, 'Executable or unknown ELF stack')
    return {'machine': 'x86_64', 'load_alignment_at_least_16384': True, 'segments': segments,
            'relro_rounded_16k': [relro[0]['vaddr'] // 16384 * 16384,
                                  (relro[0]['vaddr'] + relro[0]['memsz'] + 16383) // 16384 * 16384],
            'scope': 'Static file layout; loading is tested separately in each owned Android AVD'}


def acquire(row, folder, cache):
    url = urllib.parse.urlsplit(row['url'])
    require(url.scheme == 'https' and url.netloc in ('repo.maven.apache.org', 'dl.google.com')
            and not url.query and not url.fragment and '/' not in row['file']
            and type(row['bytes']) is int and 0 < row['bytes'] <= 4 * 1024**2
            and re.fullmatch('[0-9a-f]{64}', row['sha256']), 'Unreviewed dependency')
    if cache:
        source = cache / row['file']
        require(source.is_file() and not source.is_symlink() and source.stat().st_size == row['bytes'],
                'Missing exact cached dependency: ' + row['file'])
        raw = source.read_bytes()
    else:
        with urllib.request.urlopen(row['url'], timeout=45) as response:
            require(response.url == row['url'], 'Unexpected dependency redirect')
            raw = response.read(row['bytes'] + 1)
    require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
            'Dependency bytes differ: ' + row['file'])
    target = folder / row['file']
    target.write_bytes(raw)
    return target


def zip_entry(archive, name, raw, stored=False):
    item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    item.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
    item.create_system = 3
    item.external_attr = 0o100644 << 16
    archive.writestr(item, raw)


def project_classes(source, target, inventory):
    excluded = []
    with zipfile.ZipFile(source) as incoming, zipfile.ZipFile(target, 'x') as outgoing:
        require(incoming.testzip() is None and len(incoming.namelist()) == len(set(incoming.namelist())),
                'Malformed dependency JAR')
        for item in sorted(incoming.infolist(), key=lambda x: x.filename):
            name = item.filename
            require(not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts,
                    'Unsafe JAR entry')
            if not name.endswith('.class') or name.startswith('META-INF/') or name == 'module-info.class':
                if not item.is_dir():
                    excluded.append(name)
                continue
            require(name not in inventory, 'Duplicate dependency class: ' + name)
            raw = incoming.read(item)
            require(raw[:4] == b'\xca\xfe\xba\xbe', 'Invalid class file')
            inventory[name] = hashlib.sha256(raw).hexdigest()
            zip_entry(outgoing, name, raw)
    return excluded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', required=True, type=Path)
    parser.add_argument('--java-home', required=True, type=Path)
    parser.add_argument('--deps', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    sdk, java_home, out = args.sdk.resolve(), args.java_home.resolve(), args.out.resolve()
    require(not out.exists() and out.parent.is_dir(), 'A fresh build destination is required')
    reserve = 20 * 1024**3 if os.name == 'nt' else 2 * 1024**3
    require(shutil.disk_usage(out.parent).free >= reserve + 128 * 1024**2, 'Build disk reserve is unavailable')
    os.umask(0o077)
    out.mkdir(mode=0o700)
    logs, downloads, artifact = out / 'logs', out / 'downloads', out / 'artifact'
    for folder in (logs, downloads, artifact):
        folder.mkdir()
    exe = '.exe' if os.name == 'nt' else ''
    bt = sdk / 'build-tools/36.0.0'
    tools = {name: java_home / ('bin/' + name + exe) for name in ('java', 'javac', 'keytool')}
    tools.update({name: bt / (name + exe) for name in ('aapt2', 'zipalign')})
    tools.update(d8=bt / 'lib/d8.jar', apksigner=bt / 'lib/apksigner.jar',
                 android=sdk / 'platforms/android-36/android.jar')
    tools.update(jdk_modules=java_home / 'lib/modules', jdk_ct_sym=java_home / 'lib/ct.sym',
                 jdk_release=java_home / 'release',
                 jdk_vm=java_home / ('bin/server/jvm.dll' if os.name == 'nt' else 'lib/server/libjvm.so'))
    env = os.environ.copy()
    for name in ('JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS', 'CLASSPATH', 'JAVA_OPTS'):
        env.pop(name, None)
    env['JAVA_HOME'] = str(java_home)
    env['PATH'] = str(java_home / 'bin') + os.pathsep + env.get('PATH', '')
    env['WAEX_OPUS_QA_KEY_PASS'] = secrets.token_urlsafe(32)
    key = out / 'ephemeral-signing.p12'
    result = {'schema': 'WAEX_OPUS_PROBE_BUILD_V1', 'status': 'FAILED', 'commands': [],
              'package': PACKAGE, 'component': COMPONENT, 'min_sdk': 24, 'target_sdk': 36,
              'permissions': [], 'native_member': 'lib/x86_64/libopuscodec.so',
              'workflow_commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
              'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'runtime_tested': False,
              'phone_or_emulator_accessed': False, 'sdk_installed_or_license_accepted': False,
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}

    def run(name, arguments, timeout=120, quiet=False):
        command = list(map(str, arguments))
        stdout, stderr = logs / (name + '.stdout.log'), logs / (name + '.stderr.log')
        start, process = time.monotonic(), None
        try:
            with stdout.open('xb') as sout, stderr.open('xb') as serr:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=sout, stderr=serr, env=env)
                while process.poll() is None:
                    require(time.monotonic() - start < timeout, 'Build command timed out: ' + name)
                    require(stdout.stat().st_size <= 2 * 1024**2 and stderr.stat().st_size <= 2 * 1024**2,
                            'Build command output exceeded its bound: ' + name)
                    time.sleep(0.05)
                require(stdout.stat().st_size <= 2 * 1024**2 and stderr.stat().st_size <= 2 * 1024**2,
                        'Build command output exceeded its bound: ' + name)
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            result['commands'].append({'name': name, 'argv': command,
                                       'returncode': process.returncode if process else None,
                                       'seconds': round(time.monotonic() - start, 3),
                                       'stdout_bytes': stdout.stat().st_size if stdout.exists() else None,
                                       'stderr_bytes': stderr.stat().st_size if stderr.exists() else None,
                                       'stdout_sha256': digest(stdout) if stdout.exists() and stdout.stat().st_size <= 2 * 1024**2 else None,
                                       'stderr_sha256': digest(stderr) if stderr.exists() and stderr.stat().st_size <= 2 * 1024**2 else None})
        require(process.returncode == 0, 'Build command failed: ' + name)
        a, b = stdout.read_bytes(), stderr.read_bytes()
        require(not quiet or (not a and not b), 'D8 emitted diagnostics; both streams were preserved')
        return (a + b).decode('utf8', errors='strict')

    try:
        require(all(p.is_file() for p in tools.values()), 'The selected SDK/JDK is incomplete')
        result['tools'] = {name: {'path': str(p), 'bytes': p.stat().st_size, 'sha256': digest(p)}
                           for name, p in tools.items()}
        java_version = run('java-version', [tools['java'], '-XshowSettings:properties', '-version'])
        require(re.search(r'^\s*java.specification.version = 21\s*$', java_version, re.M), 'JDK21 is required')
        require(re.fullmatch(r'javac 21(?:\.[^\s]+)?', run('javac-version', [tools['javac'], '-version']).strip()),
                'javac21 is required')
        result['java_version'] = java_version
        before = source_pins()
        result['source_sha256'] = before
        verify_manifest(SOURCE / 'AndroidManifest.xml')
        lock = json.loads(LOCK.read_bytes())
        require(lock['schema'] == 'WAEX_OPUS_DEPENDENCY_LOCK_V1' and len(lock['inputs']) == 4,
                'Unexpected dependency closure')
        deps = {row['file']: acquire(row, downloads, args.deps) for row in lock['inputs']}
        result['dependency_lock_sha256'] = digest(LOCK)
        result['dependencies'] = lock['inputs']
        with zipfile.ZipFile(deps['opusencoder-1.2.0.aar']) as aar:
            require(aar.testzip() is None and len(aar.namelist()) == len(set(aar.namelist())), 'Invalid official AAR')
            native, classes_raw = aar.read(lock['native_member']), aar.read('classes.jar')
        require(hashlib.sha256(native).hexdigest() == lock['native_sha256']
                and hashlib.sha256(classes_raw).hexdigest() == lock['classes_jar_sha256'], 'AAR member identity differs')
        result['native_sha256'] = lock['native_sha256']
        result['native_elf'] = elf_identity(native)
        aar_classes = out / 'opusencoder-original-classes.jar'
        aar_classes.write_bytes(classes_raw)
        inventory, class_jars, projections = {}, [], {}
        for original in (aar_classes, *[p for name, p in deps.items() if name.endswith('.jar')]):
            target = out / (original.stem + '-base-classes.jar')
            projections[original.name] = project_classes(original, target, inventory)
            class_jars.append(target)
        result['dependency_class_sha256'] = inventory
        result['excluded_nonclass_or_multirelease_resources'] = projections
        result['class_metadata_policy'] = 'Base class bytes unchanged, including Kotlin.Metadata; original archives retained'
        classes, dex, assets = out / 'classes', out / 'dex', out / 'assets'
        classes.mkdir()
        dex.mkdir()
        assets.mkdir()
        result['pcm_assets'] = write_pcm_assets(assets)
        classpath = os.pathsep.join(map(str, [tools['android'], *class_jars]))
        run('javac', [tools['javac'], '--release', '8', '-g:none', '-encoding', 'UTF-8',
                      '-classpath', classpath, '-d', classes, SOURCE / 'OpusProbeInstrumentation.java'])
        compiled = sorted(classes.rglob('*.class'))
        require(1 <= len(compiled) <= 8, 'Unexpected probe class inventory')
        run('d8', [tools['java'], '-cp', tools['d8'], 'com.android.tools.r8.D8', '--release',
                   '--min-api', '24', '--lib', tools['android'], '--output', dex, *compiled, *class_jars], quiet=True)
        require([p.name for p in dex.iterdir()] == ['classes.dex'], 'Exactly one DEX is required')
        unsigned, aligned, apk = out / 'unsigned.apk', out / 'aligned.apk', artifact / 'opus-probe.apk'
        run('aapt2-link', [tools['aapt2'], 'link', '-I', tools['android'], '--manifest',
                           SOURCE / 'AndroidManifest.xml', '-o', unsigned])
        with zipfile.ZipFile(unsigned, 'a') as archive:
            zip_entry(archive, 'classes.dex', (dex / 'classes.dex').read_bytes())
            zip_entry(archive, 'lib/x86_64/libopuscodec.so', native, stored=True)
            for p in sorted(assets.iterdir()):
                zip_entry(archive, 'assets/' + p.name, p.read_bytes())
            for p in sorted((SOURCE / 'licenses').glob('*.txt')):
                zip_entry(archive, 'assets/third-party/' + p.name, p.read_bytes())
        run('zipalign', [tools['zipalign'], '-P', '16', '-f', '4', unsigned, aligned])
        run('keytool', [tools['keytool'], '-genkeypair', '-alias', 'fixture', '-keyalg', 'RSA',
                        '-keysize', '2048', '-validity', '1', '-storetype', 'PKCS12',
                        '-dname', 'CN=WAEXLabOpusSyntheticOnly', '-keystore', key,
                        '-storepass:env', 'WAEX_OPUS_QA_KEY_PASS', '-keypass:env', 'WAEX_OPUS_QA_KEY_PASS', '-noprompt'])
        signer = [tools['java'], '-jar', tools['apksigner']]
        run('sign', [*signer, 'sign', '--ks', key, '--ks-pass', 'env:WAEX_OPUS_QA_KEY_PASS',
                     '--key-pass', 'env:WAEX_OPUS_QA_KEY_PASS', '--v1-signing-enabled', 'true',
                     '--v2-signing-enabled', 'true', '--v3-signing-enabled', 'true',
                     '--v4-signing-enabled', 'false', '--out', apk, aligned])
        verification = run('signature-verify', [*signer, 'verify', '--verbose', '--print-certs', '--min-sdk-version', '24', apk])
        require('Verified using v2 scheme (APK Signature Scheme v2): true' in verification, 'V2 signature was not verified')
        badging = run('badging', [tools['aapt2'], 'dump', 'badging', apk])
        require(f"package: name='{PACKAGE}'" in badging and "minSdkVersion:'24'" in badging
                and "targetSdkVersion:'36'" in badging and 'uses-permission:' not in badging, 'APK identity or permissions differ')
        run('manifest', [tools['aapt2'], 'dump', 'xmltree', apk, '--file', 'AndroidManifest.xml'])
        run('alignment', [tools['zipalign'], '-c', '-P', '16', '4', apk])
        with zipfile.ZipFile(apk) as archive:
            require(archive.testzip() is None and len(archive.namelist()) == len(set(archive.namelist())), 'Invalid signed APK')
            require([n for n in archive.namelist() if n.startswith('lib/')] == ['lib/x86_64/libopuscodec.so'], 'Unexpected native ABI')
            item = archive.getinfo('lib/x86_64/libopuscodec.so')
            require(item.compress_type == zipfile.ZIP_STORED and archive.read(item) == native, 'Packaged native bytes differ')
            with apk.open('rb') as stream:
                stream.seek(item.header_offset + 26)
                name_size, extra_size = struct.unpack('<HH', stream.read(4))
            native_offset = item.header_offset + 30 + name_size + extra_size
            require(native_offset % 16384 == 0, 'Native ZIP data is not 16 KiB aligned')
        require(0 < apk.stat().st_size <= MAX_APK, 'APK exceeds its size bound')
        require(source_pins() == before, 'Probe source changed during build')
        require(all(digest(tools[name]) == pin['sha256'] for name, pin in result['tools'].items()), 'SDK/JDK tool changed during build')
        result.update(status='PASS_BUILD_ONLY', apk={'file': apk.name, 'bytes': apk.stat().st_size, 'sha256': digest(apk)},
                      native_zip_data_offset=native_offset, dex_sha256=digest(dex / 'classes.dex'),
                      signing='Ephemeral QA key, one immutable APK per run; no production signing')
    except Exception as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        if key.exists():
            key.unlink()
        env.pop('WAEX_OPUS_QA_KEY_PASS', None)
        result['ephemeral_key_absent'] = not key.exists()
        result['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save(out / 'build-result.json', result)
        if result['status'] == 'PASS_BUILD_ONLY' and result['ephemeral_key_absent']:
            shutil.copyfile(out / 'build-result.json', artifact / 'build-result.json')
    print(json.dumps({k: result.get(k) for k in ('status', 'apk', 'error', 'ephemeral_key_absent')}))
    return 0 if result['status'] == 'PASS_BUILD_ONLY' and result['ephemeral_key_absent'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
