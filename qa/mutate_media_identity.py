#!/usr/bin/env python3
"""Negative controls for the combined media/identity/forwarding contribution.
Each altered production source must compile and fail a behavioral assertion.
Compiler errors, missing tools, timeouts and inert replacements are not detections.
"""
from pathlib import Path
import argparse, concurrent.futures, hashlib, json, shutil, subprocess, tempfile
ROOT = Path(__file__).resolve().parents[1]
SRC = 'app/src/main/java/com/waenhancer/'
CASES = [
 ('pending_not_hidden', 'xposed/features/media/GalleryMediaExporter.java', 'values.put(MediaStore.MediaColumns.IS_PENDING, 1);', 'values.put(MediaStore.MediaColumns.IS_PENDING, 0);', 'test_gallery_export.py'),
 ('png_mislabeled', 'xposed/features/media/GalleryMediaExporter.java', 'new Format(".png", "image/png", false)', 'new Format(".jpg", "image/jpeg", false)', 'test_gallery_export.py'),
 ('rollback_omitted', 'xposed/features/media/GalleryMediaExporter.java', 'resolver.delete(row, null, null);', 'if (false) resolver.delete(row, null, null);', 'test_gallery_export.py'),
 ('truncated_source_accepted', 'xposed/features/media/GalleryMediaExporter.java', 'if (copied != expected)', 'if (false)', 'test_gallery_export.py'),
 ('conflicting_names_accepted', 'utils/ContactNameResolver.kt', 'if (name != null && name != candidate) return null', 'if (false) return null', 'test_contact_identity.py'),
 ('phone_suffix_accepted', 'utils/ContactNameResolver.kt', 'if (number != digits) continue', 'if (false) continue', 'test_contact_identity.py'),
 ('ambiguous_lid_accepted', 'utils/ContactNameResolver.kt', 'if (cursor.moveToNext()) return null', 'if (false) return null', 'test_contact_identity.py'),
 ('activity_loses_phone_namespace', 'utils/ContactNameResolver.kt', 'resolveFromWaDb(activity, "$mappedPhone@s.whatsapp.net")', 'resolveFromWaDb(activity, mappedPhone)', 'test_contact_identity.py'),
 ('legacy_overrides_canonical_disable', 'xposed/features/privacy/HideForwardedTagHook.kt', 'if (prefs.contains("hide_forwarded_tag")) prefs.getBoolean("hide_forwarded_tag", false)', 'if (prefs.contains("hide_forwarded_tag")) (prefs.getBoolean("hide_forwarded_tag", false) || prefs.getBoolean("hidetag", false))', 'test_forwarded_metadata_scope.py'),
 ('negative_score_overwritten', 'xposed/features/privacy/HideForwardedTagHook.kt', 'score is Int && score > 0', 'score is Int', 'test_forwarded_metadata_scope.py'),
 ('unrelated_table_modified', 'xposed/features/privacy/HideForwardedTagHook.kt', 'if (table == "message_forwarded")', 'if (true)', 'test_forwarded_metadata_scope.py'),
]
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 def run(case):
  name,rel,old,new,test=case
  with tempfile.TemporaryDirectory(prefix='waex-mutant-') as tmp:
   root=Path(tmp)
   shutil.copytree(ROOT/'app/src/main/java',root/'app/src/main/java')
   (root/'qa').mkdir();shutil.copy2(ROOT/'qa'/test,root/'qa'/test)
   f=root/SRC/rel;text=f.read_text();assert old in text, f'Inert mutation: {name}'
   f.write_text(text.replace(old,new))
   try:
    result=subprocess.run(['python3',str(root/'qa'/test)],capture_output=True,text=True,timeout=180)
    log=result.stdout+result.stderr
    detected=(result.returncode!=0 and 'COMPILE_OK:' in log and ('java.lang.AssertionError:' in log or 'ASSERTION|' in log))
    row={'name':name,'rc':result.returncode,'compiled':'COMPILE_OK:' in log,'detected':detected,'production_path':SRC+rel,'mutant_sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
   except subprocess.TimeoutExpired:
    log='Infrastructure failure: timeout';row={'name':name,'rc':124,'compiled':False,'detected':False}
   (a.out/(name+'.log')).write_text(log)
   print(json.dumps(row),flush=True);return row
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as e: rows=list(e.map(run,CASES))
 (a.out/'summary.json').write_text(json.dumps(rows,indent=2))
 assert all(r['detected'] for r in rows),'Some mutants were not detected by compiled behavior; inspect logs'
 print(f'PASS: {len(rows)} compiled behavioral negative controls')
if __name__=='__main__':main()
