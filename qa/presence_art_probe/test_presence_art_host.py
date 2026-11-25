#!/usr/bin/env python3
"""Controlled ADB protocol fixtures; no Android, real ADB or network access."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

FAKE_ADB=r'''#!/usr/bin/env python3
import base64,json,pathlib,shutil,sys
root=pathlib.Path(__file__).resolve().parent
config=json.loads((root/'config.json').read_text());mode=config['mode'];api=config['api']
args=sys.argv[1:]
with (root/'calls.jsonl').open('a') as stream:stream.write(json.dumps(args)+'\n')
assert args[:2]==['-s','emulator-5554']
cmd=args[2:];installed=root/'installed.flag';apk=root/'installed-apk';instrumented=root/'instrumented.flag'
package='org.waex.qa.presence.host'
remote='/data/app/'+package+'-1/base.apk'
if mode=='legacy_wrong_package_path':remote='/data/app/org.other-1/base.apk'
if mode=='legacy_empty_suffix':remote='/data/app/'+package+'-/base.apk'
if mode=='legacy_split_path':remote='/data/app/'+package+'-1/split.apk'
if mode=='legacy_traversal_path':remote='/data/app/'+package+'-1/../base.apk'
if cmd==['get-state']:print('device')
elif cmd==['shell','getprop','ro.kernel.qemu']:print('0' if mode=='non_qemu' else '1')
elif cmd==['shell','getprop','ro.build.version.sdk']:print('25' if mode=='wrong_api' else str(api))
elif cmd==['shell','pm','path',package]:
    if mode=='cleanup_unknown_path' and instrumented.exists():
        print('package manager unavailable',file=sys.stderr);raise SystemExit(20)
    if installed.exists() or mode=='preexisting':print('package:'+remote)
    else:raise SystemExit(1)
elif cmd[:1]==['install']:
    assert cmd[1]=='-t' and '-r' not in cmd
    installed.write_text('created');shutil.copyfile(cmd[2],apk)
    if mode in ['installed_mismatch','ambiguous_mismatch']:apk.write_bytes(b'different bytes')
    if mode=='installed_hash_mismatch':apk.write_bytes(b'!'+apk.read_bytes()[1:])
    if mode in ['ambiguous_install','ambiguous_mismatch']:print('transport lost after installation');raise SystemExit(1)
    print('Success')
elif cmd[:1]==['pull']:
    assert cmd[1]==remote
    if mode.startswith('legacy_'):
        message="adb: error: remote object '"+remote+"' does not exist"
        if mode=='legacy_unrelated_error':message='adb: error: permission denied'
        if mode=='legacy_extra_output':message+='\nextra diagnostic'
        if mode=='legacy_stdout_text':print('unexpected stdout')
        if mode=='legacy_partial_pull':pathlib.Path(cmd[2]).write_bytes(b'partial')
        print(message,file=sys.stderr)
        raise SystemExit(2 if mode=='legacy_wrong_returncode' else 1)
    if mode=='cleanup_readback_failure' and instrumented.exists():
        print('adb: error: permission denied',file=sys.stderr);raise SystemExit(1)
    shutil.copyfile(apk,cmd[2]);print('1 file pulled')
elif cmd[:2]==['exec-out','/system/bin/cat']:
    assert cmd==['exec-out','/system/bin/cat',remote]
    raw=apk.read_bytes()
    if mode=='legacy_wrong_size':raw+=b'!'
    if mode=='legacy_wrong_hash':raw=b'!'+raw[1:]
    if mode=='legacy_cat_oversize':raw=b'X'*(8*1024**2+1)
    if mode=='legacy_cat_stderr':print('diagnostic with otherwise correct bytes',file=sys.stderr)
    if mode=='legacy_cat_failure' or (mode=='legacy_cleanup_cat_failure' and instrumented.exists()):
        print('cat: permission denied',file=sys.stderr);raise SystemExit(1)
    sys.stdout.buffer.write(raw)
elif cmd[:3]==['shell','am','instrument']:
    instrumented.write_text('ran')
    run_id=cmd[cmd.index('run_id')+1]
    names=['pureCircleRasterizesWithoutWaex','plainAndroidViewDrawsAndClearsWhenHidden','nativeCanvasContainsGreenDotAndClearsOffline','invalidationClearsTheNativeGreenPixel']
    phases=[['circle'],['visible','hidden'],['online','offline'],['online','invalidated']]
    cases=[{'name':n,'status':'PASS','observations':[{'phase':p,'png':n+'-'+p+'.png'} for p in phase]} for n,phase in zip(names,phases)]
    if mode=='missing_phase':cases[2]['observations'].pop()
    if mode=='assertion_failure':cases[2]['status']='FAIL'
    report={'schema_version':1,'run_id':run_id if mode!='stale_nonce' else 'old-nonce','api':api,'candidate_variant':'positive','tests':4,'passed':3 if mode=='assertion_failure' else 4,'failures':1 if mode=='assertion_failure' else 0,'errors':0,'skipped':0,'cases':cases}
    (root/'device-result.json').write_text(json.dumps(report))
    bundle=dict(report)
    if mode=='bundle_mismatch':bundle['api']=25
    print('INSTRUMENTATION_RESULT: qa_result='+json.dumps(bundle))
    if mode=='failed_marker':print('INSTRUMENTATION_FAILED: stopped after result creation')
    if mode!='missing_finish':print('INSTRUMENTATION_CODE: -1')
    if mode=='duplicate_finish':print('INSTRUMENTATION_CODE: -1')
    if mode=='cleanup_replaced':apk.write_bytes(b'!'+apk.read_bytes()[1:])
    if mode=='nonzero_instrument':raise SystemExit(1)
elif cmd[:4]==['exec-out','run-as',package,'cat']:
    if cmd[4].endswith('/result.json'):sys.stdout.buffer.write((root/'device-result.json').read_bytes())
    else:sys.stdout.buffer.write(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2jV8AAAAASUVORK5CYII='))
elif cmd==['uninstall',package]:
    if mode=='cleanup_failure':print('Failure');raise SystemExit(1)
    installed.unlink();print('Success')
else:raise AssertionError('Unexpected fake ADB command '+repr(cmd))
'''

ORIGINAL_MODES=['positive','physical_serial','non_qemu','wrong_api','preexisting','wrong_apk_hash',
 'installed_mismatch','stale_nonce','missing_finish','duplicate_finish','bundle_mismatch',
 'failed_marker','nonzero_instrument','missing_phase','assertion_failure','cleanup_failure',
 'ambiguous_install','ambiguous_mismatch']
NEW_MODES=['legacy_readback','legacy_other_api','legacy_unrelated_error','legacy_extra_output',
 'legacy_stdout_text','legacy_wrong_returncode','legacy_partial_pull','legacy_wrong_package_path',
 'legacy_empty_suffix','legacy_split_path','legacy_traversal_path','legacy_wrong_size','legacy_wrong_hash',
 'legacy_cat_failure','legacy_cat_stderr','legacy_cat_oversize','legacy_cleanup_cat_failure',
 'installed_hash_mismatch','cleanup_replaced','cleanup_unknown_path','cleanup_readback_failure']
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--runner',type=Path,default=Path(__file__).with_name('run_presence_art_probe.py'))
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    results=[]
    for mode in ORIGINAL_MODES+NEW_MODES:
        d=a.out/mode;d.mkdir();fake=d/'adb-fixture';fake.write_text(FAKE_ADB);fake.chmod(0o755)
        api=25 if mode=='legacy_other_api' else 24
        (d/'config.json').write_text(json.dumps({'mode':mode,'api':api}))
        apk=d/'candidate.apk';apk.write_bytes(b'Controlled QA APK input; no Android binary')
        digest=hashlib.sha256(apk.read_bytes()).hexdigest()
        cmd=[sys.executable,str(a.runner.resolve()),'--adb',str(fake.resolve()),'--serial',
             'MOTOROLA' if mode=='physical_serial' else 'emulator-5554','--api',str(api),'--apk',str(apk.resolve()),
             '--expected-sha256','0'*64 if mode=='wrong_apk_hash' else digest,'--out',str((d/'run').resolve())]
        run=subprocess.run(cmd,capture_output=True,timeout=30)
        (d/'stdout.log').write_bytes(run.stdout);(d/'stderr.log').write_bytes(run.stderr)
        calls=[json.loads(x)[2:] for x in (d/'calls.jsonl').read_text().splitlines()] if (d/'calls.jsonl').is_file() else []
        receipt=json.loads((d/'run/receipt.json').read_text()) if (d/'run/receipt.json').is_file() else None
        issues=[]
        if (run.returncode==0)!=(mode in ['positive','legacy_readback']):issues.append('Unexpected acceptance/rejection')
        if mode in ['physical_serial','wrong_apk_hash'] and calls:issues.append('Preflight must never invoke ADB')
        if mode in ['non_qemu','wrong_api','preexisting'] and any(c[0] in ['install','uninstall'] for c in calls):issues.append('Pre-existing/unsupported device must remain untouched')
        if any(c[0]=='install' and (c[1]!='-t' or '-r' in c) for c in calls):issues.append('Installation must be testOnly without replace')
        if mode=='preexisting' and not receipt['failure']:issues.append('Existing package was not rejected explicitly')
        cleanup_expected=['positive','stale_nonce','missing_finish','duplicate_finish','bundle_mismatch',
                          'failed_marker','nonzero_instrument','missing_phase','assertion_failure','ambiguous_install','legacy_readback']
        if mode in cleanup_expected:
            if not receipt or receipt['cleanup']['status']!='PASS':issues.append('Verified owned installation must be removed')
        blocked_identity=(mode in ['installed_mismatch','installed_hash_mismatch','ambiguous_mismatch',
                                   'cleanup_replaced','cleanup_unknown_path','cleanup_readback_failure']
                          or (mode.startswith('legacy_') and mode!='legacy_readback'))
        if blocked_identity:
            if any(c[0]=='uninstall' for c in calls):issues.append('Unknown or mismatched current APK must not be removed')
            if receipt and receipt['cleanup']['status']=='PASS':issues.append('Unverified cleanup must not be PASS')
            if mode not in ['cleanup_replaced','cleanup_unknown_path','cleanup_readback_failure','legacy_cleanup_cat_failure'] and any(c[:3]==['shell','am','instrument'] for c in calls):
                issues.append('Unverified installed APK must not be instrumented')
        if mode in ['positive','legacy_readback']:
            if receipt['installed_apk_sha256']!=digest or not receipt['instrumentation_finish_verified']:issues.append('Positive identity/finish contract absent')
            if len(list((d/'run').glob('*.png')))!=7:issues.append('Positive evidence requires seven PNGs')
            if receipt['cleanup'].get('apk_sha256')!=digest or not receipt['cleanup'].get('identity_verified'):
                issues.append('Cleanup must have a fresh full identity check')
            readbacks=receipt.get('readbacks',{})
            if set(readbacks)!=set(['installed','cleanup-installed']) or any(x.get('sha256')!=digest or x.get('bytes')!=apk.stat().st_size for x in readbacks.values()):
                issues.append('Both complete readback identities required')
            if mode=='legacy_readback' and (sum(c[:2]==['exec-out','/system/bin/cat'] for c in calls)!=2 or any(x.get('method')!='adb_exec_out_cat_api24' for x in readbacks.values())):
                issues.append('Both legacy reads must use the bounded binary transport')
        no_fallback=['legacy_other_api','legacy_unrelated_error','legacy_extra_output','legacy_stdout_text',
                     'legacy_wrong_returncode','legacy_partial_pull','legacy_wrong_package_path',
                     'legacy_empty_suffix','legacy_split_path','legacy_traversal_path']
        if mode in no_fallback and any(c[:2]==['exec-out','/system/bin/cat'] for c in calls):
            issues.append('Fallback expanded beyond its literal API/path/failure condition')
        results.append({'mode':mode,'runner_exit':run.returncode,'status':'PASS' if not issues else 'FAIL','issues':issues,'adb_calls':len(calls)})
    spec=importlib.util.spec_from_file_location('presence_runner_control',a.runner);runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    for name,program,timeout,expected in [
      ('binary_exact_bytes',"import sys;sys.stdout.buffer.write(b'A\\x00\\r\\n\\xffZ')",5,None),
      ('binary_stdout_bound',"import sys;sys.stdout.buffer.write(b'X'*(8*1024**2+1))",5,RuntimeError),
      ('binary_stderr_bound',"import sys;sys.stderr.buffer.write(b'X'*65537)",5,RuntimeError),
      ('binary_deadline',"import time;time.sleep(2)",0.1,subprocess.TimeoutExpired)]:
        d=a.out/name;d.mkdir();issues=[];began=time.monotonic()
        try:
            rc=runner.binary_readback([sys.executable,'-c',program],d/'raw.bin',d/'stderr.bin',timeout=timeout)
            if expected is not None or rc!=0:issues.append('Expected binary rejection/exit differs')
            if name=='binary_exact_bytes' and (d/'raw.bin').read_bytes()!=b'A\x00\r\n\xffZ':issues.append('Binary bytes changed')
        except Exception as exc:
            if expected is None or not isinstance(exc,expected):issues.append(type(exc).__name__+': '+str(exc))
        elapsed=time.monotonic()-began
        if name=='binary_deadline' and elapsed>1.5:issues.append('Child did not stop close to the bounded deadline')
        results.append({'mode':name,'status':'PASS' if not issues else 'FAIL','issues':issues,'seconds':round(elapsed,3),'adb_calls':0})
    result={'scope':'Host protocol controls with local fake ADB; no Android execution, network or device access',
            'original_modes_preserved':18,'original_expectation_changed':'installed_mismatch must not uninstall; confirmed install alone does not prove current APK identity',
            'runner_sha256':hashlib.sha256(a.runner.read_bytes()).hexdigest(),'tests':len(results),
            'passed':sum(x['status']=='PASS' for x in results),'results':results}
    (a.out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if result['passed']!=len(results):raise SystemExit(1)

if __name__=='__main__':main()
