#!/usr/bin/env python3
"""Build only the unchanged new cache fixture with explicitly selected pinned JDK inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile

from art_cache_profile_recovery import cache_contract as admission
from art_cache_profile_recovery.jdk_observation import observe_inputs, validate_observation
from art_cache_recovery.build import (CLASS, TOOL_PINS, require, digest, save,
                                      generated_source, execute, check_dex)

# The reviewed Java bytes stay in the published parent; only its existing
# producer placeholders receive the current concrete build identity.
HERE = admission.ROOT / 'qa/art_cache_recovery'


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
        observed = observe_inputs(args.java_home, args.sdk, lock, label='selected-before-gate')
        # Retain every observed path/type/size/hash before any pin rejection.
        report['build_input_observation'] = observed
        identity = {name: {key: row.get(key) for key in ('path', 'bytes', 'sha256')}
                    for name, row in observed['tools'].items()}
        metadata = {name: row.get('sha256') for name, row in observed['sdk_metadata'].items()}
        report.update(tools=identity, sdk_metadata=metadata)
        save(out / 'selected-inputs-before-gate.json', observed)
        report['build_input_pin_gate'] = validate_observation(observed, lock)
        sdk, jdk = Path(observed['sdk_resolved']), Path(observed['java_home_resolved'])
        tools = {name: Path(row['path']) for name, row in identity.items()}
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
        after = observe_inputs(jdk, sdk, lock, label='selected-after-build')
        report['build_inputs_after'] = after
        save(out / 'selected-inputs-after-build.json', after)
        report['build_input_pin_gate_after'] = validate_observation(after, lock)
        require(after['java_home_resolved'] == observed['java_home_resolved']
                and after['sdk_resolved'] == observed['sdk_resolved'], 'Build input roots changed')
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
