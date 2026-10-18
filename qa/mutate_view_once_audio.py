#!/usr/bin/env python3
"""Compile-and-reject counterexamples for the audio resolver, hook and exporter."""
from pathlib import Path
import argparse, concurrent.futures, hashlib, json, shutil, subprocess, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'app/src/main/java/com/waenhancer/xposed/features/media/'
CASES = [
    ('wrong_audio_tag','ViewOnceAudioResolver.java','AUDIO_TAG = "view_once_audio"','AUDIO_TAG = "view_once_text"','hook'),
    ('ignore_activity_identity','ViewOnceMediaResolver.java','expected != null && expected.equals(identity(message))','expected != null','hook'),
    ('ignore_fragment_change','ViewOnceAudioResolver.java','audio(activity) != audio','false','hook'),
    ('ignore_message_change','ViewOnceAudioResolver.java','audioMessage.get(audio) != message','false','hook'),
    ('ignore_audio_data_change','ViewOnceMediaResolver.java','media.get(message) != data','false','hook'),
    ('ignore_activity_key_after_lookup','ViewOnceAudioResolver.java','!media.hasMediaKey(message, activityKey.get(activity))','false','hook'),
    ('ignore_host_false','DownloadViewOnceHook.java','!Boolean.TRUE.equals(param.getResult())','false','hook'),
    ('retain_failed_audio_action','DownloadViewOnceHook.java',
     '} catch (ReflectiveOperationException | RuntimeException | LinkageError failure) {\n                        menu.removeItem(MENU_ID_DOWNLOAD);',
     '} catch (ReflectiveOperationException | RuntimeException | LinkageError failure) {\n                        /* obsolete action retained */','hook'),
    ('skip_audio_install_rollback','DownloadViewOnceHook.java','first.unhook();','/* rollback removed */','hook'),
    ('accept_generic_ogg','GalleryMediaExporter.java','text(header, 28, 8).equals("OpusHead")','true','export'),
    ('accept_unsupported_channels','GalleryMediaExporter.java','(header[37] == 1 || header[37] == 2)','true','export'),
    ('wrong_audio_collection','GalleryMediaExporter.java','MediaStore.Audio.Media.EXTERNAL_CONTENT_URI','MediaStore.Images.Media.EXTERNAL_CONTENT_URI','export'),
    ('wrong_audio_directory','GalleryMediaExporter.java','audio() ? Environment.DIRECTORY_MUSIC','audio() ? Environment.DIRECTORY_PICTURES','export'),
    ('audio_through_gallery','GalleryMediaExporter.java','if (format.audio() != audioOnly)','if (audioOnly && !format.audio())','export'),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    def run(case):
        name, source, old, new, suite = case
        with tempfile.TemporaryDirectory(prefix='waex-audio-mutant-') as temporary:
            root = Path(temporary)
            (root / SOURCE).mkdir(parents=True)
            for file in ('DownloadViewOnceHook.java','ViewOnceMediaResolver.java',
                         'ViewOnceAudioResolver.java','GalleryMediaExporter.java'):
                shutil.copy2(ROOT / SOURCE / file, root / SOURCE / file)
            shutil.copytree(ROOT / 'qa/view_once', root / 'qa/view_once')
            for file in ('test_view_once_download.py','test_view_once_audio.py',
                         'test_gallery_export.py','view_once_audio_fixtures.py','localization_support.py'):
                shutil.copy2(ROOT / 'qa' / file, root / 'qa' / file)
            shutil.copytree(ROOT / 'app/src/main/res/values', root / 'app/src/main/res/values')
            path = root / SOURCE / source
            text = path.read_text()
            assert old in text, 'Inert mutation: ' + name
            path.write_text(text.replace(old, new))
            runner = ['qa/test_view_once_audio.py','--export-only'] if suite=='export' else ['qa/test_view_once_download.py','--audio']
            try:
                result = subprocess.run(['python3', str(root / runner[0]), *runner[1:]],
                                        capture_output=True,text=True,timeout=90)
                log = result.stdout + result.stderr
                compiled = 'COMPILE_OK:' in log
                detected = compiled and result.returncode != 0 and 'java.lang.AssertionError:' in log
                row = {'name':name,'suite':suite,'exit_code':result.returncode,
                       'compiled':compiled,'detected':detected,'path':SOURCE+source,
                       'mutant_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            except subprocess.TimeoutExpired:
                log = 'Infrastructure timeout'
                row = {'name':name,'suite':suite,'exit_code':124,'compiled':False,'detected':False}
            (args.out / (name+'.log')).write_text(log)
            print(json.dumps(row),flush=True)
            return row

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as workers:
        rows = list(workers.map(run,CASES))
    (args.out/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
    assert all(row['detected'] for row in rows), 'A negative control was not behaviorally rejected'
    print('PASS:',len(rows),'compiled audio behavioral controls')


if __name__ == '__main__':
    main()
