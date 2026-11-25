#!/usr/bin/env python3
"""Require causal failures for listener ownership, host background and overlay fallbacks.

All mutations are confined to new temporary source trees. A supplied positive
result must match every consumed source byte and show all 81 current tests green.
The underlying runner explicitly tests a declaration-only projection because the
ScreenScopedFeature contract is unavailable; this is not full-hook certification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
HOOK = 'app/src/main/java/com/waenhancer/xposed/features/customization/FloatingBottomBarHook.java'
OVERLAY = 'app/src/main/java/com/waenhancer/app/OverlayPermissionLauncher.java'
MUTATIONS = [
    ('listener-deduplication',HOOK,
     '        if (previous != null && previous.root.get() == rootView) return;\n', '',
     {'repeatedEmptyRequestsKeepOneListenerPair':3,'reattachmentCanRegisterOneFreshWait':3}),
    ('detach-listener-release',HOOK,
     '        @Override public void onViewDetachedFromWindow(View view) {\n            remove(view);\n        }',
     '        @Override public void onViewDetachedFromWindow(View view) {\n        }',
     {'detachmentRemovesBothListenersAndPendingEntry':3,'reattachmentCanRegisterOneFreshWait':3}),
    ('screen-disposal-release',HOOK,
     '    private static void clearViewState(ViewGroup root) {\n        cancelFabLayout(root);',
     '    private static void clearViewState(ViewGroup root) {',
     {'screenDisposalCancelsAnAttachedWaitBeforeItsLaterLayout':3,'disposingOneWindowRetainsTheOtherWindowsWait':3}),
    ('host-background-ownership',HOOK,
     '            if (previous != null && from == previous) {',
     '            if (previous != null) {',
     {'hostReplacedTransitionIsPreservedAsTheStartingBackground':3}),
    ('overlay-fallback',OVERLAY,
     '        return openAppInfo(packageName, launcher);',
     '        return false;',
     {'missingOverlayActivityFallsBackToAppInfo':3,'restrictedOverlayActivityFallsBackToAppInfo':3,
      'unavailableFallbackReturnsFalseAfterTwoAttempts':3}),
    ('overlay-error-classification',OVERLAY,
     '        } catch (ActivityNotFoundException | SecurityException unavailable) {',
     '        } catch (RuntimeException unavailable) {',
     {'unrelatedLauncherErrorsAreNotReportedAsUnavailableScreens':3}),
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,default=ROOT)
    parser.add_argument('--positive-result',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    for name in ['deps','dexkit-jar','core-api-jar','annotation-api-jar','sdk-jars','maven-repo','maven-settings']:
        parser.add_argument('--'+name,type=Path)
    parser.add_argument('--maven',default='mvn')
    args = parser.parse_args()
    root,out = args.source_root.resolve(),args.out.resolve()
    positive = json.loads(args.positive_result.read_text(encoding='utf-8'))
    if not (positive['accepted_result'] and positive['tests']==81 and positive['assertion_failures']==0
            and positive['complete_hook_compilation'] is False):
        raise RuntimeError('A matching green bounded-method result is required')
    identities = positive['source_sha256']
    for relative,expected in identities.items():
        if digest(root/relative) != expected:
            raise RuntimeError('Positive result does not match current source: '+relative)
    out.mkdir(parents=True,exist_ok=False)
    rows=[]
    for name,relative,before,after,expected in MUTATIONS:
        work=out/name
        source=work/'source'
        for path in identities:
            target=source/path
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(root/path,target)
        target=source/relative
        original=target.read_bytes().decode('utf-8')
        if original.count(before)!=1:
            raise RuntimeError('Mutation no longer has one exact target: '+name)
        target.write_text(original.replace(before,after,1),encoding='utf-8')
        expected_file=work/'expected-failures.json'
        expected_file.write_text(json.dumps(expected,indent=2)+'\n',encoding='utf-8')
        command=[sys.executable,str(source/'qa/android_floating_bottom_bar_methods_test.py'),
                 '--source-root',str(source),'--out',str(work/'execution'),
                 '--expected-failures',str(expected_file),'--maven',args.maven]
        for option in ['deps','dexkit_jar','core_api_jar','annotation_api_jar','sdk_jars','maven_repo','maven_settings']:
            value=getattr(args,option)
            if value: command += ['--'+option.replace('_','-'),str(value.resolve())]
        with (work/'runner.log').open('w',encoding='utf-8') as log:
            result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=360)
        report=json.loads((work/'execution/result.json').read_text(encoding='utf-8')) if (work/'execution/result.json').exists() else None
        accepted=result.returncode==0 and report is not None and report['accepted_result']
        rows.append({'name':name,'path':relative,'before_sha256':identities[relative],
                     'mutated_sha256':digest(target),'expected_failures':expected,
                     'runner_exit_code':result.returncode,'accepted_negative':accepted,
                     'execution_result_sha256':digest(work/'execution/result.json') if report else None})
        (out/'results.json').write_text(json.dumps({'positive_result_sha256':digest(args.positive_result),
            'results':rows,'expected_controls':len(MUTATIONS),'completed_controls':len(rows),
            'accepted':False,'source_unchanged':None,'complete_hook_compilation':False},indent=2)+'\n',encoding='utf-8')
        print(name,'accepted='+str(accepted),flush=True)
        if not accepted:
            raise RuntimeError('Counterfactual did not fail only the expected assertions: '+name)
    for relative,expected in identities.items():
        if digest(root/relative)!=expected:
            raise RuntimeError('Source changed during mutation run: '+relative)
    (out/'results.json').write_text(json.dumps({'positive_result_sha256':digest(args.positive_result),
        'mutator_sha256':digest(Path(__file__)),'results':rows,'expected_controls':len(MUTATIONS),
        'completed_controls':len(rows),'accepted':all(row['accepted_negative'] for row in rows),
        'source_unchanged':True,'complete_hook_compilation':False},indent=2)+'\n',encoding='utf-8')
    print('PASS: six causal mutations rejected; original source unchanged')


if __name__=='__main__':
    main()
