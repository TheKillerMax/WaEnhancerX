#!/usr/bin/env python3
"""Runtime API selection must preserve test bodies, defaults and failure gates."""
import os
import unittest
from unittest.mock import patch
from framework_sdk_matrix import runtime_env, select_sdk

class SdkSelectionTest(unittest.TestCase):
    def test_defaults_preserve_exact_bytes_and_other_attributes(self):
        for newline in ("\n", "\r\n"):
            source = ('@Config(sdk = {24, 28, 34}, manifest = Config.NONE)' + newline
                      + 'class Fixture { void scenario() { assertEquals(37, answer); } }' + newline)
            self.assertEqual(source, select_sdk(source, None, (24,28,34)))

    def test_every_api_changes_only_the_declared_java_list(self):
        source = '@Config(sdk = {24, 28, 34}, manifest = Config.NONE)\nassertEquals(34, answer);\n'
        for sdk in range(24,38):
            with self.subTest(sdk=sdk):
                expected = source.replace('{24, 28, 34}', '{'+str(sdk)+'}')
                self.assertEqual(expected, select_sdk(source, sdk, (24,28,34)))

    def test_kotlin_single_and_multiple_api_fixtures(self):
        for values, defaults in [('34',(34,)),('28, 34, 36',(28,34,36))]:
            source = '@Config(sdk = ['+values+'])\n@Test fun case() { assertTrue(result) }\n'
            self.assertEqual(source.replace('['+values+']','[37]'),select_sdk(source,37,defaults))
            self.assertEqual(source,select_sdk(source,None,defaults))

    def test_fixture_drift_never_silently_changes_default_coverage(self):
        for sdk in (None,37):
            with self.assertRaisesRegex(ValueError,'contract changed'):
                select_sdk('@Config(sdk = [24, 34, 28])',sdk,(24,28,34))

    def test_unsupported_or_noninteger_apis_fail(self):
        for sdk in (23,38,0,-1,True,34.0,'34'):
            with self.subTest(sdk=sdk), self.assertRaises(ValueError):
                select_sdk('@Config(sdk = [34])',sdk,(34,))

    def test_missing_ambiguous_or_malformed_annotations_fail(self):
        for source in ('class NoConfig {}','@Config(manifest=Config.NONE)',
                       '@Config(sdk=[34]) @Config(sdk=[34])',
                       '@Config(sdk=[34],sdk=[34])','@Config(sdk={34])',
                       '@Config(sdk=[34,])'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                select_sdk(source,37,(34,))

    def test_runtime_defaults_do_not_override_process_environment(self):
        for sdk in (None,24,34):
            self.assertIsNone(runtime_env(sdk))

    def test_modern_shared_memory_export_is_scoped_and_not_duplicated(self):
        flag = '--add-opens=java.base/jdk.internal.access=ALL-UNNAMED'
        for sdk in (35,36,37):
            with patch.dict(os.environ, {'JAVA_TOOL_OPTIONS':'-XX:ActiveProcessorCount=2'}, clear=True):
                result = runtime_env(sdk)
                self.assertEqual('-XX:ActiveProcessorCount=2 '+flag,result['JAVA_TOOL_OPTIONS'])
                self.assertEqual('-XX:ActiveProcessorCount=2',os.environ['JAVA_TOOL_OPTIONS'])
            with patch.dict(os.environ, {'JAVA_TOOL_OPTIONS':flag}, clear=True):
                self.assertEqual(flag,runtime_env(sdk)['JAVA_TOOL_OPTIONS'])

if __name__ == '__main__':
    unittest.main()
