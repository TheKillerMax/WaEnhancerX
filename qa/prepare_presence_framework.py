#!/usr/bin/env python3
"""Stage the unchanged Renderer graph and its exact Android 28/34/36 SDK view.

The current-run framework bundle supplies all 36 runtime JARs and SDKs 28/34.
Only the separately locked SDK36 may use the existing bounded HTTP transport.
Restored SDK bytes fail closed before any network request. No Android test runs
inside this preparer; consumers must pass both --deps and --sdk-dir explicitly.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import urllib.request

from framework_dependency_bundle import LOCK, checked, identity, load_lock, regular, sha, verify
from maven_dependencies import MAX_ATTEMPTS, MAX_TIMEOUT_SECONDS
from prepare_robolectric_sdks import MAX_RETRY_WAIT_SECONDS, download, supervise as supervise_transport

HERE = Path(__file__).resolve().parent
SELECTION = HERE / 'presence_framework_sdks.json'
SOURCE_NAMES = ('prepare_presence_framework.py', 'presence_framework_sdks.json',
                'framework_dependency_bundle.py', 'framework_dependency_lock.json',
                'prepare_robolectric_sdks.py', 'maven_dependencies.py',
                'android_presence_row_test.py', 'mutate_presence_rows.py')


def selection(path, lock):
    regular(path)
    row = json.loads(path.read_text(encoding='utf-8'))
    if (row.get('schema') != 1 or row.get('consumer') != 'android-presence-rows'
            or row.get('robolectric') != '4.17' or row.get('sdk_levels') != [28, 34, 36]
            or row.get('framework_lock_sha256') != sha(lock)):
        raise ValueError('Unsupported Renderer SDK selection or framework lock')
    locked = {item['name']: item for item in load_lock(lock) if item['directory'] == 'sdk-jars'}
    files = row['files']
    if not isinstance(files, list) or len(files) != 3:
        raise ValueError('Exactly the three Renderer SDKs are required')
    for item, sdk in zip(files, (28, 34, 36)):
        if (type(item.get('sdk')) is not int or item['sdk'] != sdk
                or type(item.get('bytes')) is not int or item['bytes'] <= 0
                or not re.fullmatch(r'[0-9a-f]{64}', item.get('sha256', ''))
                or not re.fullmatch(r'[A-Za-z0-9_.+-]+\.jar', item.get('name', ''))):
            raise ValueError('Malformed or reordered Renderer SDK identity')
        if sdk in (28, 34):
            version = {28: '9-robolectric-4913185-2-i7', 34: '14-robolectric-10818077-i7'}[sdk]
            name = 'android-all-instrumented-' + version + '.jar'
            original = locked.get(name)
            if (item.get('source') != 'framework_bundle' or item['name'] != name or original is None
                    or any(item[key] != original[key] for key in ('name', 'bytes', 'sha256'))):
                raise ValueError('Renderer SDK must match its existing framework bundle identity')
        else:
            version = '16-robolectric-13921718-i7'
            name = 'android-all-instrumented-' + version + '.jar'
            coordinate = 'org.robolectric:android-all-instrumented:' + version
            url = 'https://repo.maven.apache.org/maven2/org/robolectric/android-all-instrumented/' + version + '/' + name
            if (item.get('source') != 'maven_central' or item['name'] != name
                    or item.get('coordinate') != coordinate or item.get('url') != url):
                raise ValueError('SDK36 requires its exact reviewed Maven Central coordinate and URL')
    return files


def source_pins():
    return {'qa/' + name: sha(HERE / name) for name in SOURCE_NAMES}


def validate_paths(bundle, out, report):
    # Resolve containment aliases without replacing the original paths: verify()
    # still rejects symlink inputs. The supervisor also writes a sibling log.
    bundle, out = (path.resolve() for path in (bundle, out))
    if bundle == out or bundle in out.parents:
        raise ValueError('Keep evidence and the selected SDK view outside the immutable input bundle')
    evidence = (report, report.with_suffix('.worker.log'), report.with_suffix(report.suffix + '.pending'))
    for path in evidence:
        physical = path.resolve()
        if any(physical == root or root in physical.parents for root in (bundle, out)):
            raise ValueError('Keep evidence and the selected SDK view outside the immutable input bundle')


def supervise(command, bundle, out, report, timeout):
    validate_paths(bundle, out, report)
    return supervise_transport(command, out, report, timeout)


def prepare(bundle, out, report, origin, *, offline=False, timeout=180,
            selector=SELECTION, lock=LOCK, opener=urllib.request.urlopen):
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= MAX_TIMEOUT_SECONDS:
        raise ValueError('Renderer preparation timeout must be in (0, 600] seconds')
    if report.exists() or report.is_symlink() or report.with_suffix(report.suffix + '.pending').exists():
        raise ValueError('Use a new receipt path to preserve earlier attempts')
    validate_paths(bundle, out, report)
    start = time.monotonic()
    record = {'schema': 1, 'consumer': 'android-presence-rows', 'accepted': False,
              'origin': origin, 'offline': offline, 'timeout_seconds': timeout,
              'max_attempts_per_file': MAX_ATTEMPTS, 'max_single_retry_wait_seconds': MAX_RETRY_WAIT_SECONDS,
              'files': [], 'sdk_levels': [28, 34, 36], 'network_requests': 0}
    report.parent.mkdir(parents=True, exist_ok=True)

    def save():
        record['elapsed_seconds'] = round(time.monotonic() - start, 6)
        record['network_requests'] = sum(len(row['attempts']) for row in record['files'])
        pending = report.with_suffix(report.suffix + '.pending')
        pending.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        os.replace(pending, report)

    try:
        identity(**origin)
        items = selection(selector, lock)
        record.update(selection_sha256=sha(selector), framework_lock_sha256=sha(lock),
                      source_sha256=source_pins(), dependency_directory=str(bundle / 'deps'))
        record['bundle_before'] = verify(bundle, lock, origin)
        if out.is_symlink() or (out.exists() and not out.is_dir()):
            raise ValueError('Expected a real Renderer SDK directory')
        if out.exists() and {path.name for path in out.iterdir()} - {item['name'] for item in items}:
            raise ValueError('Unexpected files in the Renderer SDK destination')
        # Validate every existing SDK before filling any missing entry or requesting SDK36.
        for item in items:
            target = out / item['name']
            row = {key: item[key] for key in ('sdk', 'name', 'bytes', 'sha256')}
            row.update(attempts=[], verified=False, source=None)
            record['files'].append(row)
            if target.exists() or target.is_symlink():
                checked(target, item)
                row['source'] = 'verified_existing_destination'
            elif item['source'] == 'framework_bundle':
                row['source'] = 'same_run_framework_bundle'
            elif offline:
                raise ValueError('SDK36 missing in offline mode')
        out.mkdir(parents=True, exist_ok=True)
        for item, row in zip(items, record['files']):
            target = out / item['name']
            if row['source'] == 'same_run_framework_bundle':
                # Both paths are under runner.temp. No second copy of these large SDKs is needed.
                os.link(bundle / 'sdk-jars' / item['name'], target)
            elif row['source'] is None:
                row['source'] = 'bounded_sdk36_download'
                download(item, target, start + timeout, row, save, opener)
            checked(target, item)
            row['verified'] = True
            save()
        # A consumer is admitted only after rechecking every selected SDK and the complete bundle.
        for item in items:
            checked(out / item['name'], item)
        record['bundle_after'] = verify(bundle, lock, origin)
        if record['source_sha256'] != source_pins() or record['selection_sha256'] != sha(selector):
            raise ValueError('Preparation sources or SDK selection changed during execution')
        record['accepted'] = True
        return record
    except BaseException as failure:
        record['error'] = str(failure)
        raise
    finally:
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--run-attempt', required=True)
    parser.add_argument('--head-sha', required=True)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--timeout', type=float, default=180)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    origin = identity(args.run_id, args.run_attempt, args.head_sha)
    bundle, out, report = (path.absolute() for path in (args.bundle, args.out, args.report))
    try:
        validate_paths(bundle, out, report)
        if args.worker:
            result = prepare(bundle, out, report, origin, offline=args.offline, timeout=args.timeout)
        else:
            command = [sys.executable, str(Path(__file__).resolve()), '--worker',
                       '--bundle', str(bundle), '--out', str(out), '--report', str(report),
                       '--run-id', args.run_id, '--run-attempt', args.run_attempt, '--head-sha', args.head_sha,
                       '--timeout', str(args.timeout)]
            if args.offline:
                command.append('--offline')
            result = supervise(command, bundle, out, report, args.timeout)
    except (OSError, ValueError, RuntimeError) as failure:
        print('Renderer framework preparation failed:', failure, flush=True)
        raise SystemExit(1)
    print(json.dumps({'accepted': result['accepted'], 'network_requests': result.get('network_requests', 0),
                      'verified_sdks': sum(row.get('verified', False) for row in result['files']),
                      'origin': origin, 'sdk_levels': result.get('sdk_levels')}))
    if not result['accepted']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
