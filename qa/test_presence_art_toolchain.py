#!/usr/bin/env python3
"""Host-only compiler/diagnostic controls; no Android, build, network or download."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import build_presence_art_lab as build
from presence_art_probe import build_presence_art_probe as offline


def toolchain_fixture():
    """Synthetic receipt tied to the real source recipe; never a tool execution."""
    module, recipe = offline.compiler_contract()
    return {'schema': recipe['schema'], 'lock_sha256': build.digest(module.LOCK),
            'helper_sha256': build.digest(Path(module.__file__)), 'artifacts': recipe['artifacts'],
            'kotlin_version_output': 'info: kotlinc-jvm 2.0.20 (JRE 21.0.13+9-LTS)',
            'launcher_sha256': 'a' * 64,
            'java': {'java_home': '/host-fixture/jdk21', 'properties': {'java.specification.version': '21'},
                     'javac_version': 'javac 21.0.13',
                     'files_sha256': {name: 'b' * 64 for name in
                                     ('bin/java', 'bin/javac', 'release', 'lib/modules',
                                      'lib/ct.sym', 'lib/server/libjvm.so')}}}


def d8_fixture():
    return {stream: {'file': 'd8.' + stream + '.log', 'bytes': 0,
                     'sha256': hashlib.sha256(b'').hexdigest()} for stream in ('stdout', 'stderr')}


class CompilerControls(unittest.TestCase):
    def test_compiler_recipe_is_the_fixed_classvalue_contract(self):
        module, recipe = offline.compiler_contract()
        self.assertEqual(recipe['kotlin_version'], '2.0.20')
        self.assertEqual(recipe['java_major'], 21)
        self.assertEqual(len(recipe['artifacts']), 9)
        self.assertEqual({x['file'] for x in recipe['artifacts']}, module.LIBRARIES)
        stdlib = next(x for x in recipe['artifacts'] if x['file'] == 'kotlin-stdlib.jar')
        self.assertEqual(stdlib['sha256'], 'fb169596659a518357c4b2c16f43dc75ab1c4980565ed4b4a317a050e5e39006')
        self.assertEqual(stdlib['bytes'], 1747659)

    def test_changed_recipe_source_is_rejected_before_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); qa = root / 'qa'; probe = qa / 'presence_art_probe'
            probe.mkdir(parents=True)
            lock = copy.deepcopy(build.checked_lock())
            for rel in lock['toolchain_source_sha256']:
                target = root / rel; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((offline.HERE.parent.parent / rel).read_bytes())
            lock['toolchain_source_sha256']['qa/class_metadata_art_probe/toolchain.py'] = '0' * 64
            (qa / 'presence_art_lab_lock.json').write_text(json.dumps(lock))
            with patch.object(offline, 'HERE', probe), self.assertRaisesRegex(RuntimeError, 'recipe source changed'):
                offline.compiler_contract()

    def fake_home(self, directory):
        _, recipe = offline.compiler_contract()
        recipe = copy.deepcopy(recipe)
        home = Path(directory); (home / 'lib').mkdir()
        for row in recipe['artifacts']:
            raw = ('HOST FIXTURE ONLY:' + row['file']).encode()
            (home / 'lib' / row['file']).write_bytes(raw)
            row.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        return home, recipe

    def test_missing_extra_mutated_or_symlinked_jar_is_rejected(self):
        for mode in ('missing', 'extra', 'mutated', 'symlink'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                home, recipe = self.fake_home(directory)
                self.assertEqual(len(offline.verify_compiler_home(home, recipe)), 9)
                target = home / 'lib' / recipe['artifacts'][0]['file']
                if mode == 'missing':
                    target.unlink()
                elif mode == 'extra':
                    (home / 'lib/compose-compiler.jar').write_bytes(b'Unexpected compiler plugin')
                elif mode == 'mutated':
                    raw = target.read_bytes(); target.write_bytes(b'!' + raw[1:])
                else:
                    moved = home / 'original.jar'; target.rename(moved); target.symlink_to(moved)
                with self.assertRaises(RuntimeError):
                    offline.verify_compiler_home(home, recipe)

    def test_compiler_classpath_is_closed_and_excludes_external_plugins(self):
        _, recipe = offline.compiler_contract()
        home = Path('/host-fixture/kotlin')
        command = offline.compiler_command('/host-fixture/jdk21/bin/java', home, recipe)
        classpath = command[command.index('-cp') + 1].split(os.pathsep)
        self.assertEqual(classpath, [str(home / 'lib' / x['file']) for x in recipe['artifacts']])
        self.assertNotIn('*', ''.join(command))
        self.assertNotIn('compose-compiler', ''.join(command))
        self.assertIn('-XX:ActiveProcessorCount=2', command)
        self.assertEqual(command[-3:], ['org.jetbrains.kotlin.cli.jvm.K2JVMCompiler', '-kotlin-home', str(home)])

    def test_java_environment_clears_injected_options_and_uses_selected_jdk(self):
        module, _ = offline.compiler_contract()
        incoming = {key: '-injected-option' for key in module.JAVA_ENV_OPTIONS}
        incoming.update(PATH='/host-existing-bin', JAVA_HOME='/wrong-jdk')
        with patch.dict(os.environ, incoming, clear=True):
            env, removed = offline.clean_java_environment(Path('/chosen-jdk21'), module.JAVA_ENV_OPTIONS)
        self.assertEqual(set(removed), set(module.JAVA_ENV_OPTIONS))
        self.assertFalse(set(module.JAVA_ENV_OPTIONS).intersection(env))
        self.assertEqual(env['JAVA_HOME'], '/chosen-jdk21')
        self.assertEqual(env['PATH'], str(Path('/chosen-jdk21/bin')) + os.pathsep + '/host-existing-bin')

    def test_java_properties_preserve_values_across_lf_and_crlf(self):
        for separator in ('\n', '\r\n'):
            lines = ['Property settings:', '    java.specification.version = 21',
                     '    java.home = /host fixture/jdk21', '    java.runtime.version = 21.0.13+9-LTS',
                     '    java.class.path = ', '    unrelated = ignored']
            with self.subTest(separator=repr(separator)):
                self.assertEqual(offline.java_properties(separator.join(lines) + separator),
                                 {'java.specification.version': '21', 'java.home': '/host fixture/jdk21',
                                  'java.runtime.version': '21.0.13+9-LTS'})

    def test_receipt_rejects_other_compiler_jdk_lock_and_dependency(self):
        original = toolchain_fixture()
        build.validate_toolchain_receipt(original)
        mutations = [lambda r: r.update(kotlin_version_output='info: kotlinc-jvm 2.4.21 (JRE 21.0.13+9-LTS)'),
                     lambda r: r.update(lock_sha256='0' * 64),
                     lambda r: r.update(helper_sha256='0' * 64),
                     lambda r: r.update(launcher_sha256='not a hash'),
                     lambda r: r['java']['properties'].update({'java.specification.version': '17'}),
                     lambda r: r['java'].update(javac_version='javac 17.0.13'),
                     lambda r: r['java']['files_sha256'].pop('lib/ct.sym'),
                     lambda r: r['artifacts'][0].update(sha256='0' * 64)]
        for index, mutate in enumerate(mutations):
            value = copy.deepcopy(original); mutate(value)
            with self.subTest(case=index), self.assertRaises(RuntimeError):
                build.validate_toolchain_receipt(value)

    def test_d8_requires_both_streams_empty_without_rewriting_bytes(self):
        for stream, raw in (('stdout', b'\n'), ('stdout', b' '), ('stderr', b'Warning: kotlin metadata'),
                            ('stderr', b'Picked up JAVA_TOOL_OPTIONS'), ('stdout', b'\x00\xff')):
            with self.subTest(stream=stream, raw=raw), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                for name in ('stdout', 'stderr'):
                    (out / ('d8.' + name + '.log')).write_bytes(b'')
                self.assertEqual(offline.require_quiet_d8(out), d8_fixture())
                target = out / ('d8.' + stream + '.log'); target.write_bytes(raw)
                with self.assertRaisesRegex(RuntimeError, 'not filtered'):
                    offline.require_quiet_d8(out)
                self.assertEqual(target.read_bytes(), raw)

    def test_d8_receipt_rejects_nonempty_missing_or_noninteger_streams(self):
        build.validate_d8_receipt(d8_fixture())
        for mode in ('nonempty', 'wrong_hash', 'missing', 'boolean'):
            value = d8_fixture()
            if mode == 'nonempty': value['stderr']['bytes'] = 1
            elif mode == 'wrong_hash': value['stdout']['sha256'] = '0' * 64
            elif mode == 'missing': value.pop('stderr')
            else: value['stdout']['bytes'] = False
            with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                build.validate_d8_receipt(value)

    def test_command_recorder_preserves_separate_raw_streams_and_failure(self):
        for exit_code in (0, 3):
            with self.subTest(exit_code=exit_code), tempfile.TemporaryDirectory() as directory:
                out = Path(directory); commands = []
                program = "import sys;sys.stdout.buffer.write(b'A\\r\\n\\x00');sys.stderr.buffer.write(b'err');sys.exit(" + str(exit_code) + ')'
                if exit_code:
                    with self.assertRaises(RuntimeError):
                        offline.run_build_command(out, commands, 'host-control', [sys.executable, '-c', program], dict(os.environ))
                else:
                    offline.run_build_command(out, commands, 'host-control', [sys.executable, '-c', program], dict(os.environ))
                self.assertEqual((out / 'host-control.stdout.log').read_bytes(), b'A\r\n\x00')
                self.assertEqual((out / 'host-control.stderr.log').read_bytes(), b'err')
                self.assertEqual(commands[0]['exit_code'], exit_code)
                self.assertEqual(commands[0]['stdin'], 'closed')
                self.assertEqual(commands[0]['stdout'], {'bytes': 4, 'sha256': hashlib.sha256(b'A\r\n\x00').hexdigest()})
                self.assertEqual(json.loads((out / 'commands.json').read_bytes()), commands)

    def test_command_timeout_is_recorded_and_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory); commands = []
            with self.assertRaises(subprocess.TimeoutExpired):
                offline.run_build_command(out, commands, 'deadline-control',
                                          [sys.executable, '-c', 'import time; time.sleep(2)'],
                                          dict(os.environ), timeout=0.1)
            self.assertIsNone(commands[0]['exit_code'])
            self.assertEqual(commands[0]['failure'], 'deadline exceeded')


if __name__ == '__main__':
    unittest.main(verbosity=2)
