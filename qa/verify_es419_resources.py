#!/usr/bin/env python3
"""Compile public resources and link an isolated locale table; NOT a WAEX APK build.

Requires a real caller-supplied AAPT2. No SDK/signing/private dependencies are replaced.
The fixture contains only module strings/plurals so linking needs no platform symbols.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from xml.etree import ElementTree as ET
from localization_support import entries, stage_string_resources

ROOT = Path(__file__).resolve().parents[1]


MAX_REFERENCE_HOPS = 32


def source_reference_targets(root):
    """Keep source alias type distinct from a quoted literal such as "@string/x"."""
    references = {}
    for folder, qualifier in (('values', ''), ('values-es', 'es'), ('values-b+es+419', 'es-r419')):
        references[qualifier] = {}
        for path in sorted((Path(root) / 'app/src/main/res' / folder).glob('*.xml')):
            for element in ET.parse(path).getroot():
                if element.tag != 'string': continue
                target = re.fullmatch(r'@string/([A-Za-z_][A-Za-z0-9_]*)', ''.join(element.itertext()).strip())
                if target:
                    name = element.attrib['name']
                    assert name not in references[qualifier], ('Duplicate source alias', qualifier, name)
                    references[qualifier][name] = target.group(1)
    return references


def verify_dump(text, expected, spanish, *, reference_targets=None, details=None):
    assert 'Package name=com.waenhancer id=7f' in text, 'Wrong resource owner'
    assert spanish.keys() == expected.keys(), 'Spanish source names differ'
    if reference_targets is not None:
        assert set(reference_targets) == {'', 'es', 'es-r419'}, 'Source reference configurations differ'
    strings = {}
    literal_count = reference_count = 0
    for match in re.finditer(r'^    resource 0x[0-9a-f]+ string/([^\n]+)\n(.*?)(?=^    resource |\Z)', text, re.M | re.S):
        name, body = match.groups()
        assert name not in strings, f'Duplicate compiled string {name}'
        assert name in expected and name in spanish, ('Unexpected compiled string', name)
        qualifiers = re.findall(r'^      \(([^)]*)\) ', body, re.M)
        for qualifier in ('', 'es', 'es-r419'):
            assert qualifiers.count(qualifier) == 1, (name, qualifier, qualifiers)
        values = {}
        for value in re.finditer(r'^      \(([^)]*)\) (.*?)(?=^      \(|\Z)', body, re.M | re.S):
            qualifier, content = value.groups()
            if qualifier not in ('', 'es', 'es-r419'): continue
            content = content.rstrip('\n')
            if content.startswith('"'):
                assert content.endswith('"'), (name, 'Malformed AAPT2 string output')
                kind, value_text = 'literal', content[1:-1].replace('\n      ', '\n')
            else:
                target = re.fullmatch(r'@string/([A-Za-z_][A-Za-z0-9_]*)', content)
                assert target, (name, qualifier, 'Unsupported compiled string value')
                kind, value_text = 'reference', target.group(1)
            assert qualifier not in values, (name, qualifier, 'Duplicate compiled value')
            values[qualifier] = (kind, value_text)
            if reference_targets is not None:
                source_target = reference_targets[qualifier].get(name)
                assert (kind == 'reference') == (source_target is not None), (name, qualifier, 'Source alias kind changed')
                if source_target is not None:
                    assert value_text == source_target, (name, qualifier, 'Source alias target changed')
            if kind == 'reference':
                source_values = expected if qualifier == '' else spanish
                assert '@string/' + value_text == source_values[name][0], (name, qualifier, 'Source alias target changed')
            if qualifier in ('es', 'es-r419'):
                if kind == 'literal':
                    assert value_text == spanish[name][0], (name, qualifier, 'Compiled Spanish value changed')
                    literal_count += 1
                else:
                    reference_count += 1
        strings[name] = values
    assert strings.keys() == expected.keys(), (len(strings), len(expected))
    # Resolve only local references in this retained table, without Android or recursion.
    for name, values in strings.items():
        for qualifier, (kind, _) in values.items():
            if kind != 'reference': continue
            current, seen, hops = name, set(), 0
            while strings[current][qualifier][0] == 'reference':
                assert current not in seen, (name, qualifier, 'Reference cycle')
                assert hops < MAX_REFERENCE_HOPS, (name, qualifier, 'Reference chain exceeds limit', MAX_REFERENCE_HOPS)
                seen.add(current)
                target = strings[current][qualifier][1]
                assert target in strings, (name, qualifier, 'Missing reference target', target)
                assert qualifier in strings[target], (name, qualifier, 'Missing target configuration', target)
                current, hops = target, hops + 1
    plural = re.search(r'plurals/waex_recordings_deleted\n(.*?)(?=^    resource |^  type |\Z)', text, re.M | re.S)
    assert plural, 'Missing compiled recording plural'
    assert plural.group(1).count('one=') == 3 and plural.group(1).count('other=') == 3
    if details is not None:
        details.update({'exact_compiled_spanish_literals': literal_count,
                        'exact_compiled_spanish_references': reference_count,
                        'reference_hop_limit': MAX_REFERENCE_HOPS})
    return len(strings)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aapt2', required=True, help='Path to actual Android AAPT2 executable')
    parser.add_argument('--out', required=True, help='New directory for text evidence and temporary fixture')
    args = parser.parse_args()
    aapt2 = Path(args.aapt2).resolve()
    if not aapt2.is_file(): raise SystemExit('AAPT2 is missing')
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    commands=[]
    def run(argv, name):
        result = subprocess.run([str(a) for a in argv], text=True, encoding='utf-8', errors='replace',
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
        (out/name).write_text(result.stdout, encoding='utf-8')
        commands.append({'command':[str(a) for a in argv], 'exit':result.returncode})
        if result.returncode: raise RuntimeError(f'{name} failed: {result.returncode}')
        return result.stdout
    run([aapt2, 'version'], 'aapt2-version.txt')
    run([aapt2, 'compile', '--dir', ROOT/'app/src/main/res', '-o', out/'all-resources.zip'], 'compile-all.log')
    res=out/'res';res.mkdir()
    identities={}
    stage_string_resources(ROOT, res, identities)
    manifest=out/'AndroidManifest.xml'
    manifest.write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.waenhancer"><application /></manifest>\n', encoding="utf-8")
    run([aapt2,'compile','--dir',res,'-o',out/'compiled.zip'],'compile-fixture.log')
    run([aapt2,'link','-o',out/'resources-only.apk','--manifest',manifest,
         '--java',out/'generated','--custom-package','com.waenhancer.app',out/'compiled.zip'],'link-fixture.log')
    dump=run([aapt2,'dump','resources',out/'resources-only.apk'],'resources-table.txt')
    expected=entries(ROOT,'values')
    spanish=entries(ROOT,'values-b+es+419')
    reference_targets=source_reference_targets(ROOT)
    details={}
    count=verify_dump(dump,expected,spanish,reference_targets=reference_targets,details=details)
    controls = [dump.replace('(es-r419)', '(fr)'), dump.replace('Package name=com.waenhancer id=7f','Package name=other id=7f'),
                dump.replace('other="Se eliminaron', 'zero="Se eliminaron',1), dump.replace('(es) "Agregar"', '(es) "Add"', 1)]
    for bad in controls:
        try: verify_dump(bad,expected,spanish,reference_targets=reference_targets)
        except AssertionError: pass
        else: raise AssertionError('Bad compiled-table fixture accepted')
    (out/'result.json').write_text(json.dumps({'string_names':count,'configurations':['default','es','es-419'],
        'exact_compiled_spanish_values':2*count,'plural_resources':1,'plural_forms_per_configuration':2,'negative_parser_controls':len(controls),
        **details,'identities':identities,'commands':commands,'scope':'AAPT2 actual compile/link of resource table only; not app build or runtime selection'},indent=2), encoding="utf-8")
    print(f"PASS: {count} compiled string names, all three locale configurations, "
          f"{details['exact_compiled_spanish_literals']} exact Spanish literals, "
          f"{details['exact_compiled_spanish_references']} exact Spanish references, plural forms, "
          f"{len(controls)} table-parser controls; NOT a full app build")

if __name__=='__main__':
    main()
