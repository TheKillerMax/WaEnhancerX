#!/usr/bin/env python3
"""Prepare the existing 36-file framework graph without resolving Maven plugins.

The shared SDK transport retains its retry, Retry-After, byte-integrity and
process-deadline contracts. A restored cache is checked before any missing file
is fetched. Only the two already pinned AARs need container extraction; their
classes.jar bytes remain the existing framework lock's final identities.
"""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import urllib.request
import zipfile

from framework_dependency_bundle import LOCK, checked, load_lock, sha
import prepare_robolectric_sdks as transport

# Size bounds for the two SHA-pinned containers already named in the lock.
# These are transport metadata, not another dependency/version list.
ARCHIVE_BYTES = {
    '5ff62326b49c308c1d060466ae3cf4aa0e3deaf9295f077a6886048dda3e9b14': 5441,
    '56cb7496a06d9f2dca7d3ff76c50a8a30bd18e00a24a3b267d5a31437b278e67': 103877,
}


def validate_evidence_paths(out, report, cache=None):
    """Reject receipt side effects inside either artifact directory before any write."""
    roots = [Path(path).resolve() for path in (out, cache) if path is not None]
    evidence = (report, report.with_suffix('.worker.log'), report.with_suffix(report.suffix+'.pending'))
    for path in evidence:
        physical = path.resolve()
        if any(physical == root or root in physical.parents for root in roots):
            raise ValueError('Evidence paths must remain outside framework destination/cache')


def cleanup(record, out):
    for row in record.get('files', []):
        for name in row.get('staging_files', []):
            if Path(name).name != name or not name.startswith('.framework-stage-'):
                raise ValueError('Unsafe recorded framework staging path')
            (out/name).unlink(missing_ok=True)


def staging(out, row, save):
    with tempfile.NamedTemporaryFile(dir=out, prefix='.framework-stage-', delete=False) as stream:
        path = Path(stream.name)
    row.setdefault('staging_files', []).append(path.name)
    save()
    return path


def fetch(item, target, deadline, row, save, opener, archive_bytes):
    if 'archive_member' not in item:
        transport.download(item, target, deadline, row, save, opener)
        return
    container = staging(target.parent, row, save)
    # download() publishes by an exclusive link, so its destination must be absent.
    container.unlink()
    spec = {'name': item['name'] + '.aar', 'url': item['url'],
            'sha256': item['archive_sha256'], 'bytes': archive_bytes[item['archive_sha256']]}
    row['container'] = {key: spec[key] for key in ('sha256', 'bytes')}
    transport.download(spec, container, deadline, row, save, opener)
    extracted = staging(target.parent, row, save)
    with zipfile.ZipFile(container) as archive:
        matches = [entry for entry in archive.infolist() if entry.filename == 'classes.jar']
        if len(matches) != 1 or matches[0].file_size != item['bytes'] or matches[0].flag_bits & 1:
            raise ValueError('Pinned AAR must contain exactly one bounded, unencrypted classes.jar')
        with archive.open(matches[0]) as source, extracted.open('wb') as output:
            data = source.read(item['bytes'] + 1)
            if len(data) != item['bytes']:
                raise ValueError('AAR member differs from its pinned byte count')
            output.write(data)
    checked(extracted, item)
    os.link(extracted, target)
    row['container']['verified'] = True


def prepare(out, report, *, cache=None, offline=False, timeout=180, lock=LOCK,
            opener=urllib.request.urlopen, archive_bytes=ARCHIVE_BYTES):
    validate_evidence_paths(out, report, cache)
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= transport.MAX_TIMEOUT_SECONDS:
        raise ValueError('Framework preparation timeout must be in (0, 600] seconds')
    if report.exists():
        raise ValueError('Use a new receipt path to preserve previous attempts')
    start = time.monotonic()
    record = {'schema': 1, 'accepted': False, 'offline': offline, 'lock_sha256': sha(lock),
              'scope': 'Locked framework dependencies; Android SDKs and public APIs are separate',
              'timeout_seconds': timeout, 'max_attempts_per_file': transport.MAX_ATTEMPTS,
              'max_single_retry_wait_seconds': transport.MAX_RETRY_WAIT_SECONDS, 'files': []}
    report.parent.mkdir(parents=True, exist_ok=True)

    def save():
        record['elapsed_seconds'] = round(time.monotonic() - start, 6)
        record['network_requests'] = sum(len(row['attempts']) for row in record['files'])
        pending = report.with_suffix(report.suffix + '.pending')
        pending.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        os.replace(pending, report)

    try:
        items = [row for row in load_lock(lock) if row['directory'] == 'deps']
        for item in items:
            if ('archive_member' in item and (item['archive_member'] != 'classes.jar'
                    or item.get('archive_sha256') not in archive_bytes)):
                raise ValueError('The locked AAR needs reviewed container metadata')
        if out.is_symlink() or (out.exists() and not out.is_dir()):
            raise ValueError('Expected a real framework destination directory')
        if cache is not None and (cache.is_symlink() or not cache.is_dir()):
            raise ValueError('Expected an existing real framework cache directory')
        names = {item['name'] for item in items}
        for directory in (out, cache):
            if directory is not None and directory.exists() and {p.name for p in directory.iterdir()} - names:
                raise ValueError('Unexpected files in the framework destination or cache')
        # Preflight the whole existing graph before fetching even its first missing file.
        for item in items:
            target = out/item['name']
            source = cache/item['name'] if cache is not None else None
            row = {'name': item['name'], 'sha256': item['sha256'], 'bytes': item['bytes'],
                   'attempts': [], 'verified': False, 'source': None}
            record['files'].append(row)
            if target.exists() or target.is_symlink():
                checked(target, item)
                row['source'] = 'existing_destination'
            elif source is not None and (source.exists() or source.is_symlink()):
                checked(source, item)
                row['source'] = 'verified_cache'
            elif offline:
                raise ValueError('Locked dependency missing in offline mode: ' + item['name'])
        out.mkdir(parents=True, exist_ok=True)
        for item, row in zip(items, record['files']):
            target = out/item['name']
            if row['source'] == 'verified_cache':
                source = cache/item['name']
                try:
                    os.link(source, target)
                except OSError:
                    temporary = staging(out, row, save)
                    shutil.copyfile(source, temporary)
                    checked(temporary, item)
                    os.link(temporary, target)
            elif row['source'] is None:
                row['source'] = 'download'
                fetch(item, target, start + timeout, row, save, opener, archive_bytes)
            checked(target, item)
            row['verified'] = True
            cleanup({'files': [row]}, out)
            save()
        record['accepted'] = True
        return record
    except BaseException as failure:
        record['error'] = str(failure)
        raise
    finally:
        try:
            cleanup(record, out)
        except BaseException as failure:
            record.update(accepted=False, error='Framework staging cleanup failed: ' + str(failure))
            raise
        finally:
            save()


def supervise(command, out, report, timeout, *, cache=None):
    validate_evidence_paths(out, report, cache)
    record = transport.supervise(command, out, report, timeout)
    try:
        cleanup(record, out)
    except (OSError, ValueError) as failure:
        record.update(accepted=False, error='Framework staging cleanup failed: ' + str(failure))
    record['preparer_sha256'] = sha(Path(__file__))
    record['transport_sha256'] = sha(Path(transport.__file__))
    report.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--timeout', type=float, default=180)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    out, report = args.out.absolute(), args.report.absolute()
    cache = args.cache.absolute() if args.cache else None
    try:
        validate_evidence_paths(out, report, cache)
        if args.worker:
            result = prepare(out, report, cache=cache,
                             offline=args.offline, timeout=args.timeout)
        else:
            command = [sys.executable, str(Path(__file__).resolve()), '--worker',
                       '--out', str(out), '--report', str(report), '--timeout', str(args.timeout)]
            if args.cache:
                command += ['--cache', str(args.cache.absolute())]
            if args.offline:
                command += ['--offline']
            result = supervise(command, out, report, args.timeout, cache=cache)
    except (OSError, ValueError, RuntimeError) as failure:
        print('Framework preparation failed:', failure, flush=True)
        raise SystemExit(1)
    print(json.dumps({'accepted': result['accepted'], 'network_requests': result.get('network_requests', 0),
                      'verified_dependencies': sum(row.get('verified', False) for row in result['files']),
                      'lock_sha256': result.get('lock_sha256')}))
    if not result['accepted']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
