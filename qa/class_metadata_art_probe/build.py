#!/usr/bin/env python3
"""Build the exact baseline/candidate class-linkage probes, not the WAEX application."""
import argparse, hashlib, json, os, re, subprocess, sys, zipfile
from pathlib import Path
from toolchain import prepare as prepare_toolchain, verify_after_build

HERE = Path(__file__).resolve().parent
LOCK = HERE / 'lock.json'
VARIANTS = ('baseline', 'candidate')
def require(ok, msg):
    if not ok:
        raise RuntimeError(msg)
def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def checked_dexkit_input(path, expected_sha256):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'DexKit input must be a regular non-symlink file')
    require(path.stat().st_size == 827109 and digest(path) == expected_sha256,
            'Supplied DexKit input differs from the existing compiler lock')
    return {'path': str(path.resolve()), 'bytes': path.stat().st_size, 'sha256': digest(path)}
def save(p, value):
    p.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
def run(out, name, args, timeout=180, env=None):
    result = subprocess.run(list(map(str,args)), capture_output=True, timeout=timeout, env=env)
    (out/(name+'.stdout.log')).write_bytes(result.stdout)
    (out/(name+'.stderr.log')).write_bytes(result.stderr)
    require(result.returncode == 0, name+' failed: '+result.stderr.decode(errors='replace')[-2000:])
    return result.stdout.decode(errors='replace').strip()
def verify_text_pin(path, projections):
    require(path.is_file() and not path.is_symlink(), 'Source missing/not regular: '+str(path))
    require(set(projections)=={'lf','crlf'} and
            all(re.fullmatch('[a-f0-9]{64}',v) for v in projections.values()), 'Invalid text pin')
    raw=path.read_bytes()
    require(not raw.startswith(b'\xef\xbb\xbf'), 'Unexpected UTF-8 BOM: '+str(path))
    raw.decode('utf-8',errors='strict')
    lf=raw.replace(b'\r\n',b'\n')
    require(b'\r' not in lf and raw in (lf,lf.replace(b'\n',b'\r\n')),
            'Mixed/bare carriage returns: '+str(path))
    observed=hashlib.sha256(raw).hexdigest()
    require(observed in projections.values() and hashlib.sha256(lf).hexdigest()==projections['lf'],
            'Source mismatch: '+str(path)+' actual='+observed)
    return observed
def verify_sources(root, entry):
    pins=entry['pins']; projections=entry['checkout_sha256_by_projection']
    require(set(pins)==set(projections), 'Source projection coverage differs')
    require(all(pins[rel] in projections[rel].values() for rel in pins), 'Prior exact pins not retained')
    return {rel:verify_text_pin(root/rel,projections[rel]) for rel in pins}
def zip_member(archive, name, body):
    entry=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
    entry.compress_type=archive.compression
    entry.create_system=3
    entry.external_attr=0o100644 << 16
    archive.writestr(entry,body)
def require_quiet_d8(out, variant):
    require(all((out/(variant+'-d8.'+stream+'.log')).read_bytes()==b''
                for stream in ('stdout','stderr')), 'D8 emitted diagnostics; inspect preserved logs')
def compile_dex(out, variant, classes, probe_classes, deps, java, d8, android_jar, env=None):
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
            zip_member(z,rel,p.read_bytes())
        for p in sorted(probe_classes.rglob('*.class')):
            rel = p.relative_to(probe_classes).as_posix()
            require(rel not in class_inputs, 'Duplicate probe class')
            class_inputs[rel] = digest(p)
            zip_member(z,rel,p.read_bytes())
    require(any(n.endswith('/WaJid.class') for n in class_inputs) and
            any(n.endswith('/HideReceiptsHook.class') for n in class_inputs), 'Real target classes missing')
    dexout=out/(variant+'-dex'); dexout.mkdir()
    run(out,variant+'-d8',[java,'-cp',d8,'com.android.tools.r8.D8','--release','--min-api','24',
                           '--lib',android_jar,'--output',dexout,dst,*deps],env=env)
    require_quiet_d8(out,variant)
    dexes=sorted(dexout.glob('classes*.dex'))
    require(len(dexes)==1 and dexes[0].name=='classes.dex', 'Single DEX required')
    body=dexes[0].read_bytes()
    require(body[:4]==b'dex\n' and b'Lcom/waenhancer/xposed/core/wa/WaJid;' in body and
            b'Lcom/waenhancer/xposed/features/privacy/HideReceiptsHook;' in body, 'DEX target descriptors missing')
    require((b'Ljava/lang/ClassValue;' in body)==(variant=='baseline'), 'ClassValue descriptor differs from variant')
    artifact=out/'artifact'; artifact.mkdir(exist_ok=True)
    jar=artifact/(variant+'-art-probe.jar')
    with zipfile.ZipFile(jar,'x',zipfile.ZIP_STORED) as z:
        zip_member(z,'classes.dex',body)
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
                seen.add(n); zip_member(zo,n,zi.read(member))
        require(bool(seen),'Dependency has no classes')
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--sdk',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--java-home',type=Path,required=True)
    p.add_argument('--dexkit-jar',type=Path)
    a=p.parse_args()
    a.out=a.out.resolve(); a.out.mkdir(parents=True,exist_ok=False)
    out=a.out
    lock=json.loads(LOCK.read_bytes())
    require(os.environ.get('GITHUB_REPOSITORY')=='TheKillerMax/WaEnhancerX' and
            os.environ.get('GITHUB_REF')=='refs/heads/lab/classmetadata-current-source-20261125',
            'Only reviewed fork lab build allowed')
    require(re.fullmatch('[a-f0-9]{40}',os.environ.get('GITHUB_SHA','')), 'Missing workflow commit')
    require(digest(HERE/'Main.java')==lock['probe_sha256'],'Probe source changed')
    require(lock['schema']=='WAEX_CLASS_METADATA_ART_LOCK_V2','Wrong source lock schema')
    checked={}
    for variant in VARIANTS:
        root=getattr(a,variant).resolve()
        require(run(out,variant+'-git',['git','-C',root,'rev-parse','HEAD'])==lock['sources'][variant]['commit'], 'Source revision mismatch')
        checked[variant]=verify_sources(root,lock['sources'][variant])
    runner=a.candidate/'qa/test_receipt_stanza_runtime.py'
    fixture=a.candidate/'qa/fixtures/ReceiptStanzaRuntimeChecks.java'
    fixture_paths={'runner':runner,'fixture':fixture}
    fixture_projections=lock['fixture_checkout_sha256_by_projection']
    require(set(fixture_projections)==set(fixture_paths) and
            all(lock[k+'_sha256'] in fixture_projections[k].values() for k in fixture_paths),
            'Prior runner/fixture pins not retained')
    fixture_checkout={k:verify_text_pin(p,fixture_projections[k]) for k,p in fixture_paths.items()}
    supplied_dexkit = None
    if a.dexkit_jar is not None:
        supplied_dexkit = checked_dexkit_input(a.dexkit_jar, lock['dexkit_jar_sha256'])
    kotlin,env,toolchain_receipt=prepare_toolchain(out,a.java_home)
    env.pop('WAEX_QA_DEXKIT_JAR',None)
    if supplied_dexkit is not None:
        env['WAEX_QA_DEXKIT_JAR'] = supplied_dexkit['path']
    stdlib=Path(kotlin).resolve().parents[1]/'lib/kotlin-stdlib.jar'
    java=a.java_home/'bin/java'; javac=a.java_home/'bin/javac'
    android_jar=a.sdk/'platforms/android-36/android.jar'; d8=a.sdk/'build-tools/36.0.0/lib/d8.jar'
    for tool in (java,javac,stdlib,android_jar,d8):
        require(tool.is_file(),'Missing tool/dependency: '+str(tool))
    run(out,'java-version',[java,'-version'],env=env)
    run(out,'kotlin-version',[kotlin,'-version'],env=env)
    compiled=out/'probe-classes';compiled.mkdir()
    run(out,'probe-javac',[javac,'--release','8','-encoding','UTF-8','-classpath',android_jar,'-d',compiled,HERE/'Main.java'],env=env)
    report={'schema':'WAEX_CLASS_METADATA_ART_BUILD_V2','status':'PASS_BUILD_ONLY',
            'workflow_commit':os.environ['GITHUB_SHA'],'run_id':os.environ.get('GITHUB_RUN_ID'),
            'attempt':os.environ.get('GITHUB_RUN_ATTEMPT'),'lock_sha256':digest(LOCK),
            'probe_sha256':digest(HERE/'Main.java'),'tools_sha256':{str(x):digest(x) for x in (java,javac,stdlib,android_jar,d8)},
            'sources':lock['sources'],'fixture_checkout_sha256':fixture_checkout,'variants':{},'art_executed':False,
            'kotlin_toolchain':toolchain_receipt,'builder_sha256':digest(Path(__file__)),
            'supplied_dexkit_input':supplied_dexkit,
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
                pins==checked[variant],'Receipt contract or source pins differ')
        dexkit=receipt/'dexkit-2.2.0.jar'
        require(digest(dexkit)==lock['dexkit_jar_sha256'],'DexKit JAR mismatch')
        if deps is None:
            deps=[out/'stdlib-classes-only.jar',out/'dexkit-classes-only.jar']
            class_only(stdlib,deps[0]);class_only(dexkit,deps[1])
            env['WAEX_QA_DEXKIT_JAR']=str(dexkit)
        result_dex=compile_dex(out,variant,receipt/'classes',compiled,deps,java,d8,android_jar,env=env)
        result_dex['receipt_sha256']=digest(receipt/'result.json')
        result_dex['host_scenarios']=101;result_dex['host_checks']=702
        result_dex['checkout_source_sha256']=checked[variant]
        report['variants'][variant]=result_dex
        require(verify_sources(root,lock['sources'][variant])==checked[variant], 'Checkout changed during compilation')
        require({k:verify_text_pin(p,fixture_projections[k]) for k,p in fixture_paths.items()}==fixture_checkout,
                'Receipt fixture changed during compilation')
    verify_after_build(kotlin,toolchain_receipt)
    if supplied_dexkit is not None:
        require(checked_dexkit_input(a.dexkit_jar, lock['dexkit_jar_sha256']) == supplied_dexkit,
                'Supplied DexKit input changed during compilation')
    require(digest(Path(__file__))==report['builder_sha256'],'Build recipe changed')
    save(out/'artifact/artifact-manifest.json',report)
    print('PASS_BUILD_ONLY: both variants, no Android execution')
    return 0
if __name__=='__main__':
    raise SystemExit(main())
