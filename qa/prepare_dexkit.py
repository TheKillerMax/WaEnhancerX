#!/usr/bin/env python3
"""Acquire only the pinned DexKit 2.2.0 AAR/classes.jar used by source QA.

The existing bounded HTTP worker supplies retry/deadline handling. Importing it
does not load or resolve the framework graph. Cache hits are verified before use;
bad existing bytes fail closed and are never replaced by a download.
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

DEXKIT_SHA256 = '195979d9576ba6d68a1c60bdd3e38cd3aed068d4e0c5c6c99caa50bc25fcb9f1'
DEXKIT_AAR_SHA256 = 'cf4488da9f721750ce5ff4311e88356cbfcb1d4444c2b519b12d8bdb5f33f2c6'
DEXKIT_URL = 'https://repo.maven.apache.org/maven2/org/luckypray/dexkit/2.2.0/dexkit-2.2.0.aar'
AAR = {'name': 'dexkit-2.2.0.aar', 'bytes': 1447011,
       'sha256': DEXKIT_AAR_SHA256, 'url': DEXKIT_URL}
JAR = {'name': 'dexkit-2.2.0.jar', 'bytes': 827109, 'sha256': DEXKIT_SHA256}
DEFAULT_CACHE = Path.home() / '.cache/waex-qa/dexkit-2.2.0'
DEFAULT_TIMEOUT = 90


def prepare(cache, report, *, offline=False, timeout=DEFAULT_TIMEOUT, opener=urllib.request.urlopen):
    transport.validate_evidence_paths(cache, report)
    if not 0 < timeout <= transport.MAX_TIMEOUT_SECONDS:
        raise ValueError('DexKit timeout must be in (0, 600] seconds')
    pending = report.with_suffix(report.suffix + '.pending')
    if any(path.exists() or path.is_symlink() for path in (report, pending)):
        raise ValueError('Use a new receipt path to preserve previous attempts')
    started = time.monotonic()
    rows = [{'name': item['name'], 'bytes': item['bytes'], 'sha256': item['sha256'],
             'attempts': [], 'verified': False, 'source': None} for item in (AAR, JAR)]
    record = {'schema': 1, 'accepted': False, 'offline': offline, 'files': rows,
              'timeout_seconds': timeout, 'max_attempts_per_file': transport.MAX_ATTEMPTS,
              'max_single_retry_wait_seconds': transport.MAX_RETRY_WAIT_SECONDS,
              'preparer_sha256': sha(Path(__file__)),
              'transport_sha256': sha(Path(transport.__file__)),
              'framework_graph_resolved': False}
    report.parent.mkdir(parents=True, exist_ok=True)

    def save():
        record['elapsed_seconds'] = round(time.monotonic() - started, 6)
        record['network_requests'] = len(rows[0]['attempts'])
        pending.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        os.replace(pending, report)

    temporary = None
    try:
        if cache.is_symlink() or (cache.exists() and not cache.is_dir()):
            raise ValueError('Expected a real DexKit cache directory')
        if cache.exists() and {p.name for p in cache.iterdir()} - {AAR['name'], JAR['name']}:
            raise ValueError('Unexpected files in the dedicated DexKit cache')
        cache.mkdir(parents=True, exist_ok=True)
        for item, row in zip((AAR, JAR), rows):
            path = cache / item['name']
            if path.exists() or path.is_symlink():
                checked(path, item)
                row.update(verified=True, source='verified_cache')
        if rows[1]['verified']:
            record['accepted'] = True
            return record
        if not rows[0]['verified']:
            if offline:
                raise ValueError('Pinned DexKit AAR/classes.jar missing in offline mode')
            rows[0]['source'] = 'download'
            transport.download(AAR, cache / AAR['name'], started + timeout, rows[0], save, opener)
            rows[0]['verified'] = True
        with zipfile.ZipFile(cache / AAR['name']) as archive:
            if archive.namelist().count('classes.jar') != 1:
                raise ValueError('DexKit classes.jar must occur exactly once')
            member = archive.getinfo('classes.jar')
            if member.file_size != JAR['bytes'] or member.flag_bits & 1:
                raise ValueError('DexKit classes.jar size or encryption flag differs')
            with archive.open(member) as source:
                body = source.read(JAR['bytes'] + 1)
        with tempfile.NamedTemporaryFile(dir=cache, prefix='.sdk-download-', delete=False) as stream:
            temporary = Path(stream.name)
            rows[1]['attempts'].append({'kind': 'extract_classes_jar', 'temporary_file': temporary.name})
            save()
            stream.write(body)
        checked(temporary, JAR)
        os.link(temporary, cache / JAR['name'])
        rows[1].update(verified=True, source='verified_aar_member')
        record['accepted'] = True
        return record
    except BaseException as failure:
        record.update(error=str(failure), error_type=type(failure).__name__)
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        save()


def acquire(cache, report, *, offline=False, timeout=DEFAULT_TIMEOUT):
    cache, report = Path(cache).absolute(), Path(report).absolute()
    command = [sys.executable, str(Path(__file__).resolve()), '--worker',
               '--cache', str(cache), '--report', str(report), '--timeout', str(timeout)]
    if offline:
        command.append('--offline')
    result = transport.supervise(command, cache, report, timeout)
    if not result['accepted']:
        raise RuntimeError('Pinned DexKit acquisition failed; see ' + str(report))
    jar = cache / JAR['name']
    checked(jar, JAR)
    return jar


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=DEFAULT_CACHE)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        result = prepare(args.cache.absolute(), args.report.absolute(), offline=args.offline, timeout=args.timeout)
        print(json.dumps({'accepted': result['accepted'], 'network_requests': result['network_requests']}))
    else:
        print(acquire(args.cache, args.report, offline=args.offline, timeout=args.timeout))


if __name__ == '__main__':
    main()
