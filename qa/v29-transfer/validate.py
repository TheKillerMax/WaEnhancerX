#!/usr/bin/env python3
"""Temporary V29 runner: verify transport and exact trees before tests or blob publication.
No branch, PR, user setting or upstream ref is changed by this runner.
"""
import base64, hashlib, json, os, pathlib, subprocess, sys, time, urllib.request, zlib
HERE=pathlib.Path(__file__).resolve().parent
ROOT=pathlib.Path(os.environ['GITHUB_WORKSPACE'])
OUT=ROOT/'v29-validation'; OUT.mkdir(exist_ok=True)
BASE='50bc0eb6d93d2dc7eca9e78d2894e60393e55847'
TREE='807d723d59746d4b2e2c950d9f3581e6b9238005'
RAW_SHA='2ccfaaa350c287d0811374a11387667d7f2ed407efbf5ad019a53810d145fbb4'
rows=[]
def digest(data): return hashlib.sha256(data).hexdigest()
def run(args,cwd=None,name=None,timeout=240):
    start=time.monotonic()
    p=subprocess.run(args,cwd=cwd or ROOT,capture_output=True,text=True,timeout=timeout)
    if name:
        (OUT/(name+'.log')).write_text(p.stdout+p.stderr)
        rows.append({'name':name,'rc':p.returncode,'seconds':round(time.monotonic()-start,3)})
        (OUT/'commands.json').write_text(json.dumps(rows,indent=2))
        print(name,p.returncode,flush=True)
    if p.returncode: raise RuntimeError(str(args)+'\n'+(p.stdout+p.stderr)[-6000:])
    return p.stdout.strip()
def decode():
    parts=[]
    for repair in json.loads((HERE/'repairs.json').read_text()):
        text=(HERE/f'part{repair["part"]}.b64').read_text().strip()
        assert digest(text.encode())==repair['input_sha256'],'Unreviewed transfer input'
        for a,b,old,new in reversed(repair['edits']):
            assert text[a:b]==old,'Repair offset mismatch'
            text=text[:a]+new+text[b:]
        assert digest(text.encode())==repair['output_sha256'],'Transfer repair mismatch'
        parts.append(text)
    raw=zlib.decompress(base64.b64decode(''.join(parts),validate=True))
    assert len(raw)==90858 and digest(raw)==RAW_SHA,'Refusing altered patch payload'
    data=json.loads(raw)
    assert len(data)==4
    patches=OUT/'patches'; patches.mkdir()
    for name,content in data.items():
        assert pathlib.Path(name).name==name and name.endswith('.patch')
        (patches/name).write_text(content)
    return sorted(patches.glob('*.patch'))
def worktree(name,patches):
    path=ROOT.parent/f'v29-{name}'
    run(['git','worktree','add','--detach',str(path),BASE])
    for patch in patches: run(['git','apply','--check',str(patch)],path);run(['git','apply','--index',str(patch)],path)
    run(['git','diff','--check','--cached'],path,name+'-diff')
    return path

def validate():
    patches=decode()
    run(['git','fetch','--no-tags','https://github.com/WaEnhancerX/WaEnhancerX.git',BASE],name='fetch-pinned-base')
    assert run(['git','rev-parse',BASE+'^{tree}'])=='69b8e49c520709f8c507472af5a80ff1469cb7d9'
    test_names=['test_forwarded_metadata_scope.py','test_contact_identity.py','test_gallery_export.py']
    groups=[]
    for index,patch in enumerate(patches):
        root=worktree('single-'+str(index+1),[patch])
        if index<3:
            run([sys.executable,'qa/'+test_names[index]],root,'single-'+str(index+1),timeout=240)
        else:
            for script in sorted((root/'qa').glob('test_*.py')):
                if script.name=='test_host_class_relocations.py': continue
                run([sys.executable,str(script)],root,'qa-only-'+script.stem,timeout=240)
        run([sys.executable,'qa/check_syntax.py','--root','app/src/main/java','--json'],root,'syntax-single-'+str(index+1),timeout=240)
        run(['git','diff','--exit-code'],root)
        groups.append({'patch':patch.name,'tree':run(['git','write-tree'],root),'files':run(['git','diff','--cached','--name-only'],root).splitlines()})
    combined=worktree('combined',patches)
    assert run(['git','write-tree'],combined)==TREE,'Combined tree differs from local tested source'
    for script in sorted((combined/'qa').glob('test_*.py')):
        if script.name=='test_host_class_relocations.py': continue
        run([sys.executable,str(script)],combined,'combined-'+script.stem,timeout=240)
    run([sys.executable,'qa/check_syntax.py','--root','app/src/main/java','--json'],combined,'syntax-combined',timeout=240)
    run([sys.executable,'qa/mutate_media_identity.py','--out',str(OUT/'mutants')],combined,'compiled-negative-controls',timeout=900)
    run(['git','diff','--exit-code'],combined)
    assert run(['git','write-tree'],combined)==TREE
    files=sorted(set(p for group in groups for p in group['files']))
    assert len(files)==14
    entries=[]
    for path in files:
        src=combined/path;data=src.read_bytes();data.decode('utf-8')
        blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        dest=OUT/'source'/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        entries.append({'path':path,'mode':'100644','type':'blob','sha':blob,'sha256':digest(data)})
    summary={'base':BASE,'base_tree':'69b8e49c520709f8c507472af5a80ff1469cb7d9','combined_tree':TREE,'groups':groups,'entries':entries,'commands':rows,'limits':'Source/JVM only; no APK, native DexKit, Binder, real MediaProvider, device or LSPosed acceptance.'}
    (OUT/'validated.json').write_text(json.dumps(summary,indent=2))
    print('VALIDATED',len(rows),'commands',TREE,flush=True)

def store_blobs():
    data=json.loads((OUT/'validated.json').read_text());assert data['combined_tree']==TREE
    published=[]
    for entry in data['entries']:
        text=(OUT/'source'/entry['path']).read_bytes()
        assert digest(text)==entry['sha256']
        req=urllib.request.Request('https://api.github.com/repos/TheKillerMax/WaEnhancerX/git/blobs',method='POST',data=json.dumps({'encoding':'base64','content':base64.b64encode(text).decode()}).encode(),headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json','Content-Type':'application/json','User-Agent':'waex-v29-reviewed-blobs'})
        with urllib.request.urlopen(req,timeout=60) as response: result=json.load(response)
        assert result['sha']==entry['sha'],'Stored blob differs from tested text'
        published.append(entry)
        (OUT/'stored-blobs.json').write_text(json.dumps(published,indent=2))
    print('STORED_UNREFERENCED_BLOBS',len(published),'NO_REFS_CHANGED')
if __name__=='__main__':
    if sys.argv[1:]==['--store-blobs']:store_blobs()
    elif not sys.argv[1:]:validate()
    else:raise SystemExit('Unsupported mode')
