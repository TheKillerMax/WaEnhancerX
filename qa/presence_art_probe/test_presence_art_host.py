#!/usr/bin/env python3
"""Controlled local ADB protocol fixture; this does not run Android or contact ADB."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

FAKE_ADB=r'''#!/usr/bin/env python3
import base64,json,pathlib,shutil,sys
root=pathlib.Path(__file__).resolve().parent
config=json.loads((root/'config.json').read_text()); mode=config['mode']
args=sys.argv[1:]
with (root/'calls.jsonl').open('a') as stream:stream.write(json.dumps(args)+'\n')
assert args[:2]==['-s','emulator-5554']
cmd=args[2:];installed=root/'installed.flag';apk=root/'installed-apk'
if cmd==['get-state']: print('device')
elif cmd==['shell','getprop','ro.kernel.qemu']: print('0' if mode=='non_qemu' else '1')
elif cmd==['shell','getprop','ro.build.version.sdk']: print('25' if mode=='wrong_api' else '24')
elif cmd==['shell','pm','path','org.waex.qa.presence.host']:
    if installed.exists() or mode=='preexisting':print('package:/data/app/qa/base.apk')
    else:raise SystemExit(1)
elif cmd[:1]==['install']:
    assert cmd[1]=='-t' and '-r' not in cmd
    installed.write_text('created');shutil.copyfile(cmd[2],apk)
    if mode in ['installed_mismatch','ambiguous_mismatch']:apk.write_bytes(b'different bytes')
    if mode in ['ambiguous_install','ambiguous_mismatch']:print('transport lost after installation');raise SystemExit(1)
    print('Success')
elif cmd[:1]==['pull']:
    assert cmd[1]=='/data/app/qa/base.apk';shutil.copyfile(apk,cmd[2]);print('1 file pulled')
elif cmd[:3]==['shell','am','instrument']:
    run_id=cmd[cmd.index('run_id')+1]
    names=['pureCircleRasterizesWithoutWaex','plainAndroidViewDrawsAndClearsWhenHidden','nativeCanvasContainsGreenDotAndClearsOffline','invalidationClearsTheNativeGreenPixel']
    phases=[['circle'],['visible','hidden'],['online','offline'],['online','invalidated']]
    cases=[{'name':n,'status':'PASS','observations':[{'phase':p,'png':n+'-'+p+'.png'} for p in phase]} for n,phase in zip(names,phases)]
    if mode=='missing_phase':cases[2]['observations'].pop()
    if mode=='assertion_failure':cases[2]['status']='FAIL'
    report={'schema_version':1,'run_id':run_id if mode!='stale_nonce' else 'old-nonce','api':24,'candidate_variant':'positive','tests':4,'passed':3 if mode=='assertion_failure' else 4,'failures':1 if mode=='assertion_failure' else 0,'errors':0,'skipped':0,'cases':cases}
    (root/'device-result.json').write_text(json.dumps(report))
    bundle=dict(report)
    if mode=='bundle_mismatch':bundle['api']=25
    print('INSTRUMENTATION_RESULT: qa_result='+json.dumps(bundle))
    if mode=='failed_marker':print('INSTRUMENTATION_FAILED: stopped after result creation')
    if mode!='missing_finish':print('INSTRUMENTATION_CODE: -1')
    if mode=='duplicate_finish':print('INSTRUMENTATION_CODE: -1')
    if mode=='nonzero_instrument':raise SystemExit(1)
elif cmd[:4]==['exec-out','run-as','org.waex.qa.presence.host','cat']:
    if cmd[4].endswith('/result.json'):sys.stdout.buffer.write((root/'device-result.json').read_bytes())
    else:sys.stdout.buffer.write(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2jV8AAAAASUVORK5CYII='))
elif cmd==['uninstall','org.waex.qa.presence.host']:
    if mode=='cleanup_failure':print('Failure');raise SystemExit(1)
    installed.unlink();print('Success')
else:raise AssertionError('Unexpected fake ADB command '+repr(cmd))
'''

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--runner',type=Path,default=Path(__file__).with_name('run_presence_art_probe.py'))
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    modes=['positive','physical_serial','non_qemu','wrong_api','preexisting','wrong_apk_hash',
           'installed_mismatch','stale_nonce','missing_finish','duplicate_finish','bundle_mismatch',
           'failed_marker','nonzero_instrument','missing_phase','assertion_failure','cleanup_failure',
           'ambiguous_install','ambiguous_mismatch']
    results=[]
    for mode in modes:
        d=a.out/mode;d.mkdir();fake=d/'adb-fixture';fake.write_text(FAKE_ADB);fake.chmod(0o755)
        (d/'config.json').write_text(json.dumps({'mode':mode}))
        apk=d/'candidate.apk';apk.write_bytes(b'Controlled QA APK input; no Android binary')
        digest=hashlib.sha256(apk.read_bytes()).hexdigest()
        cmd=[sys.executable,str(a.runner.resolve()),'--adb',str(fake.resolve()),'--serial',
             'MOTOROLA' if mode=='physical_serial' else 'emulator-5554','--api','24','--apk',str(apk.resolve()),
             '--expected-sha256','0'*64 if mode=='wrong_apk_hash' else digest,'--out',str((d/'run').resolve())]
        run=subprocess.run(cmd,capture_output=True,timeout=30)
        (d/'stdout.log').write_bytes(run.stdout);(d/'stderr.log').write_bytes(run.stderr)
        calls=[json.loads(x)[2:] for x in (d/'calls.jsonl').read_text().splitlines()] if (d/'calls.jsonl').is_file() else []
        receipt=json.loads((d/'run/receipt.json').read_text()) if (d/'run/receipt.json').is_file() else None
        issues=[]
        if (run.returncode==0)!=(mode=='positive'):issues.append('Unexpected acceptance/rejection')
        if mode in ['physical_serial','wrong_apk_hash'] and calls:issues.append('Preflight must never invoke ADB')
        if mode in ['non_qemu','wrong_api','preexisting'] and any(c[0] in ['install','uninstall'] for c in calls):issues.append('Pre-existing/unsupported device must remain untouched')
        if any(c[0]=='install' and (c[1]!='-t' or '-r' in c) for c in calls):issues.append('Installation must be testOnly without replace')
        if mode=='preexisting' and not receipt['failure']:issues.append('Existing package was not rejected explicitly')
        if mode in ['positive','installed_mismatch','stale_nonce','missing_finish','duplicate_finish','bundle_mismatch','failed_marker','nonzero_instrument','missing_phase','assertion_failure','ambiguous_install']:
            if not receipt or receipt['cleanup']['status']!='PASS':issues.append('Owned installation must be removed after success or failure')
        if mode=='ambiguous_mismatch' and any(c[0]=='uninstall' for c in calls):issues.append('Ambiguous different APK must not be removed')
        if mode=='positive':
            if receipt['installed_apk_sha256']!=digest or not receipt['instrumentation_finish_verified']:issues.append('Positive identity/finish contract absent')
            if len(list((d/'run').glob('*.png')))!=7:issues.append('Positive evidence requires seven PNGs')
        results.append({'mode':mode,'runner_exit':run.returncode,'status':'PASS' if not issues else 'FAIL','issues':issues,'adb_calls':len(calls)})
    result={'scope':'Linux host protocol controls with local fake ADB; no Android execution, network or device access',
            'runner_sha256':hashlib.sha256(a.runner.read_bytes()).hexdigest(),'tests':len(results),
            'passed':sum(x['status']=='PASS' for x in results),'results':results}
    (a.out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if result['passed']!=len(results):raise SystemExit(1)

if __name__=='__main__':main()
