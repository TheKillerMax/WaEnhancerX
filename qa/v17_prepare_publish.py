#!/usr/bin/env python3
"""Validate exact public-source follow-ups; preserve objects only on the staging ref.

The final PR/integration refs are NOT written here. A separate reviewed connector
operation must advance them after inspecting this run and its exact commit trees.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ['RUNNER_TEMP'])/'waex-v17-publication'
FORK='https://github.com/TheKillerMax/WaEnhancerX.git'
STAGE='test/presence-row-review-v17-2026-10-14'
PARENTS={'presence':'f3ad6f06c346b90f6d240a2bd9080d228a21a42f',
         'receipts':'58d9726ebd732b19fc154367083b6afc32c0c7f5',
         'integration':'e5ee3d87d56d7694528e3a1ed3d999e22c8a4aee'}
P='app/src/main/java/com/waenhancer/xposed/features/'
RENDERER=P+'customization/OnlinePresenceIndicatorsHook.kt'
STORE=P+'automation/PresenceStateStore.java'
HIDE=P+'privacy/HideReceiptsHook.java'
POLICY=P+'privacy/PlayedReceiptDispatchPolicy.java'
PRESENCE=[RENDERER,STORE,'qa/android_presence_row_test.py','qa/fixtures/PresenceRowRenderingTest.kt',
          'qa/mutate_presence_rows.py','qa/test_presence_state_replay.py','qa/V17_REVIEW.md']
RECEIPTS=[HIDE,POLICY,'qa/test_played_receipt_dispatch_contract.py','qa/V17_REVIEW.md']
EXPECTED={RENDERER:'f0dbd5598d9895dae8417e896637714bae97639ccb01b32d1bd4b2c6553d9192',
          STORE:'1a33a909cb1a4de0ce5bf6197521183a6a823d44236bd78723f58f4c030e41d9',
          HIDE:'fdbf3f4a8ac6d52d72f7adfcb7c7acfd45690df62e06d61d354cf841de7ddfcf',
          POLICY:'3684ef9a0e06d6b49ce28547ed323073a74e7816b46c0c4264ffad615bc8dda0'}

def git(*args,cwd=ROOT):
    return subprocess.check_output(['git',*args],cwd=cwd,text=True).strip()

def check(cmd,name,cwd=ROOT,timeout=180):
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/(name+'.log')).open('w') as f:
        result=subprocess.run(cmd,cwd=cwd,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
    print(name,'exit='+str(result.returncode),flush=True)
    if result.returncode:
        print((OUT/(name+'.log')).read_text()[-16000:]);raise RuntimeError('Failed '+name)

def copy(relative,to):
    target=to/relative;target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/relative,target)

def new_tree(work,files):
    git('add','--',*files,cwd=work)
    changed=set(git('diff','--cached','--name-only',cwd=work).splitlines())
    assert changed <= set(files), 'Out-of-scope staged path'
    git('diff','--cached','--check',cwd=work)
    return git('write-tree',cwd=work)

def commit(tree,parents,message):
    cmd=['commit-tree',tree]
    for parent in parents:cmd+=['-p',parent]
    return git(*cmd,'-m',message)

def query_api():
    """Compile the exact new Java query expression against declared DexKit 2.2.0."""
    folder=OUT/'api';folder.mkdir()
    base='https://repo.maven.apache.org/maven2/org/luckypray/dexkit/2.2.0/dexkit-2.2.0.aar'
    check(['curl','--fail','--location','--max-time','60','-o',str(folder/'dexkit.aar'),base],'api-download')
    check(['curl','--fail','--location','--max-time','30','-o',str(folder/'dexkit.sha1'),base+'.sha1'],'api-checksum-download')
    import zipfile
    aar=(folder/'dexkit.aar').read_bytes()
    assert hashlib.sha1(aar).hexdigest()==(folder/'dexkit.sha1').read_text().strip()
    with zipfile.ZipFile(folder/'dexkit.aar') as archive:(folder/'dexkit.jar').write_bytes(archive.read('classes.jar'))
    text=(ROOT/HIDE).read_text();text=text[text.index('    private Method resolvePlayedReceiptDispatch()'):]
    marker='bridge.findMethod(';start=text.index(marker)+len(marker);depth=1;quoted=False;escape=False;end=start
    for end in range(start,len(text)):
        c=text[end]
        if quoted:
            if escape:escape=False
            elif c=='\\':escape=True
            elif c=='"':quoted=False
        elif c=='"':quoted=True
        elif c=='(':depth+=1
        elif c==')':
            depth-=1
            if depth==0:break
    expression=text[start:end]
    java='import org.luckypray.dexkit.query.FindMethod;\nimport org.luckypray.dexkit.query.matchers.MethodMatcher;\nimport org.luckypray.dexkit.query.enums.StringMatchType;\npublic class PlayedQueryAPI {public static void main(String[] args){FindMethod query='+expression+';if(query==null)throw new AssertionError();System.out.println("PASS: exact production query compiles and instantiates with DexKit 2.2.0; no native scan");}}'
    (folder/'PlayedQueryAPI.java').write_text(java)
    kotlin=Path(shutil.which('kotlinc')).resolve().parent.parent/'lib'
    cp=str(folder/'dexkit.jar')+os.pathsep+str(kotlin/'*')
    check(['javac','--release','17','-cp',cp,'-d',str(folder),str(folder/'PlayedQueryAPI.java')],'api-compile')
    check(['java','-cp',str(folder)+os.pathsep+cp,'PlayedQueryAPI'],'api-run')
    (OUT/'api-sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()},indent=2))

def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    git('config','user.name','TheKillerMax');git('config','user.email','70108066+TheKillerMax@users.noreply.github.com')
    assert git('rev-parse','HEAD')==os.environ['GITHUB_SHA']
    for patch in ['qa/v17-renderer.patch','qa/v17-alias-refinement.patch','qa/v17-played-dispatch.patch']:
        git('apply','--check',patch);git('apply',patch)
    for name,digest in EXPECTED.items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    query_api()
    work={}
    for key,parent in PARENTS.items():
        work[key]=Path(os.environ['RUNNER_TEMP'])/('waex-v17-'+key)
        git('worktree','add','--detach',str(work[key]),parent)
    for path in PRESENCE:copy(path,work['presence'])
    for path in RECEIPTS:
        if path!=HIDE:copy(path,work['receipts'])
    begin='    private void hookSenderPlayed()';end='    private boolean shouldSuppressPlayedReceipt('
    old=(work['receipts']/HIDE).read_text();new=(ROOT/HIDE).read_text()
    assert old.count(begin)==new.count(begin)==old.count(end)==new.count(end)==1
    (work['receipts']/HIDE).write_text(old[:old.index(begin)]+new[new.index(begin):new.index(end)]+old[old.index(end):])
    for path in sorted(set(PRESENCE+RECEIPTS)):copy(path,work['integration'])
    checks=[]
    for key,tests in [('presence',['test_presence_event_contract','test_presence_state_replay']),
                      ('receipts',['test_receipt_job_execution_contract','test_played_receipt_dispatch_contract'])]:
        for test in tests:
            name=key+'-'+test;check(['python3','qa/'+test+'.py'],name,work[key]);checks.append(name)
        name=key+'-production-syntax'
        check(['python3',str(ROOT/'qa/check_syntax.py'),'--root',str(work[key]/'app/src/main/java')],name)
        checks.append(name)
    check(['python3','qa/check_syntax.py','--root','app/src/main/java'],'integrated-production-syntax',work['integration'])
    checks.append('integrated-production-syntax')
    tests=sorted((work['integration']/'qa').glob('test_*.py'))
    tests=[p for p in tests if p.name!='test_host_class_relocations.py'];assert len(tests)==42,len(tests)
    for test in tests:
        name='integrated-'+test.stem
        check(['python3',str(test)],name,work['integration']);checks.append(name)
    # Real Android UI run against the exact composed candidate, independent of source tests.
    check(['python3','qa/android_presence_row_test.py','--out',str(OUT/'android-final')],
          'integrated-android-rows',work['integration'],timeout=600)
    checks.append('integrated-android-rows')
    trees={key:new_tree(work[key],PRESENCE if key=='presence' else RECEIPTS if key=='receipts' else sorted(set(PRESENCE+RECEIPTS))) for key in work}
    heads={}
    heads['presence']=commit(trees['presence'],[PARENTS['presence']], 'fix(presence): replay ordered state and measure recycled row overlays')
    heads['receipts']=commit(trees['receipts'],[PARENTS['receipts']], 'fix(receipts): restrict played interception to a verified job constructor call')
    heads['integration']=commit(trees['integration'],[PARENTS['integration'],heads['presence'],heads['receipts']], 'merge: compose verified presence row and played dispatcher follow-ups')
    transport=commit(git('rev-parse','HEAD^{tree}'),[os.environ['GITHUB_SHA'],heads['integration']], 'test(qa): preserve validated V17 commit objects without advancing PR refs')
    state={'parents':PARENTS,'heads':heads,'trees':trees,'transport':transport,'staging_start':os.environ['GITHUB_SHA'],
           'production_sha256':EXPECTED,'checks_passed':checks,'ready':True,'objects_preserved':False,
           'scope':'Source/JVM and extracted Android framework rendering, not APK/ART/LSPosed or live messaging'}
    (OUT/'publication.json').write_text(json.dumps(state,indent=2));print(json.dumps(state,indent=2))

def preserve():
    state=json.loads((OUT/'publication.json').read_text());assert state['ready'] and not state['objects_preserved']
    assert git('ls-remote',FORK,'refs/heads/'+STAGE).split()[0]==state['staging_start'],'Staging changed; inspect before retry'
    token=os.environ['WAEX_STAGE_TOKEN'];import base64
    auth=base64.b64encode(('x-access-token:'+token).encode()).decode()
    env=os.environ.copy();env.pop('WAEX_STAGE_TOKEN',None)
    env.update(GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='http.https://github.com/.extraheader',GIT_CONFIG_VALUE_0='AUTHORIZATION: basic '+auth)
    refspec=state['transport']+':refs/heads/'+STAGE
    result=subprocess.run(['git','push','--porcelain',FORK,refspec],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120)
    (OUT/'object-preservation.log').write_text(result.stdout.replace(token,'[REDACTED]').replace(auth,'[REDACTED]'))
    observed=git('ls-remote',FORK,'refs/heads/'+STAGE).split()[0]
    state['observed_staging']=observed;state['objects_preserved']=observed==state['transport']
    (OUT/'publication.json').write_text(json.dumps(state,indent=2))
    assert result.returncode==0 and state['objects_preserved'],'Write failed or ambiguous; verify refs before any retry'
    print('Validated objects preserved on staging only. PR refs remain unchanged.')

if __name__=='__main__':
    if len(sys.argv)!=2 or sys.argv[1] not in ('prepare','preserve'):raise SystemExit('Use prepare or preserve')
    {'prepare':prepare,'preserve':preserve}[sys.argv[1]]()
