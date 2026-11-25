#!/usr/bin/env python3
"""Build four pinned waexdiag ELF controls in an isolated public Linux runner.

No Android boot, APK, signing key, JNI invocation or private dependency is used.
The installed SDK license registry is read and must remain unchanged.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import sys
import time
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET
import zipfile

import android_emulator_lab_preflight as lab

AUDIT_REVISION = '1c50db163ee1b8127288ea27a055242c9899541f'
SOURCE_REVISION = '9d1a3585f2b44b90e632cd3a2a7e46ef86ebf19d'
SOURCE_SHA256 = '96647f2fb72535da9a01c49d176d2ed868f93794a172c032a5afc92ea67b5756'
BASE_CMAKE_SHA256 = 'b71381b25d68897a2f881df9809e5a10e5d8f75fc76037c2b2a2277b5ffed9be'
CANDIDATE_CMAKE_SHA256 = 'fed223aeac6d9efa008b04313e2e7a3dbe983c64becd53d5318f0093d875f7ef'
AUDITOR_SHA256 = 'e9d840a160943cf10cd766977a341e256a1815a0e87f5a9cb89bb31d2094faa1'
LICENSE_SHA1 = '24333f8a63b6825ea9c5514f83c2829b004d1fee'
METADATA_URL = lab.BASE_URL + 'repository2-1.xml'
RESERVE_BYTES = 20 * 1024 ** 3
PACKAGES = (
    {'path': 'ndk;27.0.12077973', 'name': 'ndk', 'revision': '27.0.12077973',
     'url': lab.BASE_URL + 'android-ndk-r27-linux.zip', 'bytes': 663957918,
     'sha1': '5e5cd517bdb98d7e0faf2c494a3041291e71bdcc'},
    {'path': 'cmake;3.22.1', 'name': 'cmake', 'revision': '3.22.1',
     'url': lab.BASE_URL + 'cmake-3.22.1-linux.zip', 'bytes': 22308647,
     'sha1': 'fd0a48b4a758310df8c7aa51f59840ed48fe7ed8'},
)
EXPECTED_JNI = sorted('Java_com_waenhancer_utils_NativeDiagPaths_' + suffix for suffix in (
    'lspConfigDb', 'hmaZygiskPath', 'knownHmaPackages', 'knownHmaConfigPaths',
    'hmaActiveCheckCommand', 'lspHmaCheckCommand', 'hmaShallowSearchCommand',
    'hmaConfigGlobCommand', 'lspLogGlob', 'magiskVersionCommand',
    'magiskDenylistStatusCommand', 'magiskDenylistListCommand',
    'magiskDenylistRemovePrefix', 'magiskDenylistRemoveSuffix'))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def space(path, needed=0):
    free = shutil.disk_usage(path).free
    require(free >= RESERVE_BYTES + needed, 'The 20 GiB disk reserve would be exceeded')
    return free


def command(out, name, args, env, timeout=120):
    metadata, text = lab.run(out, name, list(map(str, args)), env, timeout)
    require(metadata['returncode'] == 0 and not metadata['timed_out']
            and not metadata.get('output_truncated'), 'Command failed: ' + name)
    return text


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        raise RuntimeError('A fixed official download redirected: ' + str(code))


def open_official(url):
    require(url in {METADATA_URL, *(item['url'] for item in PACKAGES)}, 'Unexpected URL')
    return build_opener(NoRedirect()).open(
        Request(url, headers={'User-Agent': 'WAEX-Native-NDK27-Lab/1'}), timeout=30)


def confirm_metadata(root, accepted):
    licenses = {node.get('id'): lab.sdk_license_hash(''.join(node.itertext()))
                for node in root.findall('./{*}license')}
    require(licenses.get('android-sdk-license') == LICENSE_SHA1,
            'The official SDK license identity differs from the reviewed terms')
    require(LICENSE_SHA1 in accepted.get('android-sdk-license', {}).get('accepted_sha1', []),
            'The standard SDK license is not already registered as accepted')
    selected = []
    for expected in PACKAGES:
        nodes = [node for node in root.findall('./{*}remotePackage')
                 if node.get('path') == expected['path']]
        require(len(nodes) == 1, 'Missing or duplicate package: ' + expected['path'])
        node = nodes[0]
        license_node = node.find('./{*}uses-license')
        require(license_node is not None and license_node.get('ref') == 'android-sdk-license',
                'Package uses different license: ' + expected['path'])
        revision = '.'.join(lab.child_text(node, './{*}revision/{*}' + k, '0')
                            for k in ('major', 'minor', 'micro'))
        require(revision == expected['revision'], 'Package revision changed')
        archives = [item for item in node.findall('./{*}archives/{*}archive')
                    if lab.child_text(item, './{*}host-os') == 'linux']
        require(len(archives) == 1, 'Expected one Linux archive')
        complete = archives[0].find('./{*}complete')
        require(complete is not None, 'Missing complete archive')
        checksum = complete.find('./{*}checksum')
        require(checksum is not None and checksum.get('type', 'sha1') == 'sha1',
                'Unexpected official checksum algorithm')
        observed = {'path': expected['path'], 'revision': revision,
                    'url': lab.BASE_URL + lab.child_text(complete, './{*}url'),
                    'bytes': int(lab.child_text(complete, './{*}size')),
                    'sha1': checksum.text}
        require(all(observed[key] == expected[key]
                    for key in ('path', 'revision', 'url', 'bytes', 'sha1')),
                'Official archive no longer matches its reviewed pin')
        selected.append({**observed, 'license_id': 'android-sdk-license',
                         'license_sdk_sha1': LICENSE_SHA1, 'license_already_accepted': True})
    return selected


def acquire(expected, work, out, env):
    space(work, expected['bytes'])
    partial = work / (expected['name'] + '.zip.partial')
    started, count = time.monotonic(), 0
    sha1, sha256 = hashlib.sha1(), hashlib.sha256()
    with open_official(expected['url']) as response, partial.open('xb') as stream:
        require(response.status == 200, 'Unexpected archive HTTP status')
        while True:
            require(time.monotonic() - started < 600, 'Archive download exceeded ten minutes')
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            count += len(chunk)
            require(count <= expected['bytes'], 'Archive exceeds its pinned size')
            space(work, len(chunk))
            stream.write(chunk)
            sha1.update(chunk)
            sha256.update(chunk)
    require(count == expected['bytes'] and sha1.hexdigest() == expected['sha1'],
            'Archive size or official checksum mismatch; partial is not usable')
    archive = work / (expected['name'] + '.zip')
    partial.rename(archive)
    destination = work / expected['name']
    destination.mkdir()
    with zipfile.ZipFile(archive) as zipped:
        entries = zipped.infolist()
        require(len(entries) < 200000, 'Archive entry limit')
        for entry in entries:
            path = PurePosixPath(entry.filename)
            require(not path.is_absolute() and '..' not in path.parts
                    and '\\' not in entry.filename, 'Unsafe archive member path')
        expanded = sum(entry.file_size for entry in entries)
        require(expanded <= 10 * 1024 ** 3, 'Archive expansion exceeds the lab budget')
    space(work, expanded + 256 * 1024 ** 2)
    # unzip restores the Unix executable modes in the checksum-verified official archive.
    command(out, expected['name'] + '-extract',
            [shutil.which('unzip'), '-q', archive, '-d', destination], env, 180)
    space(work)
    receipt = {**expected, 'downloaded_bytes': count, 'sha1_verified': True,
               'download_sha256': sha256.hexdigest(), 'expanded_bytes': expanded,
               'elapsed_seconds': round(time.monotonic() - started, 3)}
    lab.save(out, expected['name'] + '-archive.json', receipt)
    return destination, receipt


def crosscheck_readelf(text, elf):
    observed = {'LOAD': [], 'GNU_RELRO': []}
    pattern = re.compile(r'^\s*(LOAD|GNU_RELRO)\s+'
                         r'(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+'
                         r'(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+([RWE ]+)\s+'
                         r'(0x[0-9a-fA-F]+|0)\s*$')
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            kind, offset, address, _physical, filesz, memsz, flags, align = match.groups()
            observed[kind].append((int(offset, 16), int(address, 16), int(filesz, 16),
                                   int(memsz, 16), int(align, 16),
                                   sum(value for flag, value in [('R', 4), ('W', 2), ('E', 1)]
                                       if flag in flags)))
    for kind, key in [('LOAD', 'load_segments'), ('GNU_RELRO', 'relro_segments')]:
        expected = [(item['file_offset'], item['virtual_address'], item['file_size'],
                     item['memory_size'], item['alignment'], item['flags']) for item in elf[key]]
        require(observed[kind] == expected, 'llvm-readelf and ELF parser disagree: ' + kind)
    return True


def jni_exports(text):
    names = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 8 and fields[0].endswith(':') and fields[7].startswith('Java_'):
            require(fields[3:6] == ['FUNC', 'GLOBAL', 'DEFAULT'] and fields[6] != 'UND',
                    'JNI symbol has unexpected binding, type, visibility or definition')
            names.append(fields[7])
    require(sorted(names) == EXPECTED_JNI, 'The 14 JNI exports changed or were duplicated')
    return sorted(names)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-repo', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = {'status': 'BLOCKED', 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'source_revision': SOURCE_REVISION, 'audit_revision': AUDIT_REVISION,
              'android_api': 24, 'builds': [], 'licenses_accepted_by_this_run': False,
              'jni_executed': False, 'android_booted': False, 'apk_created': False,
              'limits': 'ELF static build and exports only; no APK packaging, Android loader, JNI runtime, '
                        'WAEX application, private waexlic or opus validation.'}
    sdk, accepted_before = None, None
    try:
        lab.context_check(os.environ)
        require(shutil.which('unzip') is not None, 'Preinstalled unzip is required')
        temp = Path(os.environ['RUNNER_TEMP']).resolve()
        require(out.is_relative_to(temp), 'Reports must be under the disposable runner temporary directory')
        work = temp / 'waex-native-ndk27-work'
        work.mkdir(exist_ok=False)
        result['disk_free_before'] = space(work, sum(item['bytes'] for item in PACKAGES))
        result['workflow'] = {key: os.environ.get(key) for key in
                              ('GITHUB_REPOSITORY', 'GITHUB_REF', 'GITHUB_SHA', 'GITHUB_RUN_ID',
                               'GITHUB_RUN_ATTEMPT', 'ImageOS', 'ImageVersion')}
        env = {key: value for key, value in os.environ.items()
               if key not in ('CC', 'CXX', 'CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS',
                              'CMAKE_GENERATOR', 'CMAKE_TOOLCHAIN_FILE')}
        audit_repo = args.audit_repo.resolve()
        head = command(out, 'audit-checkout', ['git', '-C', audit_repo, 'rev-parse', 'HEAD'], env).strip()
        require(head == AUDIT_REVISION, 'The auditor/base checkout revision differs')
        source = audit_repo / 'app/src/main/cpp/waex_diag.c'
        base_cmake = audit_repo / 'app/src/main/cpp/CMakeLists.txt'
        candidate = Path(__file__).parent / 'fixtures/native_diag_16kb_CMakeLists.txt'
        audit_file = audit_repo / 'qa/audit_native_alignment.py'
        inputs = {'source': (source, SOURCE_SHA256), 'base_cmake': (base_cmake, BASE_CMAKE_SHA256),
                  'candidate_cmake': (candidate, CANDIDATE_CMAKE_SHA256), 'auditor': (audit_file, AUDITOR_SHA256)}
        result['inputs'] = {}
        for name, (path, expected) in inputs.items():
            actual = lab.sha256_file(path)
            require(actual == expected, 'Frozen input changed: ' + name)
            result['inputs'][name] = {'sha256': actual, 'bytes': path.stat().st_size}
        gradle = (audit_repo / 'app/build.gradle.kts').read_text(encoding='utf-8')
        require('ndkVersion = "27.0.12077973"' in gradle and 'version = "3.22.1"' in gradle
                and 'minSdk = 24' in gradle, 'The recorded project toolchain requirements differ')
        require(sorted(re.findall(r'^(Java_\w+)\(', source.read_text(), re.M)) == EXPECTED_JNI,
                'Source JNI declarations differ')
        spec = importlib.util.spec_from_file_location('pinned_native_auditor', audit_file)
        auditor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(auditor)
        sdk = Path(os.environ.get('ANDROID_HOME', os.environ.get('ANDROID_SDK_ROOT', ''))).resolve()
        require(sdk.is_dir() and (sdk / 'licenses').is_dir(), 'Preinstalled SDK acceptance is unavailable')
        accepted_before = lab.license_files(sdk)
        with open_official(METADATA_URL) as response:
            metadata = response.read(4 * 1024 ** 2 + 1)
        require(len(metadata) <= 4 * 1024 ** 2 and b'<!DOCTYPE' not in metadata.upper()
                and b'<!ENTITY' not in metadata.upper(), 'Invalid repository metadata')
        result['metadata'] = {'url': METADATA_URL, 'bytes': len(metadata),
                              'sha256': hashlib.sha256(metadata).hexdigest()}
        result['packages'] = confirm_metadata(ET.fromstring(metadata), accepted_before)
        lab.save(out, 'license-check.json', {'packages': result['packages'],
                                           'existing_registry': accepted_before, 'acceptance_written': False})
        destinations = {}
        for package in PACKAGES:
            destination, receipt = acquire(package, work, out, env)
            destinations[package['name']] = destination
        ndk = destinations['ndk'] / 'android-ndk-r27'
        require(re.search(r'^Pkg.Revision\s*=\s*27\.0\.12077973\s*$',
                          (ndk / 'source.properties').read_text(), re.M), 'Extracted NDK revision differs')
        cmakes = list(destinations['cmake'].rglob('bin/cmake'))
        require(len(cmakes) == 1, 'Expected one CMake executable')
        cmake, ninja = cmakes[0], cmakes[0].with_name('ninja')
        require(command(out, 'cmake-version', [cmake, '--version'], env).splitlines()[0]
                == 'cmake version 3.22.1-g37088a8', 'CMake version differs')
        command(out, 'ninja-version', [ninja, '--version'], env)
        toolbin = ndk / 'toolchains/llvm/prebuilt/linux-x86_64/bin'
        readelf = toolbin / 'llvm-readelf'
        command(out, 'clang-version', [toolbin / 'clang', '--version'], env)
        command(out, 'lld-version', [toolbin / 'ld.lld', '--version'], env)
        command(out, 'readelf-version', [readelf, '--version'], env)
        for abi, machine in [('arm64-v8a', 183), ('x86_64', 62)]:
            for variant, cmake_source in [('base', base_cmake), ('candidate', candidate)]:
                name = abi + '-' + variant
                project, build = work / ('source-' + name), work / ('build-' + name)
                project.mkdir()
                shutil.copyfile(source, project / 'waex_diag.c')
                shutil.copyfile(cmake_source, project / 'CMakeLists.txt')
                command(out, name + '-configure', [cmake, '-S', project, '-B', build, '-G', 'Ninja',
                        '-DCMAKE_MAKE_PROGRAM=' + str(ninja),
                        '-DCMAKE_TOOLCHAIN_FILE=' + str(ndk / 'build/cmake/android.toolchain.cmake'),
                        '-DANDROID_ABI=' + abi, '-DANDROID_PLATFORM=android-24',
                        '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON'], env)
                build_text = command(out, name + '-build',
                                     [cmake, '--build', build, '--parallel', '2', '--verbose'], env)
                if variant == 'candidate':
                    require(all(flag in build_text for flag in
                                ('-Wl,-z,max-page-size=16384', '-Wl,-z,common-page-size=16384')),
                            'Candidate linker invocation omitted a reviewed alignment flag')
                library = build / 'libwaexdiag.so'
                require(0 < library.stat().st_size < 1024 ** 2, 'Unexpected diagnostic ELF size')
                elf = auditor.inspect_elf(library.read_bytes())
                require(elf['elf_bits'] == 64 and elf['machine'] == machine, 'ELF ABI mismatch')
                require(bool(elf['relro_segments']), 'GNU_RELRO was lost')
                headers = command(out, name + '-readelf', [readelf, '--wide', '--program-headers', library], env)
                crosscheck_readelf(headers, elf)
                symbols = command(out, name + '-exports', [readelf, '--wide', '--dyn-syms', library], env)
                exports = jni_exports(symbols)
                compile_commands = json.loads((build / 'compile_commands.json').read_text())
                require(len(compile_commands) == 1 and 'waex_diag.c' in compile_commands[0]['file'],
                        'Unexpected source entered the isolated build')
                target = 'aarch64' if abi == 'arm64-v8a' else 'x86_64'
                tokens = shlex.split(compile_commands[0]['command'])
                require(tokens and Path(tokens[0]).resolve() == (toolbin / 'clang').resolve(),
                        'Compile database does not use clang from the exact verified NDK')
                targets = [token.split('=', 1)[1] for token in tokens if token.startswith('--target=')]
                targets += [tokens[index + 1] for index, token in enumerate(tokens[:-1])
                            if token in ('-target', '--target')]
                require(len(targets) == 1 and re.fullmatch(target + r'(?:-none)?-linux-android24', targets[0]),
                        'Compiler did not target the exact ABI/API24')
                lab.save(out, name + '-compile-commands.json', compile_commands)
                item = {'abi': abi, 'variant': variant, 'api': 24, 'elf_sha256': lab.sha256_file(library),
                        'elf_bytes': library.stat().st_size, 'elf': elf, 'llvm_readelf_agrees': True,
                        'jni_exports': exports, 'jni_export_count': len(exports),
                        'compiler_target': targets[0], 'compiler_path': str(Path(tokens[0]).resolve())}
                result['builds'].append(item)
                lab.save(out, name + '-elf.json', item)
                space(work)
        for abi in ('arm64-v8a', 'x86_64'):
            base, candidate_result = [item for item in result['builds'] if item['abi'] == abi]
            require(base['jni_exports'] == candidate_result['jni_exports'], 'JNI ABI changed')
            require('ELF_LOAD_ALIGNMENT_BELOW_16K' in base['elf']['issues'],
                    'Expected baseline alignment gap was not reproduced; investigate before attributing a fix')
            require(not candidate_result['elf']['issues'], 'Candidate has 16 KiB LOAD/RELRO findings')
        result['status'] = 'PASS_NATIVE_STATIC'
        result['disk_free_after'] = space(work)
    except Exception as error:
        result['error'] = str(error)
    finally:
        if sdk is not None and accepted_before is not None:
            try:
                result['license_registry_unchanged'] = lab.license_files(sdk) == accepted_before
            except OSError as error:
                result['license_registry_unchanged'] = False
                result['license_readback_error'] = str(error)
            if not result['license_registry_unchanged']:
                result['status'] = 'BLOCKED'
                result['error'] = 'SDK license registry changed unexpectedly'
        result['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        result['script_sha256'] = lab.sha256_file(__file__)
        result['sdk_helper_sha256'] = lab.sha256_file(lab.__file__)
        lab.save(out, 'result.json', result)
        files = [{'path': p.name, 'bytes': p.stat().st_size, 'sha256': lab.sha256_file(p)}
                 for p in sorted(out.iterdir()) if p.is_file()]
        lab.save(out, 'manifest.json', {'files': files, 'binary_artifacts_included': False})
    print(json.dumps({'status': result['status'], 'builds_observed': len(result['builds']),
                      'error': result.get('error')}))
    return 0 if result['status'] == 'PASS_NATIVE_STATIC' else 2


if __name__ == '__main__':
    sys.exit(main())
