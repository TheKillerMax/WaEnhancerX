#!/usr/bin/env python3
"""Guard resources loaded by literal names in MenuIconLoader and its callers.

This is a source retention/definition test, NOT evidence that a release APK kept
its resources. Inspect the final APK and exercise the actual Android loader too.
Use --root CHECKOUT to compare a separate baseline without modifying its source.
"""
from pathlib import Path
import argparse
import fnmatch
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from preference_type_audit import without_comments
ROOT = Path(__file__).resolve().parents[1]
TOOLS = '{http://schemas.android.com/tools}'
ICON = re.compile(r'"(ic_waex_[a-z0-9_]+|ic_deleted)"')

def validate(root):
    refs = set()
    java = root / 'app/src/main/java'
    for p in java.rglob('*'):
        if p.suffix not in ('.java', '.kt') or not p.is_file():
            continue
        code = without_comments(p.read_text(encoding='utf-8'))
        if 'MenuIconLoader' in code:
            refs.update(ICON.findall(code))
    if not refs:
        raise ValueError('No literal dynamic menu icon references found')
    res = root / 'app/src/main/res'
    keep, discard = [], []
    for p in (res / 'raw').glob('*.xml'):
        node = ET.parse(p).getroot()
        keep.extend(s.strip() for s in node.get(TOOLS + 'keep', '').split(',') if s.strip())
        discard.extend(s.strip() for s in node.get(TOOLS + 'discard', '').split(',') if s.strip())
    undefined = [n for n in sorted(refs) if not (res / 'drawable' / (n + '.xml')).is_file()]
    unprotected = [n for n in sorted(refs) if not any(fnmatch.fnmatchcase('@drawable/' + n, p) for p in keep)]
    conflicting = [n for n in sorted(refs) if any(fnmatch.fnmatchcase('@drawable/' + n, p) for p in discard)]
    if undefined or unprotected or conflicting:
        raise ValueError(f'Dynamic icon contract failed: undefined={undefined}; unprotected={unprotected}; discarded={conflicting}')
    return sorted(refs)

class DynamicMenuResourceTests(unittest.TestCase):
    def test_current_tree(self):
        names = validate(ROOT)
        self.assertIn('ic_deleted', names)
        self.assertIn('ic_waex_mark_read', names)
        print(f'Checked {len(names)} literal dynamic drawable names; APK/runtime acceptance is separate')

    def fixture(self, td, keep='@drawable/ic_waex_*,@drawable/ic_deleted', discard=''):
        root = Path(td)
        java = root / 'app/src/main/java'; java.mkdir(parents=True)
        (java / 'MenuIconLoader.java').write_text('class MenuIconLoader { String a="ic_waex_ghost_on"; /* "ic_waex_unused" */ }')
        (java / 'Consumer.kt').write_text('MenuIconLoader.load(ctx,"ic_deleted")')
        res = root / 'app/src/main/res'
        (res / 'drawable').mkdir(parents=True); (res / 'raw').mkdir()
        for name in ['ic_waex_ghost_on', 'ic_deleted']:
            (res / 'drawable' / (name + '.xml')).write_text('<vector/>')
        (res / 'raw/fixture.keep.xml').write_text(f'<resources xmlns:tools="http://schemas.android.com/tools" tools:keep="{keep}" tools:discard="{discard}"/>')
        return root

    def test_complete_rules(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(['ic_deleted', 'ic_waex_ghost_on'], validate(self.fixture(td)))

    def test_each_family_required(self):
        for keep in ['', '@drawable/ic_waex_*', '@drawable/ic_deleted', '@string/*']:
            with self.subTest(keep=keep), tempfile.TemporaryDirectory() as td:
                with self.assertRaises(ValueError): validate(self.fixture(td, keep))

    def test_missing_definition_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.fixture(td)
            (root / 'app/src/main/res/drawable/ic_deleted.xml').unlink()
            with self.assertRaises(ValueError): validate(root)

    def test_discard_conflict_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError): validate(self.fixture(td, discard='@drawable/ic_deleted'))

    def test_comments_do_not_create_dependencies(self):
        with tempfile.TemporaryDirectory() as td:
            names = validate(self.fixture(td))
            self.assertNotIn('ic_waex_unused', names)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--root', type=Path)
    args, rest = parser.parse_known_args()
    if args.root is not None: ROOT = args.root.resolve()
    unittest.main(argv=[sys.argv[0], *rest])
