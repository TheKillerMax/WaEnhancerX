#!/usr/bin/env python3
"""Run on an explicitly named fresh emulator, verify installed bytes, then clean up.

Requires QEMU/API and an initially absent QA package; uses install -t, never -r.
Does not create, reboot, wipe or select a device automatically. Every run gets a
fresh nonce; PASS requires actual Instrumentation finish and the matching JSON.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import uuid

PACKAGE='org.waex.qa.presence.host'
CASES=['pureCircleRasterizesWithoutWaex','plainAndroidViewDrawsAndClearsWhenHidden',
       'nativeCanvasContainsGreenDotAndClearsOffline','invalidationClearsTheNativeGreenPixel']
PHASES=[['circle'],['visible','hidden'],['online','offline'],['online','invalidated']]

def verified_finish(stdout, report):
    text=stdout.decode('utf-8',errors='replace')
    if re.search(r'^INSTRUMENTATION_(?:FAILED|ABORTED)\b',text,re.M):
        raise RuntimeError('Instrumentation reported failure or abortion')
    codes=re.findall(r'^INSTRUMENTATION_CODE:\s*(-?\d+)\s*$',text,re.M)
    if codes!=['-1']:raise RuntimeError('Exactly one successful Instrumentation finish code is required')
    payloads=re.findall(r'^INSTRUMENTATION_RESULT: qa_result=(.*)$',text,re.M)
    if len(payloads)!=1 or json.loads(payloads[0])!=report:
        raise RuntimeError('Final Instrumentation Bundle differs from the recovered JSON')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adb',required=True,type=Path)
    p.add_argument('--serial',required=True)
    p.add_argument('--api',required=True,type=int,choices=range(24,38))
    p.add_argument('--apk',required=True,type=Path)
    p.add_argument('--expected-sha256',required=True)
    p.add_argument('--out',required=True,type=Path)
    a=p.parse_args()
    if not re.fullmatch(r'emulator-[0-9]+',a.serial):p.error('Only an explicit emulator-NNNN serial is accepted')
    if not re.fullmatch(r'[a-f0-9]{64}',a.expected_sha256):p.error('Expected SHA-256 must be 64 lowercase hex characters')
    actual=hashlib.sha256(a.apk.read_bytes()).hexdigest()
    if actual!=a.expected_sha256:raise RuntimeError('APK bytes differ from the frozen build receipt')
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    run_id='presence-'+uuid.uuid4().hex
    commands=[];initial_absent=False;install_started=False;installed_by_run=False
    report=None;failure=None;cleanup={'status':'not_installed'};installed_sha=None;phases_complete=False;finish_verified=False

    def run(name,args,timeout=60,check=True):
        cmd=[str(a.adb),'-s',a.serial,*args];start=time.monotonic()
        try:
            result=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            (out/(name+'.stdout')).write_bytes(exc.stdout or b'');(out/(name+'.stderr')).write_bytes(exc.stderr or b'')
            commands.append({'name':name,'command':cmd,'timed_out':True,'exit_code':None,'seconds':round(time.monotonic()-start,3)})
            (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n');raise
        (out/(name+'.stdout')).write_bytes(result.stdout);(out/(name+'.stderr')).write_bytes(result.stderr)
        commands.append({'name':name,'command':cmd,'timed_out':False,'exit_code':result.returncode,'seconds':round(time.monotonic()-start,3)})
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        if check and result.returncode:raise RuntimeError(name+' failed; see retained output')
        return result

    def package_path(name):
        result=run(name,['shell','pm','path',PACKAGE],check=False)
        text=result.stdout.decode(errors='replace').strip()
        if result.returncode not in (0,1) or result.stderr.strip():raise RuntimeError('Package state unknown: '+name)
        if not text:return None
        lines=text.splitlines()
        if result.returncode!=0 or len(lines)!=1 or not lines[0].startswith('package:/'):
            raise RuntimeError('Unexpected package path response: '+name)
        path=lines[0][len('package:'):]
        if not re.fullmatch(r'/[A-Za-z0-9_./~+=-]+\.apk',path) or '..' in path.split('/'):
            raise RuntimeError('Unexpected installed APK path')
        return path

    def pull_installed(name,path):
        target=out/(name+'.apk');run(name,['pull',path,str(target)])
        return hashlib.sha256(target.read_bytes()).hexdigest()

    try:
        if run('state',['get-state']).stdout.decode().strip()!='device':raise RuntimeError('Selected emulator unavailable')
        if run('qemu',['shell','getprop','ro.kernel.qemu']).stdout.decode().strip()!='1':raise RuntimeError('Selected serial is not QEMU')
        if int(run('api',['shell','getprop','ro.build.version.sdk']).stdout.decode().strip())!=a.api:
            raise RuntimeError('Observed emulator API differs from the matrix row')
        if package_path('initial-package') is not None:raise RuntimeError('QA package already installed; a fresh emulator is required')
        initial_absent=True;install_started=True
        install=run('install',['install','-t',str(a.apk.resolve())],timeout=120,check=False)
        if install.returncode!=0 or 'Success' not in install.stdout.decode(errors='replace').splitlines():
            raise RuntimeError('QA APK installation was not confirmed')
        installed_by_run=True
        path=package_path('installed-package')
        if path is None:raise RuntimeError('Confirmed installation has no package path')
        installed_sha=pull_installed('installed',path)
        if installed_sha!=actual:raise RuntimeError('Installed APK bytes differ from the frozen candidate')
        instrument=run('instrument',['shell','am','instrument','-w','-r','-e','run_id',run_id,
             PACKAGE+'/'+PACKAGE+'.PresenceInstrumentation'],timeout=180,check=False)
        base='files/qa-presence/'+run_id+'/'
        raw=run('result',['exec-out','run-as',PACKAGE,'cat',base+'result.json']).stdout
        (out/'device-result.json').write_bytes(raw);report=json.loads(raw)
        if report.get('run_id')!=run_id or report.get('api')!=a.api:raise RuntimeError('Stale or wrong-device receipt')
        if report.get('candidate_variant')!='positive':raise RuntimeError('Only a positive candidate can be a matrix PASS')
        if [x.get('name') for x in report.get('cases',[])]!=CASES:raise RuntimeError('Missing, duplicate or unexpected cases')
        if report.get('tests')!=4 or report.get('skipped')!=0:raise RuntimeError('All four cases must execute without omissions')
        phases_complete=True
        for index,row in enumerate(report['cases']):
            phases_complete=phases_complete and [x.get('phase') for x in row.get('observations',[])]==PHASES[index]
            for obs in row.get('observations',[]):
                filename=obs['png']
                if not re.fullmatch(r'[A-Za-z0-9_-]+\.png',filename):raise RuntimeError('Unexpected evidence filename')
                content=run('png-'+filename[:-4],['exec-out','run-as',PACKAGE,'cat',base+filename]).stdout
                if not content.startswith(b'\x89PNG\r\n\x1a\n'):raise RuntimeError('Invalid PNG evidence')
                (out/filename).write_bytes(content)
        if instrument.returncode!=0:raise RuntimeError('Instrumentation command failed')
        verified_finish(instrument.stdout,report);finish_verified=True
    except Exception as exc:
        failure={'type':type(exc).__name__,'message':str(exc)}
    finally:
        if initial_absent and install_started and not installed_by_run:
            try:
                path=package_path('after-ambiguous-install')
                if path is not None:
                    installed_sha=pull_installed('ambiguous-installed',path)
                    if installed_sha==actual:installed_by_run=True
                    else:cleanup={'status':'identity_mismatch_not_removed'}
            except Exception as exc:cleanup={'status':'unknown_after_install','message':str(exc)}
        if installed_by_run:
            try:
                removed=run('uninstall',['uninstall',PACKAGE],timeout=120,check=False)
                absent=package_path('after-uninstall') is None
                ok=removed.returncode==0 and 'Success' in removed.stdout.decode(errors='replace').splitlines() and absent
                cleanup={'status':'PASS' if ok else 'FAIL','package':PACKAGE,'verified_absent':absent}
            except Exception as exc:cleanup={'status':'FAIL','package':PACKAGE,'message':str(exc)}
    success=(failure is None and cleanup['status']=='PASS' and report is not None and phases_complete and finish_verified
             and report.get('passed')==4 and report.get('failures')==0 and report.get('errors')==0
             and all(x.get('status')=='PASS' for x in report['cases']))
    receipt={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'run_id':run_id,'api':a.api,'serial':a.serial,
             'apk_sha256':actual,'installed_apk_sha256':installed_sha,'initially_absent':initial_absent,
             'status':'PASS' if success else 'FAIL','failure':failure,'cleanup':cleanup,'commands':commands,
             'scope':'Four ART Canvas/presence cases only; separate from SQLite and full application/Xposed testing.',
             'instrumentation_finish_verified':finish_verified,'all_seven_png_phases_present':phases_complete,
             'device_counts':{key:report.get(key) for key in ('tests','passed','failures','errors','skipped')} if report else None,
             'device_result_sha256':hashlib.sha256((out/'device-result.json').read_bytes()).hexdigest() if (out/'device-result.json').is_file() else None,
             'png_sha256':{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in out.glob('*.png')}}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
    if not success:raise SystemExit(1)

if __name__=='__main__':main()
