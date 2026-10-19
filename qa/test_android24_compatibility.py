#!/usr/bin/env python3
"""Require explicit older factory/reflection APIs before D8/R8 processing.

This source policy inspects JVM bytecode, not final APK compatibility. D8/R8 has
automatic Method.getParameterCount and List.of backports, so native API floors
and a baseline rejection here do not prove an APK linkage failure. Existing
behavior suites cover the same selectors. The separate cache suite executes
the production manager against a PackageInfo double that lacks the API 28
getLongVersionCode method.
"""
from pathlib import Path
import argparse
import re
import subprocess
import tempfile

from test_view_once_download import STUBS, DEX_STUBS, write

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path('app/src/main/java/com/waenhancer')
REFLECTION = re.compile(r'\.\s*(?:getParameterCount\s*\(|parameterCount\b)')
FACTORY = re.compile(r'\b(?:java\s*\.\s*util\s*\.\s*)?List\s*\.\s*of\s*\(')
POLICY_MEMBER_REFERENCES = re.compile(
    r'java/lang/reflect/(?:Method|Constructor|Executable)\.getParameterCount:'
    r'|java/util/List\.of:')


def executable_text(source):
    # Preserve newlines and offsets for useful errors; comments/string literals
    # are not API calls. The targeted spellings do not occur in interpolation.
    ignored = re.compile(r'/\*[\s\S]*?\*/|//[^\n]*|"""[\s\S]*?"""|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
    return ignored.sub(lambda match: ''.join('\n' if c == '\n' else ' ' for c in match.group()), source)


def source_violations(root):
    problems = []
    files = sorted(p for p in (root / PACKAGE).rglob('*') if p.suffix in ('.java', '.kt'))
    assert files, 'production source tree missing'
    for path in files:
        source = executable_text(path.read_text())
        for pattern, minimum in [(REFLECTION, 26), (FACTORY, 30)]:
            for match in pattern.finditer(source):
                line = source.count('\n', 0, match.start()) + 1
                problems.append(f'{path.relative_to(root)}:{line}: native API floor {minimum}; explicit older API required: {match.group().strip()}')
    return files, problems


def compiled_violations(root):
    with tempfile.TemporaryDirectory(prefix='waex-api24-symbols-') as temporary:
        stage = Path(temporary)
        write(stage, STUBS)
        write(stage, DEX_STUBS)
        sources = [root / PACKAGE / path for path in [
            'xposed/core/devkit/HookReturnTypeGuard.java',
            'xposed/features/media/ViewOnceMediaResolver.java',
            'xposed/features/media/ViewOnceAudioResolver.java',
            'utils/ContactIdentityPolicy.java',
        ]]
        classes = stage / 'classes'
        subprocess.run(['javac', '--release', '17', '-d', str(classes),
                        *map(str, sources), *map(str, stage.rglob('*.java'))], check=True, timeout=60)
        selection = root / PACKAGE / 'xposed/features/conversation/PreservedMessageSelection.kt'
        subprocess.run(['kotlinc', '-jvm-target', '17', '-cp', str(classes), '-d', str(classes),
                        str(selection)], check=True, timeout=60)
        print('COMPILE_OK: complete production Java guard/resolvers and Kotlin selection', flush=True)
        # Inspect only the actual production classes, not the deliberately modern
        # JVM fixture implementations of DexKit/Android/host types.
        names = []
        for prefix in ['com/waenhancer/xposed/core/devkit/HookReturnTypeGuard',
                       'com/waenhancer/xposed/features/media/ViewOnceMediaResolver',
                       'com/waenhancer/xposed/features/media/ViewOnceAudioResolver',
                       'com/waenhancer/xposed/features/conversation/PreservedMessageSelection']:
            for path in classes.glob(prefix + '*.class'):
                names.append(path.relative_to(classes).as_posix()[:-6].replace('/', '.'))
        assert len(names) >= 4, 'production bytecode missing'
        result = subprocess.run(['javap', '-classpath', str(classes), '-c', '-p', *names],
                                check=True, capture_output=True, text=True, timeout=60)
        return names, sorted(set(POLICY_MEMBER_REFERENCES.findall(result.stdout)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, default=ROOT,
                        help='Compile/check an unchanged earlier source tree as a negative control')
    args = parser.parse_args()
    root = args.source_root.resolve()
    # Compile before rejecting the baseline. A syntax/dependency failure must not
    # be mistaken for evidence that this source policy caught a member reference.
    names, bytecode = compiled_violations(root)
    files, source = source_violations(root)
    if bytecode or source:
        print('\n'.join(['SOURCE_POLICY: ' + issue for issue in bytecode + source]), flush=True)
        raise AssertionError(f'API 24 source policy rejected {len(source)} source sites and {len(bytecode)} pre-D8/R8 JVM member references')
    print(f'PASS: targeted API 24 source policy; {len(files)} production files; {len(names)} pre-D8/R8 production classfiles')


if __name__ == '__main__':
    main()
