#!/usr/bin/env python3
"""Prepare the exact Core/OkHttp APIs used by focused public regression suites.

Only acquisition may retry. The existing bounded HTTP worker supervises transport;
no compilation, test command, Maven graph or native library is executed here.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import urllib.request
import zipfile

from framework_dependency_bundle import checked, sha
import prepare_robolectric_sdks as transport

CONFIGS = {
    'core': {
        'cache': 'core-1.18.0',
        'source': {'name': 'core-1.18.0.aar', 'bytes': 1364590,
                   'sha256': '311d83ac67d394076ec21d12ed2d10a44b59cb2929b7dce00e5a90a93842e37d',
                   'url': 'https://dl.google.com/dl/android/maven2/androidx/core/core/1.18.0/core-1.18.0.aar'},
        'jar': {'name': 'core-1.18.0.jar', 'bytes': 1383395,
                'sha256': 'd1f5a319a77555df7e23858ffb5ed45a95ebb4263fa1ab7a993510ceb53555a0'},
        'member': 'classes.jar',
    },
    'okhttp': {
        'cache': 'okhttp-4.12.0',
        'source': {'name': 'okhttp-4.12.0.jar', 'bytes': 789531,
                   'sha256': 'b1050081b14bb7a3a7e55a4d3ef01b5dcfabc453b4573a4fc019767191d5f4e0',
                   'url': 'https://repo.maven.apache.org/maven2/com/squareup/okhttp3/okhttp/4.12.0/okhttp-4.12.0.jar'},
    },
}
DEFAULT_TIMEOUT = 90


def default_cache(artifact):
    return Path.home() / '.cache/waex-qa' / CONFIGS[artifact]['cache']


def prepare(artifact, cache, report, *, offline=False, timeout=DEFAULT_TIMEOUT, opener=urllib.request.urlopen):
    if artifact not in CONFIGS:
        raise ValueError('Unknown reviewed public API')
    transport.validate_evidence_paths(cache, report)
    if not 0 < timeout <= transport.MAX_TIMEOUT_SECONDS:
        raise ValueError('Public API timeout must be in (0, 600] seconds')
    pending = report.with_suffix(report.suffix + '.pending')
    if any(path.exists() or path.is_symlink() for path in (report, pending)):
        raise ValueError('Use a new receipt path to preserve previous attempts')
    config = CONFIGS[artifact]
    source = config['source']
    target = config.get('jar', source)
    items = [source] + ([target] if 'member' in config else [])
    started = time.monotonic()
    rows = [dict(item, attempts=[], verified=False, source=None) for item in items]
    record = {'schema': 1, 'artifact': artifact, 'accepted': False, 'offline': offline,
              'files': rows, 'timeout_seconds': timeout,
              'max_attempts_per_file': transport.MAX_ATTEMPTS,
              'max_single_retry_wait_seconds': transport.MAX_RETRY_WAIT_SECONDS,
              'preparer_sha256': sha(Path(__file__)), 'transport_sha256': sha(Path(transport.__file__)),
              'framework_graph_resolved': False, 'consumer_invocations': 0,
              'native_libraries_extracted_or_loaded': False}
    report.parent.mkdir(parents=True, exist_ok=True)

    def save():
        record['elapsed_seconds'] = round(time.monotonic() - started, 6)
        record['network_requests'] = len(rows[0]['attempts'])
        pending.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        os.replace(pending, report)

    temporary = None
    try:
        if cache.is_symlink() or (cache.exists() and not cache.is_dir()):
            raise ValueError('Expected a real dedicated public API cache directory')
        if cache.exists() and {p.name for p in cache.iterdir()} - {item['name'] for item in items}:
            raise ValueError('Unexpected files in the dedicated public API cache')
        cache.mkdir(parents=True, exist_ok=True)
        for item, row in zip(items, rows):
            path = cache / item['name']
            if path.exists() or path.is_symlink():
                checked(path, item)
                row.update(verified=True, source='verified_cache')
        if rows[-1]['verified']:
            record['accepted'] = True
            return record
        if not rows[0]['verified']:
            if offline:
                raise ValueError('Pinned public API missing in offline mode')
            rows[0]['source'] = 'download'
            transport.download(source, cache / source['name'], started + timeout, rows[0], save, opener)
            rows[0]['verified'] = True
        if 'member' in config:
            with zipfile.ZipFile(cache / source['name']) as archive:
                if archive.namelist().count(config['member']) != 1:
                    raise ValueError('Public API classes.jar must occur exactly once')
                member = archive.getinfo(config['member'])
                if member.file_size != target['bytes'] or member.flag_bits & 1:
                    raise ValueError('Public API classes.jar size or encryption flag differs')
                with archive.open(member) as stream:
                    body = stream.read(target['bytes'] + 1)
            with tempfile.NamedTemporaryFile(dir=cache, prefix='.sdk-download-', delete=False) as stream:
                temporary = Path(stream.name)
                rows[-1]['attempts'].append({'kind': 'extract_classes_jar', 'temporary_file': temporary.name})
                save()
                stream.write(body)
            checked(temporary, target)
            os.link(temporary, cache / target['name'])
            rows[-1].update(verified=True, source='verified_aar_member')
        checked(cache / target['name'], target)
        record['accepted'] = True
        return record
    except BaseException as failure:
        record.update(error=str(failure), error_type=type(failure).__name__)
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        save()


def acquire(artifact, cache, report, *, offline=False, timeout=DEFAULT_TIMEOUT):
    cache, report = Path(cache).absolute(), Path(report).absolute()
    command = [sys.executable, str(Path(__file__).resolve()), '--worker', '--artifact', artifact,
               '--cache', str(cache), '--report', str(report), '--timeout', str(timeout)]
    if offline:
        command.append('--offline')
    result = transport.supervise(command, cache, report, timeout)
    if not result['accepted']:
        raise RuntimeError('Pinned public API acquisition failed; see ' + str(report))
    config = CONFIGS[artifact]
    target = config.get('jar', config['source'])
    jar = cache / target['name']
    checked(jar, target)
    return jar


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', choices=sorted(CONFIGS), required=True)
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    cache = args.cache or default_cache(args.artifact)
    if args.worker:
        result = prepare(args.artifact, cache.absolute(), args.report.absolute(),
                         offline=args.offline, timeout=args.timeout)
        print(json.dumps({'accepted': result['accepted'], 'network_requests': result['network_requests']}))
    else:
        print(acquire(args.artifact, cache, args.report, offline=args.offline, timeout=args.timeout))


if __name__ == '__main__':
    main()
