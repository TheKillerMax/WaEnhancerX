#!/usr/bin/env python3
"""One-shot fork-only publication; tests run without the publication credential."""
import argparse
import base64
import hashlib
import json
import lzma
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence-v14'
FORK = 'TheKillerMax/WaEnhancerX'
MAIN = '4bbe5cb02ce2fe924136a9579d2582c1a4818643'
BACKUP = 'fix/backup-canonical-roundtrip-2026-10-13'
PREVIEW = 'integration/preview-current-main-2026-10-14'
CI = 'test/qa-java-kotlin-syntax-guard-2026-10'
EXPECTED = {
    BACKUP: '4cbfb68227eef4ecdc0001911cb8f2f2722dda7f',
    PREVIEW: '9cb058eeae91729801d334a71857800033efa0f5',
    CI: '6440a940de68319cf72b0c5ee7c0aeccac482928',
}
BLOBS = {
    'app/src/main/java/com/waenhancer/core/preferences/SettingsBackupCodec.kt': '6c87249ca5fcfabd611abb00635618811763ac2b',
    'qa/test_settings_backup_binary_roundtrip.py': '4d93b304fa2cf36135099b61a6b17b80e627c83d',
    'qa/kotlin/TestSettingsBackupJson.kt': '909369f7a62dcb949d83d1065b3ef32c59f1cd4c',
    'qa/test_settings_backup_json.py': '66bd37bb6dd76fd86d5fbfb1aae6629861674840',
}
WORKFLOW = '.github/workflows/source-qa.yml'
WORKFLOW_BLOB = 'b1c272ca2663e4924a1327b67dc7a6ce98278ead'
PATCH_SHA256 = '8664df11d00ad8e38f6ec5ef5f6960afaed9973e08138b86988ae50b1c1f6cae'


def git(*args, cwd=ROOT):
    return subprocess.check_output(['git', *args], cwd=cwd, text=True, timeout=120).strip()


def check_heads():
    if os.environ.get('GITHUB_REPOSITORY') != FORK:
        raise RuntimeError('This one-shot operation is restricted to the authorized fork')
    for branch, sha in EXPECTED.items():
        found = git('ls-remote', 'origin', 'refs/heads/' + branch).split()
        if not found or found[0] != sha:
            raise RuntimeError('Branch changed; refusing publication: ' + branch)
    current = git('ls-remote', 'https://github.com/WaEnhancerX/WaEnhancerX.git', 'refs/heads/main').split()
    if not current or current[0] != MAIN:
        raise RuntimeError('Upstream main changed; a new reconciliation is required')


def verify_files(cwd):
    for name, expected in BLOBS.items():
        actual = git('hash-object', name, cwd=cwd)
        if actual != expected:
            raise RuntimeError('Tested-source identity mismatch: ' + name)


def run_test(cwd, name, command, rows):
    print(name, flush=True)
    result = subprocess.run(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    (OUT / (name + '.log')).write_bytes(result.stdout)
    rows.append({'name': name, 'exit_code': result.returncode})
    (OUT / 'tests.json').write_text(json.dumps(rows, indent=2))
    if result.returncode:
        sys.stdout.write(result.stdout.decode('utf-8', errors='replace'))
        raise RuntimeError('Regression failed: ' + name)


def validate():
    check_heads()
    OUT.mkdir(exist_ok=True)
    packed = base64.b64decode((ROOT / '.qa_reviews/backup-v14.patch.xz.b64').read_text().strip(), validate=True)
    decoder = lzma.LZMADecompressor(memlimit=64 * 1024 * 1024)
    patch = decoder.decompress(packed, max_length=1024 * 1024)
    if not decoder.eof or decoder.unused_data or hashlib.sha256(patch).hexdigest() != PATCH_SHA256:
        raise RuntimeError('Patch integrity validation failed')
    patch_path = OUT / 'backup-v14.patch'
    patch_path.write_bytes(patch)
    git('fetch', '--no-tags', 'origin', *EXPECTED.values())
    git('config', 'user.name', 'TheKillerMax')
    git('config', 'user.email', '70108066+TheKillerMax@users.noreply.github.com')
    rows = []
    with tempfile.TemporaryDirectory(prefix='waex-v14-', dir=os.environ.get('RUNNER_TEMP')) as directory:
        backup = Path(directory) / 'backup'
        preview = Path(directory) / 'preview'
        git('worktree', 'add', '--detach', str(backup), EXPECTED[BACKUP])
        git('worktree', 'add', '--detach', str(preview), EXPECTED[PREVIEW])
        git('apply', '--index', str(patch_path), cwd=backup)
        changed = set(git('diff', '--cached', '--name-only', cwd=backup).splitlines())
        if changed != set(BLOBS):
            raise RuntimeError('Patch exceeds four reviewed source/test paths')
        git('diff', '--cached', '--check', cwd=backup)
        verify_files(backup)
        for test in ['test_backup_alias_policy.py', 'test_settings_backup_binary_roundtrip.py',
                     'test_settings_backup_json.py', 'test_feature_preference_schema_coverage.py',
                     'test_catalog_schema_alias_contract.py']:
            if not (backup / 'qa' / test).is_file():
                raise RuntimeError('Required standalone regression missing: ' + test)
            run_test(backup, 'standalone-' + test[:-3], [sys.executable, 'qa/' + test], rows)
        run_test(backup, 'standalone-production-syntax', [sys.executable, str(preview / 'qa/check_syntax.py'),
                 '--root', str(backup / 'app/src/main/java')], rows)
        git('commit', '-m', 'fix(backup): validate JSON values and reject malformed backup containers', cwd=backup)
        backup_sha = git('rev-parse', 'HEAD', cwd=backup)
        git('merge', '--no-ff', '-m', 'merge: integrate reviewed backup parser and persistence regressions', backup_sha, cwd=preview)
        git('merge', '--no-ff', '-m', 'merge: exercise pinned Android JSON regression in source CI', EXPECTED[CI], cwd=preview)
        verify_files(preview)
        if git('hash-object', WORKFLOW, cwd=preview) != WORKFLOW_BLOB:
            raise RuntimeError('CI workflow mismatch')
        changed_preview = set(git('diff', '--name-only', EXPECTED[PREVIEW], 'HEAD', cwd=preview).splitlines())
        if changed_preview != set(BLOBS) | {WORKFLOW}:
            raise RuntimeError('Integration includes unreviewed changes')
        tests = sorted((preview / 'qa').glob('test_*.py'))
        tests = [test for test in tests if test.name != 'test_host_class_relocations.py']
        if len(tests) != 38:
            raise RuntimeError('Unexpected source suite inventory: ' + str(len(tests)))
        run_test(preview, 'integration-production-syntax', [sys.executable, 'qa/check_syntax.py',
                 '--root', 'app/src/main/java'], rows)
        for test in tests:
            run_test(preview, 'integration-' + test.stem, [sys.executable, str(test)], rows)
        git('diff', '--check', EXPECTED[PREVIEW], 'HEAD', cwd=preview)
        preview_sha = git('rev-parse', 'HEAD', cwd=preview)
        for old, new in [(EXPECTED[BACKUP], backup_sha), (EXPECTED[PREVIEW], preview_sha)]:
            git('merge-base', '--is-ancestor', old, new)
        data = {'upstream_main': MAIN, 'expected_heads': EXPECTED, 'backup_head': backup_sha,
                'preview_head': preview_sha, 'backup_tree': git('rev-parse', backup_sha + '^{tree}'),
                'preview_tree': git('rev-parse', preview_sha + '^{tree}'), 'source_blobs': BLOBS,
                'patch_sha256': PATCH_SHA256, 'tests_passed': len(rows), 'published': False,
                'limits': 'JVM with unmodified Android 14 JSON and SharedPreferences doubles; no APK build or LSPosed device execution.'}
        (OUT / 'publication.json').write_text(json.dumps(data, indent=2))
        (OUT / 'integration.diff').write_text(git('diff', EXPECTED[PREVIEW], preview_sha))
    print(json.dumps(data, indent=2))


def publish():
    check_heads()
    data = json.loads((OUT / 'publication.json').read_text())
    rows = json.loads((OUT / 'tests.json').read_text())
    if len(rows) != 45 or any(row['exit_code'] for row in rows) or data['tests_passed'] != 45:
        raise RuntimeError('All 45 validation invocations must succeed before publication')
    for name, sha in BLOBS.items():
        if git('rev-parse', data['backup_head'] + ':' + name) != sha or git('rev-parse', data['preview_head'] + ':' + name) != sha:
            raise RuntimeError('Publication object differs from tested source')
    token = os.environ.get('WAEX_PUBLICATION_TOKEN')
    if not token:
        raise RuntimeError('Publication credential unavailable')
    env = dict(os.environ)
    env['GIT_CONFIG_COUNT'] = '1'
    env['GIT_CONFIG_KEY_0'] = 'http.https://github.com/.extraheader'
    env['GIT_CONFIG_VALUE_0'] = 'AUTHORIZATION: basic ' + base64.b64encode(('x-access-token:' + token).encode()).decode()
    command = ['git', 'push', '--atomic', 'origin', data['backup_head'] + ':refs/heads/' + BACKUP,
               data['preview_head'] + ':refs/heads/' + PREVIEW]
    result = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    (OUT / 'publication.log').write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError('Atomic non-forced publication failed; inspect actual refs before retrying')
    for branch, expected in [(BACKUP, data['backup_head']), (PREVIEW, data['preview_head'])]:
        actual = git('ls-remote', 'origin', 'refs/heads/' + branch).split()
        if not actual or actual[0] != expected:
            raise RuntimeError('Post-publication verification mismatch')
    data['published'] = True
    (OUT / 'publication.json').write_text(json.dumps(data, indent=2))
    print(json.dumps(data, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['validate', 'publish'])
    args = parser.parse_args()
    (validate if args.mode == 'validate' else publish)()
