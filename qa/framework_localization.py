"""Stage actual public localization dependencies in isolated Android test projects.

No replacement UiText/Resources implementation is generated. The resource-only
APK is a test package, not a signed WAEX application or a host installation.
"""
from pathlib import Path
import hashlib
import os
import re
import shutil
import subprocess
import sys

HELPERS = ('UiText.java', 'DisplayLocalePolicy.java')
QUALIFIERS = ('values', 'values-es', 'values-b+es+419')


def stage_localization(root, probe, identities):
    root, probe = Path(root), Path(probe)
    if not (root / 'app/src/main/java/com/waenhancer/utils/UiText.java').exists():
        return False
    for name in HELPERS:
        source = root / 'app/src/main/java/com/waenhancer/utils' / name
        target = probe / 'src/main/java/com/waenhancer/utils' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)  # Missing dependencies are fatal, not skipped.
        identities[str(source.relative_to(root))] = hashlib.sha256(source.read_bytes()).hexdigest()
    for qualifier in QUALIFIERS:
        for filename in ('strings.xml', 'ui_strings.xml'):
            source = root / 'app/src/main/res' / qualifier / filename
            target = probe / 'src/main/res' / qualifier / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            identities[str(source.relative_to(root))] = hashlib.sha256(source.read_bytes()).hexdigest()
    return True


def build_localization_table(root, out):
    """Use a real SDK AAPT2 and the existing exact-value verifier."""
    sdk = os.environ.get('ANDROID_SDK_ROOT') or os.environ.get('ANDROID_HOME')
    tools = list((Path(sdk) / 'build-tools').glob('*/aapt2')) if sdk else []
    if not tools:
        raise RuntimeError('Android SDK AAPT2 required for real locale resource tests')
    def version(path):
        return tuple(int(n) for n in re.findall(r'\d+', path.parent.name))
    aapt2 = sorted(tools, key=version)[-1]
    subprocess.run([sys.executable, str(Path(root) / 'qa/verify_es419_resources.py'),
                    '--aapt2', str(aapt2), '--out', str(out)], check=True, timeout=600)
    apk = Path(out) / 'resources-only.apk'
    if not apk.is_file():
        raise RuntimeError('AAPT2 did not produce the required locale table')
    return apk
