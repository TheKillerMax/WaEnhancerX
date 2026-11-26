#!/usr/bin/env python3
"""Prepare only the disposable public Linux runner; never accepts SDK licenses."""
import argparse
import ctypes
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import android_emulator_lab_preflight as preflight
from expansion_contract import context_check

CORE_URL = 'https://dl.google.com/android/repository/repository2-3.xml'
PIN = {
    'version': '37.3.10', 'revision': [37, 3, 10], 'build_id': '16970787',
    'archive_url': 'https://dl.google.com/android/repository/emulator-linux_x64-16970787.zip',
    'archive_bytes': 350068887,
    'archive_sha1': '5f7314368fc6c05c937f6991bb4106214dc389e7',
    'archive_sha256_reference': 'a4405349d8a9c52136ab7861e5331dc40e85574bd91cb8889a298a2ff4c52e26',
    'sha256_reference_source': 'https://developer.android.com/studio/emulator_archive',
}
LIBPULSE_PIN = {
    'package': 'libpulse0', 'architecture': 'amd64', 'version': '1:16.1+dfsg1-2ubuntu10.1',
    'repository': 'Ubuntu noble-updates/main',
    'filename': 'pool/main/p/pulseaudio/libpulse0_16.1+dfsg1-2ubuntu10.1_amd64.deb',
    'archive_bytes': 292098,
    'archive_sha256': 'b8d52aa6c2f74ae99e749c9f98d6ad2dbf924fd422371ac469725245cdd919fc',
    'reference_url': 'https://packages.ubuntu.com/noble-updates/amd64/libpulse0/download',
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def prepare_libpulse(out, env):
    release = platform.freedesktop_os_release()
    require(release.get('ID') == 'ubuntu' and release.get('VERSION_ID') == '24.04',
            'The libpulse0 pin requires Ubuntu 24.04')
    commands = {name: shutil.which(name) for name in ('sudo', 'apt-get', 'apt-cache', 'dpkg-query', 'env')}
    require(all(commands.values()), 'Preinstalled Ubuntu package tools are required')
    package = LIBPULSE_PIN['package'] + ':' + LIBPULSE_PIN['architecture']
    specification = package + '=' + LIBPULSE_PIN['version']
    query = [commands['dpkg-query'], '-W', '-f=${Status}\t${Version}\t${Architecture}\n', package]
    command, before = preflight.run(out, 'libpulse-installed-before', query, env)
    expected = 'install ok installed\t' + LIBPULSE_PIN['version'] + '\t' + LIBPULSE_PIN['architecture']
    preinstalled = command['returncode'] == 0 and before.strip() == expected
    require(preinstalled or command['returncode'] == 1,
            'An unexpected libpulse0 version/state is installed; it will not be replaced')
    if not preinstalled:
        privileged = [commands['sudo'], '-n', commands['env'], 'DEBIAN_FRONTEND=noninteractive', commands['apt-get']]
        command, _ = preflight.run(out, 'libpulse-apt-update',
                                  privileged + ['-o', 'Acquire::Retries=1', '-o', 'Acquire::http::Timeout=30', 'update'], env, timeout=120)
        require(command['returncode'] == 0 and not command.get('output_truncated'), 'Ubuntu package index refresh failed')
        command, metadata = preflight.run(out, 'libpulse-package-metadata', [commands['apt-cache'], 'show', specification], env)
        require(command['returncode'] == 0 and not command.get('output_truncated'), 'Pinned libpulse0 metadata is unavailable')
        records = [dict(line.split(': ', 1) for line in paragraph.splitlines() if line and not line[0].isspace() and ': ' in line)
                   for paragraph in metadata.strip().split('\n\n')]
        require(len(records) == 1 and all(records[0].get(key) == value for key, value in {
            'Package': LIBPULSE_PIN['package'], 'Version': LIBPULSE_PIN['version'], 'Architecture': LIBPULSE_PIN['architecture'],
            'Filename': LIBPULSE_PIN['filename'], 'Size': str(LIBPULSE_PIN['archive_bytes']), 'SHA256': LIBPULSE_PIN['archive_sha256'],
        }.items()), 'APT libpulse0 package metadata differs from the reviewed Ubuntu pin')
        command, _ = preflight.run(out, 'libpulse-install',
                                  privileged + ['--yes', '--no-install-recommends', '--no-remove', '--no-upgrade',
                                                'install', specification], env, timeout=120)
        require(command['returncode'] == 0 and not command.get('output_truncated'), 'Pinned libpulse0 installation failed')
    command, installed = preflight.run(out, 'libpulse-installed-after', query, env)
    require(command['returncode'] == 0 and installed.strip() == expected, 'Installed libpulse0 version/architecture differs from the pin')
    command, _ = preflight.run(out, 'libpulse-repository-policy', [commands['apt-cache'], 'policy', package], env)
    require(command['returncode'] == 0 and not command.get('output_truncated'), 'Cannot record libpulse0 repository policy')
    library = Path('/usr/lib/x86_64-linux-gnu/libpulse.so.0').resolve(strict=True)
    ctypes.CDLL(str(library), mode=os.RTLD_NOW)
    result = {'pin': LIBPULSE_PIN, 'preinstalled': preinstalled, 'installed_identity': installed.strip(),
              'library_path': str(library), 'library_sha256': preflight.sha256_file(library), 'library_load_confirmed': True,
              'archive_integrity_scope': 'Authenticated APT installation; repository metadata must match the reviewed archive size and SHA-256 before installation. No independent download hash is claimed.'}
    preflight.save(out, 'libpulse-result.json', result)
    return result


def acl_entries(text):
    return {line.split('#', 1)[0].strip().rsplit(':', 1)[0]: line.split('#', 1)[0].strip().rsplit(':', 1)[1]
            for line in text.splitlines() if line.startswith(('user:', 'group:', 'mask:', 'other:'))}


def prepare_kvm(out, env):
    before = preflight.inspect_kvm()
    result = {'before': before, 'acl_changed': False, 'runner_uid': os.getuid()}
    preflight.save(out, 'kvm-bootstrap.json', result)
    if before['usable']:
        result['after'] = before
        preflight.save(out, 'kvm-bootstrap.json', result)
        return result
    device = Path('/dev/kvm')
    info = device.lstat()
    require(stat.S_ISCHR(info.st_mode) and info.st_uid == 0, 'Expected root-owned KVM character device')
    require(os.getuid() != 0, 'The runner process must not run as root')
    commands = {name: shutil.which(name) for name in ('getfacl', 'setfacl', 'sudo')}
    require(all(commands.values()), 'Preinstalled ACL tools and noninteractive sudo are required')
    status, original = preflight.run(out, 'kvm-acl-before', [commands['getfacl'], '--absolute-names', '--numeric', '/dev/kvm'], env)
    require(status['returncode'] == 0, 'Cannot read the existing KVM ACL')
    original_entries = acl_entries(original)
    key = 'user:' + str(os.getuid())
    command = [commands['sudo'], '-n', commands['setfacl'], '--no-mask', '--modify', key + ':rw', '--', '/dev/kvm']
    status, _ = preflight.run(out, 'kvm-acl-grant-runner', command, env)
    require(status['returncode'] == 0, 'Runner-specific KVM ACL could not be applied')
    result['acl_changed'] = True
    status, updated = preflight.run(out, 'kvm-acl-after', [commands['getfacl'], '--absolute-names', '--numeric', '/dev/kvm'], env)
    require(status['returncode'] == 0, 'Cannot inspect the resulting KVM ACL')
    updated_entries = acl_entries(updated)
    require(all(updated_entries.get(name) == value for name, value in original_entries.items() if name != key),
            'An existing ACL entry other than the runner changed')
    require(set(updated_entries) <= set(original_entries) | {key, 'mask:'}, 'Unexpected new KVM ACL principal')
    require(updated_entries.get(key) == 'rw-', 'The named runner ACL is not read/write')
    if 'mask:' not in original_entries:
        require(updated_entries.get('mask:') == original_entries.get('group:'), 'New mask differs from the original group rights')
    require(stat.S_IMODE(device.stat().st_mode) == stat.S_IMODE(info.st_mode), 'KVM base mode bits changed')
    result['after'] = preflight.inspect_kvm()
    preflight.save(out, 'kvm-bootstrap.json', result)
    require(result['after']['usable'], 'KVM is still unavailable after the runner-specific ACL')
    return result


def official_emulator_metadata():
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, message, headers, new_url):
            raise ValueError('Repository redirects are not allowed')
    with build_opener(NoRedirect()).open(Request(CORE_URL, headers={'User-Agent': 'WAEX-Lab-Bootstrap/1'}), timeout=25) as response:
        raw = response.read(4 * 1024 ** 2 + 1)
    require(len(raw) <= 4 * 1024 ** 2 and b'<!DOCTYPE' not in raw.upper() and b'<!ENTITY' not in raw.upper(),
            'Invalid repository metadata')
    root = ET.fromstring(raw)
    candidates = [node for node in root.findall('./{*}remotePackage') if node.get('path') == 'emulator'
                  and node.find('./{*}channelRef') is not None and node.find('./{*}channelRef').get('ref') == 'channel-0']
    require(len(candidates) == 1, 'Expected one stable emulator package')
    node = candidates[0]
    revision = [int(node.findtext('./{*}revision/{*}' + name, '0')) for name in ('major', 'minor', 'micro')]
    require(revision == PIN['revision'], 'Stable emulator revision changed; review a new pin before installing')
    archives = [archive for archive in node.findall('./{*}archives/{*}archive')
                if archive.findtext('./{*}host-os') == 'linux' and archive.findtext('./{*}host-arch') == 'x64']
    require(len(archives) == 1, 'Expected one Linux x64 emulator archive')
    archive = archives[0]
    checksum = archive.find('./{*}complete/{*}checksum')
    require(archive.findtext('./{*}complete/{*}url') == PIN['archive_url'].rsplit('/', 1)[1]
            and int(archive.findtext('./{*}complete/{*}size')) == PIN['archive_bytes']
            and checksum is not None and checksum.get('type') == 'sha1' and checksum.text == PIN['archive_sha1'],
            'Official emulator archive identity differs from the reviewed pin')
    license_id = node.find('./{*}uses-license').get('ref')
    require(license_id == 'android-sdk-license', 'Unexpected emulator license')
    license_node = next(license_node for license_node in root.findall('./{*}license') if license_node.get('id') == license_id)
    require(hasattr(preflight, 'sdk_license_hash'), 'Awaiting the reviewed SDK license normalization helper')
    license_hash = preflight.sdk_license_hash(''.join(license_node.itertext()))
    return {'repository_url': CORE_URL, 'repository_sha256': hashlib.sha256(raw).hexdigest(),
            'license_id': license_id, 'sdk_license_sha1': license_hash, 'pin': PIN}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = {'schema_version': 1, 'status': 'BLOCKED', 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'issues': [], 'licenses_accepted_by_this_run': False, 'images_downloaded': False, 'vm_created': False,
              'source_sha256': preflight.sha256_file(__file__), 'pin': PIN}
    sdk, before, licenses_before = None, None, None
    try:
        context_check(os.environ)
        env = os.environ.copy()
        result['kvm'] = prepare_kvm(out, env)
        sdk = Path(env.get('ANDROID_HOME') or env.get('ANDROID_SDK_ROOT') or '/missing/sdk').resolve()
        require(sdk.is_dir(), 'Preinstalled SDK is required')
        require(shutil.disk_usage(sdk).free >= 8 * 1024 ** 3, 'Less than 8 GiB free for bootstrap and reports')
        before = preflight.sdk_snapshot(sdk)
        licenses_before = preflight.license_files(sdk)
        preflight.save(out, 'sdk-before-bootstrap.json', before)
        preflight.save(out, 'licenses-before-bootstrap.json', licenses_before)
        metadata = official_emulator_metadata()
        preflight.save(out, 'verified-emulator-metadata.json', metadata)
        require(metadata['sdk_license_sha1'] in licenses_before.get(metadata['license_id'], {}).get('accepted_sha1', []),
                'The exact emulator license is not already accepted; no download or acceptance was performed')
        state = out.parent / (out.name + '-state')
        state.mkdir(exist_ok=False)
        env.update(ANDROID_HOME=str(sdk), ANDROID_SDK_ROOT=str(sdk), ANDROID_USER_HOME=str(state),
                   ANDROID_AVD_HOME=str(state / 'avd'), ANDROID_EMULATOR_HOME=str(state / 'emulator'))
        manager = sdk / 'cmdline-tools/latest/bin/sdkmanager'
        require(manager.is_file(), 'Preinstalled SDK manager is required')
        installed = sdk / 'emulator'
        result['emulator_preexisted'] = installed.exists()
        if not installed.exists():
            command, _ = preflight.run(out, 'install-pinned-stable-emulator',
                                      [str(manager), '--sdk_root=' + str(sdk), '--channel=0', '--install', 'emulator'], env, timeout=240)
            require(command['returncode'] == 0 and not command.get('output_truncated'), 'Official emulator installation failed')
        properties = dict(line.split('=', 1) for line in (installed / 'source.properties').read_text().splitlines() if '=' in line)
        properties = {key.strip(): value.strip() for key, value in properties.items()}
        require(properties.get('Pkg.Revision') == PIN['version'], 'Installed emulator source.properties has an unexpected version')
        root = ET.parse(installed / 'package.xml').getroot()
        package = root.find('./{*}localPackage')
        require(package is not None and package.get('path') == 'emulator', 'Installed SDK package identity is invalid')
        revision = [int(package.findtext('./{*}revision/{*}' + name, '0')) for name in ('major', 'minor', 'micro')]
        require(revision == PIN['revision'], 'Installed SDK metadata has an unexpected emulator revision')
        result['linux_library'] = prepare_libpulse(out, env)
        command, version = preflight.run(out, 'installed-emulator-version', [str(installed / 'emulator'), '-version'], env)
        require(command['returncode'] == 0 and PIN['version'] in version and PIN['build_id'] in version,
                'Installed emulator executable does not report the exact version/build')
        command, _ = preflight.run(out, 'installed-emulator-accel-check', [str(installed / 'emulator'), '-accel-check'], env)
        require(command['returncode'] == 0, 'Installed emulator cannot use KVM')
        rechecked = official_emulator_metadata()
        require(rechecked['pin'] == metadata['pin'] and rechecked['sdk_license_sha1'] == metadata['sdk_license_sha1'],
                'Official package/license identity changed during installation')
        result['emulator'] = preflight.tool_identity(installed / 'emulator')
        result['qemu'] = preflight.tool_identity(installed / 'qemu/linux-x86_64/qemu-system-x86_64-headless')
        result['installed_version_and_build_confirmed'] = True
        result['archive_integrity_scope'] = 'Archive installation and repository-checksum validation are delegated to the official SDK installer; the published SHA-256 is a reference pin, not an independently measured ZIP hash.'
    except (OSError, RuntimeError, ValueError, KeyError, StopIteration, ET.ParseError) as exc:
        result['issues'].append(type(exc).__name__ + ': ' + str(exc))
    finally:
        if sdk is not None and before is not None:
            after = preflight.sdk_snapshot(sdk)
            preflight.save(out, 'sdk-after-bootstrap.json', after)
            unexpected = [name for name in set(before) | set(after) if before.get(name) != after.get(name) and not name.startswith('emulator/')]
            result['unexpected_sdk_metadata_changes'] = unexpected
            result['license_files_unchanged'] = preflight.license_files(sdk) == licenses_before
            if unexpected or not result['license_files_unchanged']:
                result['issues'].append('SDK changes exceeded emulator installation or altered existing license files')
        result['status'] = 'PASS' if result.get('installed_version_and_build_confirmed') and not result['issues'] else 'BLOCKED'
        result['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        preflight.save(out, 'bootstrap-result.json', result)
        preflight.save(out, 'manifest.json', {path.name: {'bytes': path.stat().st_size, 'sha256': preflight.sha256_file(path)}
                                            for path in sorted(out.iterdir()) if path.is_file()})
        print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
