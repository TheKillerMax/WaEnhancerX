#!/usr/bin/env python3
"""Inspect a public Linux/KVM lab without installing packages or starting a VM.

Only SDK metadata is fetched. Existing license acceptance is inspected, never
created. A successful preflight is not an Android boot or an application test.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
from urllib.parse import urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET

REPOSITORY = 'TheKillerMax/WaEnhancerX'
REF = 'refs/heads/lab/classmetadata-current-source-20261125'
BASE_URL = 'https://dl.google.com/android/repository/'
INDEX_URL = BASE_URL + 'addons_list-5.xml'
FEEDS = ('sys-img/android/sys-img2-3.xml', 'sys-img/google_apis/sys-img2-3.xml')
METADATA_URLS = {INDEX_URL, *(BASE_URL + feed for feed in FEEDS)}
API_LEVELS = tuple(range(24, 38))
MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_LOG_BYTES = 512 * 1024


def sha256_file(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(out, name, data):
    (out / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def context_check(env):
    if env.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('This preflight runs only in the isolated GitHub Actions lab')
    if env.get('GITHUB_REPOSITORY') != REPOSITORY or env.get('GITHUB_REF') != REF:
        raise RuntimeError('Unexpected repository or branch')
    event = json.loads(Path(env['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))
    repo = event.get('repository', {})
    if repo.get('full_name') != REPOSITORY or repo.get('private') is not False:
        raise RuntimeError('Only the named public fork is allowed')
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise RuntimeError('This preflight requires Linux x86_64')


def sdk_snapshot(sdk):
    paths = set()
    for pattern in ('*/package.xml', '*/*/package.xml', 'system-images/*/*/*/package.xml',
                    '*/source.properties', '*/*/source.properties',
                    'system-images/*/*/*/source.properties', 'licenses/*'):
        paths.update(p for p in sdk.glob(pattern) if p.is_file())
    return {p.relative_to(sdk).as_posix(): sha256_file(p) for p in sorted(paths)}


def license_files(sdk):
    accepted = {}
    for path in sorted((sdk / 'licenses').glob('*')):
        if path.is_file() and re.fullmatch(r'[A-Za-z0-9_.-]+', path.name):
            lines = path.read_text(encoding='utf-8').splitlines()
            accepted[path.name] = {'sha256': sha256_file(path),
                                   'accepted_sha1': [line for line in lines if re.fullmatch(r'[0-9a-f]{40}', line)]}
    return accepted


def inspect_kvm():
    path = Path('/dev/kvm')
    result = {'exists': path.exists(), 'usable': False, 'vm_created': False}
    try:
        info = path.stat()
        result.update(character_device=stat.S_ISCHR(info.st_mode),
                      mode=oct(stat.S_IMODE(info.st_mode)), uid=info.st_uid, gid=info.st_gid)
        if not result['character_device']:
            raise RuntimeError('/dev/kvm is not a character device')
        fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)
        try:
            # KVM_GET_API_VERSION and KVM_GET_VCPU_MMAP_SIZE: query only.
            result['api_version'] = fcntl.ioctl(fd, 0xAE00, 0)
            result['vcpu_mmap_bytes'] = fcntl.ioctl(fd, 0xAE04, 0)
            result['usable'] = result['api_version'] == 12 and result['vcpu_mmap_bytes'] > 0
        finally:
            os.close(fd)
    except (OSError, RuntimeError) as exc:
        result['error'] = str(exc)
    return result


def run(out, name, command, env, timeout=30):
    started = time.monotonic()
    metadata = {'command': list(map(str, command)), 'timeout_seconds': timeout}
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL, env=env, start_new_session=True)
    try:
        output, _ = process.communicate(timeout=timeout)
        metadata['timed_out'] = False
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        output, _ = process.communicate()
        metadata['timed_out'] = True
    metadata.update(returncode=process.returncode, elapsed_seconds=round(time.monotonic() - started, 3),
                    original_output_bytes=len(output), log=name + '.log')
    if len(output) > MAX_LOG_BYTES:
        metadata['output_truncated'] = True
        output = output[:MAX_LOG_BYTES] + b'\nOUTPUT LIMIT EXCEEDED\n'
    (out / (name + '.log')).write_bytes(output)
    save(out, name + '.command.json', metadata)
    return metadata, output.decode('utf-8', errors='replace')


def fetch_metadata(url):
    if url not in METADATA_URLS:
        raise ValueError('Only the three fixed XML metadata URLs may be fetched')
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, message, headers, new_url):
            raise ValueError('Metadata redirects are not allowed: ' + str(code))
    opener = build_opener(NoRedirect())
    with opener.open(Request(url, headers={'User-Agent': 'WAEX-Android-Lab-Preflight/1'}), timeout=25) as response:
        data = response.read(MAX_METADATA_BYTES + 1)
    if len(data) > MAX_METADATA_BYTES or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('Invalid or oversized repository metadata')
    return ET.fromstring(data), {'url': url, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def child_text(node, name, default=''):
    found = node.find(name)
    return ''.join(found.itertext()) if found is not None else default


def sdk_license_hash(value):
    """Hash the SDK's bound license value, without recording acceptance.

    JAXB LicenseType applies AOSP TrimStringAdapter before License hashes UTF-8.
    Verified against the official cmdline-tools 12.0 and 22.0 adapter classes.
    Source: platform/tools/base, studio-2023.1.1,
    repository/src/main/java/com/android/repository/impl/meta/TrimStringAdapter.java.
    """
    # Java regex \s is ASCII by default; Python's Unicode \s is broader.
    value = re.sub(r'(?<=[ \t\n\x0b\f\r])[ \t]*', '', value)
    value = re.sub(r'(?<!\n)\n(?!\n)', ' ', value)
    value = re.sub(r' +', ' ', value)
    # String.trim() removes only UTF-16 code units <= U+0020.
    value = value.strip(''.join(chr(code) for code in range(33)))
    return hashlib.sha1(value.encode('utf-8')).hexdigest()


def parse_feed(root, url, accepted):
    licenses = {}
    raw_licenses = {}
    for node in root.findall('./{*}license'):
        value = ''.join(node.itertext())
        license_id = node.attrib['id']
        licenses[license_id] = sdk_license_hash(value)
        raw_licenses[license_id] = hashlib.sha1(value.encode('utf-8')).hexdigest()
    packages = []
    for node in root.findall('./{*}remotePackage'):
        path = node.attrib.get('path', '')
        match = re.fullmatch(r'system-images;android-(\d+)(?:\.(\d+))?;([^;]+);x86_64', path)
        if not match or int(match[1]) not in API_LEVELS:
            continue
        api, minor, tag = int(match[1]), int(match[2] or 0), match[3]
        if tag not in ('default', 'google_apis', 'google_apis_ps16k'):
            continue
        channel = node.find('./{*}channelRef')
        if channel is None or channel.get('ref') != 'channel-0':
            continue
        details = node.find('./{*}type-details')
        if details is None or child_text(details, './{*}codename').strip():
            continue
        declared_api = child_text(details, './{*}api-level').strip()
        declared_match = re.fullmatch(r'(\d+)(?:\.(\d+))?', declared_api)
        if not declared_match or (int(declared_match[1]), int(declared_match[2] or 0)) != (api, minor):
            raise ValueError('Path and declared API disagree: ' + path)
        if child_text(details, './{*}abi').strip() != 'x86_64':
            raise ValueError('Path and declared ABI disagree: ' + path)
        preview = child_text(node, './{*}revision/{*}preview', '0').strip()
        if preview not in ('', '0'):
            continue
        license_node = node.find('./{*}uses-license')
        license_id = license_node.get('ref') if license_node is not None else None
        license_hash = licenses.get(license_id)
        archives = []
        for archive in node.findall('./{*}archives/{*}archive'):
            if child_text(archive, './{*}host-os', 'linux') not in ('', 'linux'):
                continue
            if child_text(archive, './{*}host-bits', '64') not in ('', '64'):
                continue
            if child_text(archive, './{*}host-arch', 'x86_64') not in ('', 'x86_64'):
                continue
            complete = archive.find('./{*}complete')
            if complete is None:
                continue
            checksum = complete.find('./{*}checksum')
            archives.append({'url': urljoin(url, child_text(complete, './{*}url')),
                             'download_bytes': int(child_text(complete, './{*}size', '0')),
                             'checksum_type': checksum.get('type') if checksum is not None else None,
                             'checksum': checksum.text if checksum is not None else None})
        dependencies = [{'path': dependency.get('path'),
                         'min_revision': [int(child_text(dependency, './{*}min-revision/{*}' + key, '0'))
                                          for key in ('major', 'minor', 'micro')]}
                        for dependency in node.findall('./{*}dependencies/{*}dependency')]
        packages.append({'path': path, 'api': api, 'minor': minor, 'tag': tag, 'abi': 'x86_64',
                         'revision': [int(child_text(node, './{*}revision/{*}' + key, '0'))
                                      for key in ('major', 'minor', 'micro')],
                         'source_metadata': url, 'license_id': license_id, 'license_text_sha1': license_hash,
                         'license_xml_text_sha1': raw_licenses.get(license_id),
                         'license_hash_method': 'sdk_TrimStringAdapter_then_sha1_utf8',
                         'license_already_accepted': bool(license_hash and license_hash in
                             accepted.get(license_id, {}).get('accepted_sha1', [])),
                         'archives': archives, 'dependencies': dependencies})
    return packages


def choose_targets(packages, sdk_paths):
    targets = []
    for api, mode in [(api, 'standard') for api in API_LEVELS] + [(35, '16k')]:
        tags = ('google_apis_ps16k',) if mode == '16k' else ('google_apis', 'default')
        candidates = [p for p in packages if p['api'] == api and p['tag'] in tags and p['archives']]
        candidates.sort(key=lambda p: (not (p['license_already_accepted'] and p['path'] in sdk_paths),
                                       p['minor'], tags.index(p['tag']), tuple(-v for v in p['revision'])))
        selected = candidates[0] if candidates else None
        targets.append({'api': api, 'mode': mode, 'selected': selected,
                        'selection_policy': 'prefer_preaccepted_and_listed_then_lowest_minor_then_google_apis',
                        'present_in_sdkmanager_list': bool(selected and selected['path'] in sdk_paths),
                        'candidate_paths': [p['path'] for p in candidates]})
    return targets


def tool_identity(path):
    resolved = path.resolve()
    result = {'path': str(path), 'resolved_path': str(resolved), 'exists': resolved.is_file()}
    if result['exists']:
        result.update(bytes=resolved.stat().st_size, sha256=sha256_file(resolved))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = {'schema_version': 1, 'phase': 'preflight_only', 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'status': 'BLOCKED', 'issues': [], 'android_booted': False, 'images_downloaded': False,
              'licenses_accepted_by_this_run': False, 'source_sha256': sha256_file(__file__)}
    sdk, before = None, None
    try:
        context_check(os.environ)
        result['workflow'] = {key: os.environ.get(key) for key in
                              ('GITHUB_REPOSITORY', 'GITHUB_REF', 'GITHUB_SHA', 'GITHUB_RUN_ID',
                               'GITHUB_RUN_ATTEMPT', 'RUNNER_OS', 'ImageOS', 'ImageVersion')}
        sdk_value = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
        if not sdk_value or not Path(sdk_value).is_dir():
            raise RuntimeError('A preinstalled Android SDK is required; no SDK will be installed')
        sdk = Path(sdk_value).resolve()
        before = sdk_snapshot(sdk)
        save(out, 'sdk-before.json', before)
        components = {}
        for pattern in ('ndk/*/source.properties', 'cmake/*/source.properties',
                        'build-tools/*/source.properties', 'cmdline-tools/*/source.properties',
                        'emulator/source.properties', 'platform-tools/source.properties'):
            for path in sorted(sdk.glob(pattern)):
                components[path.relative_to(sdk).as_posix()] = {
                    'sha256': sha256_file(path),
                    'properties': dict(line.split('=', 1) for line in
                                       path.read_text(encoding='utf-8').splitlines()
                                       if '=' in line and not line.lstrip().startswith('#'))}
        save(out, 'installed-component-properties.json', components)
        accepted = license_files(sdk)
        save(out, 'existing-license-identities.json', accepted)
        cpu = Path('/proc/cpuinfo').read_text()
        flags = next((line.partition(':')[2].split() for line in cpu.splitlines() if line.startswith('flags')), [])
        host = {'platform': platform.platform(), 'architecture': platform.machine(), 'cpu_count': os.cpu_count(),
                'cpu_model': next((line.partition(':')[2].strip() for line in cpu.splitlines() if line.startswith('model name')), None),
                'virtualization_flags': sorted(set(flags) & {'vmx', 'svm', 'ept', 'npt'}),
                'disk_free_bytes': shutil.disk_usage(out).free,
                'memory': {line.partition(':')[0]: line.partition(':')[2].strip()
                           for line in Path('/proc/meminfo').read_text().splitlines()
                           if line.startswith(('MemTotal:', 'MemAvailable:'))}, 'kvm': inspect_kvm()}
        save(out, 'host.json', host)
        if not host['kvm']['usable']:
            result['issues'].append('KVM unavailable to the runner; no permission or host configuration was changed')
        state = out.parent / (out.name + '-state')
        state.mkdir(exist_ok=False)
        env = os.environ.copy()
        env.update(ANDROID_USER_HOME=str(state / 'android-user'), ANDROID_AVD_HOME=str(state / 'avd'),
                   ANDROID_EMULATOR_HOME=str(state / 'emulator'), ANDROID_SDK_ROOT=str(sdk), ANDROID_HOME=str(sdk))
        manager = sdk / 'cmdline-tools/latest/bin/sdkmanager'
        if not manager.is_file():
            raise RuntimeError('Preinstalled cmdline-tools/latest/bin/sdkmanager not found')
        tools = {'sdkmanager': (manager, ['--version']), 'emulator': (sdk / 'emulator/emulator', ['-version']),
                 'adb': (sdk / 'platform-tools/adb', ['version']),
                 'java': (Path(shutil.which('java') or '/missing/java'), ['-version'])}
        identities = {}
        for name, (path, options) in tools.items():
            identities[name] = tool_identity(path)
            if not identities[name]['exists']:
                result['issues'].append('Preinstalled tool missing: ' + name)
                continue
            command, _ = run(out, name + '-version', [str(path), *options], env)
            identities[name]['version_command'] = command
            if command['returncode'] != 0 or command.get('output_truncated'):
                result['issues'].append('Tool version check failed: ' + name)
        identities['qemu_x86_64_headless'] = tool_identity(sdk / 'emulator/qemu/linux-x86_64/qemu-system-x86_64-headless')
        save(out, 'tool-identities.json', identities)
        if identities['emulator']['exists']:
            accel, _ = run(out, 'accel-check', [str(tools['emulator'][0]), '-accel-check'], env)
            if accel['returncode'] != 0:
                result['issues'].append('Emulator acceleration check failed')
        listed, listing = run(out, 'sdkmanager-list', [str(manager), '--sdk_root=' + str(sdk),
                                '--list', '--channel=0', '--include_obsolete'], env, timeout=150)
        if listed['returncode'] != 0 or listed.get('output_truncated'):
            result['issues'].append('SDK package listing failed or exceeded the output limit')
        sdk_paths = set(re.findall(r'^\s*(system-images;[^\s|]+)\s*\|', listing, re.M))
        index, identity = fetch_metadata(INDEX_URL)
        metadata = [identity]
        advertised = {child_text(site, './{*}url') for site in index.findall('./{*}site')}
        packages = []
        for feed in FEEDS:
            if feed not in advertised:
                raise RuntimeError('Expected system image repository missing from the official index: ' + feed)
            root, identity = fetch_metadata(BASE_URL + feed)
            metadata.append(identity)
            packages.extend(parse_feed(root, BASE_URL + feed, accepted))
        targets = choose_targets(packages, sdk_paths)
        save(out, 'catalog.json', {'metadata': metadata, 'stable_x86_64_packages': packages, 'targets': targets})
        for target in targets:
            label = str(target['api']) + '/' + target['mode']
            if not target['selected'] or not target['present_in_sdkmanager_list']:
                result['issues'].append('Required catalog entry not confirmed by both sources: ' + label)
            elif not target['selected']['license_already_accepted']:
                result['issues'].append('Required license has not been confirmed as preaccepted: ' + label)
        result['required_targets'] = len(targets)
        result['catalog_and_license_ready_targets'] = sum(bool(t['selected'] and t['present_in_sdkmanager_list']
            and t['selected']['license_already_accepted']) for t in targets)
    except (OSError, ValueError, RuntimeError, KeyError, ET.ParseError, subprocess.SubprocessError) as exc:
        result['issues'].append(type(exc).__name__ + ': ' + str(exc))
    finally:
        if sdk is not None and before is not None:
            after = sdk_snapshot(sdk)
            save(out, 'sdk-after.json', after)
            result['sdk_metadata_and_licenses_unchanged'] = before == after
            if before != after:
                result['issues'].append('SDK metadata/license identities changed during the preflight')
        result['status'] = 'PASS' if not result['issues'] else 'BLOCKED'
        result['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        result['limits'] = 'Metadata and host capability only. No VM creation, image download, license acceptance, APK build/install, WhatsApp account or LSPosed validation.'
        save(out, 'preflight-result.json', result)
        save(out, 'manifest.json', {p.name: {'bytes': p.stat().st_size, 'sha256': sha256_file(p)}
                                  for p in sorted(out.iterdir()) if p.is_file()})
        print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
