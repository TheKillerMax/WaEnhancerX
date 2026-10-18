#!/usr/bin/env python3
"""Require compiled behavior failures for pending-state and refresh-order defects.

Runs on temporary copies of the public source. Does not weaken provider controls.
"""
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = Path('app/src/main/java/com/waenhancer/xposed/bridge/client/PreferenceBridgeClient.java')
MUTANTS = {
    'ignore_clear_flag': ('new PendingEdit(clear, values, optimistic)', 'new PendingEdit(false, values, optimistic)'),
    'newest_read_guard': (' || syncId != latestSyncId', ''),
    'optimistic_replay': ('if (edit.optimistic) view = applyEdits(view, edit);', 'if (false) view = applyEdits(view, edit);'),
    'erase_other_pending_writes': ('pendingEdits.remove(id);\n                        if (success)', 'pendingEdits.clear();\n                        if (success)'),
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    original = (ROOT/BRIDGE).read_text()
    results = []
    for name, (old, new) in MUTANTS.items():
        if original.count(old) != 1:
            raise RuntimeError(f'Mutation {name} has an ambiguous/missing target')
        with tempfile.TemporaryDirectory(prefix='waex_bridge_mutant_') as temp:
            work = Path(temp)
            for relative in [BRIDGE, Path('qa/test_bridge_ordering.py'), Path('qa/test_bridge_contract.py'), Path('qa/java/BridgeOrderingChecks.java')]:
                dest = work/relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT/relative, dest)
            (work/BRIDGE).write_text(original.replace(old, new))
            result = subprocess.run([sys.executable, str(work/'qa/test_bridge_ordering.py')],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=90)
            (args.out/(name+'.log')).write_text(result.stdout)
            detected = result.returncode != 0 and 'COMPILE_OK' in result.stdout and 'java.lang.AssertionError:' in result.stdout
            if not detected:
                raise RuntimeError(f'{name}: expected behavioral rejection after successful compilation, got {result.returncode}')
            results.append({'mutation':name,'compiled':True,'behaviorally_rejected':True})
    (args.out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    print('PASS: four unsafe bridge variants compiled and failed behavioral assertions; no device test')

if __name__ == '__main__':
    main()
