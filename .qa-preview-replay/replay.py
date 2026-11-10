"""Reconstruct a public reviewed tree, verify its identity, stage blobs only. Never update product refs."""
from pathlib import Path
import subprocess,os,json,shutil,hashlib,base64,urllib.request
checkout=Path.cwd();recipe=checkout/'.qa-preview-replay'
R=Path(os.environ['RUNNER_TEMP'])/'preview-replay';R.mkdir(exist_ok=False)
W=R/'work/waex-pr90-media-20261110';W.parent.mkdir(parents=True)
BASE='4750124e36223dd21d8535c14f2fb658025d8480'
OLD='e7c1d0eaf771ac6b72e921b42c656c24b05bee2e'
EXPECTED_TREE='e0b4116fb9a0d5f7f76c1a14276f763b990f6959'
assert os.environ['GITHUB_REPOSITORY']=='TheKillerMax/WaEnhancerX'
def git(*args,cwd=checkout,check=True):
 p=subprocess.run(['git',*args],cwd=cwd,capture_output=True,timeout=90)
 if check and p.returncode:raise RuntimeError(p.stdout.decode(errors='replace')+p.stderr.decode(errors='replace'))
 return p
for sha in [BASE,OLD,'74b4d1fc472da79a76142341babd768371a8556c']:
 git('cat-file','-e',sha+'^{commit}')
git('worktree','add','--detach',str(W),OLD)
r=git('-c','user.name=WAEX Lab','-c','user.email=waex-lab@localhost','merge','--no-commit','--no-ff',BASE,cwd=W,check=False)
assert r.returncode==1
assert git('diff','--name-only','--diff-filter=U',cwd=W).stdout.decode().splitlines()==['app/src/main/java/com/waenhancer/xposed/features/media/MediaPreviewHook.kt']
seam=R/'work/waex-pr87-current-20261109/qa/android_preserved_dispatch_test.py';seam.parent.mkdir(parents=True)
seam.write_bytes(git('show','74b4d1fc472da79a76142341babd768371a8556c:qa/android_preserved_dispatch_test.py').stdout)
for name in ['step1.py','step2.py','step3.py']:
 space={'R':R,'W':W,'__name__':'replay_only'}
 exec(compile((recipe/name).read_text(encoding='utf-8'),name,'exec'),space)
old_doc=W/'qa/MEDIA_PREVIEW_LIFECYCLE_ACCEPTANCE.md';prior=old_doc.read_text(encoding='utf-8')
start=prior.index('The runner derives');end=prior.index('## Scope and remaining device acceptance')
text=(recipe/'acceptance-intro.md').read_text(encoding='utf-8')+'\n## Dependency and offline invocation details\n\n'+prior[start:end]
old_doc.write_text(text.rstrip()+'\n',encoding='utf-8')
shutil.copyfile(recipe/'mutate_media_preview_lifecycle.py',W/'qa/mutate_media_preview_lifecycle.py')
shutil.copyfile(recipe/'media-preview-lifecycle-qa.yml',W/'.github/workflows/media-preview-lifecycle-qa.yml')
exec(compile((recipe/'step4.py').read_text(encoding='utf-8'),'step4.py','exec'),{'W':W,'recipe':recipe})
git('add','app/src/main/java/com/waenhancer/xposed/features/media/MediaPreviewHook.kt','qa','.github/workflows',cwd=W)
# Review only the proposed delta against current main, not inherited upstream whitespace.
git('diff','--cached','--check',BASE,cwd=W)
tree=git('write-tree',cwd=W).stdout.decode().strip()
rows=[]
for path in git('diff','--cached','--name-only',BASE,cwd=W).stdout.decode().splitlines():
 assert path.startswith(('qa/','.github/workflows/','app/src/main/java/'))
 record=git('ls-files','--stage','--',path,cwd=W).stdout.decode().strip();meta,name=record.split('\t',1);mode,sha,stage=meta.split();assert stage=='0' and mode=='100644' and name==path
 data=git('cat-file','blob',sha,cwd=W).stdout
 rows.append({'path':path,'mode':mode,'type':'blob','sha':sha,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
identity={'tree':tree,'expected_tree':EXPECTED_TREE,'parents':[OLD,BASE],'files':rows,'product_refs_changed':False}
receipt=Path(os.environ['RUNNER_TEMP'])/'preview-staged-identities.json';receipt.write_text(json.dumps(identity,indent=2)+'\n')
print(json.dumps(identity),flush=True)
assert tree==EXPECTED_TREE,'Tree mismatch: do not upload anything or change any ref'
assert len(rows)==8
patch=git('diff','--cached','--binary',BASE,cwd=W).stdout
(Path(os.environ['RUNNER_TEMP'])/'preview-reviewed.patch').write_bytes(patch)
for row in rows:
 data=git('cat-file','blob',row['sha'],cwd=W).stdout;assert len(data)<150000
 request=urllib.request.Request('https://api.github.com/repos/TheKillerMax/WaEnhancerX/git/blobs',data=json.dumps({'content':base64.b64encode(data).decode(),'encoding':'base64'}).encode(),headers={'Authorization':'Bearer '+os.environ['GH_OBJECT_TOKEN'],'Accept':'application/vnd.github+json','Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28'},method='POST')
 with urllib.request.urlopen(request,timeout=60) as response: remote=json.load(response)
 assert remote['sha']==row['sha']
print('ALL_EIGHT_BLOBS_STAGED; EXACT_TREE; NO_PRODUCT_REF_CHANGED')
