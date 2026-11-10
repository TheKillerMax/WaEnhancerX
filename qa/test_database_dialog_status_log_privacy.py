#!/usr/bin/env python3
"""Reviewed DB/dialog/status diagnostic contract; source checks, not Android QA.

Each expression, its multiplicity and allowed payload kind are reviewed. A new
diagnostic requires semantic review, never a count bump or catalog regeneration.
The shared lexer rejects unsupported Xposed call forms rather than ignoring them.
This does not prove runtime reachability, arbitrary data flow or other log sinks.
"""
from collections import Counter
import json
from pathlib import Path
import re
import runpy
import sys
import unittest

QA = Path(__file__).resolve().parent
ROOT = QA.parent
sys.path.insert(0, str(QA))
import diagnostic_source_contract as shared

GateFailure = shared.GateFailure
require = shared.require
PREFIX = 'app/src/main/java/com/waenhancer/xposed/'
STORE = PREFIX + 'core/db/MessageStore.kt'
DIALOG = PREFIX + 'core/components/NativeWhatsAppDialog.kt'
STATUS = PREFIX + 'features/media/StatusDownloadHook.java'
FILES = (STORE, DIALOG, STATUS)
CATALOG = QA / 'database_dialog_status_log_contract.json'


def payload_kind(expression, kotlin=False):
    """Only reviewed literals and exception-class names are admissible here.

    This small grammar also rejects raw exceptions with previously unknown
    variable names, stack renderers and interpolations in a changed catalog.
    It is intentionally narrower than the Java/Kotlin expression languages.
    """
    require(not shared.exposure(expression), 'Private exception or identifier payload')
    lexed = shared.tokens(expression, kotlin)
    values = tuple(token.value for token in lexed)
    if kotlin:
        require(len(lexed) == 1 and lexed[0].quoted, 'Unreviewed Kotlin diagnostic expression')
        match = re.fullmatch(r'"(.*?)\$\{[A-Za-z_]\w*\.javaClass\.simpleName\}"', values[0], re.DOTALL)
        require(match is not None, 'Kotlin diagnostic must report exception class only')
        prefix = match.group(1)
        if prefix.startswith('$TAG '):
            prefix = prefix[5:]
        require('$' not in prefix, 'Dynamic Kotlin prefix requires review')
        return 'exception_class'
    require(len(lexed) >= 3 and values[:2] == ('TAG', '+') and
            lexed[2].quoted and values[2].startswith('"'), 'Unreviewed Java diagnostic prefix')
    if len(values) == 3:
        return 'literal_only'
    require(len(values) == 13 and values[3] == '+' and
            re.fullmatch(r'[A-Za-z_]\w*', values[4]) is not None and
            values[5:] == ('.', 'getClass', '(', ')', '.', 'getSimpleName', '(', ')'),
            'Java diagnostic must report exception class only; no raw Throwable, message or stack')
    return 'exception_class'


def validate_catalog(data):
    require(data.get('schema') == 1, 'Unknown diagnostic catalog schema')
    require(set(data.get('files', {})) == set(FILES), 'Catalog must cover all three production files')
    identifiers = set()
    for path in FILES:
        record = data['files'][path]
        require(isinstance(record.get('sites'), list) and record['sites'], 'Empty catalog: ' + path)
        for site in record['sites']:
            require(all(isinstance(site.get(key), str) and site[key] for key in
                        ('id', 'expression', 'purpose', 'allowed_data')), 'Incomplete callsite: ' + path)
            require(site['id'] not in identifiers, 'Duplicate callsite id: ' + site['id'])
            identifiers.add(site['id'])
            require(payload_kind(site['expression'], path.endswith('.kt')) == site['allowed_data'],
                    'Declared payload kind differs from expression: ' + site['id'])
    return data


def load_catalog(path=CATALOG):
    return validate_catalog(json.loads(path.read_text(encoding='utf-8')))


def check_logs(sources, catalog):
    validate_catalog(catalog)
    require(set(sources) == set(FILES), 'Missing or unexpected diagnostic source')
    errors, total = [], 0
    for path in FILES:
        source, record, kotlin = sources[path], catalog['files'][path], path.endswith('.kt')
        try:
            calls = list(shared.log_calls(source, kotlin))
            for line, expression in calls:
                try:
                    payload_kind(expression, kotlin)
                except GateFailure as error:
                    errors.append(f'{path}:{line}: {error}')
            actual = [shared.signature(expression, kotlin) for _, expression in calls]
            expected = [shared.signature(site['expression'], kotlin) for site in record['sites']]
            if actual != expected:
                added = sum((Counter(actual) - Counter(expected)).values())
                missing = sum((Counter(expected) - Counter(actual)).values())
                errors.append(f'{path}: diagnostic contract changed: {added} unreviewed, '
                              f'{missing} missing (or order changed); review expressions, not counts')
            declaration = record.get('tag_declaration')
            if declaration:
                require(shared.fragment(source, declaration, kotlin), 'Reviewed constant TAG changed: ' + path)
                values = shared.signature(source, kotlin)
                require(sum(values[i:i + 2] == ('TAG', '=') for i in range(len(values) - 1)) == 1,
                        'Additional TAG assignment requires review: ' + path)
            total += len(calls)
        except GateFailure as error:
            errors.append(f'{path}: {error}')
    require(not errors, '\n'.join(errors))
    return total


def check_behavior(sources):
    """Retain selected static operations and export outcome wiring, not prove UI behavior."""
    store, dialog, status = [sources[path] for path in FILES]
    for operation in ('fun getIdFromKey(', 'fun getMediaFromId(', 'fun findAccountDataDir('):
        require(shared.fragment(store, operation, True), 'Database operation removed: ' + operation)
    for operation in ('fun setTitle(', 'fun setMessage(', 'fun setPositiveButton('):
        require(shared.fragment(dialog, operation, True), 'Dialog operation removed: ' + operation)
    save = shared.block(status, 'private void saveMediaFile(Context ctx, File srcFile)')
    export = shared.block(status, 'private boolean exportStatus(Context ctx, File srcFile)')
    failure = shared.block(export, 'catch (Exception failure)')
    success = shared.block(export, 'try')
    mark = shared.block(status, 'private void markStatusSaved(String identity)')
    require(shared.fragment(save, 'if (exportStatus(ctx, srcFile)) markStatusSaved(identity);'),
            'An identity may be marked saved only after successful export')
    require(shared.fragment(success, 'StatusMediaExporter.export(ctx, srcFile);'), 'Exporter call removed')
    require(shared.fragment(success, 'return true;'), 'Export success result removed')
    require(shared.fragment(failure,
            'showToast(ctx, UiText.get(R.string.waex_ui_failed_to_download_status, '
            '"Failed to download status: ") + failure.getClass().getSimpleName());'),
            'Localized export-failure notification/category changed')
    require(shared.fragment(failure, 'return false;') and not shared.fragment(failure, 'return true;'),
            'Failed export must return false')
    for text in (save, export, mark):
        require(not re.search(r'\.\s*(?:getMessage|getLocalizedMessage|getStackTraceString|printStackTrace)\s*\(', text),
                'Private exception text restored in status save/export path')
    require(shared.fragment(mark, 'prefs.edit().putStringSet(PREF_SAVED_IDENTITIES, saved).commit();'),
            'Saved-identity persistence removed')


def main():
    sources = {path: (ROOT / path).read_text(encoding='utf-8') for path in FILES}
    total = check_logs(sources, load_catalog())
    check_behavior(sources)
    namespace = runpy.run_path(str(QA / 'test_database_dialog_status_log_gate.py'), run_name='waex_db_status_controls')
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(namespace['DatabaseDialogStatusGateTests'])
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    require(result.testsRun > 0 and result.wasSuccessful() and not result.skipped,
            'DB/dialog/status negative-control suite failed or was skipped')
    print(f'PASS: {total} reviewed DB/dialog/status expressions; payload categories and export wiring; '
          f'{result.testsRun} control tests. Source-only, not Android runtime.')


if __name__ == '__main__':
    try:
        main()
    except (GateFailure, OSError, ValueError, KeyError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        raise SystemExit(1)
