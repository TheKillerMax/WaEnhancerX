#!/usr/bin/env python3
"""Host controls only: synthetic APK container, simulated ADB; no Android or native execution."""
import copy
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile

import build_native_constants_probe as builder
import run_native_constants_probe as launcher
import validate_native_constants_probe as validate


def make_apk(path, aligned=True):
    elf = b'\x7fELF' + b'HOST-STRUCTURE-CONTROL-NOT-A-REAL-NATIVE-LIBRARY'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('AndroidManifest.xml', b'host structural fixture')
        archive.writestr('classes.dex', b'host structural fixture')
        archive.writestr(validate.CONTRACT_ENTRY,
                        (Path(validate.__file__).parent / 'native_constants_probe/expected_constants.json').read_bytes())
        entry = zipfile.ZipInfo(validate.ELF_ENTRY)
        entry.compress_type = zipfile.ZIP_STORED
        if aligned:
            padding = (-(archive.fp.tell() + 30 + len(entry.filename.encode()) + 4)) % 16384
            entry.extra = struct.pack('<HH', 0xCAFE, padding) + b'\x00' * padding
        archive.writestr(entry, elf)
    return validate.digest(path.read_bytes()), validate.digest(elf)


def receipt(apk_sha, elf_sha, nonce='a'*32, api=35, page=16384):
    return {'schema': 'WAEXDIAG_JNI_CONSTANTS_V2', 'scope': validate.SCOPE, 'package': validate.PACKAGE,
            'run_nonce': nonce, 'sdk': api, 'release': '15', 'hardware': 'ranchu',
            'supported_abis': ['x86_64', 'x86'], 'process_is_64bit': True, 'uid': 10123, 'pid': 2222,
            'application_page_size_bytes': page, 'own_apk_sha256': apk_sha,
            'bundled_elf_sha256': elf_sha, 'source_revision': validate.SOURCE_REVISION,
            'source_sha256': validate.SOURCE_SHA256, 'cmake_sha256': validate.CMAKE_SHA256,
            'contract_sha256': validate.CONTRACT_SHA256, 'load_library_returned': True,
            'jni_calls': 14, 'strings_checked': 38,
            'return_values': {name: item['value'] for name, item in validate.contract()['methods'].items()},
            'duration_ms': 7}


def output(value):
    return 'INSTRUMENTATION_RESULT: waex_native_receipt=' + json.dumps(value) + '\nINSTRUMENTATION_CODE: -1\n'


class FakeAdb:
    def __init__(self, apk, apk_sha, elf_sha, mode):
        self.apk, self.apk_sha, self.elf_sha, self.mode = apk, apk_sha, elf_sha, mode
        self.installed = mode == 'preexisting'
        self.commands = []
        self.pulls = 0

    def __call__(self, command, **kwargs):
        self.commands.append(command)
        assert command[1:3] == ['-s', validate.SERIAL]
        args, code, text = command[3:], 0, ''
        if args == ['get-state']:
            text = 'device'
        elif args[:2] == ['shell', 'getprop']:
            properties = {'ro.kernel.qemu': '1', 'sys.boot_completed': '1',
                          'ro.build.version.sdk': '35', 'ro.product.cpu.abi': 'x86_64'}
            changes = {'wrong_api': ('ro.build.version.sdk', '34'), 'wrong_abi': ('ro.product.cpu.abi', 'arm64-v8a'),
                       'wrong_qemu': ('ro.kernel.qemu', '0'), 'not_booted': ('sys.boot_completed', '0')}
            if self.mode in changes:
                key, value = changes[self.mode]; properties[key] = value
            text = properties[args[2]]
        elif args[:4] == ['shell', 'pm', 'list', 'packages']:
            assert args == ['shell', 'pm', 'list', 'packages', '--user', '0', validate.PACKAGE]
            text = 'package:' + validate.PACKAGE if self.installed else ''
        elif args[0] == 'install':
            assert args == ['install', '-t', str(self.apk)]
            if self.mode == 'install_failed':
                code, text = 1, 'Failure [INSTALL_FAILED_TEST_ONLY]'
            else:
                self.installed = True
                if self.mode == 'install_timeout':
                    raise subprocess.TimeoutExpired(command, 90)
                text = 'Performing Streamed Install\nSuccess'
                if self.mode == 'install_ambiguous':
                    text += '\nSuccess'
        elif args[:3] == ['shell', 'pm', 'path']:
            assert self.installed
            text = 'package:/data/app/~~qa/' + validate.PACKAGE + '-test/base.apk'
        elif args[0] == 'pull':
            self.pulls += 1
            data = self.apk.read_bytes()
            if self.mode == 'apk_mismatch' or self.mode == 'cleanup_wrong_hash' and self.pulls == 2:
                data = b'!' + data[1:]
            Path(args[2]).write_bytes(data)
            text = '1 file pulled'
        elif args[:3] == ['shell', 'am', 'instrument']:
            if self.mode == 'instrument_timeout':
                raise subprocess.TimeoutExpired(command, 90)
            nonce = args[args.index('run_nonce') + 1]
            value = receipt(self.apk_sha, self.elf_sha, nonce)
            if self.mode == 'nonce_mismatch': value['run_nonce'] = 'f' * 32
            if self.mode == 'bad_values': value['return_values']['lspConfigDb'] = 'different'
            if self.mode == 'load_false': value['load_library_returned'] = False
            text = output(value)
            if self.mode == 'missing_finish': text = text.replace('INSTRUMENTATION_CODE: -1\n', '')
            if self.mode == 'duplicate_finish': text += 'INSTRUMENTATION_CODE: -1\n'
            if self.mode == 'instrument_failure': text += 'INSTRUMENTATION_FAILED: synthetic\n'
        elif args[0] == 'uninstall':
            assert args == ['uninstall', validate.PACKAGE]
            if self.mode == 'uninstall_failed':
                code, text = 1, 'Failure'
            else:
                text = 'Success'
                if self.mode != 'uninstall_retained': self.installed = False
        else:
            raise AssertionError('Unexpected ADB command: ' + repr(args))
        return subprocess.CompletedProcess(command, code, text.encode())


class Controls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='waex-jni-host-')
        self.root = Path(self.temp.name)
        self.apk = self.root / 'fixture.apk'
        self.apk_sha, self.elf_sha = make_apk(self.apk)

    def tearDown(self):
        self.temp.cleanup()

    def validate(self, text):
        return validate.validate_output(text, nonce='a'*32, api=35, page_size=16384,
                                        apk_sha256=self.apk_sha, elf_sha256=self.elf_sha)

    def test_badging_aliases_positive_and_ambiguity_negative(self):
        text = "package: name='" + validate.PACKAGE + "' versionCode='1'\n{minimum}:'24'\ntargetSdkVersion:'36'\nnative-code: 'x86_64'\n"
        for field in ('sdkVersion', 'minSdkVersion'):
            self.assertEqual(builder.verify_badging(text.format(minimum=field))['minimum_field_observed'], field)
        valid = text.format(minimum='sdkVersion')
        wrong = [valid.replace("sdkVersion:'24'\n", ''), valid.replace("sdkVersion:'24'", "sdkVersion:'23'"),
                 valid + "minSdkVersion:'24'\n", valid + "sdkVersion:'23'\n",
                 valid.replace("targetSdkVersion:'36'", "targetSdkVersion:'35'"),
                 valid + "targetSdkVersion:'36'\n", valid + "uses-permission:'android.permission.INTERNET'\n",
                 valid + "uses-permission-sdk-23:'android.permission.INTERNET'\n",
                 valid.replace("'x86_64'", "'arm64-v8a'"), valid.replace(validate.PACKAGE, 'org.other')]
        for item in wrong:
            with self.subTest(item=item), self.assertRaises(ValueError): builder.verify_badging(item)

    def test_manifest_isolated(self):
        source = Path(builder.FIXTURE) / 'AndroidManifest.xml'
        builder.verify_manifest(source)
        for old, new in [('debuggable="false"', 'debuggable="true"'),
                         ('minSdkVersion="24"', 'minSdkVersion="23"'),
                         ('<application ', '<uses-permission android:name="android.permission.INTERNET"/><application ')]:
            changed = self.root / 'manifest.xml'
            changed.write_text(source.read_text().replace(old, new), encoding='utf-8')
            with self.subTest(change=old), self.assertRaises(ValueError): builder.verify_manifest(changed)

    def test_container_identity_alignment_and_single_elf(self):
        observed = validate.inspect_apk(self.apk, self.apk_sha, self.elf_sha)
        self.assertEqual(observed['elf_data_offset'] % 16384, 0)
        bad = self.root / 'unaligned.apk'; bad_sha, elf_sha = make_apk(bad, False)
        with self.assertRaises(ValueError): validate.inspect_apk(bad, bad_sha, elf_sha)
        with self.assertRaises(ValueError): validate.inspect_apk(self.apk, '0'*64, self.elf_sha)
        with self.assertRaises(ValueError): validate.inspect_apk(self.apk, self.apk_sha, '0'*64)
        with zipfile.ZipFile(self.apk, 'a') as archive: archive.writestr('lib/x86_64/extra.so', b'foreign')
        with self.assertRaises(ValueError): validate.inspect_apk(self.apk, validate.digest(self.apk.read_bytes()), self.elf_sha)

    def test_strict_json_and_instrumentation_finish(self):
        value = receipt(self.apk_sha, self.elf_sha)
        self.assertEqual(self.validate(output(value)), value)
        text = output(value)
        negatives = [text.replace('INSTRUMENTATION_CODE: -1\n', ''), text + 'INSTRUMENTATION_CODE: -1\n',
                     text.replace('INSTRUMENTATION_CODE: -1', 'INSTRUMENTATION_CODE: 0'),
                     text + 'INSTRUMENTATION_FAILED: synthetic\n', text + 'INSTRUMENTATION_ABORTED: synthetic\n',
                     text.replace('"sdk": 35', '"sdk": 35, "sdk": 35'),
                     text.replace('"duration_ms": 7', '"duration_ms": NaN'),
                     text + text.splitlines()[0] + '\n']
        for item in negatives:
            with self.subTest(item=item[-120:]), self.assertRaises(ValueError): self.validate(item)

    def test_every_jni_return_and_all_identity_gates(self):
        value = receipt(self.apk_sha, self.elf_sha)
        for name in value['return_values']:
            changed = copy.deepcopy(value)
            original = changed['return_values'][name]
            changed['return_values'][name] = original + ['wrong'] if isinstance(original, list) else original + 'wrong'
            with self.subTest(method=name), self.assertRaises(ValueError): self.validate(output(changed))
        for key, replacement in [('run_nonce','b'*32), ('sdk',34), ('sdk',True), ('application_page_size_bytes',4096),
                                 ('process_is_64bit',False), ('jni_calls',13), ('strings_checked',37),
                                 ('load_library_returned',False), ('own_apk_sha256','0'*64),
                                 ('bundled_elf_sha256','0'*64), ('source_sha256','0'*64),
                                 ('contract_sha256','0'*64), ('cmake_sha256','0'*64), ('uid',0),
                                 ('pid',0), ('duration_ms',True), ('hardware','physical'),
                                 ('supported_abis',['arm64-v8a'])]:
            changed = copy.deepcopy(value); changed[key] = replacement
            with self.subTest(key=key), self.assertRaises(ValueError): self.validate(output(changed))

    def build_receipt(self):
        return {'status':'PASS_BUILD_ONLY','schema':'WAEXDIAG_PROBE_BUILD_V2','scope':validate.SCOPE,
                'package':validate.PACKAGE,'ephemeral_key_absent':True,'license_registry_unchanged':True,
                'input_files':validate.source_inventory(),'source_revision':validate.SOURCE_REVISION,
                'source_sha256':validate.SOURCE_SHA256,'cmake_sha256':validate.CMAKE_SHA256,
                'contract_sha256':validate.CONTRACT_SHA256,'native':{'elf_sha256':self.elf_sha},
                'apk':validate.inspect_apk(self.apk,self.apk_sha,self.elf_sha)}

    def test_launcher_ownership_failure_and_cleanup_scenarios(self):
        build = self.root / 'build.json'; build.write_text(json.dumps(self.build_receipt()),encoding='utf-8')
        modes = ('pass','preexisting','wrong_api','wrong_abi','wrong_qemu','not_booted','install_failed',
                 'install_ambiguous','install_timeout','apk_mismatch','missing_finish','duplicate_finish',
                 'nonce_mismatch','bad_values','load_false','instrument_failure','instrument_timeout',
                 'cleanup_wrong_hash','uninstall_failed','uninstall_retained')
        for mode in modes:
            with self.subTest(mode=mode):
                fake = FakeAdb(self.apk,self.apk_sha,self.elf_sha,mode)
                with mock.patch.object(launcher.subprocess,'run',fake):
                    result = launcher.run_probe('adb',validate.SERIAL,35,16384,self.apk,self.apk_sha,build,self.root/mode,env={})
                self.assertEqual(result['status']=='PASS_WAEXDIAG_JNI_CONSTANTS',mode=='pass')
                commands = [command[3:] for command in fake.commands]
                if mode in ('preexisting','wrong_api','wrong_abi','wrong_qemu','not_booted'):
                    self.assertFalse(any(c[0] in ('install','uninstall') for c in commands))
                if mode in ('apk_mismatch','cleanup_wrong_hash'):
                    self.assertFalse(any(c[0]=='uninstall' for c in commands))
                if mode in ('pass','install_ambiguous','install_timeout','missing_finish','duplicate_finish',
                            'nonce_mismatch','bad_values','load_false','instrument_failure','instrument_timeout'):
                    self.assertFalse(fake.installed)
                    self.assertTrue(result['cleanup_verified'])
                self.assertFalse(list((self.root/mode).glob('*.apk')))
                self.assertFalse(any('root' in c or 'reboot' in c for c in commands))
                if mode!='pass': self.assertFalse(result['status'].startswith('PASS'))

    def test_no_adb_before_external_identity_guards(self):
        build = self.root / 'build.json'
        value = self.build_receipt(); value['input_files']['run_native_constants_probe.py']['sha256']='0'*64
        build.write_text(json.dumps(value),encoding='utf-8')
        with mock.patch.object(launcher.subprocess,'run') as run:
            with self.assertRaises(ValueError):
                launcher.run_probe('adb','physical-device',35,16384,self.apk,self.apk_sha,build,self.root/'wrong-serial',env={})
            result = launcher.run_probe('adb',validate.SERIAL,35,16384,self.apk,self.apk_sha,build,self.root/'wrong-source',env={})
            self.assertEqual(result['status'],'FAIL')
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
