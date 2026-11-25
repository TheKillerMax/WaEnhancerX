#!/usr/bin/env python3
"""Validate the four overlay-help resources and their source references.

This checks XML, duplicate keys, locale parity, placeholders and Kotlin resource
references. It does not compile Compose, render the screen or grant permission.
"""
import argparse
import re
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ('values','values-es','values-b+es+419','values-sl')
KEYS = {'overlay_restricted_settings_help','overlay_open_app_info','overlay_settings_unavailable'}
PLACEHOLDER = re.compile(r'%(?:\d+\$)?[a-zA-Z]')


def validate(root):
    resources = root/'app/src/main/res'
    translations = {}
    for locale in LOCALES:
        path = resources/locale/'overlay_permission.xml'
        document = ET.parse(path).getroot()
        if document.tag != 'resources' or any(item.tag != 'string' for item in document):
            raise ValueError('Expected only string resources: '+str(path))
        entries = list(document)
        names = [item.get('name') for item in entries]
        if set(names) != KEYS or len(names) != len(KEYS):
            raise ValueError('Overlay locale must define each required key once: '+locale)
        values = {item.get('name'):''.join(item.itertext()).strip() for item in entries}
        if any(not value for value in values.values()):
            raise ValueError('Empty overlay translation: '+locale)
        occurrences = {key:[] for key in KEYS}
        for sibling in (resources/locale).glob('*.xml'):
            for item in ET.parse(sibling).getroot():
                if item.get('name') in KEYS:
                    occurrences[item.get('name')].append(sibling.name)
        if any(len(files) != 1 for files in occurrences.values()):
            raise ValueError('Duplicate overlay resource key: '+locale)
        translations[locale] = values
    default = translations['values']
    for locale,values in translations.items():
        for key in KEYS:
            if sorted(PLACEHOLDER.findall(default[key])) != sorted(PLACEHOLDER.findall(values[key])):
                raise ValueError('Overlay placeholder mismatch: '+locale+'/'+key)
    if translations['values-es'] != translations['values-b+es+419']:
        raise ValueError('Spanish variants must retain the same reviewed overlay help')
    screen = (root/'app/src/main/java/com/waenhancer/app/PermissionsActivity.kt').read_text(encoding='utf-8')
    for key in KEYS:
        if 'R.string.'+key not in screen:
            raise ValueError('Overlay resource is not referenced by the screen: '+key)
    return len(LOCALES)*len(KEYS)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    args = parser.parse_args()
    print(f'PASS: {validate(args.root.resolve())} overlay translations, key uniqueness, placeholders and references')
