#!/usr/bin/env python3
"""Build the exact baseline/candidate class-linkage probes, not the WAEX application."""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCK = HERE / 'lock.json'
VARIANTS = ('baseline', 'candidate')
def require(ok, msg):
    if not ok:
        raise RuntimeError(msg)
def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p, value):
    p.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
def run(out, name, args, timeout=180, env=None):
    result = subprocess.run(list(map(str,args)), capture_output=True, timeout=timeout, env=env)
    (out/(name+'.stdout.log')).write_bytes(result.stdout)
    (out/(name+'.stderr.log')).write_bytes(result.stderr)
    require(result.returncode == 0, name+' failed: '+result.stderr.decode(errors='replace')[-2000:])
    return result.stdout.decode(errors='replace').strip()
def verify_sources(root, pins):
    for rel, sha in pins.items():
        p = root / rel
        require(p.is_file() and not p.is_symlink() and digest(p)==sha, 'Source mismatch: '+rel)
def compile_dex(out, variant, classes, probe_classes, deps, java, d8, android_jar):
    class_inputs, excluded = {}, []
    dst = out / (variant+'-classes.jar')
    with zipfile.ZipFile(dst,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(classes.rglob('*.class')):
            rel = p.relative_to(classes).as_posix()
            if rel.startswith(('android/','org/json/','ReceiptResourceBoundaryProbe')) or 'ReceiptStanzaRuntimeChecks' in rel:
                excluded.append(rel)
                continue
            require(rel.startswith(('com/','de/','androidx/')), 'Unexpected class: '+rel)
            class_inputs[rel] = digest(p)
            z.writestr(rel,p.read_bytes())
        for p in sorted(probe_classes.rglob('*.class')):
            rel = p.relative_to(probe_classes).as_posix()
            require(rel not in class_inputs, 'Duplicate probe class')
            class_inputs[rel] = digest(p)
            z.writestr(rel,p.read_bytes())
    require(any(n.endswith('/WaJid.class') for n in class_inputs) and
            any(n.endswith('/HideReceiptsHook.class') for n in class_inputs), 'Real target classes missing')
    dexout=out/(variant+'-dex'); dexout.mkdir()
    run(out,variant+'-d8',[java,'-cp',d8,'com.android.tools.r8.D8','--release','--min-api','24',
                           '--lib',android_jar,'--output',dexout,dst,*deps])
    dexes=sorted(dexout.glob('classes*.dex'))
    require(len(dexes)==1 and dexes[0].name=='classes.dex', 'Single DEX required')
    body=dexes[0].read_bytes()
    require(body[:4]==b'dex\n' and b'Lcom/waenhancer/xposed/core/wa/WaJid;' in body and
            b'Lcom/waenhancer/xposed/features/privacy/HideReceiptsHook;' in body, 'DEX target descriptors missing')
    require((b'Ljava/lang/ClassValue;' in body)==(variant=='baseline'), 'ClassValue descriptor differs from variant')
    artifact=out/'artifact'; artifact.mkdir(exist_ok=True)
    jar=artifact/(variant+'-art-probe.jar')
    with zipfile.ZipFile(jar,'x',zipfile.ZIP_STORED) as z:
        z.writestr('classes.dex',body)
    require(0<jar.stat().st_size<=8*1024**2, 'DEX jar size outside bounds')
    return {'inputs':class_inputs,'excluded_host_only':excluded,'dex_sha256':digest(dexes[0]),
            'jar_sha256':digest(jar),'jar_bytes':jar.stat().st_size,'classvalue_descriptor_present':variant=='baseline'}
def class_only(src,dst):
    with zipfile.ZipFile(src) as zi, zipfile.ZipFile(dst,'x',zipfile.ZIP_DEFLATED) as zo:
        seen=set()
        for member in zi.infolist():
            n=member.filename
            if n.endswith('.class') and not n.startswith('META-INF/') and n!='module-info.class':
                require(n not in seen and not n.startswith('/') and '..' not in Path(n).parts, 'Unexpected dependency class')
                seen.add(n); zo.writestr(n,zi.read(member))
        require(bool(seen),'Dependency has no classes')
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--sdk',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--java-home',type=Path,required=True)
    a=p.parse_args()
    a.out=a.out.resolve(); a.out.mkdir(parents=True,exist_ok=False)
    out=a.out
    lock=json.loads(LOCK.read_bytes())
    require(os.environ.get('GITHUB_REPOSITORY')=='TheKillerMax/WaEnhancerX' and
            os.environ.get('GITHUB_REF')=='refs/heads/lab/android-emulator-matrix-nightly8-20261124',
            'Only reviewed fork lab build allowed')
    require(re.fullmatch('[a-f0-9]{40}',os.environ.get('GITHUB_SHA','')), 'Missing workflow commit')
    require(digest(HERE/'Main.java')==lock['probe_sha256'],'Probe source changed')
    for variant in VARIANTS:
        root=getattr(a,variant).resolve()
        require(run(out,variant+'-git',['git','-C',root,'rev-parse','HEAD'])==lock['sources'][variant]['commit'], 'Source revision mismatch')
        verify_sources(root,lock['sources'][variant]['pins'])
    runner=a.candidate/'qa/test_receipt_stanza_runtime.py'
    fixture=a.candidate/'qa/fixtures/ReceiptStanzaRuntimeChecks.java'
    require(digest(runner)==lock['runner_sha256'] and digest(fixture)==lock['fixture_sha256'],'Receipt fixture changed')
    env=os.environ.copy()
    env['PATH']=str(a.java_home/'bin')+os.pathsep+env['PATH']
    env.pop('WAEX_QA_DEXKIT_JAR',None)
    kotlin=shutil.which('kotlinc',path=env['PATH'])
    require(kotlin is not None,'Preinstalled Kotlin required')
    stdlib=Path(kotlin).resolve().parents[1]/'lib/kotlin-stdlib.jar'
    java=a.java_home/'bin/java'; javac=a.java_home/'bin/javac'
    android_jar=a.sdk/'platforms/android-36/android.jar'; d8=a.sdk/'build-tools/36.0.0/lib/d8.jar'
    for tool in (java,javac,stdlib,android_jar,d8):
        require(tool.is_file(),'Missing tool/dependency: '+str(tool))
    run(out,'java-version',[java,'-version'],env=env)
    run(out,'kotlin-version',[kotlin,'-version'],env=env)
    compiled=out/'probe-classes';compiled.mkdir()
    run(out,'probe-javac',[javac,'--release','8','-encoding','UTF-8','-classpath',android_jar,'-d',compiled,HERE/'Main.java'],env=env)
    report={'schema':'WAEX_CLASS_METADATA_ART_BUILD_V1','status':'PASS_BUILD_ONLY',
            'workflow_commit':os.environ['GITHUB_SHA'],'run_id':os.environ.get('GITHUB_RUN_ID'),
            'attempt':os.environ.get('GITHUB_RUN_ATTEMPT'),'lock_sha256':digest(LOCK),
            'probe_sha256':digest(HERE/'Main.java'),'tools_sha256':{str(x):digest(x) for x in (java,javac,stdlib,android_jar,d8)},
            'sources':lock['sources'],'variants':{},'art_executed':False,
            'scope':'Complete two production class definitions with explicit host-service boundaries. No app build or hooks.'}
    deps=None
    for variant in VARIANTS:
        root=getattr(a,variant).resolve(); receipt=out/(variant+'-fixture')
        run(out,variant+'-receipt',[sys.executable,runner,'--source-root',root,'--out',receipt,'--kotlinc',kotlin],timeout=420,env=env)
        result=json.loads((receipt/'result.json').read_bytes())
        pins={k.replace('\\','/'):v for k,v in result['production_sources'].items()}
        require(result['result']=='PASS' and result['scenarios']==101 and result['checks']==702 and
                result['failed_scenarios']==0 and result['resource_lookup_boundary_rejected'] is True and
                result['complete_hook_compiled'] is True and result['complete_base_feature_compiled'] is True and
                pins==lock['sources'][variant]['pins'],'Receipt contract or source pins differ')
        dexkit=receipt/'dexkit-2.2.0.jar'
        require(digest(dexkit)==lock['dexkit_jar_sha256'],'DexKit JAR mismatch')
        if deps is None:
            deps=[out/'stdlib-classes-only.jar',out/'dexkit-classes-only.jar']
            class_only(stdlib,deps[0]);class_only(dexkit,deps[1])
            env['WAEX_QA_DEXKIT_JAR']=str(dexkit)
        result_dex=compile_dex(out,variant,receipt/'classes',compiled,deps,java,d8,android_jar)
        result_dex['receipt_sha256']=digest(receipt/'result.json')
        result_dex['host_scenarios']=101;result_dex['host_checks']=702
        report['variants'][variant]=result_dex
        verify_sources(root,lock['sources'][variant]['pins'])
    save(out/'artifact/artifact-manifest.json',report)
    print('PASS_BUILD_ONLY: both variants, no Android execution')
    return 0
if __name__=='__main__':
    raise SystemExit(main())
