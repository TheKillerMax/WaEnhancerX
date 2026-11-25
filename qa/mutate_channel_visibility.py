#!/usr/bin/env python3
"""Require exact compiled behavioral failures for the Channel visibility contracts.

Each mutation uses a small owned tree containing only the positive run's inputs.
The existing PR98 Linux watchdog closes the whole process group before log hashes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

from run_runtime_reporting_ci import run_gate

ROOT = Path(__file__).resolve().parents[1]
CHANNEL = 'app/src/main/java/com/waenhancer/xposed/features/customization/ChannelRecommendationsFilterHook.kt'
GUARD = 'app/src/main/java/com/waenhancer/xposed/utils/ViewVisibilityGuard.java'
SELECTOR = 'app/src/main/java/com/waenhancer/xposed/utils/ViewClassSelector.java'
MUTATIONS = [
    ('host-rebind', GUARD,
     '            } else {\n                reconcile(view);\n            }\n        }\n\n        private void release()',
     '            } else {\n            }\n        }\n\n        private void release()',
     {name: 3 for name in ['channelRecommendationsAreHiddenAfterHostRebind',
      'scopedPreferenceHidesAndReconciles', 'liveToggleAllowsHostBindThenResumes',
      'duplicateConstructorCallbacksRegisterOneGuard', 'movingToAnotherWindowDropsThePreviousObserver',
      'ownerCleanupIsIndependentAndIdempotent']}),
    ('host-layout-ownership', CHANNEL,
     '                visibility.bind(view)\n',
     '                visibility.bind(view)\n                view.layoutParams?.let { it.width = 0; it.height = 0; view.layoutParams = it }\n',
     {'channelHidingPreservesHostLayoutParameters': 3, 'unrelatedViewsAndHostParametersSurvive': 3}),
    ('scoped-preference', CHANNEL,
     'ViewVisibilityGuard(this) { isEnabled("channels_enhancements", false) }',
     'ViewVisibilityGuard(this) { prefs.getBoolean("channels_enhancements", false) }',
     {'scopedPreferenceHidesAndReconciles': 3}),
    ('detach-observer-release', GUARD,
     '        @Override public void onViewDetachedFromWindow(View view) {\n            removeObserver();',
     '        @Override public void onViewDetachedFromWindow(View view) {',
     {'detachStopsReconciliationAndReattachResumes': 3}),
    ('constructor-deduplication', GUARD,
     '            registration = reference != null ? reference.get() : null;',
     '            registration = null;',
     {'duplicateConstructorCallbacksRegisterOneGuard': 3}),
    ('owner-release', GUARD,
     '        ViewHookDispatcher.onUnregistered(Objects.requireNonNull(owner), this::release);',
     '        Objects.requireNonNull(owner);',
     {name: 3 for name in ['unhookReleasesExistingObserversAndConstructors',
      'backgroundUnhookStopsBeforePostedCleanup', 'releasedDetachedViewCannotResumeOnReattach',
      'backgroundReleaseRemovesDetachedListenerWithoutReattach',
      'ownerCleanupIsIndependentAndIdempotent']}),
    ('detached-worker-release', GUARD,
     '            else new Handler(Looper.getMainLooper()).post(() -> {\n                View target = owner.get();\n                if (target != null) dispose(target);\n            });',
     '            else view.post(() -> dispose(view));',
     {'backgroundReleaseRemovesDetachedListenerWithoutReattach': 3}),
    ('stable-visibility-noop', GUARD,
     'active && view.getVisibility() != View.GONE && enabled.getAsBoolean()',
     'active && enabled.getAsBoolean()',
     {'unchangedHiddenViewDoesNotWriteOnEveryLayout': 3}),
    ('nonview-target', CHANNEL,
     'check(recClass != null && View::class.java.isAssignableFrom(recClass))',
     'check(recClass != null)',
     {'nonViewChannelTargetIsRejected': 3}),
    ('selector-ambiguity', SELECTOR,
     '            if (target != null && target != candidate) {',
     '            if (false) {',
     {'distinctViewsAreRejectedAsAmbiguous': 3, 'parentAndChildMatchesAreStillAmbiguous': 3}),
    ('unchecked-cache-reuse', CHANNEL,
     '"waex_channel_rec_view_class_v2"', '"waex_channel_rec_class"',
     {'validatedSelectorUsesASeparateCacheEntry': 3}),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--positive-result', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    for name in ['deps', 'dexkit-jar', 'core-api-jar', 'annotation-api-jar', 'sdk-jars', 'maven-repo']:
        parser.add_argument('--'+name, type=Path)
    parser.add_argument('--only', nargs='+', choices=[row[0] for row in MUTATIONS])
    args = parser.parse_args()
    if os.name != 'posix':
        parser.error('The process-group supervisor requires Linux; the positive Android runner is portable')
    root, out = args.source_root.resolve(), args.out.resolve()
    positive = json.loads(args.positive_result.read_bytes())
    assert positive['mode'] == 'candidate' and positive['accepted']
    assert positive['tests'] == 75 and positive['failures'] == 0 and positive['complete_channel_compilation']
    identities = positive['source_sha256']
    assert all(sha(root/path) == pin for path, pin in identities.items())
    out.mkdir(parents=True, exist_ok=False)
    chosen = [row for row in MUTATIONS if not args.only or row[0] in args.only]
    rows = []
    for name, relative, before, after, expected in chosen:
        work, source = out/name, out/name/'source'
        for path in identities:
            target = source/path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root/path, target)
        target = source/relative
        text = target.read_text()
        assert text.count(before) == 1, name
        target.write_text(text.replace(before, after, 1), encoding='utf-8')
        expectation = work/'expected-failures.json'
        expectation.write_text(json.dumps(expected, indent=2)+'\n')
        command = [sys.executable, str(source/'qa/android_channel_visibility_test.py'),
                   '--source-root', str(source), '--out', str(work/'execution'),
                   '--expected-failures', str(expectation)]
        for option in ['deps', 'dexkit_jar', 'core_api_jar', 'annotation_api_jar', 'sdk_jars', 'maven_repo']:
            value = getattr(args, option)
            if value:
                command += ['--'+option.replace('_', '-'), str(value.resolve())]
        log = work/'runner.log'
        with log.open('w', encoding='utf-8') as stream:
            code = run_gate(command, stream, os.environ.copy(), timeout=720)
        report_path = work/'execution/result.json'
        report = json.loads(report_path.read_bytes()) if report_path.is_file() else None
        accepted = code == 0 and report is not None and report['accepted'] and report['complete_channel_compilation']
        rows.append({'name': name, 'path': relative, 'before_sha256': identities[relative],
                     'mutated_sha256': sha(target), 'expected_failures': expected,
                     'driver_exit': code, 'behaviorally_rejected': accepted,
                     'result_sha256': sha(report_path) if report else None, 'log_sha256': sha(log)})
        unchanged = all(sha(root/path) == pin for path, pin in identities.items())
        (out/'results.json').write_text(json.dumps({'rows': rows, 'expected_controls': len(chosen),
            'completed_controls': len(rows), 'source_unchanged': unchanged,
            'positive_result_sha256': sha(args.positive_result), 'mutator_sha256': sha(Path(__file__)),
            'watchdog_sha256': sha(ROOT/'qa/run_runtime_reporting_ci.py'),
            'accepted': len(rows) == len(chosen) and unchanged and all(row['behaviorally_rejected'] for row in rows)}, indent=2)+'\n')
        print(name, 'accepted='+str(accepted), flush=True)
        if not accepted or not unchanged:
            raise RuntimeError('Mutation did not meet its exact behavioral contract: '+name)


if __name__ == '__main__':
    main()
