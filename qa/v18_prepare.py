#!/usr/bin/env python3
"""Pinned, source-only V18 validation. Functional refs are NOT advanced by this script."""
import base64,gzip,hashlib,json,os
from pathlib import Path
import subprocess,sys

PINS={
 'preview':('integration/preview-current-main-2026-10-14','562da7d08fc3926b2463c29c064815f79a80fcff'),
 'manual':('fix/blue-reply-exact-recipient-bounded-state-2026-10','3f7136929a4e5ec8f7d12c38a477e3c3bd38e852'),
 'presence':('fix/presence-message-event-contract-2026-10-14','0cd347d1f0578eb439d44f8dca0bd594500db0ea'),
 'styles':('fix/styles-typed-save-failure-2026-10-14','dbc1312e5b827acdaaedf58c3961c73400225592'),
 'qa':('test/qa-java-kotlin-syntax-guard-2026-10','4ca4c42f7774818ecb3691134dfdbf76bbe3236a')}
STAGE='test/manual-presence-validation-v18-2026-10-14'
PAYLOAD='3c4e4c92d83d82c580147685903d4bafec1f6f487aba66bba502971749f28bec'
ROOT=Path.cwd();BASE=Path(os.environ['RUNNER_TEMP'])/'waex-v18';OUT=Path(os.environ['RUNNER_TEMP'])/'waex-v18-evidence'
ENV=dict(os.environ,GIT_AUTHOR_NAME='TheKillerMax',GIT_AUTHOR_EMAIL='70108066+TheKillerMax@users.noreply.github.com',GIT_COMMITTER_NAME='TheKillerMax',GIT_COMMITTER_EMAIL='70108066+TheKillerMax@users.noreply.github.com')
BASE.mkdir(exist_ok=True);OUT.mkdir(exist_ok=True)
results=[];heads={};trees={}
def git(*args,cwd=ROOT,stdin=None):
 return subprocess.run(['git',*args],cwd=cwd,input=stdin,text=True,capture_output=True,check=True,env=ENV).stdout.strip()
def run(name,cmd,cwd,negative=False,timeout=300):
 p=subprocess.run(cmd,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
 (OUT/(name+'.log')).write_text(p.stdout)
 ok=p.returncode==0 if not negative else p.returncode!=0 and ('java.lang.AssertionError' in p.stdout or 'java.lang.IllegalStateException' in p.stdout) and 'error:' not in p.stdout
 row={'name':name,'exit_code':p.returncode,'expected_failure':negative,'accepted':ok};results.append(row)
 (OUT/'tests.json').write_text(json.dumps(results,indent=2))
 print(('PASS ' if ok else 'FAIL ')+name,flush=True)
 if not ok:raise RuntimeError(name+'\n'+p.stdout[-12000:])
 return p.stdout

def checkout(name,sha):
 path=BASE/name;git('worktree','add','--detach',str(path),sha);return path

def apply(path,text):
 if text:git('apply','--check','-',cwd=path,stdin=text);git('apply','-',cwd=path,stdin=text)
 git('diff','--check',cwd=path)

def commit(path,name,parents,message):
 git('add','-A',cwd=path);tree=git('write-tree',cwd=path)
 args=['commit-tree',tree]
 for p in parents:args+=['-p',p]
 sha=git(*args,cwd=path,stdin=message+'\n');git('reset','--hard',sha,cwd=path)
 heads[name]=sha;trees[name]=tree;return sha

def preserve():
    # Preserve reviewed objects only on the staging ref; user PR refs require separate guarded updates.
    assert os.environ['GITHUB_REPOSITORY']=='TheKillerMax/WaEnhancerX'
    assert os.environ['GITHUB_REF']=='refs/heads/'+STAGE
    state=json.loads((OUT/'state.json').read_text());assert state['validation_passed']
    combinedhead=state['heads']['preview']
    git('merge-base','--is-ancestor',PINS['preview'][1],combinedhead)
    actual=git('ls-remote','origin','refs/heads/'+STAGE).split()[0];assert actual==os.environ['GITHUB_SHA']
    stage=git('commit-tree',git('rev-parse','HEAD^{tree}'),'-p',actual,'-p',combinedhead,stdin='test(qa): preserve validated V18 commit objects only\n')
    auth=base64.b64encode(('x-access-token:'+os.environ['V18_STAGE_TOKEN']).encode()).decode()
    p=subprocess.run(['git','-c','http.https://github.com/.extraheader=AUTHORIZATION: basic '+auth,'push','origin',stage+':refs/heads/'+STAGE],cwd=ROOT,text=True,capture_output=True)
    (OUT/'stage-push.log').write_text((p.stdout+p.stderr).replace(auth,'[REDACTED]'))
    state['staging_head']=stage;state['stage_objects_preserved']=p.returncode==0 and git('ls-remote','origin','refs/heads/'+STAGE).split()[0]==stage
    (OUT/'state.json').write_text(json.dumps(state,indent=2));assert state['stage_objects_preserved'],'Inspect staging state before retry; no functional refs advanced'
    print(json.dumps(state,indent=2),flush=True)

if len(sys.argv)>1 and sys.argv[1]=='preserve':
    preserve();raise SystemExit(0)

# Do not reconstruct on stale refs or write a non-fork repository.
assert os.environ['GITHUB_REPOSITORY']=='TheKillerMax/WaEnhancerX'
for name,(branch,sha) in PINS.items():
 actual=git('ls-remote','origin','refs/heads/'+branch).split()[0]
 assert actual==sha,(name,actual,sha)
packed=base64.b64decode((ROOT/'qa/v18_payload.gz.b64').read_text().strip(),validate=True)
raw=gzip.decompress(packed);assert len(raw)<200000 and hashlib.sha256(raw).hexdigest()==PAYLOAD
payload=json.loads(raw)
for path in payload['files_sha256']:
 assert path.startswith(('app/src/main/java/','qa/')) and '..' not in Path(path).parts
(OUT/'payload-sha256.txt').write_text(PAYLOAD+'\n')

manual=checkout('manual',PINS['manual'][1]);apply(manual,payload['patches']['manual'])
manager=manual/'app/src/main/java/com/waenhancer/core/preferences/WaexPreferenceManager.java'
text=manager.read_text();assert 'public boolean putPublicString(' not in text and 'private static boolean isPublicType(' not in text
anchor='    public java.util.Set<String> getStringSet('
assert text.count(anchor)==1;manager.write_text(text.replace(anchor,payload['helper']+anchor,1))
manualhead=commit(manual,'manual',[PINS['manual'][1]],'fix(styles): report failed manual read-control persistence')
for test in ['test_manual_blue_tick_ui.py','test_manual_seen_tick_persistence.py','test_blue_receipt_recipient_isolation.py']:
 run('manual-'+test,['python3','qa/'+test],manual)

presence=checkout('presence',PINS['presence'][1]);apply(presence,payload['patches']['presence'])
presencehead=commit(presence,'presence',[PINS['presence'][1]],'fix(presence): invalidate denied and disconnected observations before rendering')
for test in ['test_presence_event_contract.py','test_presence_state_replay.py','test_presence_invalidation.py','test_presence_state_invalidation.py']:
 run('presence-'+test,['python3','qa/'+test],presence)

styles=checkout('styles',PINS['styles'][1]);apply(styles,payload['patches']['styles'])
styleshead=commit(styles,'styles',[PINS['styles'][1]],'test(styles): preserve typed editor coverage across checked manual wiring')
for test in ['test_style_non_boolean_guard.py','test_style_boolean_alias_wiring.py','test_media_preference_sync.py']:
 run('styles-'+test,['python3','qa/'+test],styles)

qa=checkout('qa',PINS['qa'][1]);workflow=qa/'.github/workflows/source-qa.yml';text=workflow.read_text()
for old,new in [
 ('            qa/test_manual_blue_tick_ui.py \\\n','            qa/test_manual_blue_tick_ui.py \\\n            qa/test_manual_seen_tick_persistence.py \\\n'),
 ('            qa/test_presence_state_replay.py \\\n','            qa/test_presence_state_replay.py \\\n            qa/test_presence_invalidation.py \\\n            qa/test_presence_state_invalidation.py \\\n')]:
 assert text.count(old)==1; text=text.replace(old,new,1)
step='''      - name: Require tests for merged checked-save and invalidation APIs
        shell: bash
        run: |
          set -euo pipefail
          store=app/src/main/java/com/waenhancer/xposed/features/automation/PresenceStateStore.java
          ui=app/src/main/java/com/waenhancer/ui/screens/settings/StylesSettingsScreen.kt
          if grep -q 'updateAndGetTransition(' "$store"; then
            test -f qa/test_presence_invalidation.py
            test -f qa/test_presence_state_invalidation.py
          fi
          if grep -q 'putPublicString("seentick", nextPlacement)' "$ui"; then
            test -f qa/test_manual_seen_tick_persistence.py
          fi

'''
anchor='      - name: Run additional source-only QA suites when merged\n';assert text.count(anchor)==1
workflow.write_text(text.replace(anchor,step+anchor,1))
(qa/'qa/mutate_manual_presence.py').write_text(payload['extra']['qa/mutate_manual_presence.py'])
qahead=commit(qa,'qa',[PINS['qa'][1]],'test(qa): require manual persistence and presence lifecycle regressions')

combined=checkout('combined',PINS['preview'][1]);parent=PINS['preview'][1]
for name,topic in [('manual',manualhead),('presence',presencehead),('styles',styleshead)]:
 apply(combined,payload['patches'][name])
 parent=commit(combined,'combined-'+name,[parent,topic],'merge: retain reviewed V18 '+name+' changes')
(combined/'.github/workflows/source-qa.yml').write_text(workflow.read_text())
for path,text in payload['extra'].items():(combined/path).write_text(text)
combinedhead=commit(combined,'preview',[parent,qahead],'merge: integrate V18 regression CI and explicit review boundaries')
for path,sha in payload['files_sha256'].items():
 actual=hashlib.sha256((combined/path).read_bytes()).hexdigest();assert actual==sha,(path,actual,sha)
for path in ['app/src/main/java/com/waenhancer/xposed/features/automation/PresenceStateStore.java','app/src/main/java/com/waenhancer/xposed/features/customization/OnlinePresenceIndicatorsHook.kt']:
 assert (presence/path).read_bytes()==(combined/path).read_bytes(),path

for name,source in [('manual',manual),('presence',presence),('combined',combined)]:
 run(name+'-syntax',['python3',str(combined/'qa/check_syntax.py'),'--root',str(source/'app/src/main/java')],source)
tests=sorted(p for p in (combined/'qa').glob('test_*.py') if p.name!='test_host_class_relocations.py')
assert len(tests)==45,len(tests)
# Serial runner keeps independent logs and avoids hiding a failed process in a pipeline.
for test in tests:run('combined-'+test.stem,['python3',str(test)],combined)

# Equivalent query construction against the declared real dependency, not a native scan.
deps=BASE/'dexkit';deps.mkdir()
run('dexkit-download',['curl','--fail','--location','--max-time','90','-o',str(deps/'dexkit.aar'),'https://repo.maven.apache.org/maven2/org/luckypray/dexkit/2.2.0/dexkit-2.2.0.aar'],ROOT)
assert hashlib.sha256((deps/'dexkit.aar').read_bytes()).hexdigest()=='cf4488da9f721750ce5ff4311e88356cbfcb1d4444c2b519b12d8bdb5f33f2c6'
import zipfile,shutil
with zipfile.ZipFile(deps/'dexkit.aar') as z:(deps/'dexkit.jar').write_bytes(z.read('classes.jar'))
hook=(combined/'app/src/main/java/com/waenhancer/xposed/features/automation/PresenceToastsHook.java').read_text()
query=hook.split('MethodDataList matches = bridge.findMethod(',1)[1].split(';\n',1)[0].rstrip();assert query.endswith(')');query=query[:-1]
java='''import org.luckypray.dexkit.query.FindMethod;import org.luckypray.dexkit.query.matchers.MethodMatcher;import org.luckypray.dexkit.query.enums.StringMatchType;
public final class PresenceQuery {public static void main(String[]args){Object query='''+query+''';System.out.println("PASS: production presence query compiled and instantiated against DexKit 2.2.0; no native scan");}}'''
(deps/'PresenceQuery.java').write_text(java)
kotlin=Path(shutil.which('kotlinc')).resolve().parent.parent/'lib';cp=str(deps/'dexkit.jar')+os.pathsep+str(kotlin/'*')
run('dexkit-javac',['javac','--release','17','-cp',cp,str(deps/'PresenceQuery.java')],deps)
run('dexkit-query',['java','-cp',str(deps)+os.pathsep+cp,'PresenceQuery'],deps)
(OUT/'PresenceQuery.java').write_text(java)

baseline=checkout('baseline',PINS['preview'][1]);(baseline/'qa/test_manual_seen_tick_persistence.py').write_text((combined/'qa/test_manual_seen_tick_persistence.py').read_text())
run('baseline-manual',['python3','qa/test_manual_seen_tick_persistence.py'],baseline,negative=True)
run('baseline-presence',['python3',str(combined/'qa/test_presence_invalidation.py'),'--source-root',str(baseline)],baseline,negative=True)
run('negative-controls',['python3','qa/mutate_manual_presence.py','--out',str(OUT/'mutants')],combined,timeout=600)
run('android-rows',['python3','qa/android_presence_row_test.py','--out',str(BASE/'android')],combined,timeout=900)
run('android-negative-controls',['python3','qa/mutate_presence_rows.py',str(BASE/'android-mutants'),str(BASE/'android/deps')],combined,timeout=900)
for src in [BASE/'android',BASE/'android-mutants']:
 dest=OUT/src.name
 for path in src.rglob('*'):
  if path.is_file() and path.suffix in ('.log','.json','.kt') and 'deps' not in path.relative_to(src).parts:
   target=dest/path.relative_to(src);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
for topic,text in payload['patches'].items():(OUT/(topic+'.patch')).write_text(text)
state={'pins':PINS,'heads':heads,'trees':trees,'functional_refs_published':False,'validation_passed':True,'tests':len(results),'files_sha256':payload['files_sha256']}
(OUT/'state.json').write_text(json.dumps(state,indent=2))
print(json.dumps(state,indent=2),flush=True)
