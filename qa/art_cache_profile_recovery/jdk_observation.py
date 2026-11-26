#!/usr/bin/env python3
"""Read fixed JDK/SDK inputs before gates; never execute an observed tool."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import os
import stat

from art_cache_profile_recovery import cache_contract as admission
from art_cache_recovery.build import TOOL_PINS, require, save

MAX_FILE_BYTES = 512 * 1024 * 1024
JDK_MEMBERS = ('bin/java', 'bin/javac', 'release', 'lib/modules', 'lib/ct.sym', 'lib/server/libjvm.so')
LABELS = ('preinstalled-before-setup', 'selected-before-gate', 'selected-after-build')


def observe_root(path):
    path = Path(path)
    result = {'requested_path': str(path), 'resolved_path': None}
    try:
        result['resolved_path'] = str(path.resolve())
    except (OSError, RuntimeError, ValueError) as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
    return result


def observe_file(path):
    path = Path(path)
    result = {'path': str(path), 'resolved_path': None, 'exists': False, 'regular': False,
              'symlink': False, 'bytes': None, 'sha256': None, 'stable_during_hash': False}
    try:
        result['symlink'] = path.is_symlink()
        result['resolved_path'] = str(path.resolve())
        before = path.stat()
        result.update(exists=True, regular=stat.S_ISREG(before.st_mode), bytes=before.st_size)
        require(result['regular'] and 0 < before.st_size <= MAX_FILE_BYTES,
                'Observed input is not a bounded nonempty regular file')
        with path.open('rb') as stream:
            opened = os.fstat(stream.fileno())
            require((opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) ==
                    (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns),
                    'Input identity changed while opening')
            result['sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
            after_fd = os.fstat(stream.fileno())
        after = path.stat()
        key = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        require(key(before) == key(after_fd) == key(after), 'Input identity changed while hashing')
        result['stable_during_hash'] = True
    except (OSError, RuntimeError, ValueError) as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
    return result


def observe_inputs(jdk, sdk, lock, *, label):
    require(label in LABELS, 'Unknown tool observation stage')
    requested_jdk, requested_sdk = Path(jdk), Path(sdk)
    roots = {'jdk': observe_root(requested_jdk), 'sdk': observe_root(requested_sdk)}
    # A failed root resolution is itself evidence. Still attempt every fixed
    # member so one rejected root cannot hide the other input observations.
    jdk = Path(roots['jdk']['resolved_path']) if roots['jdk']['resolved_path'] else requested_jdk
    sdk = Path(roots['sdk']['resolved_path']) if roots['sdk']['resolved_path'] else requested_sdk
    jdk_files = {name: observe_file(jdk / name) for name in JDK_MEMBERS}
    tools = {'java': jdk_files['bin/java'], 'javac': jdk_files['bin/javac'],
             'android_jar': observe_file(sdk / 'platforms/android-36/android.jar'),
             'd8_jar': observe_file(sdk / 'build-tools/36.0.0/lib/d8.jar')}
    sdk_metadata = {name: observe_file(sdk / name) for name in lock['build_sdk_metadata_sha256']}
    return {'schema': 'WAEX_CACHE_ONLY_BUILD_INPUT_OBSERVATION_V1',
            'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'label': label,
            'status': 'OBSERVED_NOT_YET_QUALIFIED', 'java_home_argument': str(requested_jdk),
            'java_home_resolved': roots['jdk']['resolved_path'], 'sdk_argument': str(requested_sdk),
            'sdk_resolved': roots['sdk']['resolved_path'], 'root_observations': roots,
            'tool_or_compiler_execution': False, 'jdk_files': jdk_files, 'tools': tools,
            'sdk_metadata': sdk_metadata,
            'expected': {'jdk_selection': lock['jdk_selection'], 'jdk_file_sha256': lock['jdk_file_sha256'],
                         'tool_sha256': lock['build_tool_sha256'],
                         'sdk_metadata_sha256': lock['build_sdk_metadata_sha256']}}


def validate_observation(observed, lock):
    require(type(observed) is dict and observed.get('schema') == 'WAEX_CACHE_ONLY_BUILD_INPUT_OBSERVATION_V1'
            and observed.get('label') in LABELS and observed.get('tool_or_compiler_execution') is False,
            'Build-input observation identity differs')
    expected = {'jdk_selection': lock['jdk_selection'], 'jdk_file_sha256': lock['jdk_file_sha256'],
                'tool_sha256': lock['build_tool_sha256'], 'sdk_metadata_sha256': lock['build_sdk_metadata_sha256']}
    require(observed.get('expected') == expected and lock['build_tool_sha256'] == TOOL_PINS,
            'Observation changed the existing tool or exact JDK pins')
    roots = observed.get('root_observations')
    require(type(roots) is dict and set(roots) == {'jdk', 'sdk'}
            and all(type(row) is dict and 'error' not in row
                    and type(row.get('resolved_path')) is str and Path(row['resolved_path']).is_absolute()
                    for row in roots.values())
            and roots['jdk']['resolved_path'] == observed.get('java_home_resolved')
            and roots['sdk']['resolved_path'] == observed.get('sdk_resolved'),
            'Build input root resolution failed or differs')
    for group, pins in (('tools', TOOL_PINS), ('jdk_files', lock['jdk_file_sha256']),
                        ('sdk_metadata', lock['build_sdk_metadata_sha256'])):
        rows = observed.get(group)
        require(type(rows) is dict and set(rows) == set(pins), 'Observation coverage differs: ' + group)
        for name, expected_sha in pins.items():
            row = rows[name]
            require(type(row) is dict and row.get('exists') is True and row.get('regular') is True
                    and row.get('stable_during_hash') is True and 'error' not in row
                    and type(row.get('bytes')) is int and 0 < row['bytes'] <= MAX_FILE_BYTES
                    and row.get('sha256') == expected_sha,
                    'Existing pinned input differs: ' + group + '/' + name)
    jdk, sdk = Path(observed['java_home_resolved']), Path(observed['sdk_resolved'])
    for name in JDK_MEMBERS:
        require(observed['jdk_files'][name]['path'] == str(jdk / name), 'JDK member path differs')
    require(observed['tools']['java'] == observed['jdk_files']['bin/java']
            and observed['tools']['javac'] == observed['jdk_files']['bin/javac']
            and observed['tools']['android_jar']['path'] == str(sdk / 'platforms/android-36/android.jar')
            and observed['tools']['d8_jar']['path'] == str(sdk / 'build-tools/36.0.0/lib/d8.jar'),
            'Tool observations refer to different roots or launchers')
    for name in lock['build_sdk_metadata_sha256']:
        require(observed['sdk_metadata'][name]['path'] == str(sdk / name), 'SDK metadata path differs')
    return {'status': 'PASS_EXACT_JDK_AND_UNCHANGED_SDK_INPUT_PINS',
            'jdk_files': len(JDK_MEMBERS), 'tool_files': len(TOOL_PINS),
            'jdk_selection': lock['jdk_selection'], 'tool_execution_for_identity': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--java-home', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    lock = admission.context_check(os.environ)
    # This stage records the preinstalled path only. It cannot qualify or reject
    # the later selected JDK, and absence is retained instead of being fabricated.
    observed = observe_inputs(args.java_home, args.sdk, lock, label='preinstalled-before-setup')
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    save(out / 'preinstalled-jdk-observation.json', observed)
    print(json.dumps({'status': observed['status'], 'label': observed['label'],
                      'tool_execution': False, 'observation_sha256': admission.digest(out / 'preinstalled-jdk-observation.json')}))


if __name__ == '__main__':
    main()
