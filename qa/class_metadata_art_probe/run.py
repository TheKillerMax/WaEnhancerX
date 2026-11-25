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

def capture_pull(command,target,output,errors,env,timeout=60):
    """Use ADB sync framing, with bounded files, closed stdin and the owned server."""
    require(not target.exists() and not target.is_symlink(),'Readback payload already exists')
    start=time.monotonic();process=None
    def bounded():
        for path,limit in ((target,MAX_JAR_BYTES),(output,MAX_STDERR_BYTES),(errors,MAX_STDERR_BYTES)):
            require(not path.is_symlink(),'Readback output was redirected')
            if path.exists():
                require(path.is_file() and path.stat().st_size<=limit,'Sync readback exceeded its output bound')
    with output.open('xb') as stdout,errors.open('xb') as stderr:
        try:
            process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=stdout,
                                     stderr=stderr,env=env)
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

def verify_pull_identity(target,output,errors,returncode,pin):
    require(returncode==0 and output.stat().st_size==0 and errors.stat().st_size==0,
            'Quiet sync readback failed or emitted diagnostics')
    require(target.is_file() and not target.is_symlink(),'Sync readback payload is missing or redirected')
    size=target.stat().st_size
    require(size==pin['jar_bytes'] and 0<size<=MAX_JAR_BYTES,'Guest JAR size differs')
    observed=digest(target)
    require(observed==pin['jar_sha256'],'Guest JAR identity differs')
    return {'bytes':size,'sha256':observed,'matches_producer':True}

def retain_bounded(path,limit,out):
    """Preserve failed evidence; explicitly label a bounded prefix after overflow."""
    if not path.exists() and not path.is_symlink():return {'exists':False}
    require(path.is_file() and not path.is_symlink(),'Readback evidence was redirected')
    observed=path.stat().st_size
    if observed>limit:
        with path.open('r+b') as stream:stream.truncate(limit)
    return {'exists':True,'path':path.relative_to(out).as_posix(),
            'observed_bytes':observed,'retained_bytes':path.stat().st_size,
            'retained_sha256':digest(path),'truncated_to_bound':observed>limit}

def jar_readback(adb,serial,path,pin,out,label,env):
    """Fresh full sync read before execution/removal; failed bytes remain evidence."""
    require(serial=='emulator-5580' and re.fullmatch(
        r'/data/local/tmp/waex-classmetadata-[a-f0-9]{32}-(?:baseline|candidate)\.jar',path),
        'Readback outside the owned emulator probe path')
    require(re.fullmatch(r'[a-z0-9-]+',label) and type(pin['jar_bytes']) is int
            and 0<pin['jar_bytes']<=MAX_JAR_BYTES
            and re.fullmatch('[a-f0-9]{64}',pin['jar_sha256']),'Invalid readback identity')
    record_path=out/(label+'-readback.json')
    require(not record_path.exists() and not record_path.is_symlink(),'Readback receipt already exists')
    data=out/(label+'-readback-data');data.mkdir()
    target=data/'payload.bin';output=data/'stdout.log';errors=data/'stderr.log'
    # -q suppresses progress only; -Z selects uncompressed sync, including old adbd.
    command=[str(adb),'-s',serial,'pull','-q','-Z',path,str(target)]
    record={'command':command,'method':'adb_pull_sync_uncompressed','status':'BLOCKED',
            'expected_bytes':pin['jar_bytes'],'expected_sha256':pin['jar_sha256'],
            'stdin':'closed','server_environment':'owned_boot_context',
            'payload_retained':False,'returncode':None,'attempts':1}
    start=time.monotonic()
    try:
        record['returncode']=capture_pull(command,target,output,errors,env)
        record.update(verify_pull_identity(target,output,errors,record['returncode'],pin))
        record['status']='PASS'
    except Exception as exc:
        record['failure']=type(exc).__name__+': '+str(exc)
        raise
    finally:
        try:
            for name,file,limit in [('payload',target,MAX_JAR_BYTES),
                                     ('stdout',output,MAX_STDERR_BYTES),('stderr',errors,MAX_STDERR_BYTES)]:
                record[name+'_retention']=retain_bounded(file,limit,out)
            if record['status']=='PASS':
                require(record['payload_retention']['retained_sha256']==pin['jar_sha256'],
                        'Readback payload changed after verification')
                target.unlink()
                record['payload_retention']['removed_matching_duplicate']=True
            else:
                record['payload_retained']=record['payload_retention']['exists']
        except Exception as exc:
            record['status']='BLOCKED';record['retention_failure']=type(exc).__name__+': '+str(exc)
            record['payload_retained']=target.is_file() and not target.is_symlink()
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
    def test_sync_capture_preserves_bytes_environment_and_closed_stdin(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'payload';output=Path(folder)/'stdout';errors=Path(folder)/'errors'
            env=dict(os.environ,WAEX_READBACK_TEST='owned-context')
            script="import os,sys,pathlib;assert os.environ['WAEX_READBACK_TEST']=='owned-context';assert sys.stdin.buffer.read()==b'';pathlib.Path(sys.argv[1]).write_bytes(b'PK\\x00\\xff\\n\\r\\n')"
            self.assertEqual(capture_pull([sys.executable,'-c',script,str(target)],target,output,errors,env),0)
            self.assertEqual(target.read_bytes(),b'PK\x00\xff\n\r\n')
            self.assertEqual(output.read_bytes(),b'');self.assertEqual(errors.read_bytes(),b'')

    def test_sync_capture_timeout_reaps_child(self):
        from unittest.mock import patch
        children=[];original=subprocess.Popen
        def tracked(*args,**kwargs):
            child=original(*args,**kwargs);children.append(child);return child
        with tempfile.TemporaryDirectory() as folder,patch.object(subprocess,'Popen',side_effect=tracked):
            with self.assertRaises(subprocess.TimeoutExpired):
                capture_pull([sys.executable,'-c','import time;time.sleep(60)'],
                             Path(folder)/'payload',Path(folder)/'stdout',Path(folder)/'errors',
                             os.environ.copy(),timeout=0.2)
            self.assertEqual(len(children),1)
            self.assertIsNotNone(children[0].poll())

    def test_sync_capture_bounds_payload_and_both_diagnostic_streams(self):
        for stream,limit in [('payload',MAX_JAR_BYTES),('stdout',MAX_STDERR_BYTES),('stderr',MAX_STDERR_BYTES)]:
            with self.subTest(stream=stream),tempfile.TemporaryDirectory() as folder:
                target=Path(folder)/'payload'
                script=('import sys,pathlib;pathlib.Path(sys.argv[1]).write_bytes(b"x"*'+str(limit+1)+')'
                        if stream=='payload' else 'import sys;sys.'+stream+'.buffer.write(b"x"*'+str(limit+1)+')')
                with self.assertRaisesRegex(RuntimeError,'output bound'):
                    capture_pull([sys.executable,'-c',script,str(target)],target,Path(folder)/'stdout',
                                 Path(folder)/'errors',os.environ.copy())

    def test_sync_identity_rejects_missing_partial_changed_failed_and_diagnostic_reads(self):
        good=b'PK\x00\xff\n\r\n';pin={'jar_bytes':len(good),'jar_sha256':hashlib.sha256(good).hexdigest()}
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'payload';output=Path(folder)/'stdout';errors=Path(folder)/'errors'
            target.write_bytes(good);output.write_bytes(b'');errors.write_bytes(b'')
            self.assertTrue(verify_pull_identity(target,output,errors,0,pin)['matches_producer'])
            for raw,stdout,stderr,rc in [(good[:-1],b'',b'',0),(good+b'x',b'',b'',0),
                                       (b'X'+good[1:],b'',b'',0),(good,b'',b'error',0),
                                       (good,b'Unexpected output',b'',0),(good,b'',b'',1)]:
                target.write_bytes(raw);output.write_bytes(stdout);errors.write_bytes(stderr)
                with self.subTest(raw=raw,stdout=stdout,stderr=stderr,rc=rc),self.assertRaises(RuntimeError):
                    verify_pull_identity(target,output,errors,rc,pin)
            target.unlink();output.write_bytes(b'');errors.write_bytes(b'')
            with self.assertRaisesRegex(RuntimeError,'missing or redirected'):
                verify_pull_identity(target,output,errors,0,pin)

    def test_readback_scope_and_unknown_identity_stop_before_capture(self):
        from unittest.mock import patch
        pin={'jar_bytes':7,'jar_sha256':'a'*64}
        path='/data/local/tmp/waex-classmetadata-'+'a'*32+'-candidate.jar'
        cases=[('phone',path,pin),('emulator-5580',path+';id',pin),
               ('emulator-5580',path.replace('/tmp/','/tmp/../'),pin),
               ('emulator-5580',path,dict(pin,jar_bytes=0)),
               ('emulator-5580',path,dict(pin,jar_bytes=True)),
               ('emulator-5580',path,dict(pin,jar_bytes=MAX_JAR_BYTES+1)),
               ('emulator-5580',path,dict(pin,jar_sha256='unknown'))]
        with tempfile.TemporaryDirectory() as folder,patch(__name__+'.capture_pull') as capture:
            for serial,remote,identity in cases:
                with self.subTest(serial=serial,remote=remote,identity=identity),self.assertRaises(RuntimeError):
                    jar_readback('adb',serial,remote,identity,Path(folder),'identity',{})
            capture.assert_not_called()

    def test_readback_uses_fresh_bytes_and_preserves_failed_identity(self):
        from unittest.mock import patch
        good=b'PK\x00\xff\n\r\n';pin={'jar_bytes':len(good),'jar_sha256':hashlib.sha256(good).hexdigest()}
        remote='/data/local/tmp/waex-classmetadata-'+'b'*32+'-baseline.jar'
        env={'ADB_SERVER_SOCKET':'tcp:localhost:5999'};seen=[]
        def captured(command,target,output,errors,actual_env,timeout=60):
            self.assertEqual(command,['adb','-s','emulator-5580','pull','-q','-Z',remote,str(target)])
            self.assertIs(actual_env,env);seen.append(command)
            target.write_bytes(good if len(seen)==1 else b'X'+good[1:])
            output.write_bytes(b'');errors.write_bytes(b'');return 0
        with tempfile.TemporaryDirectory() as folder,patch(__name__+'.capture_pull',side_effect=captured):
            out=Path(folder)
            self.assertEqual(jar_readback('adb','emulator-5580',remote,pin,out,'before',env)['status'],'PASS')
            self.assertFalse((out/'before-readback-data/payload.bin').exists())
            with self.assertRaisesRegex(RuntimeError,'identity differs'):
                jar_readback('adb','emulator-5580',remote,pin,out,'cleanup',env)
            record=json.loads((out/'cleanup-readback.json').read_bytes())
            self.assertEqual(record['status'],'BLOCKED');self.assertIn('identity differs',record['failure'])
            self.assertTrue(record['payload_retained']);self.assertEqual(record['attempts'],1)
            self.assertEqual((out/record['payload_retention']['path']).read_bytes(),b'X'+good[1:])
            self.assertEqual(len(seen),2)
            with self.assertRaisesRegex(RuntimeError,'receipt already exists'):
                jar_readback('adb','emulator-5580',remote,pin,out,'cleanup',env)
            self.assertEqual(len(seen),2)

    def test_sync_capture_refuses_existing_or_redirected_destination_before_process(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder,patch.object(subprocess,'Popen') as popen:
            root=Path(folder);target=root/'payload';target.write_bytes(b'preserve')
            with self.assertRaises(RuntimeError):
                capture_pull(['never'],target,root/'stdout',root/'stderr',{})
            self.assertEqual(target.read_bytes(),b'preserve')
            target.unlink();target.symlink_to(root/'missing')
            with self.assertRaises(RuntimeError):
                capture_pull(['never'],target,root/'stdout',root/'stderr',{})
            popen.assert_not_called()

    def test_failed_oversized_evidence_keeps_a_labelled_bounded_prefix(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder);path=out/'payload';path.write_bytes(b'original-long-data')
            row=retain_bounded(path,8,out)
            self.assertEqual(row['observed_bytes'],18);self.assertEqual(row['retained_bytes'],8)
            self.assertTrue(row['truncated_to_bound']);self.assertEqual(path.read_bytes(),b'original')
            self.assertEqual(row['retained_sha256'],hashlib.sha256(b'original').hexdigest())

    def test_sync_process_zero_exit_still_requires_complete_identity_and_empty_diagnostics(self):
        good=b'PK'+bytes(range(64));pin={'jar_bytes':len(good),'jar_sha256':hashlib.sha256(good).hexdigest()}
        remote='/data/local/tmp/waex-classmetadata-'+'c'*32+'-candidate.jar'
        program='''#!/usr/bin/env python3
import os,pathlib,sys
args=sys.argv[1:]
if args[:5]!=['-s','emulator-5580','pull','-q','-Z']:raise RuntimeError('Wrong sync arguments')
if os.environ.get('ADB_SERVER_SOCKET')!='tcp:localhost:5999':raise RuntimeError('Lost owned server')
root=pathlib.Path(__file__).parent
with (root/'calls').open('a') as stream:stream.write('one\\n')
mode=os.environ['WAEX_PULL_TEST_MODE'];good=b'PK'+bytes(range(64));raw=good
if mode=='short-rc-zero':raw=good[:-28]
if mode=='changed-rc-zero':raw=b'X'+good[1:]
if mode!='missing-rc-zero':pathlib.Path(args[-1]).write_bytes(raw)
if mode=='stdout-rc-zero':sys.stdout.write('unexpected output')
if mode=='stderr-rc-zero':sys.stderr.write('unexpected diagnostic')
sys.exit(3 if mode=='failed-with-complete-payload' else 0)
'''
        modes=['pass','short-rc-zero','changed-rc-zero','missing-rc-zero','stdout-rc-zero',
               'stderr-rc-zero','failed-with-complete-payload']
        for mode in modes:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);fake=root/'adb-fixture';fake.write_text(program);fake.chmod(0o755)
                env=dict(os.environ,ADB_SERVER_SOCKET='tcp:localhost:5999',WAEX_PULL_TEST_MODE=mode)
                if mode=='pass':
                    self.assertEqual(jar_readback(fake,'emulator-5580',remote,pin,root,'read',env)['status'],'PASS')
                else:
                    with self.assertRaises(RuntimeError):jar_readback(fake,'emulator-5580',remote,pin,root,'read',env)
                record=json.loads((root/'read-readback.json').read_bytes())
                self.assertEqual(record['status'],'PASS' if mode=='pass' else 'BLOCKED')
                self.assertEqual(record['attempts'],1);self.assertEqual((root/'calls').read_text(),'one\n')
                payload=root/'read-readback-data/payload.bin'
                self.assertEqual(payload.exists(),mode not in ('pass','missing-rc-zero'))
                if mode=='short-rc-zero':
                    self.assertEqual(payload.read_bytes(),good[:-28])
                    self.assertEqual(record['payload_retention']['observed_bytes'],len(good)-28)

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
