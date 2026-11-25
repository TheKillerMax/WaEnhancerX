#!/usr/bin/env python3
"""Validate one neutral SQLite instrumentation receipt; no device commands."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

SCHEMA = 'WAEX_EMULATOR_SQLITE_PROBE_V1'
PACKAGE = 'org.lab.waex.qa.sqlite'
EXPECTED_CHECKS = 280


def exact_integer(value, minimum=0):
    return type(value) is int and value >= minimum


def reject_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def validate(log, expected_nonce, expected_api, expected_page_size):
    if not re.fullmatch('[a-f0-9]{32}', expected_nonce):
        raise ValueError('Invalid expected run nonce')
    if not 24 <= expected_api <= 37 or expected_page_size not in (4096, 16384):
        raise ValueError('Invalid expected Android environment')
    if len(log.encode('utf-8')) > 256 * 1024:
        raise ValueError('Instrumentation output limit exceeded')
    lines = log.splitlines()
    prefix = 'INSTRUMENTATION_RESULT: waex_sqlite_receipt='
    receipts = [line[len(prefix):] for line in lines if line.startswith(prefix)]
    codes = [line for line in lines if line.startswith('INSTRUMENTATION_CODE:')]
    if len(receipts) != 1 or codes != ['INSTRUMENTATION_CODE: -1']:
        raise ValueError('Missing/duplicate receipt or unsuccessful instrumentation result')
    if any('INSTRUMENTATION_FAILED' in line or 'INSTRUMENTATION_ABORTED' in line or
           line.startswith(('INSTRUMENTATION_RESULT: waex_sqlite_error=',
                            'INSTRUMENTATION_RESULT: shortMsg=', 'INSTRUMENTATION_RESULT: longMsg=')) for line in lines):
        raise ValueError('Instrumentation reported a failure')
    result = json.loads(receipts[0], object_pairs_hook=reject_duplicate_pairs,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON number')))
    for key, expected in {'schema': SCHEMA, 'package': PACKAGE, 'run_nonce': expected_nonce,
                          'sdk': expected_api, 'application_page_size_bytes': expected_page_size,
                          'checks': EXPECTED_CHECKS, 'own_db_absent': True,
                          'process_is_64bit': True, 'page_size_rows': 96, 'trials_each': 24,
                          'newest_insert_and_anchor_delete_controls': True,
                          'null_fallback': 'coalesce(taken_ms,added_ms), both milliseconds',
                          'seek_predicate': 'SCALAR_LEXICOGRAPHIC_SQLITE_3_9',
                          'scope': 'OWN_SYNTHETIC_SQLITE_ANDROID_FRAMEWORK_NO_WAEX_PHOTOS_MEDIASTORE_BINDER_PROVIDER_LSPOSED'}.items():
        if type(result.get(key)) is not type(expected) or result[key] != expected:
            raise ValueError('Receipt contract mismatch: ' + key)
    if result.get('hardware') not in ('ranchu', 'goldfish'):
        raise ValueError('Not the expected emulator hardware')
    if (not isinstance(result.get('supported_abis'), list) or 'x86_64' not in result['supported_abis'] or
            not all(isinstance(abi, str) and abi for abi in result['supported_abis'])):
        raise ValueError('Missing x86_64 ABI')
    if not exact_integer(result.get('uid'), 10000) or not exact_integer(result.get('pid'), 1):
        raise ValueError('Invalid own UID/PID metadata')
    if not isinstance(result.get('release'), str) or not result['release']:
        raise ValueError('Missing Android release')
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:\..+)?', result.get('sqlite_version', '')):
        raise ValueError('Invalid SQLite version')
    if result.get('journal_mode') not in ('delete', 'truncate', 'persist', 'memory', 'wal', 'off'):
        raise ValueError('Invalid SQLite journal mode')
    db_page = result.get('sqlite_page_size_bytes')
    if not exact_integer(db_page, 512) or db_page > 65536 or db_page & (db_page - 1):
        raise ValueError('Invalid SQLite database page size')
    duration = result.get('duration_ms')
    if type(duration) not in (int, float) or not math.isfinite(duration) or not 0 < duration <= 180000:
        raise ValueError('Invalid fixture duration')
    sizes = result.get('sizes')
    if not isinstance(sizes, list) or len(sizes) != 3:
        raise ValueError('Missing workload stages')
    for stage, rows in zip(sizes, (50000, 100000, 150000)):
        if stage.get('rows') != rows or stage.get('offset') != rows * 4 // 5 or stage.get('new_rows') != 50000:
            raise ValueError('Workload size changed')
        if not exact_integer(stage.get('database_pages'), 1):
            raise ValueError('Invalid database page count')
        for query in ('indexed_offset', 'materialized_seek', 'expression_seek'):
            metric = stage.get(query, {})
            samples = metric.get('samples_ns', [])
            if len(samples) != 24 or not all(exact_integer(sample) for sample in samples):
                raise ValueError('Invalid timing sample inventory: ' + query)
            for field, value in [('median_ms', statistics.median(samples) / 1e6),
                                 ('p90_ms', sorted(samples)[math.ceil(len(samples) * .9) - 1] / 1e6)]:
                measured = metric.get(field)
                if type(measured) not in (int, float) or not math.isfinite(measured) or not math.isclose(measured, value, rel_tol=1e-9, abs_tol=1e-9):
                    raise ValueError('Timing summary mismatch: ' + query + '.' + field)
            plan = metric.get('plan')
            if not isinstance(plan, list) or not plan or not all(isinstance(line, str) and line for line in plan):
                raise ValueError('Missing query plan: ' + query)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--expected-nonce', required=True)
    parser.add_argument('--expected-api', type=int, required=True)
    parser.add_argument('--expected-page-size', type=int, choices=(4096, 16384), required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit('A new report path is required')
    raw = args.log.read_bytes()
    if len(raw) > 256 * 1024:
        raise SystemExit('Instrumentation output limit exceeded')
    receipt = validate(raw.decode('utf-8'), args.expected_nonce, args.expected_api, args.expected_page_size)
    report = {'status': 'PASS_SQLITE_FIXTURE_ONLY', 'instrumentation_log_sha256': hashlib.sha256(raw).hexdigest(),
              'receipt': receipt, 'android_device_result': True,
              'waex_application_tested': False, 'binder_provider_identity_tested': False,
              'native_library_16k_compatibility_tested': False,
              'performance_improvement_claimed': False}
    args.out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: receipt[key] for key in ('schema', 'sdk', 'supported_abis',
                                                  'application_page_size_bytes', 'sqlite_page_size_bytes', 'checks')}))


if __name__ == '__main__':
    main()
