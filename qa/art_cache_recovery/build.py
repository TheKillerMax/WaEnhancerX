#!/usr/bin/env python3
"""Build one new Java-only cache identity JAR; no canonical workload inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import zipfile
import zlib

from class_metadata_profile_recovery import recovery_contract as admission

HERE = Path(__file__).resolve().parent
CLASS = 'org.lab.waex.qa.artcache.CacheLifecycleMain'
TOOL_PINS = {
    'java': '9cad3f2620d3ef2ed10b26f922af7e773d54fdaa05f615d6d6df014f3fec4155',
    'javac': '2cc288a26beebc50ca7cd924847dffbfb38ef3314e105bba6d4ebce03a0bcb6b',
    'android_jar': 'd9eb9da824d9e247a352f570f01e1169e725b2954bca9e283a71786c59b59f9a',
    'd8_jar': '4097ff9c46c185c6e7214da7fe9b1befb5adeea5cc9ca349270e0249904f9240',
}
KNOWN_JAVAC8_OPTIONS = (
    b'warning: [options] source value 8 is obsolete and will be removed in a future release\n'
    b'warning: [options] target value 8 is obsolete and will be removed in a future release\n'
    b'warning: [options] To suppress warnings about obsolete options, use -Xlint:-options.\n'
    b'3 warnings\n'
)


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def generated_source(raw, producer):
    require(set(producer) == {'workflow_commit', 'run_id', 'attempt'}
            and re.fullmatch(r'[0-9a-f]{40}', producer['workflow_commit']) is not None
            and re.fullmatch(r'[1-9][0-9]*', producer['run_id']) is not None
            and producer['attempt'] == '1', 'Malformed concrete producer')
    for token, key in (('__PRODUCER_HEAD__', 'workflow_commit'), ('__PRODUCER_RUN__', 'run_id'),
                       ('__PRODUCER_ATTEMPT__', 'attempt')):
        require(raw.count(token.encode()) == 1, 'Producer placeholder count differs')
        raw = raw.replace(token.encode(), producer[key].encode('ascii'))
    return raw


def execute(out, name, command, env):
    record = {'command': list(map(str, command)), 'timeout_seconds': 120, 'stdin': 'closed'}
    try:
        result = subprocess.run(record['command'], env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=120)
        record['returncode'] = result.returncode
        for kind, raw in (('stdout', result.stdout), ('stderr', result.stderr)):
            (out / (name + '.' + kind + '.log')).write_bytes(raw[:512 * 1024])
            record[kind + '_bytes'] = len(raw)
        require(result.returncode == 0 and len(result.stdout) <= 512 * 1024
                and len(result.stderr) <= 512 * 1024, 'Compiler failed or exceeded output bound')
        require(result.stdout == b'' and (result.stderr == b'' or (name == 'cache-javac' and result.stderr in
                (KNOWN_JAVAC8_OPTIONS, KNOWN_JAVAC8_OPTIONS.replace(b'\n', b'\r\n')))),
                'Unreviewed compiler diagnostics')
        record.update(status='PASS', diagnostics='QUIET' if not result.stderr else 'EXACT_KNOWN_JDK21_SOURCE_TARGET8_OPTIONS_WARNINGS')
    except Exception as error:
        record.update(status='BLOCKED', error=type(error).__name__ + ': ' + str(error))
        if isinstance(error, subprocess.TimeoutExpired):
            for kind, raw in (('stdout', error.stdout or b''), ('stderr', error.stderr or b'')):
                (out / (name + '.' + kind + '.log')).write_bytes(raw[:512 * 1024])
                record[kind + '_bytes'] = len(raw)
        raise
    finally:
        save(out / (name + '.command.json'), record)


def check_dex(raw):
    require(112 <= len(raw) <= 65000 and raw[:8] in (b'dex\n035\0', b'dex\n037\0', b'dex\n038\0', b'dex\n039\0'),
            'Unexpected single-class DEX header or byte bound')
    require(struct.unpack_from('<III', raw, 32) == (len(raw), 112, 0x12345678)
            and struct.unpack_from('<I', raw, 96)[0] == 1, 'DEX size/header/class count differs')
    require(hashlib.sha1(raw[32:]).digest() == raw[12:32]
            and zlib.adler32(raw[12:]) & 0xffffffff == struct.unpack_from('<I', raw, 8)[0], 'DEX integrity differs')
    require(('L' + CLASS.replace('.', '/') + ';').encode() in raw, 'New fixture class absent')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--java-home', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    lock = admission.context_check(os.environ)
    require(lock.get('build_tool_sha256') == TOOL_PINS, 'Shared build-tool pins differ')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    artifact = out / 'artifact'; artifact.mkdir()
    producer = {'workflow_commit': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                'attempt': os.environ['GITHUB_RUN_ATTEMPT']}
    lock_path = Path(admission.__file__).with_name('lock.json')
    report = {'schema': 'WAEX_ART_CACHE_PROBE_BUILD_V1', 'status': 'BLOCKED', 'producer': producer,
              'lock_sha256': digest(lock_path), 'source_sha256': lock['source_sha256'],
              'inherited_source_sha256': lock['inherited_source_sha256'],
              'scope': 'NEW_CACHE_LIFECYCLE_FIXTURE_ONLY', 'canonical_jars_included': False,
              'canonical_workloads_executed': 0, 'android_executed': False}
    try:
        sdk, jdk = args.sdk.resolve(), args.java_home.resolve()
        tools = {'java': jdk / 'bin/java', 'javac': jdk / 'bin/javac',
                 'android_jar': sdk / 'platforms/android-36/android.jar',
                 'd8_jar': sdk / 'build-tools/36.0.0/lib/d8.jar'}
        identity = {}
        for name, path in tools.items():
            require(path.is_file() and digest(path) == TOOL_PINS[name], 'Existing pinned tool differs: ' + name)
            identity[name] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest(path)}
        metadata = {name: digest(sdk / name) for name in lock['build_sdk_metadata_sha256']}
        require(metadata == lock['build_sdk_metadata_sha256'], 'Existing SDK metadata differs')
        report.update(tools=identity, sdk_metadata=metadata)
        classes, dex, source_dir = out / 'classes', out / 'dex', out / 'generated'
        for path in (classes, dex, source_dir): path.mkdir()
        template = (HERE / 'CacheLifecycleMain.java').read_bytes()
        generated = generated_source(template, producer)
        source = source_dir / 'CacheLifecycleMain.java'; source.write_bytes(generated)
        env = os.environ.copy()
        env.update(JAVA_HOME=str(jdk), PATH=str(jdk / 'bin') + os.pathsep + env.get('PATH', ''))
        execute(out, 'cache-javac', [tools['javac'], '--release', '8', '-encoding', 'UTF-8',
                                    '-classpath', tools['android_jar'], '-d', classes, source], env)
        class_files = sorted(classes.rglob('*.class'))
        require([p.relative_to(classes).as_posix() for p in class_files] == [CLASS.replace('.', '/') + '.class'],
                'Cache fixture must compile to exactly one new class')
        execute(out, 'cache-d8', [tools['java'], '-cp', tools['d8_jar'], 'com.android.tools.r8.D8',
                                 '--release', '--min-api', '27', '--lib', tools['android_jar'],
                                 '--output', dex, *class_files], env)
        require([p.name for p in dex.iterdir()] == ['classes.dex'], 'Single DEX required')
        body = (dex / 'classes.dex').read_bytes(); check_dex(body)
        jar = artifact / 'cache-probe.jar'
        with zipfile.ZipFile(jar, 'x', zipfile.ZIP_STORED) as archive:
            entry = zipfile.ZipInfo('classes.dex', date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3; entry.external_attr = 0o100644 << 16
            archive.writestr(entry, body)
        require(jar.stat().st_size <= 65536, 'Cache JAR exceeds its byte bound')
        with zipfile.ZipFile(jar) as archive:
            require(archive.namelist() == ['classes.dex'] and archive.read('classes.dex') == body
                    and archive.testzip() is None, 'Cache JAR readback differs')
        for name, path in tools.items(): require(digest(path) == identity[name]['sha256'], 'Build tool changed')
        require({name: digest(sdk / name) for name in metadata} == metadata, 'SDK metadata changed')
        require(admission.context_check(os.environ) == lock, 'Admission/source state changed during build')
        report.update(status='PASS_NEW_CACHE_PROBE_BUILD_ONLY',
                      probe={'jar_bytes': jar.stat().st_size, 'jar_sha256': digest(jar),
                             'dex_sha256': hashlib.sha256(body).hexdigest(), 'class_name': CLASS, 'min_sdk': 27,
                             'source_sha256': hashlib.sha256(template).hexdigest(),
                             'generated_source_sha256': hashlib.sha256(generated).hexdigest()}, sdk_changed=False)
        save(artifact / 'artifact-manifest.json', report)
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        save(out / 'build-result.json', report)
    print(json.dumps({'status': report['status'], 'manifest_sha256': digest(artifact / 'artifact-manifest.json')}))


if __name__ == '__main__':
    main()
