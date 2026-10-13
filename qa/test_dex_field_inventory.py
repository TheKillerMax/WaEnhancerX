#!/usr/bin/env python3
"""Synthetic DEX table/encoded-field regressions; no proprietary APK required."""
import importlib.util
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

spec=importlib.util.spec_from_file_location('dex_field_inventory',Path(__file__).with_name('dex_field_inventory.py'))
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

OWNER='Lcom/whatsapp/jobqueue/job/SendE2EMessageJob;'


def uleb(value):
    result=bytearray()
    while True:
        x=value&0x7f
        value>>=7
        result.append(x|0x80 if value else x)
        if not value: return bytes(result)


def sample(names=('jid','participant')):
    strs=[OWNER,'Ljava/lang/String;',*names]
    string_ids=112
    typeids=string_ids+4*len(strs)
    fieldids=typeids+4*2
    classdefs=fieldids+8*len(names)
    stringdata=classdefs+32
    contents=bytearray()
    offsets=[]
    for s in strs:
        offsets.append(stringdata+len(contents))
        contents.extend(uleb(len(s)))
        contents.extend(s.encode())
        contents.append(0)
    class_data_off=stringdata+len(contents)
    classdata=uleb(0)+uleb(len(names))+uleb(0)+uleb(0)
    for i in range(len(names)):
        classdata+=uleb(0 if i==0 else 1)+uleb(1)
    final=class_data_off+len(classdata)
    b=bytearray(final)
    b[:8]=b'dex\n035\x00'
    struct.pack_into('<I',b,32,final)
    struct.pack_into('<I',b,36,112)
    struct.pack_into('<I',b,40,0x12345678)
    for a,c,o in [(56,len(strs),string_ids),(64,2,typeids),(80,len(names),fieldids),(96,1,classdefs)]:
        struct.pack_into('<II',b,a,c,o)
    for i,o in enumerate(offsets):struct.pack_into('<I',b,string_ids+4*i,o)
    struct.pack_into('<II',b,typeids,0,1)
    for i in range(len(names)):struct.pack_into('<HHI',b,fieldids+8*i,0,1,i+2)
    struct.pack_into('<IIIIIIII',b,classdefs,0,1,0xffffffff,0,0xffffffff,0,class_data_off,0)
    b[stringdata:class_data_off]=contents
    b[class_data_off:]=classdata
    return bytes(b)

class DexFieldInventoryTests(unittest.TestCase):
    def test_declared_jid_and_participant(self):
        fields=module.declared_fields(sample(),OWNER)
        self.assertEqual(fields,[{'name':'jid','type':'Ljava/lang/String;'},
                                 {'name':'participant','type':'Ljava/lang/String;'}])

    def test_missing_named_field_is_reported(self):
        fields=module.declared_fields(sample(('A0J','participant')),OWNER)
        self.assertNotIn('jid',{f['name'] for f in fields})

    def test_not_definition_does_not_match(self):
        self.assertIsNone(module.declared_fields(sample(),'Lcom/whatsapp/Other;'))

    def test_truncated_and_corrupted_tables_fail_closed(self):
        raw=bytearray(sample())
        raw[32:36]=b'\x00\x00\x00\x00'
        with self.assertRaises(module.MalformedDex):module.declared_fields(bytes(raw),OWNER)
        raw=bytearray(sample())
        raw[60:64]=b'\xff\xff\xff\xff'
        with self.assertRaises(module.MalformedDex):module.declared_fields(bytes(raw),OWNER)
        raw=bytearray(sample())
        fieldid_off=struct.unpack_from('<I',raw,84)[0]
        struct.pack_into('<I',raw,fieldid_off+4,0xffffffff)
        with self.assertRaises(module.MalformedDex):module.declared_fields(bytes(raw),OWNER)

    def test_cli_report_matches_expected_field(self):
        with tempfile.TemporaryDirectory() as dest:
            path=Path(dest)/'synthetic.apk'
            with zipfile.ZipFile(path,'w') as z:z.writestr('classes.dex',sample())
            ok=module.inspect_apk(path,OWNER,'jid')
            self.assertTrue(ok['expected_field_declared'])
            self.assertEqual(ok['field_count'],2)
            self.assertEqual(ok['status'],'PRESENT')
            with zipfile.ZipFile(path,'w') as z:z.writestr('classes.dex',sample(('A0J',)))
            bad=module.inspect_apk(path,OWNER,'jid')
            self.assertFalse(bad['expected_field_declared'])
            self.assertEqual(bad['status'],'MISSING_FIELD')

if __name__=='__main__':unittest.main(verbosity=2)
