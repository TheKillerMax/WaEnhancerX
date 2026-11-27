"""Identify the installed CLI inputs used by the standalone Preserve fixture, not by Gradle."""
import hashlib
import json
import os
import re
import sys


MEMBERS = ('bin/kotlinc', 'lib/kotlin-compiler.jar', 'lib/kotlin-stdlib.jar',
           'lib/kotlinx-coroutines-core-jvm.jar')
# Relative to the resolved distribution. Local release ZIP; Linux image at C03 run 45884975781.
OBSERVED = {
    '2.0.20': (
        '64d62a197fbec5f32f77c6724cce33ead4034b2ec3f873c056cde19fe00f324e',
        '31ade4e3a65a2750c84b90788d37f23d89baa0e3e5c88538eda18914c908ee6d',
        'fb169596659a518357c4b2c16f43dc75ab1c4980565ed4b4a317a050e5e39006',
        'c24c8bb27bb320c4a93871501a7e5e0c61607638907b197aef675513d4c820be',
    ),
    '2.4.21': (
        '7082c4cdf466d4a8c0879eccd2bbd0011204ff10267a7eba921c08982201ec92',
        'dc96436fac5160a39a071f3b82d7683f2912bbbf19fe7e26be66533c045a824e',
        'bd8250210584cb659847dce9cda660f8e9906e5def7fbebcea93dc6dcb6a88a3',
        '9860906a1937490bf5f3b06d2f0e10ef451e65b95b269f22daf68a3d1f5065c5',
    ),
}


def check_identity(launcher, command, out):
    launcher = launcher.resolve(strict=True)
    home = launcher.parents[1]
    versions = {name: (out/file).read_text(errors='replace').strip() for name, file in (
        ('kotlin', 'compiler-version.log'), ('java', 'java-version.log'), ('javac', 'javac-version.log'))}
    banners = [line for line in versions['kotlin'].splitlines() if 'kotlinc-jvm' in line]
    banner = re.fullmatch(r'info: kotlinc-jvm (\S+) \(JRE 21(?:[.+-][^\s()]*)?\)', banners[0]) if len(banners) == 1 else None
    label = banner.group(1) if banner else None
    jdk21 = (re.search(r'(?m)^(?:openjdk|java) version "21(?:[.+-]|")', versions['java']) and
             re.search(r'(?m)^javac 21(?:[.+-]|$)', versions['javac']))
    hashes = {}
    for member in MEMBERS:
        path = home/member
        hashes[member] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    if os.name == 'nt':
        # The batch file locates the home; Java runs K2JVMCompiler. Compare the ZIP's POSIX
        # member, not the batch file, with the recorded POSIX digest. No Windows run attested.
        layout = launcher == home/'bin/kotlinc.bat' and label == '2.0.20'
    else:
        layout = launcher == (home/'bin/kotlinc').resolve() and (label != '2.4.21' or sys.platform == 'linux')
    matched = bool(layout and jdk21 and tuple(hashes.values()) == OBSERVED.get(label))
    receipt = {'identity_matched': matched, 'version': label, 'versions': versions,
               'platform': sys.platform, 'kotlin_home': str(home), 'path_launcher': str(launcher),
               'compiler_command': command, 'files_sha256': hashes,
               'application_gradle_toolchain_equivalence_claimed': False}
    (out/'toolchain.json').write_text(json.dumps(receipt, indent=2) + '\n')
    if not matched:
        raise RuntimeError('Unrecognized Preserve CLI identity; qualify the toolchain (see toolchain.json)')
