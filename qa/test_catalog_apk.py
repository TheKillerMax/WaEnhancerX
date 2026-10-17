#!/usr/bin/env python3
"""Positive and negative tests for compiled-catalog QA; no APK installation."""
import json
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile
from verify_catalog_apk import required_strings, parse_dump, assess, inspect

ASSET = json.dumps([{'id':'group','tabId':'privacy','keys':['alpha']}]).encode()
NAMES = ['catalog_tab_privacy','feat_alpha_desc','feat_alpha_title','sec_group']
def dump(names=NAMES, package='com.waenhancer', config='', value='"text"'):
    return 'Binary APK\nPackage name='+package+' id=7f\n  type string id=0e entryCount=4\n'+''.join(
        f'    resource 0x7f0e{i:04x} string/{name}\n      ({config}) {value}\n' for i,name in enumerate(names))

class CatalogApkTests(unittest.TestCase):
    def test_catalog_names(self): self.assertEqual(NAMES, required_strings(ASSET))
    def test_duplicate_placements_share_resource(self):
        self.assertEqual(NAMES, required_strings(json.dumps(json.loads(ASSET)*2).encode()))
    def test_empty_catalog(self):
        with self.assertRaises(ValueError):required_strings(b'[]')
    def test_wrong_catalog_root(self):
        with self.assertRaises(ValueError):required_strings(b'{}')
    def test_duplicate_json_property(self):
        with self.assertRaises(ValueError):required_strings(b'[{"id":"x","id":"y","tabId":"p","keys":["a"]}]')
    def test_malformed_groups(self):
        for g in [None,{}, {'id':'g','tabId':1,'keys':['a']},{'id':'g','tabId':'p','keys':[]},
                  {'id':'g','tabId':'p','keys':['../a']},{'id':'g','tabId':'p','keys':[None]}]:
            with self.subTest(group=g),self.assertRaises(ValueError):required_strings(json.dumps([g]).encode())
    def test_oversized_catalog(self):
        with self.assertRaises(ValueError):required_strings(b' '*(1024*1024+1))
    def test_complete_dump(self):self.assertTrue(assess(NAMES,parse_dump(dump(),'com.waenhancer'))['passed'])
    def test_missing_string(self):
        r=assess(NAMES,parse_dump(dump(NAMES[:-1]),'com.waenhancer'));self.assertFalse(r['passed']);self.assertEqual(['sec_group'],r['missing'])
    def test_locale_only_is_not_default(self):
        r=assess(NAMES,parse_dump(dump(config='es'),'com.waenhancer'));self.assertEqual(NAMES,r['invalid_or_missing_default'])
    def test_empty_defaults_fail(self):
        for value in ['""','" "','@0x7f0e0000','(null)']:
            with self.subTest(value=value):self.assertFalse(assess(NAMES,parse_dump(dump(value=value),'com.waenhancer'))['passed'])
    def test_foreign_package_rejected(self):
        with self.assertRaises(ValueError):parse_dump(dump(package='com.other'),'com.waenhancer')
    def test_foreign_entries_do_not_satisfy_target(self):
        s=dump(NAMES[:-1])+dump(['sec_group'],package='other').removeprefix('Binary APK\n')
        self.assertEqual(['sec_group'],assess(NAMES,parse_dump(s,'com.waenhancer'))['missing'])
    def test_literal_in_value_does_not_satisfy_name(self):
        r=assess(NAMES,parse_dump(dump(['unrelated'],value='"'+','.join(NAMES)+'"'),'com.waenhancer'));self.assertEqual(NAMES,r['missing'])
    def test_not_a_resource_dump(self):
        for s in ['', 'text '+','.join(NAMES), 'Proto APK\n'+dump()]:
            with self.subTest(text=s),self.assertRaises(ValueError):parse_dump(s,'com.waenhancer')
    def test_duplicate_names_rejected(self):
        with self.assertRaises(ValueError):parse_dump(dump(NAMES+[NAMES[0]]),'com.waenhancer')
    def test_duplicate_configs_rejected(self):
        with self.assertRaises(ValueError):parse_dump(dump()+'      () "again"\n','com.waenhancer')
    def test_duplicate_package_rejected(self):
        with self.assertRaises(ValueError):parse_dump(dump()+dump().removeprefix('Binary APK\n'),'com.waenhancer')
    def test_conflicting_ids_rejected(self):
        with self.assertRaises(ValueError):parse_dump(dump().replace('0x7f0e0001','0x7f0e0000'),'com.waenhancer')
    def test_unrecognized_resource_rejected(self):
        with self.assertRaises(ValueError):parse_dump(dump()+'    resource malformed\n','com.waenhancer')
    def test_multilocale(self):
        s=dump()+ '      (es) "texto"\n';r=parse_dump(s,'com.waenhancer');self.assertEqual('"texto"',r['sec_group']['es'])
    def test_missing_apk(self):
        with self.assertRaises(ValueError):inspect(Path('/nonexistent/waex.apk'),'aapt2','com.waenhancer')
    def test_archive_boundaries_and_tools(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'a.apk'
            with zipfile.ZipFile(path,'w') as z:z.writestr('assets/preference_catalog.json',ASSET);z.writestr('resources.arsc',b'fixture')
            with self.assertRaises(ValueError):inspect(path,'not-aapt2','com.waenhancer','0'*64)
            with self.assertRaises(FileNotFoundError):inspect(path,'waex-nonexistent-aapt2-tool','com.waenhancer')
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                with zipfile.ZipFile(path,'a') as z:z.writestr('resources.arsc',b'duplicate')
            with self.assertRaises(ValueError):inspect(path,'not-aapt2','com.waenhancer')
    def test_truncated_apk(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'a.apk';p.write_bytes(b'PK\x03\x04')
            with self.assertRaises(zipfile.BadZipFile):inspect(p,'aapt2','com.waenhancer')

if __name__=='__main__': unittest.main()
