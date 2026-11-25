#!/usr/bin/env python3
"""Host-only producer and cleanup controls; all Android transport here is synthetic."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_android_opus_probe as controller


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ProducerControls(unittest.TestCase):
    def test_current_run_identity_rejects_cross_attempt_and_cross_commit(self):
        environment = {'GITHUB_SHA': 'a' * 40, 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}
        receipt = {'workflow_commit': 'a' * 40, 'run_id': '123', 'attempt': '1'}
        with patch.dict(os.environ, environment):
            controller.same_run(receipt)
            for key, value in (('workflow_commit', 'b' * 40), ('run_id', '124'), ('attempt', '2'), ('attempt', 1)):
                with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                    controller.same_run(dict(receipt, **{key: value}))

    def test_bounded_producer_bytes_reject_truncation_modification_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'artifact'; raw = b'HOST_CONTROL_ONLY'; p.write_bytes(raw)
            self.assertEqual(controller.bounded_file(p, sha(raw), 100), p)
            for body in (raw[:-1], raw + b'x', b'X' + raw[1:]):
                p.write_bytes(body)
                with self.assertRaises(RuntimeError):
                    controller.bounded_file(p, sha(raw), 100)
            p.write_bytes(raw)
            with self.assertRaises(RuntimeError):
                controller.bounded_file(p, sha(raw), len(raw) - 1)
            if os.name != 'nt':
                link = Path(tmp) / 'link'; link.symlink_to(p)
                with self.assertRaises(RuntimeError):
                    controller.bounded_file(link, sha(raw), 100)

    def test_package_path_rejects_splits_traversal_and_other_roots(self):
        good = 'package:/data/app/~~token/org.lab.waex.qa.opus-token/base.apk\n'
        self.assertEqual(controller.installed_apk_path(good), good.strip().removeprefix('package:'))
        for bad in ('', good + good, good + 'package:/data/app/a/split.apk\n',
                    good.replace('/~~token/', '/../'), good.replace('/data/app/', '/sdcard/'),
                    good.replace('base.apk', 'base.apk;id'), good.replace('base.apk', 'split.apk')):
            with self.subTest(bad=bad), self.assertRaises(RuntimeError):
                controller.installed_apk_path(bad)

    def test_receipt_boolean_contract_rejects_integer_substitutes(self):
        controller.exact_fields({'closed': True}, {'closed': True})
        with self.assertRaises(RuntimeError):
            controller.exact_fields({'closed': 1}, {'closed': True})


class CleanupControls(unittest.TestCase):
    def exercise(self, *, preexisting=False, validation_failure=False, tamper_cleanup=False,
                 installation_failure=False, qemu='1', uid='2000'):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp); out = work / 'reports'; out.mkdir()
            apk = work / 'fixture.apk'; raw = b'SYNTHETIC_CONTROLLER_FIXTURE'; apk.write_bytes(raw)
            build = work / 'build.json'; build.write_text('{}')
            decoder = work / 'decoder.so'; decoder.write_bytes(b'NOT_LOADED')
            decoder_receipt = work / 'decoder.json'; decoder_receipt.write_text('{}')
            context = SimpleNamespace(target='api35', serial='emulator-5580', api=35,
                                      guest={'abi': 'x86_64'}, adb=Path('/owned/adb'),
                                      application_page_size_bytes=4096, work=work, out=out,
                                      result={}, env={'OWNED_ADB_CONTEXT': 'yes'})
            names = []; present = preexisting

            def transport(folder, name, command, environment, timeout=30, required=True):
                nonlocal present
                self.assertIs(environment, context.env)
                self.assertEqual(command[:3], ['/owned/adb', '-s', 'emulator-5580'])
                names.append(name)
                text = ''
                if name == 'opus-guest-emulator': text = qemu + '\n'
                elif name == 'opus-shell-uid': text = uid + '\n'
                elif 'package-' in name: text = 'package:' + controller.PACKAGE + '\n' if present else ''
                elif name == 'opus-install':
                    if installation_failure: raise RuntimeError('SYNTHETIC_INSTALL_FAILURE')
                    present = True; text = 'Success\n'
                elif name.endswith('-path'): text = 'package:/data/app/owned/base.apk\n'
                elif name.endswith('-pull'):
                    altered = tamper_cleanup and name == 'opus-before-uninstall-pull'
                    Path(command[-1]).write_bytes((b'X' + raw[1:]) if altered else raw)
                elif name == 'opus-uninstall': present = False; text = 'Success\n'
                elif name != 'opus-instrumentation': raise AssertionError('Unexpected transport command: ' + name)
                (folder / (name + '.log')).write_text(text)
                return {'returncode': 0, 'failure': None}, text

            report = {'android_receipt': {'checks': 189}, 'transport': {'jni_calls': 157}}
            outcome = RuntimeError('SYNTHETIC_VALIDATION_FAILURE') if validation_failure else None
            action = controller.opus_action(apk, build, sha(raw), sha(build.read_bytes()), decoder,
                                            decoder_receipt, sha(decoder.read_bytes()), sha(decoder_receipt.read_bytes()))
            error = None
            with patch.object(controller, 'invoke', side_effect=transport), \
                    patch.object(controller, 'validate_probe', side_effect=outcome,
                                 return_value=(report, {'pcm48k': b'HOST_ONLY', 'pcm16k': b'HOST_ONLY'})):
                try:
                    action(context)
                except RuntimeError as caught:
                    error = str(caught)
            phase = json.loads((out / 'opus-phase.json').read_bytes())
            return names, phase, error, present

    def test_success_checks_fresh_identity_before_uninstall_and_confirms_absence(self):
        names, phase, error, present = self.exercise()
        self.assertIsNone(error); self.assertFalse(present); self.assertEqual(phase['status'], 'PASS')
        self.assertTrue(phase['package_absent_after_cleanup'])
        self.assertLess(names.index('opus-before-uninstall-pull'), names.index('opus-uninstall'))
        self.assertLess(names.index('opus-uninstall'), names.index('opus-package-after-cleanup'))

    def test_runtime_failure_still_cleans_only_the_owned_apk(self):
        names, phase, error, present = self.exercise(validation_failure=True)
        self.assertIn('SYNTHETIC_VALIDATION_FAILURE', error)
        self.assertIn('opus-uninstall', names); self.assertFalse(present)
        self.assertEqual(phase['status'], 'BLOCKED'); self.assertTrue(phase['package_absent_after_cleanup'])

    def test_changed_apk_is_never_uninstalled_and_both_errors_survive(self):
        names, phase, error, present = self.exercise(validation_failure=True, tamper_cleanup=True)
        self.assertNotIn('opus-uninstall', names); self.assertTrue(present)
        self.assertIn('execution_error', phase); self.assertIn('cleanup_error', phase)
        self.assertIn('SYNTHETIC_VALIDATION_FAILURE', error)
        self.assertFalse(phase['package_absent_after_cleanup']); self.assertEqual(phase['status'], 'BLOCKED')

    def test_existing_package_is_preserved_without_install_or_uninstall(self):
        names, phase, error, present = self.exercise(preexisting=True)
        self.assertIsNotNone(error); self.assertTrue(present)
        self.assertNotIn('opus-install', names); self.assertNotIn('opus-uninstall', names)
        self.assertEqual(phase['status'], 'BLOCKED')

    def test_unacknowledged_install_is_not_promoted_to_pass(self):
        names, phase, error, present = self.exercise(installation_failure=True)
        self.assertIn('SYNTHETIC_INSTALL_FAILURE', error); self.assertFalse(present)
        self.assertNotIn('opus-uninstall', names); self.assertEqual(phase['status'], 'BLOCKED')

    def test_non_emulator_or_root_shell_stops_before_package_mutation(self):
        for kwargs in ({'qemu': '0'}, {'uid': '0'}):
            names, phase, error, present = self.exercise(**kwargs)
            self.assertIsNotNone(error); self.assertFalse(present)
            self.assertNotIn('opus-install', names); self.assertNotIn('opus-uninstall', names)
            self.assertEqual(phase['status'], 'BLOCKED')


if __name__ == '__main__':
    unittest.main()
