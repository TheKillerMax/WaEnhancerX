#!/usr/bin/env python3
"""Compile the complete audio hook path, then the real exporter with real file IO.

Android, host, DexKit metadata and storage services are explicit doubles. The
embedded Opus fixtures are generated silence, not WhatsApp/device recordings.
--baseline-exporter runs the previous public export route against identical bytes;
it compiles the unchanged exporter before checking the desired audio behavior.
"""
from pathlib import Path
import argparse, hashlib, subprocess, sys, tempfile
from test_gallery_export import STUBS

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'app/src/main/java/com/waenhancer/xposed/features/media'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--baseline-exporter', type=Path)
    p.add_argument('--export-only', action='store_true')
    p.add_argument('--dexkit-jar', type=Path)
    a = p.parse_args()
    if not a.export_only and not a.baseline_exporter:
        subprocess.run([sys.executable, str(ROOT / 'qa/test_view_once_download.py'), '--audio',
                        *(['--dexkit-jar', str(a.dexkit_jar)] if a.dexkit_jar else [])],
                       check=True, timeout=120)
    source = a.baseline_exporter or SOURCE / 'GalleryMediaExporter.java'
    with tempfile.TemporaryDirectory(prefix='waex-audio-export-') as temporary:
        d = Path(temporary)
        for relative, text in STUBS.items():
            path = d / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text + '\n')
        staged = d / 'GalleryMediaExporter.java'
        staged.write_bytes(source.read_bytes())
        entry = 'export' if a.baseline_exporter else 'exportAudio'
        (d / 'AudioEntryPoint.java').write_text('''package com.waenhancer.xposed.features.media;
final class AudioEntryPoint { static void export(android.content.Context c,java.io.File f)
throws java.io.IOException { GalleryMediaExporter.''' + entry + '''(c,f); } }
''')
        subprocess.run(['javac', '--release', '17', '-d', str(d / 'classes'),
                        str(ROOT / 'qa/view_once/ViewOnceAudioExportTest.java'),
                        *map(str, d.rglob('*.java'))], check=True, timeout=60)
        print('COMPILE_OK: complete real exporter and explicit storage doubles', flush=True)
        subprocess.run(['java', '-cp', str(d / 'classes'),
                        'com.waenhancer.xposed.features.media.ViewOnceAudioExportTest', str(d / 'files')],
                       check=True, timeout=60)
        print('SOURCE_SHA256:', source.name, hashlib.sha256(source.read_bytes()).hexdigest(), flush=True)


if __name__ == '__main__':
    main()
