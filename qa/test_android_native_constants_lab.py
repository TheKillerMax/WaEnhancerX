#!/usr/bin/env python3
"""Integration controls use the reviewed lock, mock boot/ADB and synthetic receipts only."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import android_native_constants_lab as lab
from android_emulator_lab_pilot import BootContext, guest_version_identity
from android_emulator_lab_preflight import save, sha256_file
import summarize_native_constants_lab as summary
import test_native_constants_probe as controls
import validate_native_constants_probe as validate


class LabControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='waex-native-integration-')
        self.root = Path(self.temp.name)
        self.lock_path = Path(__file__).parent / 'android_emulator_lab_matrix_lock.json'
        self.lock, _ = lab.checked_lock(self.lock_path, 'api35')
        self.bundle = self.root / 'bundle'; self.bundle.mkdir()
        self.apk = self.bundle / 'native-constants-probe.apk'
        self.apk_sha, self.elf_sha = controls.make_apk(self.apk)
        self.build = {
            'schema':'WAEXDIAG_PROBE_BUILD_V2','status':'PASS_BUILD_ONLY','scope':validate.SCOPE,
            'package':validate.PACKAGE,'source_revision':validate.SOURCE_REVISION,
            'source_sha256':validate.SOURCE_SHA256,'cmake_sha256':validate.CMAKE_SHA256,
            'contract_sha256':validate.CONTRACT_SHA256,'ephemeral_key_absent':True,
            'license_registry_unchanged':True,'licenses_accepted_by_this_run':False,
            'jni_executed':False,'android_booted':False,'input_files':validate.source_inventory(),
            'tools':{'java':{'sha256':self.lock['tool_sha256']['java']}},
            'native':{'elf_sha256':self.elf_sha,'abi':'x86_64','api':24,
                      'elf':{'issues':[],'relro_segments':[{'control':True}]},
                      'jni_exports':list(validate.contract()['methods'])},
            'apk':validate.inspect_apk(self.apk,self.apk_sha,self.elf_sha)}
        self.build_path = self.bundle / 'build-result.json'
        self.build_path.write_text(json.dumps(self.build),encoding='utf-8')
        self.build_sha = sha256_file(self.build_path)

    def tearDown(self):
        self.temp.cleanup()

    def action(self):
        return lab.native_action(self.bundle,self.apk_sha,self.build_sha,self.lock)

    def context(self,target='api35-16k',suffix=''):
        work=self.root/(target+suffix); out=work/'reports'; out.mkdir(parents=True)
        api, _, pages=lab.TARGETS[target]
        guest={'sdk':str(api),'abi':'x86_64','application_page_size_bytes':str(pages),'sdk_full_property':''}
        return BootContext(target,api,0,pages,Path('adb'),validate.SERIAL,{},work,out,guest,
                           self.lock['targets'][target],{})

    def test_exact_targets_and_unchanged_source_pins(self):
        self.assertEqual(set(lab.TARGETS),{'api35','api35-16k'})
        for target in lab.TARGETS:
            _,entry=lab.checked_lock(self.lock_path,target)
            self.assertEqual(entry['image']['path'],lab.TARGETS[target][1])
            self.assertEqual(entry['application_page_size_bytes'],lab.TARGETS[target][2])
        with self.assertRaises(ValueError): lab.checked_lock(self.lock_path,'api24')
        with mock.patch.object(validate,'source_inventory',return_value={}):
            with self.assertRaises(ValueError): lab.checked_lock(self.lock_path,'api35')

    def test_independent_producer_hashes_before_boot(self):
        apk, _, _ = lab.verified_bundle(self.bundle,self.apk_sha,self.build_sha,self.lock)
        self.assertEqual(apk,self.apk)
        for apk_sha,build_sha in [('0'*64,self.build_sha),(self.apk_sha,'0'*64)]:
            with self.subTest(apk_sha=apk_sha), self.assertRaises(ValueError):
                lab.verified_bundle(self.bundle,apk_sha,build_sha,self.lock)
        original=self.build_path.read_bytes()
        self.build_path.write_bytes(original+b' ')
        with self.assertRaises(ValueError):
            lab.verified_bundle(self.bundle,self.apk_sha,self.build_sha,self.lock)
        self.build_path.write_bytes(original)
        with mock.patch.object(lab,'context_check'), mock.patch.object(lab,'boot_main') as boot:
            argv=['adapter','--target','api35','--lock',str(self.lock_path),'--out',str(self.root/'unused'),
                  '--apk-dir',str(self.bundle),'--apk-sha256',self.apk_sha,'--build-receipt-sha256','0'*64]
            with mock.patch.object(sys,'argv',argv),self.assertRaises(ValueError):lab.main()
            boot.assert_not_called()

    def test_adapter_preserves_specific_receipt_and_ownership(self):
        original_receipt=controls.receipt
        for target in lab.TARGETS:
            with self.subTest(target=target):
                context=self.context(target)
                fake=controls.FakeAdb(self.apk,self.apk_sha,self.elf_sha,'pass')
                def modeled_guest_receipt(*args,**kwargs):
                    value=original_receipt(*args,**kwargs)
                    value['application_page_size_bytes']=context.application_page_size_bytes
                    return value
                with mock.patch.object(lab.probe.subprocess,'run',fake), mock.patch.object(
                        controls,'receipt',side_effect=modeled_guest_receipt):
                    phase=self.action()(context)
                self.assertEqual(phase['status'],'PASS')
                self.assertEqual(phase['probe']['status'],'PASS_WAEXDIAG_JNI_CONSTANTS')
                self.assertTrue(phase['package_absent_after_cleanup'])
                self.assertEqual(phase['probe']['receipt']['jni_calls'],14)
                self.assertTrue(context.result['apk_install_attempted'])
                self.assertTrue(context.result['apk_installed'])
                self.assertFalse(fake.installed)
                self.assertEqual(sha256_file(context.out/'native-build-result.json'),self.build_sha)

    def test_adapter_does_not_promote_failure_or_use_wrong_context(self):
        for mode in ('load_false','uninstall_failed'):
            with self.subTest(mode=mode):
                context=self.context(suffix='-'+mode)
                fake=controls.FakeAdb(self.apk,self.apk_sha,self.elf_sha,mode)
                with mock.patch.object(lab.probe.subprocess,'run',fake),self.assertRaises(ValueError):
                    self.action()(context)
                phase=json.loads((context.out/'native-constants-phase.json').read_text())
                self.assertEqual(phase['status'],'BLOCKED')
        wrong=self.root/'wrong';wrong.mkdir()
        context=BootContext('api35',35,0,4096,Path('adb'),'physical-device',{},wrong,wrong,
                            {'sdk':'35','abi':'x86_64','application_page_size_bytes':'4096'},
                            self.lock['targets']['api35'],{})
        with mock.patch.object(lab.probe,'run_probe') as run,self.assertRaises(ValueError):
            self.action()(context)
        run.assert_not_called()

    def sealed_result(self):
        context=self.context()
        fake=controls.FakeAdb(self.apk,self.apk_sha,self.elf_sha,'pass')
        with mock.patch.object(lab.probe.subprocess,'run',fake):
            phase=self.action()(context)
        result={'target':context.target,'status':'PASS','phase':'waexdiag_jni_constants',
                'android_booted':True,'requested_phase_completed':True,'owned_emulator_reaped':True,
                'license_files_unchanged':True,'apk_install_attempted':True,'apk_installed':True,
                'licenses_accepted_by_this_run':False,'github_run_id':'42','github_run_attempt':'1',
                'github_head_sha':'a'*40,'lock_sha256':sha256_file(self.lock_path),
                'source_sha256':self.lock['source_sha256']['qa/android_emulator_lab_pilot.py'],
                'issues':[],'guest':context.guest,'guest_version':guest_version_identity(context.guest,context.entry['image']),
                'phase_receipt':phase}
        save(context.out,'native-result.json',result)
        self.seal(context.out)
        return context.out/'native-result.json'

    def seal(self,directory):
        save(directory,'manifest.json',{p.relative_to(directory).as_posix():
              {'bytes':p.stat().st_size,'sha256':sha256_file(p)}
              for p in directory.rglob('*') if p.is_file() and p.name!='manifest.json'})

    def row(self,path):
        return summary.validate_row(path,self.lock,sha256_file(self.lock_path),'42','1','a'*40,
                                    self.apk_sha,self.build_sha)

    def test_summary_revalidates_raw_instrumentation_and_run_identity(self):
        path=self.sealed_result()
        self.assertEqual(self.row(path)['status'],'PASS')
        original=path.read_bytes()
        result=json.loads(original);result['github_run_id']='old'
        save(path.parent,path.name,result);self.seal(path.parent)
        with self.assertRaises(ValueError):self.row(path)
        path.write_bytes(original)
        log=next((path.parent/'native-probe').glob('*-instrumentation.log'))
        log.write_text(log.read_text().replace('INSTRUMENTATION_CODE: -1',''),encoding='utf-8')
        self.seal(path.parent)
        with self.assertRaises(ValueError):self.row(path)

    def test_summary_requires_both_targets_and_no_issue(self):
        rows={name:{'status':'PASS'} for name in lab.TARGETS}
        self.assertEqual(summary.matrix_status(rows,[]),'PASS_TWO_WAEXDIAG_PAGE_ENVIRONMENTS')
        self.assertEqual(summary.matrix_status({'api35':{'status':'PASS'}},[]),'BLOCKED')
        self.assertEqual(summary.matrix_status(rows,['duplicate current-run receipt']),'BLOCKED')
        rows['api35-16k']['status']='MISSING'
        self.assertEqual(summary.matrix_status(rows,[]),'BLOCKED')


if __name__=='__main__':
    unittest.main(verbosity=2)
