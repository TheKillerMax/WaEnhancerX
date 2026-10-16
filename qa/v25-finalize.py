#!/usr/bin/env python3
"""Validate exact public candidates and preserve Git objects on a test ref only."""
import base64,gzip,hashlib,json,os,shutil,subprocess,time,xml.etree.ElementTree as ET
from pathlib import Path
STAGE=Path.cwd();TMP=Path(os.environ['RUNNER_TEMP']);OUT=TMP/'v25-final-evidence';OUT.mkdir()
MAIN='6e0aa7accd8ab988205d39e3eb582c7379b49a70'
OLD='a4778e55c106ebaa1e12ac74a07bfd5b613d2fae'
ROOT=TMP/'v25-final-source'
P='app/src/main/java/com/waenhancer/'
TREE='a3108c1e4c7f28e8d099fbf91311c552bdfdd02e'
REF='test/stability-validation-v25-2026-10-16'

def git(*args,cwd=STAGE,env=None,data=None):
 return subprocess.check_output(['git',*args],cwd=cwd,env=env,input=data,text=True).strip()

def apply(packed_text,compressed_sha,patch_sha,name):
 packed=base64.b64decode(packed_text,validate=True);assert hashlib.sha256(packed).hexdigest()==compressed_sha,'Transfer failed before candidate execution'
 patch=gzip.decompress(packed);assert hashlib.sha256(patch).hexdigest()==patch_sha
 f=OUT/name;f.write_bytes(patch);git('apply','--index',str(f),cwd=ROOT)

git('worktree','add','--detach',str(ROOT),OLD)
apply(''.join((STAGE/f'qa/v25-transfer-{i}.txt').read_text().strip() for i in range(1,7)),
 '9a8fb4896164ab68e1a6585985bf87a63095b272a6d83d3a7d7fee737a927cd1','2066f646f9e827fb1d6d8c6a073e58579210757832becdc2e4891e54e6318ad9','initial.patch')
assert git('write-tree',cwd=ROOT)=='14cc51f172fc3e6aeca72f31a7ab43350dd60e1e'
git('apply','--index',str(STAGE/'qa/v25-framework-fixture-fix.patch'),cwd=ROOT)
assert git('write-tree',cwd=ROOT)=='d47d440ecdc5ea4967e0f1dafd1d57e1ae238d8a'
apply((STAGE/'qa/v25-final-delta.txt').read_text().strip(),
 'a659dee4c6f8bd5c47424737f2d5e294428bb6b1da0823f1689d5b58173dae60','5a1f78f1cfde2c3d98658ba103b2861a1b5ca75f7c29083984d22015a7178cb9','final-delta.patch')
assert git('write-tree',cwd=ROOT)==TREE
(OUT/'input-tree.txt').write_text(TREE+'\n')
(OUT/'combined.patch').write_text(git('diff','--cached','--binary',OLD,cwd=ROOT)+'\n')
results=[]
def run(name,cmd,cwd=ROOT,timeout=1100):
 start=time.monotonic();log=OUT/(name+'.log');print('RUN '+name,flush=True)
 with log.open('w') as f:r=subprocess.run(cmd,cwd=cwd,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
 row={'name':name,'command':cmd,'code':r.returncode,'seconds':round(time.monotonic()-start,2)};results.append(row);(OUT/'results.json').write_text(json.dumps(results,indent=2))
 if r.returncode:print(log.read_text()[-16000:],flush=True)
 assert r.returncode==0,name

for p in sorted((ROOT/'qa').glob('test_*.py')):
 if p.name!='test_host_class_relocations.py':run('combined-'+p.stem,['python3',str(p)])
run('production-syntax',['python3','qa/check_syntax.py','--root','app/src/main/java'])
run('compiled-negative-stability',['python3','qa/mutate_stability_contracts.py','--out',str(OUT/'mutants')])
run('compiled-negative-runtime',['python3','qa/mutate_runtime_evidence.py','--out',str(OUT/'runtime-mutants')])
run('stability-framework',['python3','qa/verify_stability_framework.py','--out',str(TMP/'v25-final-framework')])
run('presence-framework',['python3','qa/android_presence_row_test.py','--out',str(TMP/'v25-final-presence')])
run('runtime-framework',['python3','qa/verify_runtime_framework.py','--out',str(TMP/'v25-final-runtime')])
# A real Compose old-source control must fail by the targeted assertion, not compilation.
clock=ROOT/(P+'ui/components/RuntimeObservationClock.kt');current=clock.read_bytes()
try:
 clock.write_text(git('show',OLD+':'+P+'ui/components/RuntimeObservationClock.kt')+'\n')
 cmd=['python3','qa/verify_stability_framework.py','--mode','clock','--out',str(TMP/'v25-old-clock')]
 with (OUT/'old-clock-control.log').open('w') as log:r=subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=1100)
 reports=list((TMP/'v25-old-clock/evidence').glob('TEST-*.xml'));assert r.returncode!=0 and len(reports)==1
 t=ET.parse(reports[0]).getroot();assert t.get('tests')=='1' and t.get('failures')=='1'
 failures=t.findall('.//failure');assert len(failures)==1 and 'Clock reused a prior composition time' in failures[0].get('message','')
 (OUT/'old-clock-control.json').write_text(json.dumps({'compiled':True,'tests':1,'expected_behavior_failures':1}))
finally:clock.write_bytes(current)
assert git('diff',cwd=ROOT)==''

git('config','user.name','TheKillerMax');git('config','user.email','70108066+TheKillerMax@users.noreply.github.com')
common=['qa/verify_stability_framework.py']
specs=[
 {'key':'update','branch':'fix/update-session-integrity-2026-10-16','base':MAIN,'message':'fix(updates): isolate verified downloads and cancel queued installation',
 'paths':[P+x for x in ['update/UpdateDownloader.kt','update/UpdateTransferPolicy.kt','update/UpdateDownloadSession.kt','update/ReleaseRepository.kt','ui/components/UpdateDownloadSheet.kt','ui/navigation/Navigation.kt','ui/screens/settings/ChangelogScreen.kt','ui/screens/settings/ReleaseDetailsScreen.kt','xposed/utils/RootCommandRunner.java']]+common+['qa/test_update_download_contract.py','qa/test_update_session.py','qa/fixtures/StabilityUpdateTest.kt','qa/UPDATE_STABILITY_ACCEPTANCE.md'],
 'tests':['test_update_download_contract.py','test_update_session.py','test_restart_safety.py']},
 {'key':'recorder','branch':'fix/recorder-failure-cleanup-2026-10-16','base':MAIN,'message':'fix(recording): release the local recorder after stop failures',
 'paths':[P+'xposed/features/media/CallRecordingHook.java','qa/test_recorder_cleanup.py','qa/RECORDER_CLEANUP_ACCEPTANCE.md'],'tests':['test_recorder_cleanup.py']},
 {'key':'filter','branch':'perf/filter-snapshot-work-2026-10-16','base':MAIN,'message':'perf(filters): skip empty traversals and coalesce immutable reloads',
 'paths':[P+'xposed/features/customization/FilterItemsHook.kt','qa/test_filter_work.py','qa/fixtures/StabilityFilterTest.kt','qa/FILTER_WORK_ACCEPTANCE.md']+common,'tests':['test_filter_work.py']},
 {'key':'clock','branch':'fix/runtime-compatibility-evidence-2026-10-15','base':'6af387369e688b7b4ca3c3fdbefb4c026a75e60d','message':'fix(diagnostics): use live time between lifecycle invalidations',
 'paths':[P+'ui/components/RuntimeObservationClock.kt',P+'ui/screens/settings/SystemHealthScreen.kt','qa/test_runtime_observation_clock.py','qa/fixtures/StabilityClockTest.kt','qa/CLOCK_RECOMPOSITION_ACCEPTANCE.md']+common,
 'tests':['test_runtime_observation_clock.py','test_runtime_diagnostics.py','test_startup_reconciliation.py']},
 {'key':'qa','branch':'fix/qa-localized-catalog-2026-10-15','base':'71d198399a07487f7559d420aa92dd7c1811bb59','message':'test(qa): require stability contracts and real lifecycle regressions',
 'paths':['.github/workflows/source-qa.yml','qa/mutate_stability_contracts.py','qa/fixtures/StabilityClockTest.kt','qa/fixtures/StabilityUpdateTest.kt','qa/fixtures/StabilityFilterTest.kt']+common,'tests':[]},
]
for spec in specs:
 env=dict(os.environ,GIT_INDEX_FILE=str(TMP/('index-'+spec['key'])))
 git('read-tree',spec['base'],env=env)
 for path in spec['paths']:
  assert path.startswith(('app/src/main/java/','qa/','.github/workflows/')) and path.endswith(('.kt','.java','.py','.md','.yml'))
  blob=git('hash-object','-w',str(ROOT/path));git('update-index','--add','--cacheinfo','100644',blob,path,env=env)
 tree=git('write-tree',env=env);sha=git('commit-tree',tree,'-p',spec['base'],'-m',spec['message'])
 changed=git('diff-tree','--no-commit-id','--name-only','-r',spec['base'],sha).splitlines();assert set(changed)<=set(spec['paths'])
 spec.update({'sha':sha,'tree':tree,'changed_files':changed})
 check=TMP/('standalone-'+spec['key']);git('worktree','add','--detach',str(check),sha)
 for test in spec['tests']:run('standalone-'+spec['key']+'-'+test,['python3','qa/'+test],cwd=check)
 if spec['key']=='qa':
  for p in sorted((check/'qa').glob('test_*.py')):
   if p.name!='test_host_class_relocations.py':run('standalone-qa-'+p.stem,['python3',str(p)],cwd=check)
 run('syntax-'+spec['key'],['python3','qa/check_syntax.py','--root','app/src/main/java'],cwd=check)
 if spec['key'] in ['update','filter','clock']:
  run('framework-'+spec['key'],['python3','qa/verify_stability_framework.py','--mode',spec['key'],'--out',str(TMP/('v25-standalone-'+spec['key']))],cwd=check)
 (OUT/(spec['key']+'.patch')).write_text(git('diff','--binary',spec['base'],sha)+'\n')
 (OUT/'candidates.json').write_text(json.dumps(specs,indent=2))

# Final tree already validated; parents preserve each focused contribution and old integration.
args=['commit-tree',TREE,'-p',OLD]
for s in specs:args+=['-p',s['sha']]
integration=git(*args,'-m','merge: retain validated update, recorder, filter and live-clock improvements')
(OUT/'integration.json').write_text(json.dumps({'old':OLD,'sha':integration,'tree':TREE,'parents':[OLD]+[s['sha'] for s in specs]},indent=2))
# No functional ref changes here. Preserve objects on the current disposable test branch.
head=git('rev-parse','HEAD');assert git('ls-remote','origin','refs/heads/'+REF).split()[0]==head
assert git('ls-remote','https://github.com/WaEnhancerX/WaEnhancerX.git','refs/heads/main').split()[0]==MAIN
proof=git('commit-tree',git('rev-parse','HEAD^{tree}'),'-p',head,'-p',integration,'-m','test(qa): preserve fully validated stability candidate objects')
git('push','origin',proof+':refs/heads/'+REF)
(OUT/'preserved-proof.txt').write_text(proof+'\n')
print('ALL VALIDATIONS PASSED; ONLY TEST REF ADVANCED',flush=True)
