#!/usr/bin/env python3
"""Compile-and-reject controls for the actual view-once resolver and export hook."""
from pathlib import Path
import argparse, concurrent.futures, hashlib, json, shutil, subprocess, tempfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE='app/src/main/java/com/waenhancer/xposed/features/media/'
CASES=[
 ('skip_partial_registration_rollback', 'DownloadViewOnceHook.java', 'first.unhook();', '/* rollback removed */'),
 ('initial_page', 'ViewOnceMediaResolver.java', 'invoke(currentMessage, null, viewer, index)', 'invoke(currentMessage, null, viewer, 0)'),
 ('first_ambiguous_contract', 'ViewOnceMediaResolver.java', 'if (distinct.size() != 1) throw incompatible();', 'if (distinct.isEmpty()) throw incompatible();'),
 ('ignore_identity_change', 'ViewOnceMediaResolver.java', '!before.equals(identity(current))', 'false'),
 ('ignore_data_replacement', 'ViewOnceMediaResolver.java', 'media.get(current) != data', 'false'),
 ('ignore_page_change', 'ViewOnceMediaResolver.java', '(Integer) invoke(currentIndex, page) != index', 'false'),
 ('ignore_pager_replacement', 'ViewOnceMediaResolver.java', 'pager.get(viewer) != page', 'false'),
 ('accept_abandoned_export', 'DownloadViewOnceHook.java', 'EXPORTING.get() == ticket && enabled()', 'enabled()'),
 ('abandoned_clears_retry', 'DownloadViewOnceHook.java', 'EXPORTING.compareAndSet(ticket, null);', 'EXPORTING.set(null);'),
 ('skip_worker_preference', 'DownloadViewOnceHook.java', 'EXPORTING.get() == ticket && enabled()', 'EXPORTING.get() == ticket'),
]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    def run(case):
        name,source,old,new=case
        with tempfile.TemporaryDirectory(prefix='waex-vo-mutant-') as temporary:
            root=Path(temporary)
            (root/SOURCE).mkdir(parents=True)
            for file in ('DownloadViewOnceHook.java','ViewOnceMediaResolver.java','ViewOnceAudioResolver.java'):
                if not (ROOT/SOURCE/file).exists():continue
                shutil.copy2(ROOT/SOURCE/file,root/SOURCE/file)
            shutil.copytree(ROOT/'qa/view_once',root/'qa/view_once')
            shutil.copy2(ROOT/'qa/test_view_once_download.py',root/'qa/test_view_once_download.py')
            shutil.copy2(ROOT/'qa/localization_support.py',root/'qa/localization_support.py')
            shutil.copytree(ROOT/'app/src/main/res/values',root/'app/src/main/res/values')
            path=root/SOURCE/source;text=path.read_text();assert old in text,'Inert mutation: '+name
            path.write_text(text.replace(old,new))
            try:
                result=subprocess.run(['python3',str(root/'qa/test_view_once_download.py')],capture_output=True,text=True,timeout=90)
                log=result.stdout+result.stderr
                compiled='COMPILE_OK:' in log
                detected=compiled and result.returncode!=0 and 'java.lang.AssertionError:' in log
                row={'name':name,'exit_code':result.returncode,'compiled':compiled,'detected':detected,
                     'path':SOURCE+source,'mutant_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            except subprocess.TimeoutExpired:
                log='Infrastructure timeout';row={'name':name,'exit_code':124,'compiled':False,'detected':False}
            (args.out/(name+'.log')).write_text(log)
            print(json.dumps(row),flush=True);return row
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as workers:
        rows=list(workers.map(run,CASES))
    (args.out/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
    assert all(row['detected'] for row in rows),'A negative control was not behaviorally rejected'
    print('PASS:',len(rows),'compiled behavioral controls')

if __name__=='__main__':main()
