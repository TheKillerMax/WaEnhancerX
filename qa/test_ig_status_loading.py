#!/usr/bin/env python3
"""Execute IG status loading with real Java workers and explicit Android/host doubles.

Compiles the complete production IGStatusAdapter and IGStatusView, plus the real
queue and sampling helper. The hook registry/snapshot bodies are copied verbatim
from source. This does not emulate Android decoding, rendering, LSPosed selectors,
WhatsApp databases or measure frame time. Optional --baseline-root requires the
old source to compile and fail the same main-thread I/O assertion.
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
from android_presence_row_test import extract
from fixtures.ig_status_android_doubles import STUBS
from localization_support import write_display_adapter

ROOT = Path(__file__).resolve().parents[1]
VIEWS = Path('app/src/main/java/com/waenhancer/xposed/views')
HOOK = Path('app/src/main/java/com/waenhancer/xposed/features/customization/IGStatusHook.java')


def hook_harness(source):
    fields = '\n'.join(line.strip() for line in source.splitlines()
                       if 'static final CopyOnWriteArrayList<Object> items' in line
                       or 'static final List<' in line and 'statusContainers' in line)
    methods = [extract(source, 'private static void updateAllContainers()')]
    methods.append(extract(source, 'public static Object[] snapshotItems()')
                   if 'public static Object[] snapshotItems()' in source
                   else 'public static Object[] snapshotItems() { return items.toArray(); }')
    registration = extract(source, 'synchronized (statusContainers)')
    return '''package com.waenhancer.xposed.features.customization;
import java.util.*;import java.lang.ref.WeakReference;
import java.util.concurrent.CopyOnWriteArrayList;
import com.waenhancer.xposed.views.IGStatusView;
public class IGStatusHook {
''' + fields + '\n' + '\n'.join(methods) + '''
public static void register(int id, IGStatusView statusContainer) {
''' + registration + '\n}\n}\n'


def execute(source_root, out, baseline=False):
    out.mkdir(parents=True, exist_ok=True)
    for name, code in STUBS.items():
        file = out / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(code, encoding='utf-8')
    hook = out / 'com/waenhancer/xposed/features/customization/IGStatusHook.java'
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(hook_harness((source_root / HOOK).read_text()), encoding='utf-8')
    # Presentation-only English adapter with IDs from the actual resources.
    # Real UiText/locale ownership is exercised by test_es419_runtime.py.
    write_display_adapter(ROOT, out)
    classes = out / 'classes'
    classes.mkdir()
    cmd = ['javac', '--release', '17', '-d', str(classes)]
    cmd += [str(file) for file in out.rglob('*.java')]
    cmd += [str(source_root / VIEWS / (name + '.java')) for name in ['IGStatusAdapter', 'IGStatusView']]
    cmd += [str(ROOT / VIEWS / (name + '.java')) for name in ['StatusRowWorkQueue', 'StatusThumbnailPolicy']]
    cmd += [str(source_root / 'app/src/main/java/com/waenhancer/utils/ContactIdentityPolicy.java')]
    cmd += [str(ROOT / 'qa/java' / (name + '.java')) for name in ['TestIGStatusLoading', 'TestStatusRowWorkQueue']]
    compiled = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    (out / 'compile.log').write_text(compiled.stdout)
    if compiled.returncode:
        raise RuntimeError('Compilation failed; this is not a behavioral rejection:\n' + compiled.stdout)
    print(('BASELINE' if baseline else 'CANDIDATE') + ': complete adapter/view and worker compile OK', flush=True)
    test_root = out / 'storage'
    test_root.mkdir()
    result = subprocess.run(['java', '-Dqa.root=' + str(test_root), '-cp', str(classes),
                             'com.waenhancer.xposed.views.TestIGStatusLoading'],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    (out / 'binding.log').write_text(result.stdout)
    if baseline:
        if result.returncode == 0 or 'AssertionError: binding performed I/O on the main caller' not in result.stdout:
            raise RuntimeError('Baseline must fail the binding I/O assertion after compilation:\n' + result.stdout)
        print('PASS: baseline compiled and was rejected for main-thread binding I/O', flush=True)
        return
    print(result.stdout, end='', flush=True)
    if result.returncode:
        raise RuntimeError('Adapter/view control-flow tests failed')
    queue = subprocess.run(['java', '-cp', str(classes), 'com.waenhancer.xposed.views.TestStatusRowWorkQueue'],
                           text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    (out / 'queue.log').write_text(queue.stdout)
    print(queue.stdout, end='', flush=True)
    if queue.returncode:
        raise RuntimeError('Production worker queue tests failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--baseline-root', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    source = (args.source_root / VIEWS / 'IGStatusAdapter.java').read_text()
    hook = (args.source_root / HOOK).read_text()
    # Keep the production resource ceiling and publication lock wired to the executable tests.
    assert 'new StatusRowWorkQueue(2, 32)' in source
    assert hook.count('synchronized (items)') >= 4
    for match in re.finditer(r'items\.clear\(\);\s*items\.addAll\(newList\);', hook):
        assert 'synchronized (items)' in hook[max(0, match.start() - 80):match.start()]
    if args.out:
        execute(args.source_root.resolve(), args.out.resolve() / 'candidate')
        if args.baseline_root:
            execute(args.baseline_root.resolve(), args.out.resolve() / 'baseline', True)
    else:
        with tempfile.TemporaryDirectory(prefix='waex_ig_status_') as directory:
            execute(args.source_root.resolve(), Path(directory) / 'candidate')
            if args.baseline_root:
                execute(args.baseline_root.resolve(), Path(directory) / 'baseline', True)


if __name__ == '__main__':
    main()
