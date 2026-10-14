"""Build pinned, already-reviewed trees, validate them, then fast-forward fork refs.

Run prepare without credentials. Publish is a separate last step; it accepts only
four hard-coded fork refs and rejects changed source heads or mismatching trees.
"""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys

BASE = '4bbe5cb02ce2fe924136a9579d2582c1a4818643'
HEADS = {
    12: '81823e09b931762a792ea9323e9f3a301935d545',
    13: '1ee18e57915577302d0cb6c76ae0684883ae399b',
    15: '4c1cfe8ef89ada5ff6f47226d51c3b165283e162',
    17: '48893573cc009bd6398fe0d7d3ce126e450d62b9',
    23: '814305c9c0332f410d1bf08c7373c80d9db6935e',
    25: '32aa6b25d7875ff9444f5d3d40244f9d0b2753d6',
    26: 'bb125d4a85d0aa4a6d398632fa8746eb69e8776d',
    27: '3d10f12c958cc01c9bbf055860e33cb2ebfb684a',
    32: '4cbfb68227eef4ecdc0001911cb8f2f2722dda7f',
    35: 'b9a191839124569dc7135fc4f5c1873a4dcd6b4f',
    36: 'ec5e34cd3c50aa220b7de862f0d072a2a4c3bf6b',
}
TREES = {
    'pr15': 'ea74aa1ad36037a770b638bc87a6c6dda331572a',
    'pr35': 'f8380302787759d4d43f5bffd8bff3c0e71a1c3e',
    'typed': '441b5140cdc54be6418304deac4ea81fb430d67d',
    'integration': '0e32a7b38d7251728a547157a596000ba16afb26',
}
BRANCHES = {
    'pr15': 'fix/startup-feature-isolation-2026-10',
    'pr35': 'fix/blue-reply-exact-recipient-bounded-state-2026-10',
    'typed': 'fix/styles-typed-save-failure-2026-10-14',
    'integration': 'integration/preview-current-main-2026-10-14',
}
FORK = 'https://github.com/TheKillerMax/WaEnhancerX.git'
UPSTREAM = 'https://github.com/WaEnhancerX/WaEnhancerX.git'
TMP = Path(os.environ['RUNNER_TEMP']).resolve()
REPO = TMP / 'waex-validated-publication-repo'
OUT = TMP / 'waex-publication-evidence'
HELPERS = Path(__file__).resolve().parent
BLUE = 'app/src/main/java/com/waenhancer/xposed/features/privacy/BlueOnReplyHook.java'
STYLE = 'app/src/main/java/com/waenhancer/ui/screens/settings/StylesSettingsScreen.kt'
MAIN = 'app/src/main/java/com/waenhancer/xposed/MainHook.java'
CONFLICT = r'<<<<<<< [^\n]+\n(.*?)=======\n(.*?)>>>>>>> [^\n]+\n'


def run(args, cwd=REPO, ok=(0,), env=None, timeout=240):
    result = subprocess.run(args, cwd=cwd, capture_output=True, env=env, timeout=timeout)
    if result.returncode not in ok:
        raise RuntimeError(f'Command {args[:3]} exited {result.returncode}: '
                           + result.stderr.decode('utf-8', 'replace'))
    return result


def git(*args, **kwargs):
    return run(['git', *args], **kwargs)


def text(result):
    return result.stdout.decode('utf-8').strip()


def save(name, value):
    OUT.mkdir(exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2), encoding='utf-8')


def check_remote_initial():
    assert text(git('ls-remote', UPSTREAM, 'refs/heads/main')).split()[0] == BASE, 'Upstream moved'
    lines = text(git('ls-remote', UPSTREAM, *[f'refs/pull/{n}/head' for n in HEADS])).splitlines()
    observed = {int(line.split()[1].split('/')[2]): line.split()[0] for line in lines}
    assert observed == HEADS, 'At least one PR moved; re-review required'
    old = {BRANCHES['pr15']: HEADS[15], BRANCHES['pr35']: HEADS[35]}
    for label, branch in BRANCHES.items():
        entry = text(git('ls-remote', FORK, 'refs/heads/' + branch))
        if branch in old:
            assert entry.split()[0] == old[branch], 'Existing branch moved'
        else:
            assert not entry, 'New branch already exists; inspect rather than overwrite'


def checkout(ref):
    # REPO is a fresh RUNNER_TEMP clone, never a user checkout.
    assert REPO.parent == TMP and REPO.name == 'waex-validated-publication-repo'
    git('read-tree', '--reset', '-u', ref)


def merge_tree(left, right):
    result = git('merge-tree', '--write-tree', '--messages', left, right, ok=(0, 1))
    output = result.stdout.decode('utf-8')
    tree = output.splitlines()[0]
    assert re.fullmatch('[0-9a-f]{40}', tree)
    return tree, result.returncode, output


def commit(tree, parents, message):
    args = ['commit-tree', tree]
    for parent in parents:
        args += ['-p', parent]
    args += ['-m', message]
    sha = text(git(*args))
    assert re.fullmatch('[0-9a-f]{40}', sha)
    return sha


def checked_tree(label):
    git('add', '-u')
    tree = text(git('write-tree'))
    assert tree == TREES[label], f'{label}: expected {TREES[label]}, got {tree}'
    git('diff', '--cached', '--check', BASE)
    return tree


def reconcile(number):
    tree, status, output = merge_tree(BASE, HEADS[number])
    assert status == 1, 'Conflict contract changed'
    (OUT / f'original-merge-{number}.txt').write_text(output)
    checkout(tree)
    if number == 15:
        p = REPO / MAIN
        source = p.read_text()
        assert len(list(re.finditer(CONFLICT, source, re.S))) == 1
        replacement = '''                                            try {
                                                showInjectionToastOnFirstVisibleActivity();
                                            } catch (Throwable t) {
                                                XposedBridge.log("[WAEX] Injection toast unavailable: "
                                                        + t.getClass().getSimpleName());
                                            }
'''
        p.write_text(re.sub(CONFLICT, lambda _: replacement, source, flags=re.S))
        p = REPO / 'qa/test_startup_reconciliation.py'
        source = p.read_text()
        source = source.replace("'Injecting WAEX hooks into WhatsApp...' in main and 'Injection toast unavailable:' in main", "'showInjectionToastOnFirstVisibleActivity();' in main and 'Injection toast unavailable:' in main")
        source = source.replace("('Injecting WAEX hooks into WhatsApp...', 'Injection toast unavailable:'),", "('showInjectionToastOnFirstVisibleActivity();', 'Injection toast unavailable:'),")
        source = source.replace(" 'registry installed':", """ 'visible-activity toast retained': 'public void onActivityResumed(android.app.Activity activity)' in main and '"WAEX hooks injected"' in main,
 'toast listener removed': 'ActivityTracker.removeListener(this);' in main,
 'toast per-process bound': 'INJECTION_TOAST_SHOWN.compareAndSet(false, true)' in main,
 'typed styles registry retained': all(name in registry for name in ('CustomDpiHook.class', 'ChatFilterDisplayHook.class', 'HideHomeTabsHook.class', 'CssThemeHook.class')),
 'registry installed':""")
        p.write_text(source)
    else:
        p = REPO / BLUE
        source = p.read_text()
        assert len(list(re.finditer(CONFLICT, source, re.S))) == 1
        p.write_text(re.sub(CONFLICT, lambda m: m[2], source, flags=re.S))
        p = REPO / STYLE
        source = p.read_text()
        assert len(list(re.finditer(CONFLICT, source, re.S))) == 3
        def resolve(match):
            a, b = match[1], match[2]
            if 'put(key, false)' in a:
                return a + '                } else ' + b.lstrip()
            if 'val canonicalKey' in a and 'val updatePreference' not in a:
                return a
            assert 'val updatePreference' in a
            start = '''    val updatePreference: (String, Boolean) -> Unit = update@{ key, value ->
        if (StyleNonBooleanPreferencePolicy.requiresDedicatedEditor(key)) return@update
'''
            assert a.startswith(start)
            special = '''        if (key == "seen_tick_customization") {
            val currentPlacement = preferenceManager.getString("seentick", "0")
            preferenceManager.putString("seentick",
                ManualSeenTickPreferencePolicy.valueAfterExplicitToggle(value, currentPlacement))
            settingsState[key] = ManualSeenTickPreferencePolicy.isEnabled(
                preferenceManager.getString("seentick", "0"))
            return@update
        }
'''
            return start + special + a[len(start):]
        p.write_text(re.sub(CONFLICT, resolve, source, flags=re.S))
    label = 'pr' + str(number)
    tree = checked_tree(label)
    return commit(tree, [HEADS[number], BASE],
                  f'merge(main): reconcile PR #{number} with current lifecycle and typed styles')


def test(label, args):
    # Tokens are not exposed to any repository test process.
    env = {k: v for k, v in os.environ.items() if k not in {'GITHUB_TOKEN', 'GH_TOKEN', 'PUBLISH_TOKEN'}}
    result = run(args, ok=tuple(range(256)), env=env, timeout=420)
    log = result.stdout + b'\nSTDERR:\n' + result.stderr
    (OUT / (label + '.log')).write_bytes(log)
    print(f'{label}: exit {result.returncode}', flush=True)
    assert result.returncode == 0, log.decode('utf-8', 'replace')[-8000:]
    return {'name': label, 'command': args, 'exit_code': result.returncode}


def prepare():
    assert not os.environ.get('PUBLISH_TOKEN')
    assert not REPO.exists(), 'Do not reuse an existing checkout'
    OUT.mkdir(exist_ok=True)
    run(['git', 'clone', '--no-checkout', FORK, str(REPO)], cwd=TMP)
    git('config', 'user.name', 'github-actions[bot]')
    git('config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')
    check_remote_initial()
    git('fetch', '--no-tags', UPSTREAM, BASE, *HEADS.values())
    results = []
    commits = {label: reconcile(n) for label, n in [('pr15', 15), ('pr35', 35)]}
    receipt_source = git('show', commits['pr35'] + ':' + BLUE).stdout
    checkout(BASE)
    run([sys.executable, str(HELPERS / 'apply_typed_fix.py'), str(REPO)])
    commits['typed'] = commit(checked_tree('typed'), [BASE],
                              'fix(styles): report typed preference save failures without closing editors')
    for script in sorted((REPO / 'qa').glob('test_*.py')):
        if script.name != 'test_host_class_relocations.py':
            results.append(test('typed-' + script.stem, [sys.executable, str(script)]))
    checkout(commits['pr15'])
    results.append(test('pr15-startup', [sys.executable, 'qa/test_startup_reconciliation.py']))
    checkout(commits['pr35'])
    for script in ['test_blue_receipt_recipient_isolation.py', 'test_manual_blue_tick_ui.py']:
        results.append(test('pr35-' + script[:-3], [sys.executable, 'qa/' + script]))
    current = BASE
    merges = []
    for item in [26, 27, 12, 13, 32, 15, 17, 25, 35, 36, 23, 'typed']:
        right = commits[item] if isinstance(item, str) else commits.get('pr' + str(item), HEADS[item])
        tree, status, output = merge_tree(current, right)
        checkout(tree)
        if status:
            assert item == 35, 'Unexpected merge conflict; stop for review'
            conflict_paths = []
            for p in (REPO / 'app/src/main/java').rglob('*'):
                if p.suffix in {'.kt', '.java'} and re.search(r'^<<<<<<< ', p.read_text(), re.M):
                    conflict_paths.append(str(p.relative_to(REPO)))
            assert conflict_paths == [BLUE], conflict_paths
            # The reconciled file exactly matches the locally tested combined file.
            (REPO / BLUE).write_bytes(receipt_source)
            git('add', '-u')
            tree = text(git('write-tree'))
        current = commit(tree, [current, right], f'merge: validate reviewed {item} on current main (not a release)')
        merges.append({'item': item, 'commit': current, 'tree': tree, 'conflict_resolved': bool(status)})
    assert text(git('rev-parse', current + '^{tree}')) == TREES['integration'], 'Combined tree differs from tested source'
    commits['integration'] = current
    checkout(current)
    for p in (REPO / 'app/src/main/java').rglob('*'):
        if p.suffix in {'.kt', '.java'}:
            assert not re.search(r'^(<<<<<<<|=======|>>>>>>>)', p.read_text(), re.M), str(p)
    whitespace = git('diff', '--cached', '--check', BASE, ok=(0, 2))
    (OUT / 'inherited-whitespace.log').write_bytes(whitespace.stdout + whitespace.stderr)
    if whitespace.returncode:
        assert whitespace.stdout.decode().strip() == 'qa/test_private_hook_logs.py:200: new blank line at EOF.'
        print('Inherited PR #25 formatting warning: extra EOF blank line; no new fix changes that file.')
    results.append(test('integration-syntax', [sys.executable, 'qa/check_syntax.py', '--json']))
    scripts = sorted((REPO / 'qa').glob('test_*.py'))
    scripts = [p for p in scripts if p.name != 'test_host_class_relocations.py']
    assert len(scripts) == 37, 'Review the changed test inventory'
    for script in scripts:
        results.append(test('integration-' + script.stem, [sys.executable, str(script)]))
    save('validation.json', {'base': BASE, 'heads_before': HEADS, 'branches': BRANCHES,
                              'trees': TREES, 'commits': commits, 'merges': merges,
                              'tests': results, 'validated': True,
                              'scope': 'Source/JVM only; no Android build, APK installation or LSPosed test.'})
    for label, sha in commits.items():
        (OUT / (label + '.patch')).write_bytes(git('diff', '--binary', BASE, sha).stdout)
    print(json.dumps({'validated_commits': commits, 'tests': len(results)}, indent=2))


def publish():
    data = json.loads((OUT / 'validation.json').read_text())
    assert data['validated'] and data['base'] == BASE and data['trees'] == TREES
    assert data['branches'] == BRANCHES and all(x['exit_code'] == 0 for x in data['tests'])
    check_remote_initial()
    commits = data['commits']
    assert set(commits) == set(BRANCHES)
    for label, sha in commits.items():
        assert re.fullmatch('[0-9a-f]{40}', sha)
        assert text(git('rev-parse', sha + '^{tree}')) == TREES[label]
    for label, num in [('pr15', 15), ('pr35', 35)]:
        git('merge-base', '--is-ancestor', HEADS[num], commits[label])
    token = os.environ['PUBLISH_TOKEN']
    auth = base64.b64encode(('x-access-token:' + token).encode()).decode()
    env = os.environ.copy()
    env['GIT_CONFIG_COUNT'] = '1'
    env['GIT_CONFIG_KEY_0'] = 'http.https://github.com/.extraheader'
    env['GIT_CONFIG_VALUE_0'] = 'AUTHORIZATION: basic ' + auth
    # Atomic, non-forced push: no existing history is rewritten and no main ref is touched.
    result = git('push', '--atomic', FORK,
                 *[commits[label] + ':refs/heads/' + branch for label, branch in BRANCHES.items()],
                 env=env, ok=tuple(range(256)))
    observed = {}
    for label, branch in BRANCHES.items():
        value = text(git('ls-remote', FORK, 'refs/heads/' + branch))
        observed[label] = value.split()[0] if value else None
    save('publication.json', {'exit_code': result.returncode, 'expected': commits, 'observed': observed,
                              'published': observed == commits})
    assert result.returncode == 0 and observed == commits, 'Publication rejected or ambiguous; inspect refs, do not blindly retry'
    print(json.dumps({'published': observed, 'upstream_untouched': BASE}, indent=2))


if __name__ == '__main__':
    assert len(sys.argv) == 2 and sys.argv[1] in {'prepare', 'publish'}
    (prepare if sys.argv[1] == 'prepare' else publish)()
