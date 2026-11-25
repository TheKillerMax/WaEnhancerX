#!/usr/bin/env python3
"""Reject eight compilable HMA regressions with selected real framework scenarios.

The positive control executes the union of the same scenario methods first.
Fixture bodies remain exact; only @Test annotations outside each selection are
removed in disposable copies. Compilation/setup failures never count as kills.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from android_hma_test import PRODUCTION

ROOT = Path(__file__).resolve().parents[1]
DIAG = 'app/src/main/java/com/waenhancer/utils/HmaDiagnostics.kt'
POLICY = 'app/src/main/java/com/waenhancer/utils/HmaConfigPolicy.java'
CONFIG = 'app/src/main/java/com/waenhancer/utils/HmaConfigFile.java'
FLOW = 'qa/fixtures/HmaFlowTest.kt'
CONTRACT = 'qa/fixtures/HmaContractTest.java'
TEMPLATE_GUARD = '''        if (root.has("templates") && templates == null) {
            throw new JSONException("Unsupported HMA templates value");
        }
'''
MUTATIONS = [
    ('caller-uid', DIAG, 'if (uid != Process.myUid()) null else {', 'if (false) null else {',
     {FLOW: {'invalidOrForeignApplicationUidNeverReachesRoot'}}),
    ('live-scope', DIAG, 'if (!scope.isLive || !scope.contains(targetPackage))',
     'if (!scope.contains(targetPackage))', {FLOW: {'cachedScopeCannotAuthorizeAConfigRepair'}}),
    ('repair-lock', DIAG, '            synchronized(repairLock) {', '            synchronized(Any()) {',
     {FLOW: {'pendingCheckCannotPublishAnOldReportAfterRepairInvalidatesCache',
             'twoScopedRepairsSerializeAndPreserveBothTargets'}}),
    ('template-shape', POLICY, TEMPLATE_GUARD, '',
     {FLOW: {'malformedTemplateShapePreservesLiveFileWithoutCreatingBackup'},
      CONTRACT: {'malformedTemplateContainerFailsWithoutDiscardingOriginalValue'}}),
    ('list-shape', POLICY, 'if (object.has(field) && object.optJSONArray(field) == null)',
     'if (false)', {CONTRACT: {'malformedSelectedListsAreNeverNormalizedIntoEmptyArrays'}}),
    ('private-user', CONFIG, 'return path.startsWith("/data/user/" + userId + "/");',
     'return true;', {FLOW: {'workProfilePrivateRepairPreservesOwnerAliasesAndOtherProfiles'}}),
    ('utf8-snapshot', CONFIG, '.onMalformedInput(CodingErrorAction.REPORT)',
     '.onMalformedInput(CodingErrorAction.REPLACE)',
     {FLOW: {'malformedUtf8SnapshotPreservesLiveBytesWithoutCreatingBackup'},
      CONTRACT: {'snapshotRejectsMalformedUtf8RatherThanReplacingOriginalBytes'}}),
    ('template-elements', POLICY, 'if (!(reference instanceof String))', 'if (false)',
     {FLOW: {'nonStringTemplateReferenceNeverCreatesBackupOrWrites'},
      CONTRACT: {'nonStringTemplateReferencesAreNeverCoercedIntoNames'}}),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_tests(text, names, kotlin):
    expression = r'@Test\s+fun\s+(\w+)' if kotlin else r'@Test\s+public\s+void\s+(\w+)'
    discovered = {m.group(1) for m in re.finditer(expression, text)}
    if not names <= discovered:
        raise ValueError('Required scenario missing: ' + str(names - discovered))
    return re.sub(expression, lambda m: m.group(0) if m.group(1) in names
                  else m.group(0).replace('@Test ', '', 1), text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--deps', type=Path, required=True)
    parser.add_argument('--sdk-jars', type=Path)
    parser.add_argument('--maven-repo', type=Path)
    args = parser.parse_args()
    root, out = args.source_root.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    supporting = [
        'app/src/main/cpp/waex_diag.c',
        'app/src/main/java/com/waenhancer/utils/NativeDiagPaths.kt',
        'app/src/main/java/com/waenhancer/utils/LsposedScopeReader.kt',
        'qa/android_hma_test.py', FLOW, CONTRACT,
        'qa/fixtures/RootCommandBoundedChecks.java', 'qa/fixtures/hma_command_service.py',
    ]
    paths = list(dict.fromkeys(PRODUCTION + supporting))
    original = {p: sha(root / p) for p in paths}
    union = {FLOW: set(), CONTRACT: set()}
    for *_, selected in MUTATIONS:
        for fixture, names in selected.items():
            union[fixture].update(names)
    cases = [('positive-control', None, None, None, union)] + MUTATIONS
    results = []
    for name, changed_path, old, replacement, selected in cases:
        case = out / name
        candidate = case / 'source'
        for relative in paths:
            destination = candidate / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / relative, destination)
        for fixture in (FLOW, CONTRACT):
            path = candidate / fixture
            path.write_text(select_tests(path.read_text(), selected.get(fixture, set()), fixture == FLOW))
        if changed_path:
            path = candidate / changed_path
            text = path.read_text()
            if text.count(old) != 1:
                raise AssertionError('Mutation must change exactly one reviewed span: ' + name)
            path.write_text(text.replace(old, replacement))
        selected_count = sum(map(len, selected.values())) * 3
        suite = 'all' if len(selected) == 2 else 'flow' if FLOW in selected else 'contracts'
        expected_failures = selected_count if changed_path else 0
        command = [sys.executable, str(candidate / 'qa/android_hma_test.py'),
            '--source-root', str(candidate), '--out', str(case / 'evidence'),
            '--deps', str(args.deps.resolve()), '--suite', suite,
            '--expect-assertion-failures', str(expected_failures)]
        if args.sdk_jars:
            command += ['--sdk-jars', str(args.sdk_jars.resolve())]
        if args.maven_repo:
            command += ['--maven-repo', str(args.maven_repo.resolve())]
        with (case / 'supervisor.log').open('wb') as log:
            process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        evidence_path = case / 'evidence/result.json'
        evidence = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
        junit_path = case / 'evidence/junit.log'
        junit = junit_path.read_text() if junit_path.exists() else ''
        # Check identity of failed methods as well as counts and failure classes.
        failed_methods = re.findall(r'(?m)^\d+\) ([^\n(]+)\(', junit)
        expected_methods = sorted(method + suffix for names in selected.values() for method in names
                                  for suffix in ('[24]', '[28]', '')) if changed_path else []
        accepted = process.returncode == 0 and evidence.get('accepted') is True \
            and evidence.get('framework_tests') == selected_count \
            and evidence.get('assertion_failures') == expected_failures \
            and sorted(failed_methods) == expected_methods
        row = {'name': name, 'accepted': accepted, 'suite': suite,
               'selected_methods': {k: sorted(v) for k, v in selected.items()},
               'framework_tests': evidence.get('framework_tests'),
               'assertion_failures': evidence.get('assertion_failures'),
               'failed_methods': failed_methods, 'expected_methods': expected_methods,
               'supervisor_exit': process.returncode, 'command': command,
               'source_sha256': {p: sha(candidate / p) for p in paths},
               'mutation': None if not changed_path else {'path': changed_path, 'old': old, 'new': replacement},
               'result_sha256': sha(evidence_path) if evidence_path.exists() else None}
        results.append(row)
        (out / 'results.json').write_text(json.dumps({'mutator_sha256': sha(Path(__file__)),
            'baseline_source_sha256': original,
            'cases': results, 'all_accepted': all(r['accepted'] for r in results)}, indent=2) + '\n')
        print(json.dumps({k: row[k] for k in ('name', 'accepted', 'framework_tests', 'assertion_failures')}), flush=True)
        if not accepted:
            print((case / 'supervisor.log').read_text()[-5000:])
            raise SystemExit('Mutation control was not accepted: ' + name)
    if {p: sha(root / p) for p in paths} != original:
        raise AssertionError('Original candidate changed during mutation testing')


if __name__ == '__main__':
    main()
