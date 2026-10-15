#!/usr/bin/env python3
"""Reject deliberately unsafe manual-save/lifecycle/cache variants by behavior, not syntax errors."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
UI='app/src/main/java/com/waenhancer/ui/screens/settings/StylesSettingsScreen.kt'
HOOK='app/src/main/java/com/waenhancer/xposed/features/automation/PresenceToastsHook.java'
STORE='app/src/main/java/com/waenhancer/xposed/features/automation/PresenceStateStore.java'
POLICY='app/src/main/java/com/waenhancer/xposed/features/automation/PresenceEventPolicy.java'
MANUAL='qa/test_manual_seen_tick_persistence.py';LIFE='qa/test_presence_invalidation.py';CACHE='qa/test_presence_state_invalidation.py'
VARIANTS=[
 ('manual-ignore-failure',UI,'if (preferenceManager.putPublicString("seentick", nextPlacement)) {','if (run { preferenceManager.putPublicString("seentick", nextPlacement); true }) {',MANUAL),
 ('manual-no-error',UI,'// A failed commit can already have changed memory. Keep the last confirmed UI state.\n                Toast.makeText(context, "Unable to save setting", Toast.LENGTH_SHORT).show()','// Fault: failure hidden',MANUAL),
 ('manual-use-failed-memory',UI,'// A failed commit can already have changed memory. Keep the last confirmed UI state.','settingsState[key] = ManualSeenTickPreferencePolicy.isEnabled(preferenceManager.getString("seentick", "0"))',MANUAL),
 ('manual-loses-overflow',UI,'valueAfterExplicitToggle(value, currentPlacement)','valueAfterExplicitToggle(value, "0")',MANUAL),
 ('manual-wrong-key',UI,'putPublicString("seentick", nextPlacement)','putPublicString("chatfilter", nextPlacement)',MANUAL),
 ('manual-wrong-ui-state',UI,'settingsState[key] = ManualSeenTickPreferencePolicy.isEnabled(nextPlacement)','settingsState[key] = !ManualSeenTickPreferencePolicy.isEnabled(nextPlacement)',MANUAL),
 ('online-unguarded-main-queue',HOOK,'if (stillValid.getAsBoolean()) Toast.makeText','if (true) Toast.makeText',LIFE),
 ('online-ignore-denial',HOOK,'if (!event.known) {','if (false) {',LIFE),
 ('online-ignore-transport',HOOK,'PresenceStateStore.invalidateAll();','// Fault: transport state retained',LIFE),
 ('online-wrong-disconnect-code',POLICY,'what == 1 || what == 4','what == 1 || what == 3',LIFE),
 ('online-steal-new-transition',HOOK,'final long transitionId = PresenceStateStore.updateAndGetTransition(event.jid, event.online);','boolean transition = PresenceStateStore.update(event.jid, event.online);\n                    final long transitionId = transition ? PresenceStateStore.get(event.jid).transitionRevision : 0L;',LIFE),
 ('cache-ignore-unknown-alias',STORE,'candidate != null && (latest == null','candidate != null && candidate.known && (latest == null',CACHE),
 ('cache-access-order-resurrection',STORE,'new LinkedHashMap<String, State>(256, 0.75f, false)','new LinkedHashMap<String, State>(256, 0.75f, true)',CACHE),
 ('cache-denial-fake-last-seen',STORE,'record(jid, false, false);','record(jid, true, false);',CACHE),
]

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--root',type=Path,default=ROOT);args=ap.parse_args()
 args.out.mkdir(parents=True,exist_ok=True)
 def execute(v):
  name,relative,old,new,test=v;original=(args.root/relative).read_text()
  if original.count(old)!=1:raise AssertionError('Non-unique mutation '+name)
  with tempfile.TemporaryDirectory(prefix='waex_v18_fault_') as td:
   dest=Path(td)/'source';shutil.copytree(args.root,dest,ignore=shutil.ignore_patterns('.git','__pycache__','build'))
   (dest/relative).write_text(original.replace(old,new,1))
   p=subprocess.run(['python3',str(dest/test)],capture_output=True,text=True,timeout=180)
   log=p.stdout+p.stderr;(args.out/(name+'.log')).write_text(log)
   behavioral=p.returncode!=0 and ('java.lang.AssertionError' in log or 'java.lang.IllegalStateException' in log)
   if not behavioral or 'error:' in log or 'CompilationError' in log:
    raise AssertionError('Not a compiled behavioral rejection '+name+'\n'+log[-3000:])
   print('REJECTED_BY_BEHAVIOR',name,flush=True)
   return {'variant':name,'behaviorally_rejected':True,'test':test,'replaced':old,'with':new}
 with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(execute,VARIANTS))
 (args.out/'results.json').write_text(json.dumps(results,indent=2));print('PASS:',len(results),'compiled negative controls',flush=True)
if __name__=='__main__':main()
