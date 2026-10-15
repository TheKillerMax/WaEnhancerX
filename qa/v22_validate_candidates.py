#!/usr/bin/env python3
"""Staging-only public source validation; never move functional branches."""
import base64, gzip, hashlib, json, os, pathlib, shutil, subprocess, sys, time
ROOT=pathlib.Path.cwd(); OUT=pathlib.Path(os.environ['RUNNER_TEMP'])/'v22-evidence'; OUT.mkdir(exist_ok=True)
def git(*args, data=None):
    return subprocess.check_output(['git',*args],input=data).decode().strip()
def run(name,cmd,timeout=300):
    p=OUT/(name+'.log'); start=time.monotonic()
    with p.open('w') as log:
        result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
    status={'name':name,'exit':result.returncode,'seconds':time.monotonic()-start}
    (OUT/(name+'.result.json')).write_text(json.dumps(status))
    print(status,flush=True)
    if result.returncode:
        print(p.read_text()[-18000:],flush=True)
        raise RuntimeError(name+' failed')

def main():
    staging=os.environ['GITHUB_SHA']; staging_tree=git('rev-parse',staging+'^{tree}')
    parts=[]
    for name in ['1','2','3a','3b','4a','4b','5a','5b']:
        p=(ROOT/('qa/v22-candidate-payload.part'+name)).read_text()
        # Two insertion errors were detected by the transfer-only checksum run.
        # Restore the exact local input; the whole payload and every resulting blob are pinned below.
        if name=='5b' and len(p)==3834:
            assert p[2010]=='r' and p[2031]=='F'
            p=p[:2031]+p[2032:]
            p=p[:2010]+p[2011:]
        parts.append(p)
    packed=base64.b64decode(''.join(parts),validate=True)
    assert hashlib.sha256(packed).hexdigest()=='4cf2ec16a6fdb4cbf0f8d64345ac87ccf1de128f492c36333cc6f001adf991a2'
    spec=json.loads(gzip.decompress(packed)); (OUT/'verified-recipes.json').write_text(json.dumps(spec))
    git('config','user.name','TheKillerMax');git('config','user.email','70108066+TheKillerMax@users.noreply.github.com')
    for sha,recipe in spec['recipes'].items():
        if 'text' in recipe: text=recipe['text']
        else:
            original=subprocess.check_output(['git','cat-file','blob',recipe['base']]).decode()
            pieces=original.splitlines(keepends=True) if recipe.get('lines') else original
            text=''.join(''.join(pieces[x[0]:x[1]]) if isinstance(x,list) else x for x in recipe['parts'])
        actual=git('hash-object','-w','--stdin',data=text.encode())
        assert actual==sha,(sha,actual)
    messages={
      'targets':'fix(targets): select exact declared WhatsApp packages in every entry path',
      'runtime':'fix(diagnostics): distinguish inaccessible compatibility rules and stale runtime evidence',
      'qa':'test(qa): require target and runtime regressions when their contracts are present',
      'pr35':'merge: reconcile receipt isolation and checked manual controls with localized main',
      'pr41':'merge: preserve measured presence replay and invalidation on current main'}
    candidates={}
    git('checkout','--detach',spec['base'])
    for name,entry in spec['inputs'].items():
        git('read-tree',spec['base'])
        for path,blob in entry['entries'].items():
            assert not path.startswith('/') and '..' not in pathlib.PurePosixPath(path).parts
            git('update-index','--add','--cacheinfo',blob['mode'],blob['sha'],path)
        tree=git('write-tree');assert tree==entry['tree'],(name,tree,entry['tree'])
        parents=[v for p in entry['parents'] for v in ['-p',p]]
        commit=git('commit-tree',tree,*parents,'-m',messages[name])
        candidates[name]={'sha':commit,'tree':tree,'parents':entry['parents'],'branch':spec['names'][name]}
    (OUT/'candidates.json').write_text(json.dumps(candidates,indent=2))
    tests={
     'targets':['test_declared_targets.py'],
     'runtime':['test_runtime_diagnostics.py','test_startup_reconciliation.py','test_provider_derived_keys.py'],
     'pr35':['test_blue_receipt_recipient_isolation.py','test_manual_blue_tick_ui.py','test_manual_seen_tick_persistence.py','test_receipt_job_execution_contract.py','test_played_receipt_dispatch_contract.py'],
     'pr41':['test_presence_event_contract.py','test_presence_state_replay.py','test_presence_invalidation.py','test_presence_state_invalidation.py','test_notification_memory.py']}
    for name,scripts in tests.items():
        git('checkout','--detach','--force',candidates[name]['sha'])
        for script in scripts:run(name+'-'+script,['python3','qa/'+script])
    git('checkout','--detach','--force',spec['base'])
    icons='352943f608bca4d69c4009e365eb6a1bb9b645f0'
    for name in ['qa','icons','targets','runtime','pr35','pr41']:
        head=icons if name=='icons' else candidates[name]['sha']
        run('merge-'+name,['git','merge','--no-ff','--no-edit',head])
    tree=git('write-tree');assert tree==spec['integrated_tree'],(tree,spec['integrated_tree'])
    old='684fa83e4f82df4bf2e3b0d705f04ed96566a64f'
    parents=[old,spec['base'],icons]+[candidates[n]['sha'] for n in ['qa','targets','runtime','pr35','pr41']]
    head=git('commit-tree',tree,*[x for p in parents for x in ['-p',p]],'-m','merge: reconcile current main, runtime diagnostics, receipts, presence and resource QA')
    candidates['integrated']={'sha':head,'tree':tree,'parents':parents,'branch':spec['names']['integrated']}
    (OUT/'candidates.json').write_text(json.dumps(candidates,indent=2))
    git('checkout','--detach','--force',head)
    run('integrated-syntax',['python3','qa/check_syntax.py'])
    scripts=sorted(p for p in pathlib.Path('qa').glob('test_*.py') if p.name!='test_host_class_relocations.py')
    assert len(scripts)==51,len(scripts)
    for script in scripts:run('integrated-'+script.name,['python3',str(script)])
    run('android-presence-rows',['python3','qa/android_presence_row_test.py','--out',str(OUT.parent/'v22-rows')],900)
    run('runtime-real-framework',['python3','qa/verify_runtime_framework.py','--out',str(OUT.parent/'v22-runtime-framework')],900)
    (OUT/'verification.json').write_text(json.dumps({'source_scripts':len(scripts),'standalone_scripts':sum(map(len,tests.values())),'integrated_tree':tree,'all_passed':True},indent=2))
    # Preserve tested commit objects through a holding commit on this staging branch only.
    branch='test/runtime-reconciliation-v22-2026-10-15'
    remote=git('ls-remote','origin','refs/heads/'+branch).split()[0]
    assert remote==staging,(remote,staging)
    hold=git('commit-tree',staging_tree,'-p',staging,'-p',head,'-m','test(qa): preserve validated candidate objects without moving functional refs')
    run('preserve-tested-objects',['git','push','origin',hold+':refs/heads/'+branch])
    (OUT/'holding-commit.txt').write_text(hold+'\n')

try:
    main()
finally:
    # No downloaded APKs, dependency jars, classes or private configuration in evidence.
    for folder in ['v22-rows','v22-runtime-framework']:
        source=OUT.parent/folder
        if not source.exists():continue
        dest=OUT/folder;dest.mkdir(exist_ok=True)
        for p in source.rglob('*'):
            if p.is_file() and 'deps' not in p.parts and 'apks' not in p.parts and p.suffix in {'.log','.json','.xml','.txt'}:
                if folder=='v22-runtime-framework' and 'evidence' not in p.parts:continue
                target=dest/p.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
