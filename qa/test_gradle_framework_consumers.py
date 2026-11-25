"""Check consumer ownership and early CLI rejection; never launch Gradle or ADB."""
import argparse
import contextlib
import io
import itertools
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import framework_dependency_bundle as bundles
import runtime_framework_inputs as inputs
import verify_interface_scale_framework as interface
import verify_stability_framework as stability

OUT = BUNDLE = ORIGIN = None
RUNNERS = {'stability': (stability, 'stability-fixture'),
           'interface-scale': (interface, 'interface-scale-fixture')}


class ConsumerChecks(unittest.TestCase):
    def test_incomplete_bundle_origin_is_rejected_before_output_or_prepare(self):
        values = [str(BUNDLE), ORIGIN['run_id'], ORIGIN['run_attempt'], ORIGIN['head_sha']]
        flags = ['--framework-bundle', '--bundle-run-id', '--bundle-run-attempt', '--bundle-head-sha']
        for consumer, (runner, _) in RUNNERS.items():
            for bits in itertools.product((False, True), repeat=4):
                if not any(bits) or all(bits):
                    continue
                with self.subTest(consumer=consumer, flags=bits):
                    out = OUT / (consumer + '-incomplete-' + ''.join(map(str, map(int, bits))))
                    argv = [runner.__file__, '--out', str(out)]
                    for present, flag, value in zip(bits, flags, values):
                        if present:
                            argv += [flag, value]
                    with patch.object(sys, 'argv', argv), contextlib.redirect_stderr(io.StringIO()), \
                         patch.object(inputs, 'prepare', side_effect=AssertionError('Preparation reached before origin validation')):
                        with self.assertRaises(SystemExit) as error:
                            runner.main()
                    self.assertEqual(error.exception.code, 2)
                    self.assertFalse(out.exists())

    def test_invalid_origin_or_unavailable_sdk_is_rejected_before_output(self):
        for consumer, (runner, _) in RUNNERS.items():
            for field, invalid in (('run_id', 'not-a-run'), ('run_attempt', '0'), ('head_sha', 'abc'), ('sdk', '35')):
                with self.subTest(consumer=consumer, invalid=field):
                    origin = dict(ORIGIN)
                    origin[field] = invalid
                    out = OUT / (consumer + '-invalid-' + field)
                    argv = [runner.__file__, '--out', str(out), '--framework-bundle', str(BUNDLE),
                            '--bundle-run-id', origin['run_id'], '--bundle-run-attempt', origin['run_attempt'],
                            '--bundle-head-sha', origin['head_sha']]
                    if field == 'sdk':
                        argv += ['--sdk', invalid]
                    with patch.object(sys, 'argv', argv), contextlib.redirect_stderr(io.StringIO()), \
                         patch.object(inputs, 'prepare', side_effect=AssertionError('Invalid identity reached prepare')):
                        with self.assertRaises((SystemExit, ValueError)):
                            runner.main()
                    self.assertFalse(out.exists())

    def test_consumer_project_and_runner_must_agree_before_bundle_access(self):
        cases = [
            ('unknown', 'stability-fixture', Path(stability.__file__)),
            ('stability', 'runtime-fixture', Path(stability.__file__)),
            ('stability', 'stability-fixture', None),
            ('stability', 'stability-fixture', inputs.QA / 'verify_runtime_framework.py'),
            ('interface-scale', 'interface-scale-fixture', Path(stability.__file__)),
            ('interface-scale', 'interface-scale-fixture', OUT / 'verify_interface_scale_framework.py'),
            ('runtime', 'runtime-fixture', Path(interface.__file__)),
        ]
        for index, (consumer, project, runner) in enumerate(cases):
            with self.subTest(consumer=consumer, project=project, runner=str(runner)):
                destination = OUT / ('invalid-ownership-' + str(index))
                with patch.object(inputs, 'verify', side_effect=AssertionError('Wrong consumer reached bundle access')):
                    with self.assertRaises(ValueError):
                        inputs.prepare(BUNDLE, destination, *ORIGIN.values(), consumer=consumer,
                                       project=project, runner=runner)
                self.assertFalse(destination.exists())

    def test_three_consumers_keep_exact_native_inputs_and_their_own_provenance(self):
        rows = [('runtime', 'runtime-fixture', inputs.QA / 'verify_runtime_framework.py'),
                *[(name, project, Path(runner.__file__)) for name, (runner, project) in RUNNERS.items()]]
        for consumer, project, runner in rows:
            with self.subTest(consumer=consumer):
                options = {} if consumer == 'runtime' else {'consumer': consumer, 'project': project, 'runner': runner}
                record = inputs.prepare(BUNDLE, OUT / ('prepared-' + consumer), *ORIGIN.values(), **options)
                expected_files = [runner, Path(inputs.__file__), inputs.QA / 'framework_dependency_bundle.py',
                                  inputs.QA / 'framework_dependency_lock.json', inputs.POM]
                expected_pins = {path.relative_to(inputs.QA.parent).as_posix(): bundles.sha(path) for path in expected_files}
                self.assertEqual(record['source_sha256'], expected_pins)
                self.assertEqual(record['bundle']['origin'], ORIGIN)
                self.assertEqual(record['sdk_resolution'], 'offline')
                self.assertIn('rootProject.name="' + project + '"', inputs.settings(record))
                self.assertIn('includeVersion("org.robolectric", "nativeruntime-dist-compat", "1.0.19")', inputs.settings(record))
                if consumer == 'runtime':
                    self.assertEqual(record['schema'], 'WAEX_RUNTIME_FRAMEWORK_INPUTS_V1')
                    self.assertEqual(set(record), {'schema', 'bundle', 'bundle_directory', 'repository_uri', 'native',
                                                  'pom', 'sdk_directory', 'sdk_resolution', 'source_sha256', 'scope'})
                else:
                    self.assertEqual(record['schema'], 'WAEX_GRADLE_FRAMEWORK_INPUTS_V1')
                    self.assertEqual(record['consumer'], consumer)
                    self.assertEqual(record['project_name'], project)
                    self.assertEqual(record['runner'], runner.relative_to(inputs.QA.parent).as_posix())
                    self.assertNotIn('qa/verify_runtime_framework.py', record['source_sha256'])


def main():
    global OUT, BUNDLE, ORIGIN
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args()
    OUT, BUNDLE = args.out.resolve(), args.bundle.resolve()
    OUT.mkdir(parents=True, exist_ok=False)
    metadata = json.loads((BUNDLE / 'bundle.json').read_bytes())
    identity = metadata['origin']
    ORIGIN = bundles.identity(identity['run_id'], identity['run_attempt'], identity['head_sha'])
    before = bundles.verify(BUNDLE, inputs.QA / 'framework_dependency_lock.json', ORIGIN)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ConsumerChecks))
    after = bundles.verify(BUNDLE, inputs.QA / 'framework_dependency_lock.json', ORIGIN)
    files = [Path(__file__), Path(inputs.__file__), Path(stability.__file__), Path(interface.__file__), inputs.POM]
    report = {'accepted': result.wasSuccessful(), 'tests': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'optimization': sys.flags.optimize,
              'bundle_before': before, 'bundle_after': after,
              'source_sha256': {path.relative_to(inputs.QA.parent).as_posix(): bundles.sha(path) for path in files},
              'scope': 'Two CLI boundaries, three exact consumer identities and unchanged Runtime defaults; no Gradle, Android or device execution.'}
    (OUT / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
