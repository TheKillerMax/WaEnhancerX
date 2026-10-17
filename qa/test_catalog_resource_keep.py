#!/usr/bin/env python3
"""Require retention rules for dynamically resolved catalog strings.

This source check is necessary but not sufficient. Run verify_catalog_apk.py
against the final optimized APK before publishing; XML presence is not evidence
that the resources survived shrinking.
"""
from pathlib import Path
import fnmatch
import tempfile
import unittest
import xml.etree.ElementTree as ET
from verify_catalog_apk import required_strings
ROOT=Path(__file__).resolve().parents[1]
KEEP='{http://schemas.android.com/tools}keep'
DISCARD='{http://schemas.android.com/tools}discard'

def validate(root):
    required=required_strings((root/'app/src/main/assets/preference_catalog.json').read_bytes())
    patterns=[];discard=[]
    for path in (root/'app/src/main/res/raw').glob('*.xml'):
        tree=ET.parse(path).getroot()
        patterns += [p.strip() for p in tree.get(KEEP,'').split(',') if p.strip()]
        discard += [p.strip() for p in tree.get(DISCARD,'').split(',') if p.strip()]
    missing=[n for n in required if not any(fnmatch.fnmatchcase('@string/'+n,p) for p in patterns)]
    conflicts=[n for n in required if any(fnmatch.fnmatchcase('@string/'+n,p) for p in discard)]
    if missing or conflicts:raise ValueError('Unprotected catalog strings: '+str(missing)+'; discarded: '+str(conflicts))
    return len(required)

class ResourceRetentionTests(unittest.TestCase):
    def test_actual_tree_has_complete_retention(self):self.assertGreater(validate(ROOT),0)
    def fixture(self,td,attrs):
        root=Path(td);a=root/'app/src/main/assets';a.mkdir(parents=True)
        (a/'preference_catalog.json').write_text('[{"id":"g","tabId":"t","keys":["alpha"]}]')
        raw=root/'app/src/main/res/raw';raw.mkdir(parents=True)
        (raw/'keep_test.xml').write_text('<resources xmlns:tools="http://schemas.android.com/tools" '+attrs+' />')
        return root
    def test_each_required_family_is_protected(self):
        families=['@string/feat_*_title','@string/feat_*_desc','@string/sec_*','@string/catalog_tab_*']
        for missing in range(4):
            with self.subTest(missing=missing),tempfile.TemporaryDirectory() as td:
                root=self.fixture(td,'tools:keep="'+','.join(p for i,p in enumerate(families) if i!=missing)+'"')
                with self.assertRaises(ValueError):validate(root)
    def test_explicit_names_work(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.fixture(td,'tools:keep="@string/feat_alpha_title,@string/feat_alpha_desc,@string/sec_g,@string/catalog_tab_t"')
            self.assertEqual(4,validate(root))
    def test_discard_conflict_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.fixture(td,'tools:keep="@string/*" tools:discard="@string/feat_*"')
            with self.assertRaises(ValueError):validate(root)
    def test_empty_rules_fail(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.fixture(td,'')
            with self.assertRaises(ValueError):validate(root)
if __name__=='__main__':unittest.main()
