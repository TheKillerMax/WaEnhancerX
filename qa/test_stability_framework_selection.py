#!/usr/bin/env python3
"""Validate suite identities, source inventory and fail-closed fixture selection."""
import ast
from pathlib import Path
import re
import tempfile
import unittest

import verify_stability_framework as runner

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {'update': 12, 'filter': 3, 'evidence': 15, 'clock': 1}


def literal_assignment(name):
    tree = ast.parse((ROOT / 'qa/verify_stability_framework.py').read_text())
    values = [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    ]
    if len(values) != 1:
        raise AssertionError('Expected one literal assignment for ' + name)
    return ast.literal_eval(values[0])


def fake_root(root, with_clock=False):
    for mode in EXPECTED:
        fixture = root / ('qa/fixtures/Stability' + mode.title() + 'Test.kt')
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.touch()
    if with_clock:
        clock = root / 'app/src/main/java/com/waenhancer/ui/components/RuntimeObservationClock.kt'
        clock.parent.mkdir(parents=True)
        clock.touch()


class StabilitySelectionTests(unittest.TestCase):
    def test_current_all_runs_current_classifier_once(self):
        self.assertEqual(['update', 'filter', 'evidence'], runner.select_modes('all', ROOT))
        self.assertEqual(['evidence'], runner.select_modes('evidence', ROOT))

    def test_absent_clock_fails_instead_of_claiming_classifier_is_clock(self):
        with self.assertRaisesRegex(ValueError, 'no clock suite ran'):
            runner.select_modes('clock', ROOT)

    def test_present_clock_keeps_distinct_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_root(root, with_clock=True)
            self.assertEqual(['update', 'filter', 'evidence', 'clock'], runner.select_modes('all', root))
            self.assertEqual(['clock'], runner.select_modes('clock', root))

    def test_missing_selected_fixture_is_fatal(self):
        for mode in EXPECTED:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                fake_root(root, with_clock=True)
                (root / ('qa/fixtures/Stability' + mode.title() + 'Test.kt')).unlink()
                with self.assertRaisesRegex(ValueError, 'Missing selected stability fixture'):
                    runner.select_modes(mode, root)
                with self.assertRaisesRegex(ValueError, 'Missing selected stability fixture'):
                    runner.select_modes('all', root)

    def test_standalone_mode_does_not_require_other_fixtures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = root / 'qa/fixtures/StabilityEvidenceTest.kt'
            fixture.parent.mkdir(parents=True)
            fixture.touch()
            self.assertEqual(['evidence'], runner.select_modes('evidence', root))

    def test_unknown_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown stability mode'):
            runner.select_modes('obsolete', ROOT)

    def test_preserved_method_inventory_and_runner_totals(self):
        self.assertEqual(EXPECTED, literal_assignment('expected'))
        for mode, count in EXPECTED.items():
            fixture = ROOT / ('qa/fixtures/Stability' + mode.title() + 'Test.kt')
            methods = re.findall(r'@Test\s+fun\s+(\w+)', fixture.read_text())
            self.assertEqual(count, len(methods), mode)
            self.assertEqual(len(methods), len(set(methods)), mode)
        self.assertEqual(30, sum(EXPECTED[m] for m in runner.select_modes('all', ROOT)))

    def test_current_modes_stage_existing_production_sources(self):
        sources = literal_assignment('sources')
        self.assertEqual(set(EXPECTED), set(sources))
        self.assertEqual(['utils/InjectionEvidence.kt'], sources['evidence'])
        for mode in runner.select_modes('all', ROOT):
            self.assertEqual(len(sources[mode]), len(set(sources[mode])), mode)
            for path in sources[mode]:
                self.assertTrue((ROOT / 'app/src/main/java/com/waenhancer' / path).is_file(), path)
        for path in ('ui/designsystem/WaexColors.kt', 'xposed/utils/HookErrors.java'):
            self.assertIn(path, sources['update'])
        for path in ('xposed/features/customization/LayoutPassThrottle.kt',
                     'xposed/utils/HostResourceIds.java', 'xposed/utils/HookErrors.java'):
            self.assertIn(path, sources['filter'])


if __name__ == '__main__':
    unittest.main()
