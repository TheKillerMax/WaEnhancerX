#!/usr/bin/env python3
"""Inject reviewed faults into disposable source copies; require Android assertion failures."""
from pathlib import Path
import importlib.util
import json
import sys
import tempfile

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('android_rows',root/'qa/android_presence_row_test.py')
qa=importlib.util.module_from_spec(spec);spec.loader.exec_module(qa)
if len(sys.argv)!=3:
    raise SystemExit('Usage: python3 qa/mutate_presence_rows.py OUTPUT_DIRECTORY VERIFIED_DEPENDENCIES_DIRECTORY')
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
deps=Path(sys.argv[2]).resolve()
qa.TESTS=qa.TESTS.replace('sdk = [28, 34, 36]','sdk = [34]')
renderer=(root/qa.RENDERER).read_text();store=(root/qa.STORE).read_text()
measure='''        overlay.measure(
            View.MeasureSpec.makeMeasureSpec(row.width.coerceAtLeast(0), View.MeasureSpec.EXACTLY),
            View.MeasureSpec.makeMeasureSpec(row.height.coerceAtLeast(0), View.MeasureSpec.EXACTLY)
        )'''
variants=[
 ('denial-is-known-offline',qa.STORE,'record(jid, false, false);','record(jid, true, false);'),
 ('no-global-clear',qa.STORE,'            STATES.clear();','            // Fault: old transport observations retained'),
 ('unknown-cannot-mask-alias',qa.STORE,'candidate != null && (latest == null','candidate != null && candidate.known && (latest == null'),
 ('no-overlay-measure',qa.RENDERER,measure,''),
 ('ignore-cached-alias',qa.RENDERER,'PresenceStateStore.getLatest(keys)','PresenceStateStore.get(jid)'),
 ('alias-does-not-repaint',qa.RENDERER,'        queuePresenceRefresh()\n    }\n\n    companion object','    }\n\n    companion object'),
 ('oldest-alias-wins',qa.STORE,'candidate.revision > latest.revision','candidate.revision < latest.revision'),
 ('no-observation-order',qa.STORE,'long revision = ++nextRevision;\n            long changedAt','long revision = nextRevision;\n            long changedAt'),
 ('ignore-repeat-observation',qa.STORE,'notifyListeners(key, state);','if (transition) notifyListeners(key, state);'),
 ('conflicting-alias-overwrites',qa.RENDERER,'if (previous == null || previous == jid) jid else ""','jid'),
 ('stale-dot-on-cleared-row',qa.RENDERER,'        render(row, null)\n    }','    }'),
 ('drop-current-event-render',qa.RENDERER,'render(row, stateForRow(boundJid))','render(row, null)'),
 ('offline-state-is-visible',qa.RENDERER,'if (state?.known == true && state.online) View.VISIBLE','if (state != null) View.VISIBLE'),
 ('drop-host-layout-direction',qa.RENDERER,'        overlay.layoutDirection = row.layoutDirection','        // Fault: host direction omitted'),
 ('duplicate-overlays',qa.RENDERER,'        rowOverlays[row]?.get()?.let { return it }','        // Fault: existing overlay ignored'),
]
results=[]
for name,path,old,new in variants:
 folder=out/name;folder.mkdir()
 original=renderer if path==qa.RENDERER else store
 if original.count(old)!=1:raise AssertionError('Non-unique reviewed fault '+name)
 with tempfile.TemporaryDirectory(prefix='waex_mutant_') as td:
  candidate=Path(td)
  for relative,text in [(qa.RENDERER,renderer),(qa.STORE,store)]:
   p=candidate/relative;p.parent.mkdir(parents=True,exist_ok=True)
   p.write_text(text.replace(old,new,1) if relative==path else text)
  try:qa.execute(candidate,folder,deps,False)
  except RuntimeError:
   log=(folder/'junit.log').read_text() if (folder/'junit.log').is_file() else ''
   if not any(kind in log for kind in ('java.lang.AssertionError', 'org.junit.ComparisonFailure')) or 'Tests run: 25,' not in log or 'initializationError' in log:
    raise AssertionError('Fault was not rejected by Android assertions: '+name)
  else:raise AssertionError('Fault survived: '+name)
  results.append({'mutation':name,'rejected_by_behavior':True,'android_api':34})
  (out/'mutation-results.json').write_text(json.dumps(results,indent=2))
 print('REJECTED_BY_ASSERTION',name,flush=True)
print('PASS:',len(results),'reviewed faults rejected by Android 14 behavioral assertions')
