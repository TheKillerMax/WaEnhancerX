#!/usr/bin/env python3
"""Prepare the three locked Robolectric SDKs once, before offline test consumers.

Uses the existing framework lock and identity verifier. Existing incorrect bytes
fail before any request. Only bounded transient transport failures are retried;
long Retry-After intervals stop explicitly instead of retrying before permission.
"""
import argparse
import datetime
from email.utils import parsedate_to_datetime
import http.client
import json
import math
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from framework_dependency_bundle import LOCK, checked, load_lock, sha
from maven_dependencies import MAX_ATTEMPTS, MAX_TIMEOUT_SECONDS

TRANSIENT_HTTP = {408, 429, 500, 502, 503, 504}
MAX_RETRY_WAIT_SECONDS = 30.0


def retry_after(value):
    if value is None:
        return 0.0
    if value.strip().isdigit():
        return float(value.strip())
    when = parsedate_to_datetime(value)
    if when.tzinfo is None:
        raise ValueError('Retry-After date has no timezone')
    return max(0.0, (when - datetime.datetime.now(datetime.timezone.utc)).total_seconds())


def download(item, destination, deadline, record, save, opener):
    for number in range(1, MAX_ATTEMPTS + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('SDK preparation exhausted its total time budget')
        attempt = {'number': number, 'url': item['url'], 'timeout_seconds': min(30.0, remaining),
                   'retryable': False, 'bytes': 0, 'status': 'started'}
        record['attempts'].append(attempt)
        save()
        temporary = None
        delay = 0.0
        try:
            request = urllib.request.Request(item['url'], headers={'User-Agent': 'WAEX-locked-framework-QA'})
            with opener(request, timeout=attempt['timeout_seconds']) as response:
                attempt['http_status'] = response.status
                if response.status != 200:
                    raise ValueError('SDK response must have status 200')
                with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.sdk-download-', delete=False) as stream:
                    temporary = Path(stream.name)
                    attempt['temporary_file'] = temporary.name
                    save()
                    while True:
                        if time.monotonic() >= deadline:
                            raise TimeoutError('SDK preparation exhausted its total time budget')
                        block = response.read1(min(1024 * 1024, item['bytes'] + 1 - attempt['bytes']))
                        if not block:
                            break
                        attempt['bytes'] += len(block)
                        if attempt['bytes'] > item['bytes']:
                            raise ValueError('SDK response exceeds its pinned byte count')
                        stream.write(block)
            checked(temporary, item)
            # Publish only complete verified bytes, without replacing a concurrent file.
            os.link(temporary, destination)
            attempt['status'] = 'verified'
            save()
            return
        except urllib.error.HTTPError as failure:
            attempt.update(http_status=failure.code, error=str(failure), status='http_failure')
            attempt['retryable'] = failure.code in TRANSIENT_HTTP
            if attempt['retryable']:
                try:
                    delay = retry_after(failure.headers.get('Retry-After'))
                    attempt['retry_after_seconds'] = delay
                except (ValueError, TypeError, OverflowError) as invalid:
                    attempt.update(retryable=False, retry_after_error=str(invalid))
            failure.close()
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.IncompleteRead) as failure:
            denied_tls = isinstance(getattr(failure, 'reason', failure), ssl.SSLCertVerificationError)
            attempt.update(error=str(failure), status='transport_failure', retryable=not denied_tls)
        except BaseException as failure:
            attempt.update(error=str(failure), status='nonretryable_failure', retryable=False)
            save()
            raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        remaining = deadline - time.monotonic()
        delay = max(float(number), delay)
        if not attempt['retryable'] or number == MAX_ATTEMPTS:
            save()
            raise RuntimeError('SDK transport failed without an allowed retry: ' + item['name'])
        if delay >= remaining or delay > MAX_RETRY_WAIT_SECONDS:
            attempt['status'] = 'retry_deferred_beyond_budget'
            save()
            raise RuntimeError('Server retry interval exceeds the bounded SDK preparation budget')
        attempt['wait_seconds'] = delay
        save()
        time.sleep(delay)


def prepare(out, report, *, cache=None, offline=False, timeout=180, lock=LOCK, opener=urllib.request.urlopen):
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= MAX_TIMEOUT_SECONDS:
        raise ValueError('SDK preparation timeout must be in (0, 600] seconds')
    if report.exists():
        raise ValueError('Use a new receipt path to preserve previous attempts')
    start = time.monotonic()
    record = {'schema': 1, 'accepted': False, 'offline': offline, 'lock_sha256': sha(lock),
              'timeout_seconds': timeout, 'max_attempts_per_file': MAX_ATTEMPTS,
              'max_single_retry_wait_seconds': MAX_RETRY_WAIT_SECONDS, 'files': []}
    report.parent.mkdir(parents=True, exist_ok=True)

    def save():
        record['elapsed_seconds'] = round(time.monotonic() - start, 6)
        record['network_requests'] = sum(len(row['attempts']) for row in record['files'])
        pending = report.with_suffix(report.suffix+'.pending')
        pending.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
        os.replace(pending, report)

    try:
        items = [row for row in load_lock(lock) if row['directory'] == 'sdk-jars']
        if out.is_symlink() or (out.exists() and not out.is_dir()):
            raise ValueError('Expected a real SDK directory')
        if cache is not None and (cache.is_symlink() or not cache.is_dir()):
            raise ValueError('Expected an existing real SDK cache directory')
        expected_names = {row['name'] for row in items}
        if out.exists() and {p.name for p in out.iterdir()} - expected_names:
            raise ValueError('Unexpected files in the SDK destination')
        # Validate every selected existing input before downloading one missing artifact.
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
                raise ValueError('Locked SDK missing in offline mode: ' + item['name'])
        out.mkdir(parents=True, exist_ok=True)
        for item, row in zip(items, record['files']):
            target = out/item['name']
            if row['source'] == 'verified_cache':
                source = cache/item['name']
                try:
                    os.link(source, target)
                except OSError:
                    with target.open('xb') as destination, source.open('rb') as origin:
                        shutil.copyfileobj(origin, destination)
            elif row['source'] is None:
                row['source'] = 'download'
                download(item, target, start + timeout, row, save, opener)
            checked(target, item)
            row['verified'] = True
            save()
        record['accepted'] = True
        return record
    except BaseException as failure:
        record['error'] = str(failure)
        raise
    finally:
        save()


def supervise(command, out, report, timeout):
    """Bound the entire worker, including a response body that keeps trickling bytes."""
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= MAX_TIMEOUT_SECONDS:
        raise ValueError('Worker timeout must be in (0, 600] seconds')
    log = report.with_suffix('.worker.log')
    if report.exists() or log.exists() or report.with_suffix(report.suffix+'.pending').exists():
        raise ValueError('Use new evidence paths for a new SDK preparation attempt')
    report.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    with log.open('w', encoding='utf-8') as stream:
        if os.name == 'posix':
            from run_runtime_reporting_ci import run_gate
            code = run_gate(command, stream, os.environ.copy(), timeout=timeout)
        else:
            # The SDK worker performs only Python HTTP/file operations and starts no children.
            process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                code = 'infrastructure_timeout'
    record = json.loads(report.read_bytes()) if report.exists() else {'accepted': False, 'files': []}
    for row in record['files']:
        for attempt in row['attempts']:
            name = attempt.get('temporary_file')
            if name and Path(name).name == name and name.startswith('.sdk-download-'):
                (out/name).unlink(missing_ok=True)
    report.with_suffix(report.suffix+'.pending').unlink(missing_ok=True)
    record.update(supervisor_exit=code, worker_deadline_seconds=timeout,
                  supervisor_elapsed_seconds=round(time.monotonic()-start, 6),
                  worker_closed=True, worker_log_sha256=sha(log), resolver_sha256=sha(Path(__file__)))
    record['accepted'] = code == 0 and record.get('accepted') is True
    if code == 'infrastructure_timeout':
        record['error'] = 'SDK worker reached its total process deadline; no test consumer started'
    report.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
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
    try:
        if args.worker:
            result = prepare(args.out.resolve(), args.report.resolve(), cache=args.cache.resolve() if args.cache else None,
                             offline=args.offline, timeout=args.timeout)
        else:
            command = [sys.executable, str(Path(__file__).resolve()), '--worker',
                       '--out', str(args.out.resolve()), '--report', str(args.report.resolve()),
                       '--timeout', str(args.timeout)]
            if args.cache:
                command += ['--cache', str(args.cache.resolve())]
            if args.offline:
                command += ['--offline']
            result = supervise(command, args.out.resolve(), args.report.resolve(), args.timeout)
    except (OSError, ValueError, RuntimeError) as failure:
        print('SDK preparation failed:', failure, flush=True)
        raise SystemExit(1)
    print(json.dumps({'accepted': result['accepted'], 'network_requests': result.get('network_requests', 0),
                      'verified_sdks': sum(row.get('verified', False) for row in result['files']),
                      'lock_sha256': result.get('lock_sha256')}))
    if not result['accepted']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
