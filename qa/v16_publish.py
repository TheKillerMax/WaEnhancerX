"""Validate pinned topic trees without credentials; then atomically publish four fork refs."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from v16_contract_transform import apply

BASE = '4bbe5cb02ce2fe924136a9579d2582c1a4818643'
PREVIEW = '3e905763cff99331d5cce5857e5889716d4947ad'
QA = '6440a940de68319cf72b0c5ee7c0aeccac482928'
FORK = 'https://github.com/TheKillerMax/WaEnhancerX.git'
UPSTREAM = 'https://github.com/WaEnhancerX/WaEnhancerX.git'
BRANCHES = {
    'receipts': 'fix/receipt-job-execution-contract-2026-10-14',
    'presence': 'fix/presence-message-event-contract-2026-10-14',
    'qa': 'test/qa-java-kotlin-syntax-guard-2026-10',
    'integration': 'integration/preview-current-main-2026-10-14',
}
TREES = {
    'receipts': '42c03f9c36222bc83c6d2a909e700716501ce58b',
    'presence': '0c2caf8658104266173ec6b1beaaa21646c416bf',
    'integration-receipts': 'a58a7359e7356dab5efa884cef2da3f81b9a2beb',
    'integration-presence': '24130fe20f2331fb02560b840cf9a340ffecbd27',
    'integration': 'c1b6dca585c9061f2d14688552b4d78ca895c4d2',
}
F = 'app/src/main/java/com/waenhancer/xposed/features/'
PATHS = {
    'receipts': [F+'privacy/HideReceiptsHook.java', F+'privacy/ReceiptJobExecutionPolicy.java', 'qa/test_receipt_job_execution_contract.py'],
    'presence': [F+'automation/PresenceToastsHook.java', F+'automation/PresenceEventPolicy.java', 'qa/test_presence_event_contract.py'],
}
WORKFLOW = '.github/workflows/source-qa.yml'
DOC = 'qa/V16_CONTRACT_ACCEPTANCE.md'
SOURCE = Path(__file__).resolve().parents[1]
TMP = Path(os.environ['RUNNER_TEMP']).resolve()
REPO = TMP/'waex-v16-reviewed'
OUT = TMP/'waex-v16-publication'
results = []


def run(command, cwd=REPO, check=True, env=None):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, env=env, timeout=300)
    if check and result.returncode:
        raise RuntimeError('Command failed: ' + str(command[:3]) + '\n' + result.stdout + result.stderr)
    return result


def git(*args):
    return run(['git', *args]).stdout.strip()


def remote(url, ref):
    value = git('ls-remote', url, ref)
    return value.split()[0] if value else None


def check_refs():
    assert remote(UPSTREAM, 'refs/heads/main') == BASE, 'Upstream moved; review again'
    for label, branch in BRANCHES.items():
        expected = {'qa': QA, 'integration': PREVIEW}.get(label)
        assert remote(FORK, 'refs/heads/'+branch) == expected, 'Branch changed or already exists: '+branch
    for number, sha in {
        17: '48893573cc009bd6398fe0d7d3ce126e450d62b9',
        35: '3f7136929a4e5ec8f7d12c38a477e3c3bd38e852',
        39: 'dbc1312e5b827acdaaedf58c3961c73400225592',
    }.items():
        assert remote(UPSTREAM, f'refs/pull/{number}/head') == sha, 'Overlapping PR moved'


def checkout(ref):
    assert REPO.parent == TMP and REPO.name == 'waex-v16-reviewed'
    git('read-tree', '--reset', '-u', ref)


def changed(parent, allowed):
    actual = set(git('diff', '--cached', '--name-only', parent).splitlines())
    assert actual == set(allowed), (actual, allowed)
    git('diff', '--cached', '--check', parent)


def make_commit(tree, message, parents):
    args = ['-c', 'commit.gpgsign=false', 'commit-tree', tree, '-m', message]
    for parent in parents:
        args += ['-p', parent]
    return git(*args)


def stage_topic(topic, tree_label, parent):
    apply(REPO, topic)
    for name in PATHS[topic][1:]:
        (REPO/name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE/name, REPO/name)
    git('add', *PATHS[topic])
    changed(parent, PATHS[topic])
    actual = git('write-tree')
    assert actual == TREES[tree_label], f'{tree_label}: expected {TREES[tree_label]}, got {actual}'
    return actual


def test(label, command):
    result = run(command, check=False)
    (OUT/(label+'.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
    results.append({'label': label, 'command': command, 'exit': result.returncode})
    (OUT/'tests.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    assert result.returncode == 0, 'Test failed: '+label
    print('PASS', label, flush=True)


def prepare():
    assert not os.environ.get('WAEX_PUBLISH_TOKEN'), 'Do not expose publication credentials to tests'
    assert not REPO.exists(), 'Refuse to reuse a previous checkout'
    OUT.mkdir(exist_ok=True)
    run(['git', 'clone', '--no-checkout', FORK, str(REPO)], cwd=TMP)
    git('config', 'user.name', 'TheKillerMax')
    git('config', 'user.email', '70108066+TheKillerMax@users.noreply.github.com')
    git('config', 'core.hooksPath', '/dev/null')
    git('fetch', '--no-tags', UPSTREAM, BASE)
    git('fetch', '--no-tags', 'origin', PREVIEW, QA)
    check_refs()
    heads = {}
    parser = str(SOURCE/'qa/check_syntax.py')
    for topic in ('receipts', 'presence'):
        checkout(BASE)
        tree = stage_topic(topic, topic, BASE)
        heads[topic] = make_commit(tree, 'fix('+topic+'): enforce the reviewed host execution contract', [BASE])
        test(topic+'-standalone', ['python3', PATHS[topic][-1]])
        test(topic+'-syntax', ['python3', parser, '--root', 'app/src/main/java'])
        git('diff', '--exit-code')
        (OUT/(topic+'-main.patch')).write_text(git('diff', BASE, heads[topic])+'\n', encoding='utf-8')
    checkout(QA)
    original = (REPO/WORKFLOW).read_text(encoding='utf-8')
    assert original == (SOURCE/WORKFLOW).read_text(encoding='utf-8'), 'QA workflow differs from reviewed integration'
    needle = '            qa/test_manual_blue_tick_ui.py \\\n'
    assert original.count(needle) == 1
    workflow = original.replace(needle, needle+'            qa/test_receipt_job_execution_contract.py \\\n            qa/test_presence_event_contract.py \\\n')
    (REPO/WORKFLOW).write_text(workflow, encoding='utf-8')
    git('add', WORKFLOW)
    changed(QA, [WORKFLOW])
    heads['qa'] = make_commit(git('write-tree'), 'test(qa): include receipt execution and presence event contracts', [QA])
    left = PREVIEW
    for topic in ('receipts', 'presence'):
        checkout(left)
        tree = stage_topic(topic, 'integration-'+topic, left)
        left = make_commit(tree, 'merge: reconcile '+topic+' contract with existing fork integration', [left, heads[topic]])
    checkout(left)
    (REPO/WORKFLOW).write_text(workflow, encoding='utf-8')
    shutil.copyfile(SOURCE/DOC, REPO/DOC)
    git('add', WORKFLOW, DOC)
    changed(left, [WORKFLOW, DOC])
    assert git('write-tree') == TREES['integration'], 'Final integrated tree mismatch'
    heads['integration'] = make_commit(TREES['integration'], 'merge: integrate contract regression CI and acceptance notes', [left, heads['qa']])
    scripts = [p for p in sorted((REPO/'qa').glob('test_*.py')) if p.name != 'test_host_class_relocations.py']
    assert len(scripts) == 40, 'Unexpected integrated test inventory'
    test('integrated-production-syntax', ['python3', 'qa/check_syntax.py', '--root', 'app/src/main/java'])
    for path in scripts:
        test('integrated-'+path.stem, ['python3', str(path.relative_to(REPO))])
    git('diff', '--exit-code')
    assert len(results) == 45 and all(item['exit'] == 0 for item in results)
    assert git('write-tree') == TREES['integration']
    state = {'base': BASE, 'previous_preview': PREVIEW, 'heads': heads, 'trees': TREES, 'branches': BRANCHES,
             'test_processes': len(results), 'ready': True, 'published': False,
             'scope': 'Public-source JVM/Java/Kotlin verification only; no APK/Android/native DexKit/LSPosed execution'}
    (OUT/'publication.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
    (OUT/'integration.patch').write_text(git('diff', PREVIEW, heads['integration'])+'\n', encoding='utf-8')
    print(json.dumps(state, indent=2), flush=True)


def publish():
    state = json.loads((OUT/'publication.json').read_text(encoding='utf-8'))
    assert state['ready'] and not state['published'] and state['branches'] == BRANCHES
    assert state['trees'] == TREES and set(state['heads']) == set(BRANCHES)
    check_refs()
    for label, sha in state['heads'].items():
        assert len(sha) == 40 and all(c in '0123456789abcdef' for c in sha)
        parent = QA if label == 'qa' else PREVIEW if label == 'integration' else BASE
        git('merge-base', '--is-ancestor', parent, sha)
        if label in TREES:
            assert git('rev-parse', sha+'^{tree}') == TREES[label]
    token = os.environ['WAEX_PUBLISH_TOKEN']
    auth = base64.b64encode(('x-access-token:'+token).encode()).decode()
    command = ['git', '-c', 'http.https://github.com/.extraheader=AUTHORIZATION: basic '+auth,
               'push', '--atomic', FORK]
    command += [sha+':refs/heads/'+BRANCHES[label] for label, sha in state['heads'].items()]
    result = run(command, check=False)
    # Never retry an ambiguous write. Inspect every ref before reporting the state.
    observed = {label: remote(FORK, 'refs/heads/'+branch) for label, branch in BRANCHES.items()}
    state['observed_heads'] = observed
    state['published'] = observed == state['heads']
    (OUT/'publication.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
    assert state['published'], 'Publication failed or ambiguous; inspect refs, do not retry blindly'
    print('Verified four fork refs after atomic non-forced publication; upstream main untouched.', flush=True)


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in ('prepare', 'publish'):
        raise SystemExit('Usage: v16_publish.py prepare|publish')
    {'prepare': prepare, 'publish': publish}[sys.argv[1]]()
