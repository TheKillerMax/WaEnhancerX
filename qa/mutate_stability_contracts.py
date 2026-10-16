#!/usr/bin/env python3
"""Require behavioral rejection of compiled unsafe variants in temporary copies.
No compiler error, timeout or source-only assertion counts as a detection.
"""
import argparse, json, re, shutil, subprocess, sys, tempfile
from pathlib import Path
P='app/src/main/java/com/waenhancer/'
CASES=[
 ('download-hash-ignored',P+'update/UpdateTransferPolicy.kt','if (!actual.equals(expectedHash, true))','if (false)','test_update_download_contract.py'),
 ('download-size-ignored',P+'update/UpdateTransferPolicy.kt','if (expectedSize > 0 && bytes > expectedSize)','if (false)','test_update_download_contract.py'),
 ('download-shared-file',P+'update/UpdateDownloader.kt','File.createTempFile("waex_download_", ".apk", context.cacheDir)','File(context.cacheDir, "shared.apk")','test_update_download_contract.py'),
 ('download-late-cancel',P+'update/UpdateDownloader.kt','if (call.isCanceled()) return\n                        // Unique final path:','if (false) return\n                        // Unique final path:','test_update_download_contract.py'),
 ('download-callback-ownership',P+'update/UpdateDownloader.kt','handedOff = true\n                        callback.onSuccess(file)','callback.onSuccess(file)\n                        handedOff = true','test_update_download_contract.py'),
 ('progress-unthrottled',P+'update/UpdateTransferPolicy.kt','now - previous < 250L','now - previous < 0L','test_update_download_contract.py'),
 ('session-cancel-keeps-permission',P+'update/UpdateDownloadSession.kt','state = State.CANCELLED','state = State.OPEN','test_update_session.py'),
 ('session-double-complete',P+'update/UpdateDownloadSession.kt','if (state != State.OPEN) return false','if (state == State.CANCELLED) return false','test_update_session.py'),
 ('filter-empty-traversal',P+'xposed/features/customization/FilterItemsHook.kt','if (rules.isEmpty()) return','if (false) return','test_filter_work.py'),
 ('filter-mutable-publication',P+'xposed/features/customization/FilterItemsHook.kt','targetMap = java.util.Collections.unmodifiableMap(next)','targetMap = next','test_filter_work.py'),
 ('filter-mixed-traversal-snapshot',P+'xposed/features/customization/FilterItemsHook.kt','applyFiltersRecursively(view.getChildAt(i), rules)','applyFiltersRecursively(view.getChildAt(i), targetMap)','test_filter_work.py'),
 ('recorder-skips-failed-stop-release',P+'xposed/features/media/CallRecordingHook.java','if (active != null) active.release();','if (active != null && valid) active.release();','test_recorder_cleanup.py'),
]

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--out',type=Path,required=True);p.add_argument('--only',nargs='*');a=p.parse_args()
 a.out.mkdir(parents=True,exist_ok=False);results=[]
 for name,path,old,new,test in CASES:
  if a.only and name not in a.only:continue
  with tempfile.TemporaryDirectory(prefix='waex-stability-mutation-') as tmp:
   root=Path(tmp)/'src'
   shutil.copytree(a.root,root,ignore=shutil.ignore_patterns('.git','.gradle','build','__pycache__','*.apk','*.ttf','*.otf','*.jks','*.keystore'))
   f=root/path;s=f.read_text();assert s.count(old)==1,(name,'source drift',s.count(old));f.write_text(s.replace(old,new))
   try:r=subprocess.run([sys.executable,str(root/'qa'/test)],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
   except subprocess.TimeoutExpired:raise RuntimeError(name+': timeout is not behavioral detection')
   (a.out/(name+'.log')).write_text(r.stdout)
   ok=r.returncode!=0 and 'COMPILE_OK' in r.stdout and bool(re.search(r'(?:java.lang.AssertionError|java.lang.IllegalStateException: (?:Check failed|overrun admitted|limit admitted|empty rules traversed views|mixed snapshot during traversal|mutable published rules))',r.stdout))
   results.append({'name':name,'test':test,'returncode':r.returncode,'compiled_behavior_failure':ok})
   (a.out/'results.json').write_text(json.dumps(results,indent=2))
   if not ok:raise RuntimeError(name+': no behavioral failure after compilation\n'+r.stdout[-3500:])
   print('REJECTED: '+name,flush=True)
 print(f'PASS: {len(results)} compiled unsafe variants rejected by behavior')
if __name__=='__main__':main()
