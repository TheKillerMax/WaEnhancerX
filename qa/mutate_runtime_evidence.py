#!/usr/bin/env python3
"""Behavioral negative controls on public source in disposable copies.
Never runs real Android root; compilation/infrastructure errors are not detections.
"""
import argparse,json,shutil,subprocess,sys,tempfile
from pathlib import Path
U='app/src/main/java/com/waenhancer/utils/'
G='app/src/main/java/com/waenhancer/xposed/core/VersionGuard.kt'
H='app/src/main/java/com/waenhancer/xposed/features/privacy/HideReceiptsHook.java'
# Retired cache/heartbeat expiry and obsolete custom-version REVIEW policy are not restored.
# Current identity, frame, collection-time and unavailable-evidence controls replace those cases.
CASES = [('target-substring',
  'app/src/main/java/com/waenhancer/utils/DeclaredWhatsAppTargets.java',
  'PACKAGES.contains(packageName)',
  '(PACKAGES.contains(packageName) || packageName.contains("whatsapp"))',
  'test_declared_targets.py'),
 ('target-case-fold',
  'app/src/main/java/com/waenhancer/utils/DeclaredWhatsAppTargets.java',
  'PACKAGES.contains(packageName)',
  'PACKAGES.contains(packageName.toLowerCase(java.util.Locale.ROOT))',
  'test_declared_targets.py'),
 ('unavailable-admitted',
  'app/src/main/java/com/waenhancer/utils/UniversalVersionValidator.kt',
  'RULES_UNAVAILABLE(false)',
  'RULES_UNAVAILABLE(true)',
  'test_runtime_diagnostics.py'),
 ('foreign-resource-owner',
  'app/src/main/java/com/waenhancer/utils/UniversalVersionValidator.kt',
  'if (resources.getResourceName(id) != "$MODULE_PACKAGE:array/universal_supported_versions") return null',
  'if (false) return null',
  'test_runtime_diagnostics.py'),
 ('foreign-module-context',
  'app/src/main/java/com/waenhancer/utils/UniversalVersionValidator.kt',
  'if (moduleContext.packageName != MODULE_PACKAGE) return null',
  'if (false) return null',
  'test_runtime_diagnostics.py'),
 ('resource-context-loads-code',
  'app/src/main/java/com/waenhancer/utils/UniversalVersionValidator.kt',
  'Context.CONTEXT_IGNORE_SECURITY',
  'Context.CONTEXT_IGNORE_SECURITY or Context.CONTEXT_INCLUDE_CODE',
  'test_runtime_diagnostics.py'),
 ('fatal-resource-error-hidden',
  'app/src/main/java/com/waenhancer/utils/UniversalVersionValidator.kt',
  '} catch (_: LinkageError) {\n            null',
  '} catch (_: Throwable) {\n            null',
  'test_runtime_diagnostics.py'),
 ('unknown-means-stopped',
  'app/src/main/java/com/waenhancer/utils/InjectionEvidence.kt',
  'runningPids == null -> InjectionEvidence.PROCESS_OBSERVATION_UNAVAILABLE',
  'runningPids == null -> InjectionEvidence.PROCESS_STOPPED',
  'test_runtime_diagnostics.py'),
 ('obsolete-pause',
  'app/src/main/java/com/waenhancer/xposed/core/VersionGuard.kt',
  'if (generation != decisionGeneration.get() || decision.allowed) return@runOnUiThread',
  'if (false) return@runOnUiThread',
  'test_runtime_diagnostics.py'),
 ('receipt-argument-fallback',
  'app/src/main/java/com/waenhancer/xposed/features/privacy/HideReceiptsHook.java',
  'String captureJid = canonicalJid(jid);',
  'String captureJid = canonicalJid(jid); if (captureJid == null) captureJid = findJidInArguments(param.args);',
  'test_receipt_job_execution_contract.py'),
 ('receipt-participant-exemption',
  'app/src/main/java/com/waenhancer/xposed/features/privacy/HideReceiptsHook.java',
  '&& !hasExplicitReceiptIds(jid, param.args))',
  '&& !hasExplicitReceiptIds(resolveConversationTarget(jid, participant), param.args))',
  'test_receipt_job_execution_contract.py'),
 ('foreign-process-uid-admitted',
  'app/src/main/java/com/waenhancer/utils/XposedRuntimeInspector.kt',
  ' || parts[2].toIntOrNull() != expectedUids[parts[1]]',
  '',
  'test_runtime_diagnostics.py'),
 ('foreign-package-profile-admitted',
  'app/src/main/java/com/waenhancer/utils/XposedRuntimeInspector.kt',
  ' && AndroidUserScope.userIdForUid(info.uid) == userId',
  '',
  'test_runtime_diagnostics.py'),
 ('same-profile-context-uid-admitted',
  'app/src/main/java/com/waenhancer/utils/XposedRuntimeInspector.kt',
  'context.packageName == MODULE_PACKAGE_NAME && context.applicationInfo.uid == processUid',
  'context.packageName == MODULE_PACKAGE_NAME',
  'test_runtime_diagnostics.py'),
 ('missing-package-row-admitted',
  'app/src/main/java/com/waenhancer/utils/XposedRuntimeInspector.kt',
  'complete = valid && running.keys == expectedUids.keys',
  'complete = valid',
  'test_runtime_diagnostics.py'),
 ('pid-list-globbing',
  'app/src/main/java/com/waenhancer/utils/XposedRuntimeInspector.kt',
  'set -f\\ncommand -v pidof',
  'command -v pidof',
  'test_runtime_diagnostics.py'),
 ('manager-pid-not-verified',
  'app/src/main/java/com/waenhancer/utils/TargetAppManager.kt',
  '\n            ?.takeIf { ProfileProcessProbe.containsManagerProcess(it) }',
  '',
  'test_runtime_diagnostics.py'),
 ('timestamp-after-command',
  'app/src/main/java/com/waenhancer/utils/TargetAppManager.kt',
  'parseRuntime(output, expectedUids, startedAt)',
  'parseRuntime(output, expectedUids, SystemClock.elapsedRealtime())',
  'test_runtime_diagnostics.py'),
 ('partial-output-promoted',
  'app/src/main/java/com/waenhancer/utils/TargetAppManager.kt',
  'val lines = output.lineSequence()',
  'val lines = (if (output.trimEnd().endsWith(PS_END)) output else output + "\\n" + PS_END).lineSequence()',
  'test_runtime_diagnostics.py')]

EXPECTED_UID_FAILURES = {
 'foreign-process-uid-admitted': 'incomplete or foreign observation rejected',
 'foreign-package-profile-admitted': 'target other profile rejects before root',
 'same-profile-context-uid-admitted': 'context other package UID in same profile',
 'missing-package-row-admitted': 'incomplete or foreign observation rejected',
 'pid-list-globbing': 'pid-glob-not-expanded',
 'manager-pid-not-verified': 'exact complete frame and manager PID required',
 'timestamp-after-command': 'root observation starts before collection',
 'partial-output-promoted': 'exact complete frame and manager PID required',
}

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--out',type=Path,required=True);p.add_argument('--only',nargs='*');a=p.parse_args()
 a.out.mkdir(parents=True,exist_ok=False);results=[]
 if a.only and set(a.only)-{row[0] for row in CASES}:raise ValueError('Unknown mutation requested: '+str(set(a.only)-{row[0] for row in CASES}))
 for name,path,old,new,test in CASES:
  if a.only and name not in a.only:continue
  with tempfile.TemporaryDirectory(prefix='waex-negative-') as folder:
   root=Path(folder)/'source'
   shutil.copytree(a.root,root,ignore=shutil.ignore_patterns('.git','.gradle','build','__pycache__','*.apk','*.ttf','*.otf','*.jks','*.keystore'))
   f=root/path;s=f.read_text();assert s.count(old)==1,(name,'source contract drift',s.count(old));f.write_bytes(s.replace(old,new).encode('utf-8'))
   try:
    r=subprocess.run([sys.executable,str(root/'qa'/test)],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
   except subprocess.TimeoutExpired:raise RuntimeError(name+': timeout is not a behavioral detection')
   (a.out/(name+'.log')).write_text(r.stdout)
   expected=EXPECTED_UID_FAILURES.get(name)
   behavioral=r.returncode!=0 and 'COMPILE_OK:' in r.stdout and ('ASSERTION|' in r.stdout or 'AssertionError:' in r.stdout) and (expected is None or expected in r.stdout)
   if not behavioral:raise RuntimeError(name+': not rejected by behavior after compilation\n'+r.stdout[-2500:])
   results.append({'name':name,'test':test,'exit':r.returncode,'compiled':True,'behaviorally_rejected':True,'expected_invariant':expected})
   (a.out/'results.json').write_text(json.dumps(results,indent=2));print('REJECTED:',name,flush=True)
 print(f'PASS: {len(results)} compiled unsafe variants rejected; no Android/LSPosed claim')
if __name__=='__main__':main()
