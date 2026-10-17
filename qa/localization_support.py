"""Explicit display adapters for tests of non-localization behavior; no Android runtime claimed."""
from pathlib import Path
import re
from xml.etree import ElementTree as ET


def android_text(text):
    if len(text) >= 2 and text[0] == text[-1] == '"':
        text = text[1:-1]
    return text.replace(r'\n', '\n').replace(r'\t', '\t').replace(r'\"', '"').replace(r"\'", "'").replace(r'\$', '$').replace('\\\\', '\\')


def entries(root, folder):
    out = {}
    for path in sorted((Path(root)/'app/src/main/res'/folder).glob('*.xml')):
        for element in ET.parse(path).getroot():
            if element.tag == 'string':
                key = element.attrib['name']
                assert key not in out, f'Duplicate resource {folder}/{key}'
                out[key] = (android_text(''.join(element.itertext())), element.attrib.get('formatted') != 'false')
    return out


def write_r(root, destination):
    values = entries(root, 'values')
    ids = {key: 0x7f020000 + i for i, key in enumerate(sorted(values))}
    lines = ['package com.waenhancer.app;', 'public final class R {', 'public static final class string {']
    lines += [f'public static final int {key} = {value};' for key, value in ids.items()]
    lines += ['}', 'public static final class plurals { public static final int waex_recordings_deleted = 0x7f010000; }', '}']
    path = Path(destination)/'com/waenhancer/app/R.java'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines))
    return path, ids


def write_display_adapter(root, destination):
    """English rendering adapter only for existing restart/other non-locale tests.

    The actual UiText source is exercised separately by test_es419_runtime.py.
    No root, permission, persistence or callback logic is substituted here.
    """
    r, _ = write_r(root, destination)
    path = Path(destination)/'com/waenhancer/utils/UiText.java'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('''package com.waenhancer.utils;
public final class UiText {
 public static String get(int id, String fallback, Object... args) {
  return args.length == 0 ? fallback : String.format(java.util.Locale.ENGLISH, fallback, args);
 }
}''')
    return [r, path]
