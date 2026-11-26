#!/usr/bin/env python3
"""Build only the new identity driver; copy the verified historical workload JARs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import zipfile

from expansion_contract import CANONICAL, HERE, context_check, digest, require, save, verify_canonical

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


def compiler_diagnostics(name, stdout, stderr):
    require(stdout == b'', 'Compiler emitted unexpected stdout: ' + name)
    if stderr == b'':
        return 'QUIET'
    require(name == 'driver-javac' and stderr in
            (KNOWN_JAVAC8_OPTIONS, KNOWN_JAVAC8_OPTIONS.replace(b'\n', b'\r\n')),
            'Compiler emitted unreviewed diagnostics: ' + name)
    return 'EXACT_KNOWN_JDK21_SOURCE_TARGET8_OPTIONS_WARNINGS'


def execute(out, name, command, env):
    record = {'command': list(map(str, command)), 'timeout_seconds': 120, 'stdin': 'closed'}
    try:
        result = subprocess.run(record['command'], env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=120)
        record['returncode'] = result.returncode
        for kind, raw in (('stdout', result.stdout), ('stderr', result.stderr)):
            (out / (name + '.' + kind + '.log')).write_bytes(raw[:512 * 1024])
            record[kind + '_bytes'] = len(raw)
        require(result.returncode == 0 and len(result.stdout) <= 512 * 1024 and
                len(result.stderr) <= 512 * 1024, 'Compiler failed or exceeded diagnostic bounds: ' + name)
        record['diagnostics'] = compiler_diagnostics(name, result.stdout, result.stderr)
        record['status'] = 'PASS'
    except Exception as error:
        record.update(status='BLOCKED', error=type(error).__name__ + ': ' + str(error))
        if isinstance(error, subprocess.TimeoutExpired):
            for kind, raw in (('stdout', error.stdout or b''), ('stderr', error.stderr or b'')):
                (out / (name + '.' + kind + '.log')).write_bytes(raw[:512 * 1024])
                record[kind + '_bytes'] = len(raw)
        raise
    finally:
        save(out / (name + '.command.json'), record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--canonical', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--java-home', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    lock = context_check(os.environ)
    require(lock.get('build_tool_sha256') == TOOL_PINS, 'Reviewed build tool pins differ')
    historical = verify_canonical(args.canonical.resolve())
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    artifact = out / 'artifact'
    artifact.mkdir()
    report = {'schema': 'WAEX_ART_PROFILE_EXPANSION_BUILD_V1', 'status': 'BLOCKED',
              'workflow_commit': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'lock_sha256': digest(HERE / 'lock.json'),
              'canonical_producer': CANONICAL, 'canonical_rebuilt': False,
              'historical_host_tests_repeated': False, 'art_executed': False,
              'current_build_scope': 'IDENTITY_DRIVER_ONLY_WITH_UNCHANGED_HISTORICAL_WORKLOAD_JARS',
              'artifact_archive_digest_scope': 'Historical API digest is pinned provenance; expanded member hashes are independently verified here.',
              'source_sha256': lock['source_sha256'], 'inherited_source_sha256': lock['inherited_source_sha256']}
    try:
        sdk = args.sdk.resolve()
        jdk = args.java_home.resolve()
        tools = {'java': jdk / 'bin/java', 'javac': jdk / 'bin/javac',
                 'android_jar': sdk / 'platforms/android-36/android.jar',
                 'd8_jar': sdk / 'build-tools/36.0.0/lib/d8.jar'}
        identity = {}
        for name, path in tools.items():
            require(path.is_file() and digest(path) == TOOL_PINS[name], 'Existing build tool differs: ' + name)
            identity[name] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest(path)}
        metadata = {name: digest(sdk / name) for name in lock['build_sdk_metadata_sha256']}
        require(metadata == lock['build_sdk_metadata_sha256'], 'Existing SDK metadata differs')
        report.update(tools=identity, sdk_metadata=metadata)
        env = os.environ.copy()
        env['JAVA_HOME'] = str(jdk)
        env['PATH'] = str(jdk / 'bin') + os.pathsep + env.get('PATH', '')
        classes, dex = out / 'classes', out / 'dex'
        classes.mkdir()
        dex.mkdir()
        execute(out, 'driver-javac', [tools['javac'], '--release', '8', '-encoding', 'UTF-8',
                                     '-classpath', tools['android_jar'], '-d', classes,
                                     HERE / 'ExpansionMain.java'], env)
        class_files = sorted(classes.rglob('*.class'))
        require([p.relative_to(classes).as_posix() for p in class_files] ==
                ['org/lab/waex/qa/classmetadata/expansion/ExpansionMain.class'],
                'Driver compilation produced unexpected classes')
        execute(out, 'driver-d8', [tools['java'], '-cp', tools['d8_jar'], 'com.android.tools.r8.D8',
                                  '--release', '--min-api', '25', '--lib', tools['android_jar'],
                                  '--output', dex, *class_files], env)
        require([p.name for p in dex.iterdir()] == ['classes.dex'], 'Driver requires one DEX only')
        body = (dex / 'classes.dex').read_bytes()
        require(112 <= len(body) <= 256 * 1024 and body[:4] == b'dex\n' and
                struct.unpack_from('<I', body, 96)[0] == 1 and
                b'Lorg/lab/waex/qa/classmetadata/expansion/ExpansionMain;' in body,
                'Driver DEX has unexpected class definitions or size')
        jar = artifact / 'identity-driver.jar'
        with zipfile.ZipFile(jar, 'x', zipfile.ZIP_STORED) as archive:
            entry = zipfile.ZipInfo('classes.dex', date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, body)
        require(jar.stat().st_size <= 256 * 1024, 'Driver JAR exceeds its bound')
        for name in ('baseline-art-probe.jar', 'candidate-art-probe.jar', 'artifact-manifest.json'):
            dest = 'canonical-artifact-manifest.json' if name == 'artifact-manifest.json' else name
            shutil.copyfile(args.canonical / name, artifact / dest)
        require(digest(artifact / 'canonical-artifact-manifest.json') == CANONICAL['manifest_sha256'],
                'Historical manifest copy differs')
        for variant, pin in CANONICAL['variants'].items():
            p = artifact / (variant + '-art-probe.jar')
            require(p.stat().st_size == pin['jar_bytes'] and digest(p) == pin['jar_sha256'],
                    'Historical JAR copy differs')
        for name, path in tools.items():
            require(digest(path) == identity[name]['sha256'], 'Build tool changed: ' + name)
        require({name: digest(sdk / name) for name in metadata} == metadata, 'SDK metadata changed during build')
        require(context_check(os.environ) == lock, 'Source/admission state changed during driver build')
        report.update(status='PASS_DRIVER_BUILD_CANONICAL_REUSE',
                      driver={'jar_bytes': jar.stat().st_size, 'jar_sha256': digest(jar),
                              'dex_sha256': hashlib.sha256(body).hexdigest(),
                              'class_name': 'org.lab.waex.qa.classmetadata.expansion.ExpansionMain',
                              'source_sha256': digest(HERE / 'ExpansionMain.java'), 'min_sdk': 25},
                      historical_qualification_not_reexecuted={v: {'host_checks': historical['variants'][v]['host_checks'],
                                                                  'host_scenarios': historical['variants'][v]['host_scenarios']}
                                                               for v in CANONICAL['variants']},
                      current_workload_tests_executed=0, sdk_changed=False)
        save(artifact / 'artifact-manifest.json', report)
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        save(out / 'build-result.json', report)
    print(json.dumps({'status': report['status'], 'manifest_sha256': digest(artifact / 'artifact-manifest.json')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
