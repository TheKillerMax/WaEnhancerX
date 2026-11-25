#!/usr/bin/env python3
"""Host-only controls for receipt rejection and the exact portable SQL strings.

Synthetic receipt fixtures are not Android execution evidence.
"""
import copy
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('sqlite_probe_validator', HERE / 'validate_android_sqlite_probe.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
NONCE = '0123456789abcdef0123456789abcdef'


def fixture():
    samples = [i * 1000000 for i in range(1, 25)]
    metric = {'samples_ns': samples, 'median_ms': 12.5, 'p90_ms': 22.0, 'plan': ['SYNTHETIC PLAN']}
    return {'schema': validator.SCHEMA, 'package': validator.PACKAGE, 'run_nonce': NONCE,
            'sdk': 24, 'release': '7.0', 'hardware': 'ranchu', 'supported_abis': ['x86_64'],
            'process_is_64bit': True, 'uid': 10001, 'pid': 42,
            'application_page_size_bytes': 4096, 'sqlite_page_size_bytes': 4096,
            'sqlite_version': '3.9.2', 'journal_mode': 'delete', 'checks': 280, 'own_db_absent': True,
            'page_size_rows': 96, 'trials_each': 24, 'duration_ms': 1234.0,
            'newest_insert_and_anchor_delete_controls': True,
            'null_fallback': 'coalesce(taken_ms,added_ms), both milliseconds',
            'seek_predicate': 'SCALAR_LEXICOGRAPHIC_SQLITE_3_9',
            'scope': 'OWN_SYNTHETIC_SQLITE_ANDROID_FRAMEWORK_NO_WAEX_PHOTOS_MEDIASTORE_BINDER_PROVIDER_LSPOSED',
            'sizes': [{'rows': rows, 'offset': rows * 4 // 5, 'new_rows': 50000, 'database_pages': 100,
                       **{name: copy.deepcopy(metric) for name in ('indexed_offset', 'materialized_seek', 'expression_seek')}}
                      for rows in (50000, 100000, 150000)]}


def transcript(receipt):
    return 'INSTRUMENTATION_RESULT: waex_sqlite_receipt=' + json.dumps(receipt) + '\nINSTRUMENTATION_CODE: -1\n'


class ReceiptControls(unittest.TestCase):
    def accept(self, text, api=24, page=4096):
        return validator.validate(text, NONCE, api, page)

    def test_valid_synthetic_receipt(self):
        self.assertEqual(self.accept(transcript(fixture()))['checks'], 280)

    def test_application_and_database_pages_are_independent(self):
        receipt = fixture(); receipt['sdk'] = 35; receipt['application_page_size_bytes'] = 16384
        self.assertEqual(self.accept(transcript(receipt), 35, 16384)['sqlite_page_size_bytes'], 4096)

    def test_wrong_environment_identity_or_cleanup_is_rejected(self):
        for key, value in [('sdk', 25), ('run_nonce', 'f' * 32), ('package', 'com.waenhancer'),
                           ('application_page_size_bytes', 16384), ('checks', 279), ('own_db_absent', False),
                           ('process_is_64bit', False), ('hardware', 'cebu'), ('uid', 0), ('pid', 0),
                           ('supported_abis', ['arm64-v8a']), ('sqlite_page_size_bytes', 3000),
                           ('sqlite_version', 'unknown'), ('journal_mode', 'unknown'), ('duration_ms', -1)]:
            receipt = fixture(); receipt[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.accept(transcript(receipt))

    def test_missing_duplicate_or_failed_instrumentation_is_rejected(self):
        valid = transcript(fixture())
        for text in ['', valid + valid, valid.replace('CODE: -1', 'CODE: 0'),
                     valid.replace('CODE: -1', 'CODE: -1\nINSTRUMENTATION_FAILED: fixture'),
                     'INSTRUMENTATION_RESULT: shortMsg=Process crashed.\n' + valid,
                     'INSTRUMENTATION_RESULT: waex_sqlite_error=fixture\n' + valid]:
            with self.subTest(text=text[:70]), self.assertRaises(ValueError):
                self.accept(text)

    def test_duplicate_json_keys_and_nonfinite_values_are_rejected(self):
        valid = transcript(fixture())
        for text in [valid.replace('"sdk": 24', '"sdk": 25, "sdk": 24'),
                     valid.replace('1234.0', 'NaN')]:
            with self.assertRaises(ValueError):
                self.accept(text)

    def test_missing_workload_or_timing_corruption_is_rejected(self):
        for mutate in [lambda r: r['sizes'].pop(), lambda r: r['sizes'][0].update(rows=49999),
                       lambda r: r['sizes'][0]['materialized_seek']['samples_ns'].pop(),
                       lambda r: r['sizes'][0]['materialized_seek'].update(median_ms=999),
                       lambda r: r['sizes'][0]['expression_seek'].update(plan=[])]:
            receipt = fixture(); mutate(receipt)
            with self.assertRaises(ValueError):
                self.accept(transcript(receipt))


def sql_constants():
    source = (HERE / 'android_sqlite_probe/SqliteProbeInstrumentation.java').read_text(encoding='utf-8')
    result = {}
    for name, expression in re.findall(r'private static final String (SELECT|OFF|SEEK|EXPR)=(.*?);', source):
        tokens = re.findall(r'"(?:\\.|[^"\\])*"|SELECT', expression)
        remainder = re.sub(r'"(?:\\.|[^"\\])*"|SELECT|[+\s]', '', expression)
        if remainder:
            raise ValueError('Unexpected SQL constant expression')
        result[name] = ''.join(result[token] if token == 'SELECT' else json.loads(token) for token in tokens)
    if set(result) != {'SELECT', 'OFF', 'SEEK', 'EXPR'}:
        raise ValueError('Missing production SQL constants')
    return result


class PortableSqlControls(unittest.TestCase):
    def test_actual_predicates_match_independent_ordering_and_reject_boundary_mutation(self):
        sql = sql_constants()
        with sqlite3.connect(':memory:') as db:
            db.execute('CREATE TABLE media(_id INTEGER PRIMARY KEY,taken_ms INTEGER,added_ms INTEGER NOT NULL,sort_ms INTEGER NOT NULL,bytes INTEGER NOT NULL,kind INTEGER NOT NULL)')
            db.execute('CREATE INDEX idx_seek ON media(sort_ms DESC,_id DESC)')
            db.execute('CREATE INDEX idx_expr ON media(coalesce(taken_ms,added_ms) DESC,_id DESC)')
            rows = []
            for i in range(1, 513):
                timestamp = 1600000000000 + (i % 17) * 1000
                taken = None if i % 5 == 0 else timestamp
                added = timestamp + (i % 3) * 1000
                rows.append((i, taken, added, added if taken is None else taken, 8192 + i, i % 7 == 0))
            db.executemany('INSERT INTO media VALUES(?,?,?,?,?,?)', rows)
            ordered = sorted([(row[0], row[3], row[4], int(row[5])) for row in rows], key=lambda row: (row[1], row[0]), reverse=True)
            for offset in (1, 96, 256, 416, 511):
                anchor = ordered[offset - 1]
                args = (str(anchor[1]), str(anchor[1]), str(anchor[0]), '96')
                expected = ordered[offset:offset + 96]
                for name in ('SEEK', 'EXPR'):
                    self.assertEqual(db.execute(sql[name], args).fetchall(), expected)
                self.assertNotEqual(db.execute(sql['SEEK'].replace('_id<', '_id<=', 1), args).fetchall(), expected)


if __name__ == '__main__':
    unittest.main()
