#!/usr/bin/env python3
"""Unit/smoke tests of direct preference type/wire mismatch detection."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from preference_type_audit import analyse, scan, without_comments

SYNTHETIC_SCHEMA = '''
add(entries, "enable_foo", Type.BOOLEAN, Sensitivity.PUBLIC_SETTING, Store.PUBLIC);
add(entries, "status_mode", Type.STRING, Sensitivity.PUBLIC_SETTING, Store.PUBLIC);
add(entries, "color", Type.INT, Sensitivity.PUBLIC_SETTING, Store.PUBLIC);
'''


class PreferenceTypeAuditTests(unittest.TestCase):
    def test_string_and_block_comments_are_ignored(self):
        raw = '''
// preferenceManager.putInt("enable_foo", 3);
/* preferenceManager.putBoolean("status_mode", true); */
preferenceManager.putBoolean("enable_foo", true);
val sample = "// not a comment";
'''
        masked = without_comments(raw)
        self.assertNotIn('putInt("enable_foo"', masked)
        self.assertNotIn('putBoolean("status_mode"', masked)
        self.assertIn('putBoolean("enable_foo"', masked)
        self.assertEqual(len(masked), len(raw))
        self.assertEqual(masked.count('\n'), raw.count('\n'))

    def test_mismatched_write_and_read_are_separated(self):
        src = {
          'Ui.kt': 'manager.putString("color", "#FF0000"); manager.getBoolean("status_mode", false);',
          'Hook.java': 'prefs.getInt("color", 0); prefs.putBoolean("enable_foo", true);',
        }
        result = analyse(SYNTHETIC_SCHEMA, src)
        self.assertEqual(result['schema_keys'], 3)
        self.assertEqual(result['counts']['matched_literals'], 4)
        self.assertEqual(len(result['mismatched_writes']), 1)
        self.assertEqual(result['mismatched_writes'][0]['key'], 'color')
        self.assertEqual(len(result['mismatched_reads']), 1)
        self.assertEqual(result['mismatched_reads'][0]['key'], 'status_mode')

    def test_unknown_keys_are_not_declared_wrong_type(self):
        r = analyse(SYNTHETIC_SCHEMA, {'t.java': 'prefs.putBoolean("unknown", true);'})
        self.assertEqual(r['counts']['unknown_literals'], 1)
        self.assertFalse(r['mismatched_writes'])

    def test_dynamic_key_not_guessed(self):
        r = analyse(SYNTHETIC_SCHEMA, {'t.java': 'prefs.putBoolean(someDynamicKey, true);'})
        self.assertEqual(r['counts']['matched_literals'], 0)

    def test_current_upstream_source_is_readable(self):
        root = Path(__file__).resolve().parents[1]
        if not (root/'app/src/main/java/com/waenhancer/config/PreferenceSchema.java').is_file():
            self.skipTest('Fixture-only run: no full WAEX source tree')
        result = scan(root)
        self.assertGreater(result['schema_keys'], 300)
        self.assertGreater(result['counts']['matched_literals'], 100)
        self.assertEqual(result['counts']['known_literals'] + result['counts']['unknown_literals'],
                         result['counts']['matched_literals'])


if __name__ == '__main__':
    unittest.main()
