#!/usr/bin/env python3
"""Run the neutral ClassValue linkage probe only inside the existing owned Linux AVD."""
import argparse, hashlib, json, os, re, secrets, subprocess, sys, tempfile, time, unittest
from pathlib import Path
QA = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(QA))
HERE=Path(__file__).resolve().parent
VARIANTS=('baseline','candidate')
TARGET_NAMES=('api24','api30','api33','api34')
CLASSES=('com.waenhancer.xposed.core.wa.WaJid','com.waenhancer.xposed.features.privacy.HideReceiptsHook')
def require(ok,msg):
    if not ok: raise RuntimeError(msg)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
MAX_JAR_BYTES=8*1024**2
MAX_STDERR_BYTES=65536

def capture_binary(command,target,errors,env,timeout=60):
    """Read raw ADB bytes with the owned server environment and bounded lifetime."""
    start=time.monotonic();process=None
    def bounded():
        require(target.stat().st_size<=MAX_JAR_BYTES and errors.stat().st_size<=MAX_STDERR_BYTES,
                'Binary readback exceeded its output bound')
    with target.open('xb') as output,errors.open('xb') as diagnostics:
        try:
            process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=output,
                                     stderr=diagnostics,env=env)
            while process.poll() is None:
                bounded()
                remaining=timeout-(time.monotonic()-start)
                if remaining<=0:raise subprocess.TimeoutExpired(command,timeout)
                try:process.wait(timeout=min(0.05,remaining))
                except subprocess.TimeoutExpired:pass
            bounded()
            return process.returncode
        finally:
            if process is not None and process.poll() is None:
                process.kill();process.wait(timeout=5)

def verify_binary_identity(target,errors,returncode,pin):
    require(returncode==0 and errors.stat().st_size==0,'Binary readback failed or emitted diagnostics')
    size=target.stat().st_size
    require(size==pin['jar_bytes'] and 0<size<=MAX_JAR_BYTES,'Guest JAR size differs')
    observed=digest(target)
    require(observed==pin['jar_sha256'],'Guest JAR identity differs')
    return {'bytes':size,'sha256':observed,'matches_producer':True}

def jar_readback(adb,serial,path,pin,out,label,env):
    """Fresh producer identity before execution/removal, without guest hash utilities."""
    require(serial=='emulator-5580' and re.fullmatch(
        r'/data/local/tmp/waex-classmetadata-[a-f0-9]{32}-(?:baseline|candidate)\.jar',path),
        'Readback outside the owned emulator probe path')
    require(re.fullmatch(r'[a-z0-9-]+',label) and type(pin['jar_bytes']) is int
            and 0<pin['jar_bytes']<=MAX_JAR_BYTES
            and re.fullmatch('[a-f0-9]{64}',pin['jar_sha256']),'Invalid readback identity')
    record_path=out/(label+'-readback.json')
    require(not record_path.exists(),'Readback receipt already exists')
    command=[str(adb),'-s',serial,'exec-out','/system/bin/cat',path]
    record={'command':command,'method':'adb_exec_out_cat_binary','status':'BLOCKED',
            'expected_bytes':pin['jar_bytes'],'expected_sha256':pin['jar_sha256'],
            'stdin':'closed','server_environment':'owned_boot_context',
            'payload_retained':False,'returncode':None}
    start=time.monotonic()
    try:
        # Keep receipts for every fresh read; identical JAR payloads are in the build artifact.
        with tempfile.TemporaryDirectory(prefix='waex-classmeta-readback-') as folder:
            target=Path(folder)/'payload.bin';errors=Path(folder)/'stderr.bin'
            try:
                record['returncode']=capture_binary(command,target,errors,env)
                record.update(verify_binary_identity(target,errors,record['returncode'],pin))
                record['status']='PASS'
            finally:
                record['stdout_bytes']=target.stat().st_size if target.exists() else 0
                record['stderr_bytes']=errors.stat().st_size if errors.exists() else 0
                if errors.exists():
                    with errors.open('rb') as stream:
                        record['stderr']=stream.read(MAX_STDERR_BYTES).decode('utf8',errors='replace')
    except Exception as exc:
        record['failure']=type(exc).__name__+': '+str(exc)
        raise
    finally:
        record['seconds']=round(time.monotonic()-start,3)
        with record_path.open('x',encoding='utf8') as stream:
            json.dump(record,stream,indent=2);stream.write('\n')
    return record

def markers(nonce,variant,api):
    require(re.fullmatch('[a-f0-9]{32}',nonce) and variant in VARIANTS and api in (24,30,33,34),'Invalid oracle identity')
    old=variant=='baseline' and api<34
    status='EXPECTED_CLASSVALUE_LINKAGE_ERROR' if old else 'INITIALIZED'
    checks=7 if old else 14 if variant=='candidate' else 13
    return ['API|'+str(api)+'|CLASSVALUE|'+str(api>=34).lower(),
            *['CLASS|'+c+'|'+status for c in CLASSES],
            'WAEX_CLASS_METADATA_ART|'+nonce+'|'+variant+'|'+str(api)+'|'+str(checks)+'|PASS']
def validate_output(text,nonce,variant,api):
    actual=[l.strip() for l in text.splitlines() if l.startswith(('API|','CLASS|','WAEX_CLASS_METADATA_ART|'))]
    require(actual==markers(nonce,variant,api),'Missing, reordered, duplicate or incorrect runtime markers')
    require('FATAL EXCEPTION' not in text and 'Exception in thread' not in text and 'java.lang.AssertionError' not in text,'Unexpected runtime exception')
    return int(actual[-1].split('|')[-2])
class HostTests(unittest.TestCase):
    def test_binary_capture_preserves_bytes_environment_and_closed_stdin(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'payload';errors=Path(folder)/'errors'
            env=dict(os.environ,WAEX_READBACK_TEST='owned-context')
            script="import os,sys;assert os.environ['WAEX_READBACK_TEST']=='owned-context';assert sys.stdin.buffer.read()==b'';sys.stdout.buffer.write(b'PK\\x00\\xff\\n\\r\\n')"
            self.assertEqual(capture_binary([sys.executable,'-c',script],target,errors,env),0)
            self.assertEqual(target.read_bytes(),b'PK\x00\xff\n\r\n')
            self.assertEqual(errors.read_bytes(),b'')

    def test_binary_capture_timeout_reaps_child(self):
        from unittest.mock import patch
        children=[];original=subprocess.Popen
        def tracked(*args,**kwargs):
            child=original(*args,**kwargs);children.append(child);return child
        with tempfile.TemporaryDirectory() as folder,patch.object(subprocess,'Popen',side_effect=tracked):
            with self.assertRaises(subprocess.TimeoutExpired):
                capture_binary([sys.executable,'-c','import time;time.sleep(60)'],
                               Path(folder)/'payload',Path(folder)/'errors',os.environ.copy(),timeout=0.2)
            self.assertEqual(len(children),1)
            self.assertIsNotNone(children[0].poll())

    def test_binary_capture_output_bounds(self):
        for stream,limit in [('stdout',MAX_JAR_BYTES),('stderr',MAX_STDERR_BYTES)]:
            with self.subTest(stream=stream),tempfile.TemporaryDirectory() as folder:
                script='import sys;sys.'+stream+'.buffer.write(b"x"*'+str(limit+1)+')'
                with self.assertRaisesRegex(RuntimeError,'output bound'):
                    capture_binary([sys.executable,'-c',script],Path(folder)/'payload',
                                   Path(folder)/'errors',os.environ.copy())

    def test_binary_identity_rejects_changed_partial_failed_and_diagnostic_reads(self):
        good=b'PK\x00\xff\n\r\n';pin={'jar_bytes':len(good),'jar_sha256':hashlib.sha256(good).hexdigest()}
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'payload';errors=Path(folder)/'errors'
            target.write_bytes(good);errors.write_bytes(b'')
            self.assertTrue(verify_binary_identity(target,errors,0,pin)['matches_producer'])
            for raw,diagnostic,rc in [(good[:-1],b'',0),(good+b'x',b'',0),
                                      (b'X'+good[1:],b'',0),(good,b'error',0),(good,b'',1)]:
                target.write_bytes(raw);errors.write_bytes(diagnostic)
                with self.subTest(raw=raw,diagnostic=diagnostic,rc=rc),self.assertRaises(RuntimeError):
                    verify_binary_identity(target,errors,rc,pin)

    def test_readback_scope_and_unknown_identity_stop_before_capture(self):
        from unittest.mock import patch
        pin={'jar_bytes':7,'jar_sha256':'a'*64}
        path='/data/local/tmp/waex-classmetadata-'+'a'*32+'-candidate.jar'
        cases=[('phone',path,pin),('emulator-5580',path+';id',pin),
               ('emulator-5580',path.replace('/tmp/','/tmp/../'),pin),
               ('emulator-5580',path,dict(pin,jar_bytes=0)),
               ('emulator-5580',path,dict(pin,jar_bytes=MAX_JAR_BYTES+1)),
               ('emulator-5580',path,dict(pin,jar_sha256='unknown'))]
        with tempfile.TemporaryDirectory() as folder,patch(__name__+'.capture_binary') as capture:
            for serial,remote,identity in cases:
                with self.subTest(serial=serial,remote=remote,identity=identity),self.assertRaises(RuntimeError):
                    jar_readback('adb',serial,remote,identity,Path(folder),'identity',{})
            capture.assert_not_called()

    def test_readback_uses_fresh_bytes_and_records_failed_identity(self):
        from unittest.mock import patch
        good=b'PK\x00\xff\n\r\n';pin={'jar_bytes':len(good),'jar_sha256':hashlib.sha256(good).hexdigest()}
        remote='/data/local/tmp/waex-classmetadata-'+'b'*32+'-baseline.jar'
        env={'ADB_SERVER_SOCKET':'tcp:localhost:5999'};seen=[]
        def captured(command,target,errors,actual_env,timeout=60):
            self.assertEqual(command,['adb','-s','emulator-5580','exec-out','/system/bin/cat',remote])
            self.assertIs(actual_env,env);seen.append(command)
            target.write_bytes(good if len(seen)==1 else b'X'+good[1:]);errors.write_bytes(b'');return 0
        with tempfile.TemporaryDirectory() as folder,patch(__name__+'.capture_binary',side_effect=captured):
            out=Path(folder)
            self.assertEqual(jar_readback('adb','emulator-5580',remote,pin,out,'before',env)['status'],'PASS')
            with self.assertRaisesRegex(RuntimeError,'identity differs'):
                jar_readback('adb','emulator-5580',remote,pin,out,'cleanup',env)
            record=json.loads((out/'cleanup-readback.json').read_bytes())
            self.assertEqual(record['status'],'BLOCKED');self.assertIn('identity differs',record['failure'])
            self.assertEqual(len(seen),2)
            with self.assertRaisesRegex(RuntimeError,'receipt already exists'):
                jar_readback('adb','emulator-5580',remote,pin,out,'cleanup',env)
            self.assertEqual(len(seen),2)

    def test_expected(self):
        for api in (24,30,33,34):
            for variant in VARIANTS:
                with self.subTest(api=api,variant=variant):
                    n='a'*32; lines=markers(n,variant,api)
                    self.assertEqual(validate_output('\n'.join(lines),n,variant,api),7 if api<34 and variant=='baseline' else 14 if variant=='candidate' else 13)
    def test_fail_closed(self):
        n='a'*32; lines=markers(n,'candidate',24)
        for damaged in [lines[:-1],lines+lines[-1:],lines[::-1],['API|25|CLASSVALUE|false',*lines[1:]],
                        [*lines[:-1],lines[-1].replace(n,'b'*32)],
                        [*lines[:-1],lines[-1].replace('|14|','|13|')],
                        [lines[0],lines[1].replace('INITIALIZED','EXPECTED_CLASSVALUE_LINKAGE_ERROR'),*lines[2:]],
                        lines+['java.lang.AssertionError: hidden failure']]:
            with self.subTest(damaged=damaged),self.assertRaises(RuntimeError):
                validate_output('\n'.join(damaged),n,'candidate',24)
    def test_exact_line_ending_projections_and_negatives(self):
        from build import verify_text_pin
        lf=b'first\nsecond\n'; crlf=lf.replace(b'\n',b'\r\n')
        projections={'lf':hashlib.sha256(lf).hexdigest(),'crlf':hashlib.sha256(crlf).hexdigest()}
        with tempfile.TemporaryDirectory() as folder:
            f=Path(folder)/'source.java'
            for raw in (lf,crlf):
                f.write_bytes(raw)
                self.assertEqual(verify_text_pin(f,projections),hashlib.sha256(raw).hexdigest())
            for raw in (lf[:-1],lf+b'\n',lf.replace(b'first',b'first '),b'first\r\nsecond\n',
                        b'first\rsecond\r',b'\xef\xbb\xbf'+lf,lf.replace(b'second',b'other')):
                f.write_bytes(raw)
                with self.subTest(raw=raw),self.assertRaises(RuntimeError):
                    verify_text_pin(f,projections)
    def test_variant_boundary(self):
        n='a'*32
        with self.assertRaises(RuntimeError):
            validate_output('\n'.join(markers(n,'baseline',24)),n,'candidate',24)
        with self.assertRaises(RuntimeError):
            validate_output('\n'.join(markers(n,'baseline',33)),n,'baseline',34)
def main():
    from android_emulator_lab_pilot import main as boot_main, invoke
    from android_emulator_lab_matrix import TARGETS, checked_lock as matrix_lock
    from android_emulator_lab_preflight import save
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',choices=TARGET_NAMES,required=True)
    parser.add_argument('--lock',type=Path,required=True)
    parser.add_argument('--artifact',type=Path,required=True)
    parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--out',type=Path,required=True)
    a=parser.parse_args()
    folder=a.artifact.resolve();manifest=folder/'artifact-manifest.json'
    require({p.name for p in folder.iterdir()}=={'artifact-manifest.json',*[v+'-art-probe.jar' for v in VARIANTS]},'Unexpected artifact files')
    require(re.fullmatch('[a-f0-9]{64}',a.manifest_sha256) and digest(manifest)==a.manifest_sha256,'Independent producer manifest hash differs')
    built=json.loads(manifest.read_bytes())
    lock=json.loads((HERE/'lock.json').read_bytes())
    require(built['schema']=='WAEX_CLASS_METADATA_ART_BUILD_V2' and built['status']=='PASS_BUILD_ONLY' and
            built['workflow_commit']==os.environ.get('GITHUB_SHA') and built['run_id']==os.environ.get('GITHUB_RUN_ID') and
            built['attempt']==os.environ.get('GITHUB_RUN_ATTEMPT') and built['lock_sha256']==digest(HERE/'lock.json') and
            built['probe_sha256']==digest(HERE/'Main.java') and built['sources']==lock['sources'] and built['art_executed'] is False,'Producer provenance differs')
    require(set(built['variants'])==set(VARIANTS),'Producer variants differ')
    require(lock['schema']=='WAEX_CLASS_METADATA_ART_LOCK_V2','Wrong source lock schema')
    def verify_checkout(actual, projections, prior):
        require(set(actual)==set(projections)==set(prior),'Checkout receipt coverage differs')
        require(all(set(projections[k])=={'lf','crlf'} and prior[k] in projections[k].values()
                    and actual[k] in projections[k].values() for k in projections),'Checkout receipt hash differs')
    verify_checkout(built['fixture_checkout_sha256'],lock['fixture_checkout_sha256_by_projection'],
                    {'runner':lock['runner_sha256'],'fixture':lock['fixture_sha256']})
    for v in VARIANTS:
        entry=lock['sources'][v]
        verify_checkout(built['variants'][v]['checkout_source_sha256'],entry['checkout_sha256_by_projection'],entry['pins'])
    for v in VARIANTS:
        p=folder/(v+'-art-probe.jar'); identity=built['variants'][v]
        require(not p.is_symlink() and digest(p)==identity['jar_sha256'] and p.stat().st_size==identity['jar_bytes'] and
                0<p.stat().st_size<=8*1024**2 and identity['host_checks']==702 and identity['host_scenarios']==101,'Artifact identity differs')
    def after_boot(ctx):
        require(ctx.serial=='emulator-5580' and ctx.target==a.target and ctx.api in (24,30,33,34) and
                ctx.application_page_size_bytes==4096,'Unexpected boot context')
        base=[str(ctx.adb),'-s',ctx.serial]
        def command(label,tail,timeout=30):
            _,text=invoke(ctx.out,label,base+tail,ctx.env,timeout=timeout)
            return text.strip()
        require(command('classmeta-qemu',['shell','getprop','ro.kernel.qemu'])=='1','Not emulator')
        require(command('classmeta-abi',['shell','getprop','ro.product.cpu.abi'])=='x86_64','Unexpected ABI')
        require(command('classmeta-sdk',['shell','getprop','ro.build.version.sdk'])==str(ctx.api),'Unexpected SDK')
        require(command('classmeta-uid',['shell','id','-u'])=='2000','Shell UID required')
        receipts={}
        for v in VARIANTS:
            n=secrets.token_hex(16);path='/data/local/tmp/waex-classmetadata-'+n+'-'+v+'.jar'
            source=folder/(v+'-art-probe.jar'); pin=built['variants'][v]
            def absent(label):
                require(command(label,['shell','if [ ! -e '+path+' ] && [ ! -L '+path+' ]; then echo ABSENT; else echo PRESENT; fi'])=='ABSENT','Probe path not absent')
            def identity(label):
                return jar_readback(ctx.adb,ctx.serial,path,pin,ctx.out,label,ctx.env)
            absent(v+'-before')
            row={'nonce':n,'api':ctx.api,'variant':v,'jar_sha256':pin['jar_sha256'],'status':'BLOCKED','cleanup_verified':False}
            receipts[v]=row
            try:
                command(v+'-push',['push',str(source),path],60)
                identity(v+'-identity')
                command(v+'-read-only',['shell','chmod','0444',path])
                identity(v+'-before-execution')
                output=command(v+'-art',['shell','CLASSPATH='+path,'app_process','/system/bin','org.lab.waex.qa.classmetadata.Main',n,v,str(ctx.api)],90)
                row['checks']=validate_output(output,n,v,ctx.api)
                row['status']='PASS'
            except Exception as exc:
                row['failure']=type(exc).__name__+': '+str(exc)
                raise
            finally:
                try:
                    # Refuse to remove any path unless its current bytes match our producer.
                    identity(v+'-cleanup-identity')
                    command(v+'-remove',['shell','rm','--',path])
                    absent(v+'-after')
                    row['cleanup_verified']=True
                except Exception as exc:
                    row['cleanup_failure']=type(exc).__name__+': '+str(exc)
                    raise
                finally:
                    save(ctx.out,'class-metadata-receipts.json',receipts)
            require(row['status']=='PASS' and row['cleanup_verified'],'Runtime or cleanup failed')
        return {'status':'PASS','variants':receipts,'scope':'Isolated ART class-linkage/cache probes, no full app or hooks'}
    return boot_main(['--target',a.target,'--lock',str(a.lock),'--out',str(a.out)],
                     targets={name:TARGETS[name] for name in TARGET_NAMES},read_lock=matrix_lock,
                     boot_action=after_boot,phase='class_metadata_art',result_name='class-metadata-art-result.json',
                     limits='ClassValue linkage and selected cache behavior only; no device/WAEX app/Xposed/DSU claim.')
if __name__=='__main__':
    if sys.argv[1:]==['--host-tests']:
        unittest.main(argv=[sys.argv[0]],verbosity=2)
    else:raise SystemExit(main())
