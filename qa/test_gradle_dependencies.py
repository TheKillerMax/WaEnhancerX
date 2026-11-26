"""Real child-process controls for dependency-only retries; no network or Android."""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import gradle_dependencies as helper

OUT = None
FAKE = r'''
import json,pathlib,subprocess,sys,time
root=pathlib.Path(__file__).parent
config=json.loads((root/'config.json').read_text())
calls=root/'calls.jsonl'
index=len(calls.read_text().splitlines()) if calls.exists() else 0
with calls.open('a') as stream:stream.write(json.dumps(sys.argv[1:])+'\n')
step=config[min(index,len(config)-1)]
print(step.get('text',''),flush=True)
if step.get('child'):
 subprocess.Popen([sys.executable,'-c','import pathlib,time;time.sleep(1);pathlib.Path('+repr(str(root/'orphan'))+').write_text("escaped")'])
if step.get('change'):(root/'probe/build.gradle.kts').write_text('changed')
if step.get('change_wrapper'):
 (root/'gradle/wrapper').mkdir(parents=True,exist_ok=True)
 (root/'gradle/wrapper/gradle-wrapper.properties').write_text('different distribution')
time.sleep(step.get('sleep',0))
raise SystemExit(step.get('exit',0))
'''
SUCCESS = {'text': '> Task '+helper.TASK+'\n'+helper.MARKER+'\nBUILD SUCCESSFUL', 'exit': 0}
THROTTLE = {'text': "Could not resolve x:y:1. Could not GET resource. Received status code 429 from server: Too Many Requests", 'exit': 1}


class DependencyChecks(unittest.TestCase):
    def setUp(self):
        self.root = OUT/self._testMethodName
        self.root.mkdir()
        (self.root/'probe').mkdir()
        for name in ('settings.gradle.kts','gradle.properties','probe/build.gradle.kts'):
            (self.root/name).write_text('fixture')
        self.wrapper = self.root/'gradlew.py'
        self.wrapper.write_text(FAKE)
        self.log = self.root/'dependencies.log'

    def configure(self, steps):
        (self.root/'config.json').write_text(json.dumps(steps))

    def prepare(self, **kwargs):
        with patch.object(helper, 'BACKOFF_SECONDS', (.001,.002)):
            return helper.prepare_dependencies(self.wrapper,self.root,self.log,bash=sys.executable,**kwargs)

    def calls(self):
        path = self.root/'calls.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def report(self):
        return json.loads(self.log.with_suffix('.json').read_text())

    def test_success_runs_dependency_task_without_consumer(self):
        self.configure([SUCCESS]);result=self.prepare()
        self.assertTrue(result['accepted'])
        self.assertEqual(result['consumer_runs'],0)
        self.assertEqual(len(self.calls()),1)
        self.assertEqual(self.calls()[0][-1],helper.TASK)
        self.assertNotIn('--refresh-dependencies',self.calls()[0])

    def test_same_arguments_recover_transient_resolution_on_third_attempt(self):
        self.configure([THROTTLE,THROTTLE,SUCCESS]);result=self.prepare()
        self.assertEqual(len(self.calls()),3)
        self.assertTrue(all(c==self.calls()[0] for c in self.calls()))
        self.assertEqual(len(result['attempts']),3)
        self.assertTrue(all(a['retryable'] for a in result['attempts'][:2]))
        self.assertEqual(self.log.read_text().count('status code 429'),2)

    def test_baseline_no_retry_retains_original_throttle_failure(self):
        self.configure([THROTTLE,SUCCESS])
        with self.assertRaises(helper.GradleDependencyError):self.prepare(max_attempts=1)
        self.assertEqual(len(self.calls()),1)
        self.assertFalse(self.report()['accepted'])

    def test_persistent_transport_failure_is_bounded(self):
        self.configure([THROTTLE])
        with self.assertRaises(helper.GradleDependencyError):self.prepare()
        self.assertEqual(len(self.calls()),3)
        self.assertFalse(self.report()['accepted'])

    def test_offline_never_retries_or_changes_mode(self):
        self.configure([THROTTLE,SUCCESS])
        with self.assertRaises(helper.GradleDependencyError):self.prepare(offline=True)
        self.assertEqual(len(self.calls()),1)
        self.assertEqual(self.calls()[0][-1],'--offline')

    def test_compiler_test_integrity_auth_and_missing_artifact_fail_without_retry(self):
        for index,message in enumerate(('Compilation error','Script compilation errors','Could not compile script',
            'There were failing tests','AssertionError','Dependency verification failed','checksum mismatch',
            'invalid signature','401 Unauthorized','403 Forbidden','Received status code 404')):
            with self.subTest(message=message):
                self.log=self.root/('failure-'+str(index)+'.log')
                self.configure([{'text':THROTTLE['text']+'\n'+message,'exit':1},SUCCESS])
                # Reset the child fixture's deterministic step index for each control.
                (self.root/'calls.jsonl').unlink(missing_ok=True)
                with self.assertRaises(helper.GradleDependencyError):self.prepare()
                self.assertEqual(len(self.calls()),1)

    def test_other_task_is_rejected_even_if_exit_zero_and_success_marker_present(self):
        self.configure([{'text':'> Task :probe:testDebugUnitTest\n'+SUCCESS['text'],'exit':0}])
        with self.assertRaises(helper.GradleDependencyError):self.prepare()
        self.assertEqual(len(self.calls()),1)
        self.assertEqual(self.report()['attempts'][0]['forbidden_tasks'],[':probe:testDebugUnitTest'])

    def test_zero_exit_requires_single_task_and_single_success_marker(self):
        for index,text in enumerate(('BUILD SUCCESSFUL',helper.MARKER,
            '> Task '+helper.TASK, SUCCESS['text']+'\n'+helper.MARKER,
            '> Task '+helper.TASK+'\n'+SUCCESS['text'])):
            with self.subTest(text=text):
                self.log=self.root/('incomplete-'+str(index)+'.log')
                self.configure([{'text':text,'exit':0}])
                with self.assertRaises(helper.GradleDependencyError):self.prepare()

    def test_failure_after_preparation_marker_does_not_pass(self):
        self.configure([{**SUCCESS,'exit':1}])
        with self.assertRaises(helper.GradleDependencyError):self.prepare()
        self.assertFalse(self.report()['accepted'])

    def test_inputs_changed_in_attempt_prevent_admission(self):
        self.configure([{**SUCCESS,'change':True}])
        with self.assertRaises(helper.GradleDependencyError):self.prepare()
        self.assertFalse(self.report()['accepted'])
        self.assertEqual(len(self.calls()),1)

    def test_changed_wrapper_distribution_prevents_admission(self):
        self.configure([{**SUCCESS,'change_wrapper':True}])
        with self.assertRaises(helper.GradleDependencyError):self.prepare()
        self.assertFalse(self.report()['accepted'])
        self.assertEqual(len(self.calls()),1)

    @unittest.skipUnless(os.name=='posix','POSIX process group closure; Windows requires its own qualification')
    def test_deadline_closes_owned_child_tree_without_retry(self):
        self.configure([{'text':THROTTLE['text'],'sleep':5,'child':True}])
        started=time.monotonic()
        with self.assertRaises(helper.GradleDependencyError):self.prepare(timeout=.2)
        self.assertLess(time.monotonic()-started,2)
        self.assertEqual(len(self.calls()),1)
        self.assertTrue(self.report()['attempts'][0]['timed_out'])
        time.sleep(1.05)
        self.assertFalse((self.root/'orphan').exists())

    def test_invalid_limits_fail_before_output_or_execution(self):
        self.configure([SUCCESS])
        for args in ({'timeout':0},{'timeout':601},{'timeout':math.inf},{'timeout':True},
                     {'max_attempts':0},{'max_attempts':4},{'max_attempts':True},{'offline':'yes'}):
            with self.subTest(args=args),self.assertRaises(ValueError):self.prepare(**args)
        self.assertFalse(self.log.exists());self.assertEqual(self.calls(),[])

    def test_existing_evidence_is_not_overwritten(self):
        self.configure([SUCCESS]);self.prepare();original=self.log.read_bytes()
        with self.assertRaises(ValueError):self.prepare()
        self.assertEqual(self.log.read_bytes(),original);self.assertEqual(len(self.calls()),1)

    def test_missing_launcher_is_explicit_and_does_not_start_consumer(self):
        self.configure([SUCCESS])
        with self.assertRaises(OSError):helper.prepare_dependencies(self.wrapper,self.root,self.log,bash='/missing/launcher')
        self.assertFalse(self.report()['accepted']);self.assertEqual(self.report()['consumer_runs'],0)


def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='waex-gradle-deps-') as temporary:
        OUT=args.out.resolve() if args.out else Path(temporary)/'evidence'
        OUT.mkdir(parents=True,exist_ok=False)
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DependencyChecks))
        (OUT/'result.json').write_text(json.dumps({'accepted':result.wasSuccessful(),'tests':result.testsRun,
            'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
            'scope':'Actual controlled child processes; no real Gradle, Android or network.'},indent=2)+'\n')
        return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
