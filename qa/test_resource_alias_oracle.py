#!/usr/bin/env python3
"""New alias-only parser controls over an already saved AAPT2 dump.

No AAPT2/compiler subprocess is invoked. The four historical controls in the
verifier main() are not called. Expected-map mutations are local case data,
never changes to the source fixture. All calls preserve verify_dump's int result.
"""
from pathlib import Path
import argparse
import copy
import datetime
import hashlib
import json
import re
from localization_support import entries
from verify_es419_resources import MAX_REFERENCE_HOPS, source_reference_targets, verify_dump


DESC = 'feat_app_interface_size_desc'
TITLE = 'feat_app_interface_size_title'
SPANISH = ('es', 'es-r419')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def block(text, name):
    match = re.search(r'^    resource 0x[0-9a-f]+ string/' + re.escape(name) +
                      r'\n.*?(?=^    resource |\Z)', text, re.M | re.S)
    assert match, ('Missing control input', name)
    return match


def with_value(text, name, qualifier, payload):
    item = block(text, name)
    pattern = r'^      \(' + re.escape(qualifier) + r'\) .*?(?=^      \(|\Z)'
    replacement = '' if payload is None else f'      ({qualifier}) {payload}\n'
    changed, count = re.subn(pattern, lambda _: replacement, item.group(), flags=re.M | re.S)
    assert count == 1, ('Ambiguous control input', name, qualifier)
    return text[:item.start()] + changed + text[item.end():]


def source_graph_case(text, spanish, references, graph):
    """Mutate saved values and their expected source maps together to isolate graph checks."""
    spanish, references = dict(spanish), copy.deepcopy(references)
    for name, target in graph.items():
        spanish[name] = ('@string/' + target, spanish[name][1])
        for qualifier in SPANISH:
            text = with_value(text, name, qualifier, '@string/' + target)
            references[qualifier][name] = target
    return text, spanish, references


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Exact reviewed source root with complete values/es/es419 directories')
    parser.add_argument('--dump', type=Path, required=True, help='Already saved resources-table.txt; no compiler is started')
    parser.add_argument('--out', type=Path, required=True, help='New evidence directory, never reused')
    args = parser.parse_args()
    root, dump_path, output = args.root.resolve(), args.dump.resolve(), args.out.resolve()
    dump_raw = dump_path.read_bytes()
    assert len(dump_raw) <= 2 * 1024 * 1024, 'Saved dump exceeds bounded fixture size'
    # Match subprocess(text=True) while retaining the exact raw-file hash below.
    text = dump_raw.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
    expected, spanish = entries(root, 'values'), entries(root, 'values-b+es+419')
    references = source_reference_targets(root)
    assert len(expected) == len(spanish) == 1834, 'This execution requires the reviewed composition'
    assert references == {q: {DESC: 'interface_size_desc', TITLE: 'interface_size_title'} for q in ('', *SPANISH)}, 'Reviewed alias source inputs differ'
    assert MAX_REFERENCE_HOPS == 32, 'Reviewed graph limit differs'
    output.mkdir(parents=True, exist_ok=False)
    cases = []

    def add(name, fixture, wanted, *, source=spanish, refs=references, reason=None, legacy=False, details=None, derivation='saved dump or payload-only mutation'):
        cases.append({'name': name, 'text': fixture, 'wanted': wanted, 'spanish': source,
                      'references': refs, 'reason': reason, 'legacy': legacy,
                      'details': details, 'derivation': derivation})

    add('saved_aliases_legacy_three_arguments', text, 'accept', legacy=True)
    add('saved_aliases_typed_and_counted', text, 'accept', details={
        'exact_compiled_spanish_literals': 3664, 'exact_compiled_spanish_references': 4,
        'reference_hop_limit': 32})
    add('wrong_existing_target', with_value(text, DESC, 'es', '@string/interface_size_title'),
        'reject', reason='Source alias target changed')

    for name, graph, reason in [
        ('absent_target', {DESC: 'waex_alias_missing_control'}, 'Missing reference target'),
        ('self_cycle', {DESC: DESC}, 'Reference cycle'),
        ('two_node_cycle', {DESC: TITLE, TITLE: DESC}, 'Reference cycle'),
    ]:
        changed, case_source, case_refs = source_graph_case(text, spanish, references, graph)
        add(name, changed, 'reject', source=case_source, refs=case_refs, reason=reason,
            derivation='saved dump plus coherent expected-source graph mutation')

    choices = [name for name in sorted(expected) if name not in {DESC, TITLE, 'interface_size_desc', 'interface_size_title'}]
    assert len(choices) > MAX_REFERENCE_HOPS + 1
    for hops, wanted in [(MAX_REFERENCE_HOPS, 'accept'), (MAX_REFERENCE_HOPS + 1, 'reject')]:
        graph = {choices[index]: choices[index + 1] for index in range(hops)}
        changed, case_source, case_refs = source_graph_case(text, spanish, references, graph)
        add(f'chain_{hops}_hops', changed, wanted, source=case_source, refs=case_refs,
            reason='Reference chain exceeds limit' if wanted == 'reject' else None,
            derivation='saved dump plus coherent expected-source graph mutation')

    quoted = text
    for qualifier in SPANISH:
        quoted = with_value(quoted, DESC, qualifier, '"@string/interface_size_desc"')
    add('source_alias_changed_to_literal', quoted, 'reject', reason='Source alias kind changed')
    literal_refs = copy.deepcopy(references)
    for qualifier in SPANISH:
        del literal_refs[qualifier][DESC]
    add('literal_with_reference_shaped_text', quoted, 'accept', refs=literal_refs,
        details={'exact_compiled_spanish_literals': 3666, 'exact_compiled_spanish_references': 2,
                 'reference_hop_limit': 32},
        derivation='saved dump with explicit quoted-literal source type; normalized text is unchanged')

    item = block(text, DESC)
    add('missing_alias_name', text[:item.start()] + text[item.end():], 'reject')
    add('missing_alias_configuration', with_value(text, DESC, 'es-r419', None), 'reject')
    add('duplicate_alias_name', text + item.group(), 'reject', reason='Duplicate compiled string')
    add('invalid_reference_name', with_value(text, DESC, 'es', '@string/../invalid'),
        'reject', reason='Unsupported compiled string value')
    assert len(cases) == 14

    rows = []
    for case in cases:
        details = {}
        row = {'name': case['name'], 'expected': case['wanted'], 'derivation': case['derivation'],
               'fixture_sha256': digest(case['text'].encode('utf-8')),
               'spanish_map_sha256': digest(json.dumps(case['spanish'], sort_keys=True, ensure_ascii=False).encode('utf-8')),
               'reference_map_sha256': digest(json.dumps(case['references'], sort_keys=True, ensure_ascii=False).encode('utf-8'))}
        try:
            if case['legacy']:
                count = verify_dump(case['text'], expected, case['spanish'])
            else:
                count = verify_dump(case['text'], expected, case['spanish'],
                                    reference_targets=case['references'], details=details)
        except AssertionError as error:
            row.update({'observed': 'reject', 'assertion': str(error),
                        'accepted': case['wanted'] == 'reject' and
                        (case['reason'] is None or case['reason'] in str(error))})
        else:
            row.update({'observed': 'accept', 'returned_count': count, 'details': details,
                        'accepted': case['wanted'] == 'accept' and type(count) is int and count == 1834 and
                        (case['details'] is None or details == case['details'])})
        rows.append(row)
    result = {'schema': 'WAEX_SAVED_DUMP_ALIAS_ORACLE_CONTROLS_V1',
              'finished_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'dump': {'path': str(dump_path), 'bytes': len(dump_raw), 'sha256': digest(dump_raw)},
              'normalized_dump': {'utf8_bytes': len(text.encode('utf-8')),
                                  'sha256': digest(text.encode('utf-8')),
                                  'universal_newlines': True},
              'source_root': str(root), 'controls': rows,
              'total_controls': len(rows), 'expected_accepts': 4, 'expected_rejections': 10,
              'status': 'PASS_NEW_ALIAS_PARSER_CONTROLS_ONLY' if all(r['accepted'] for r in rows) else 'FAIL_RETAINED_DO_NOT_REPLAY',
              'AAPT2_invocations': 0, 'historical_four_negative_controls_executed': 0,
              'Android_calls': 0, 'source_fixture_modified': False,
              'scope': 'Parser behavior on the saved dump and declared alias-only data mutations; no compilation or Android execution.'}
    with (output / 'result.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'controls': len(rows),
                      'accepted_controls': sum(r['accepted'] for r in rows), 'AAPT2_invocations': 0}))
    return 0 if all(row['accepted'] for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
