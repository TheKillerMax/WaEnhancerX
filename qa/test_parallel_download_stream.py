#!/usr/bin/env python3
"""Compile the production stream and verify HTTP Range integrity and fallback.

JVM fixtures do not demonstrate natural WhatsApp hook installation or media
downloads. The default compiler flag enforces Android-compatible Java 17 APIs.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / 'app/src/main/java/com/waenhancer/xposed/features/media/ParallelDownloadingInputStream.java'
FIXTURES = ROOT / 'qa/fixtures/parallel_download'


def main():
    with tempfile.TemporaryDirectory(prefix='waex-parallel-stream-') as output:
        subprocess.run([
            'javac', '--release', '17', '-d', output,
            str(PRODUCTION), str(FIXTURES / 'XposedBridge.java'),
            str(FIXTURES / 'ParallelDownloadingStreamTest.java'),
        ], check=True)
        subprocess.run([
            'java', '-cp', output,
            'com.waenhancer.xposed.features.media.ParallelDownloadingStreamTest',
        ], check=True)


if __name__ == '__main__':
    main()
