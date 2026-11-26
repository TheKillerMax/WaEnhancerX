#!/usr/bin/env python3
"""Observe and clean only a new cache fixture on API27/28 owned AVDs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import time
import zipfile

from class_metadata_profile_recovery import recovery_contract as admission
from class_metadata_profile_recovery import recovery_pilot as pilot
from art_cache_recovery.build import CLASS, check_dex, digest, generated_source, require, save
from art_cache_recovery.owned_tree import OwnedTree
from art_cache_recovery.validate import validate_output

HERE = Path(__file__).resolve().parent
MAX_LOG = 65536
PHASE_SECONDS = 240
WORK_SECONDS = 120


def verified_bundle(bundle, manifest_sha, lock, env):
    require(bundle.is_dir() and not bundle.is_symlink()
            and {p.name for p in bundle.iterdir()} == {'artifact-manifest.json', 'cache-probe.jar'},
            'Cache artifact must contain no canonical workload JARs')
    require(all(p.is_file() and not p.is_symlink() for p in bundle.iterdir()), 'Artifact member redirected')
    manifest = bundle / 'artifact-manifest.json'
    require(re.fullmatch(r'[0-9a-f]{64}', manifest_sha) is not None
            and 0 < manifest.stat().st_size <= 256 * 1024 and digest(manifest) == manifest_sha,
            'Current cache producer manifest differs')
    row = json.loads(manifest.read_bytes())
    producer = {'workflow_commit': env['GITHUB_SHA'], 'run_id': env['GITHUB_RUN_ID'], 'attempt': env['GITHUB_RUN_ATTEMPT']}
    required = {'schema': 'WAEX_ART_CACHE_PROBE_BUILD_V1', 'status': 'PASS_NEW_CACHE_PROBE_BUILD_ONLY',
                'producer': producer, 'lock_sha256': digest(Path(admission.__file__).with_name('lock.json')),
                'source_sha256': lock['source_sha256'], 'inherited_source_sha256': lock['inherited_source_sha256'],
                'scope': 'NEW_CACHE_LIFECYCLE_FIXTURE_ONLY', 'canonical_jars_included': False,
                'canonical_workloads_executed': 0, 'android_executed': False, 'sdk_changed': False}
    for key, expected in required.items():
        require(type(row.get(key)) is type(expected) and row[key] == expected, 'Cache producer differs: ' + key)
    probe = row.get('probe')
    require(type(probe) is dict and set(probe) == {'jar_bytes', 'jar_sha256', 'dex_sha256', 'class_name',
            'min_sdk', 'source_sha256', 'generated_source_sha256'}, 'Probe build fields differ')
    template = (HERE / 'CacheLifecycleMain.java').read_bytes()
    require(probe['class_name'] == CLASS and probe['min_sdk'] == 27
            and probe['source_sha256'] == hashlib.sha256(template).hexdigest()
            and probe['generated_source_sha256'] == hashlib.sha256(generated_source(template, producer)).hexdigest(),
            'Current generated probe source differs')
    jar = bundle / 'cache-probe.jar'
    require(type(probe['jar_bytes']) is int and 0 < probe['jar_bytes'] <= 65536
            and jar.stat().st_size == probe['jar_bytes'] and digest(jar) == probe['jar_sha256'], 'Probe JAR differs')
    with zipfile.ZipFile(jar) as archive:
        require(archive.namelist() == ['classes.dex'] and archive.testzip() is None, 'Probe archive members/CRC differ')
        entry = archive.getinfo('classes.dex')
        require(entry.compress_type == zipfile.ZIP_STORED and not (entry.flag_bits & 1)
                and 112 <= entry.file_size <= 65000, 'Probe DEX packaging differs')
        body = archive.read(entry); check_dex(body)
        require(hashlib.sha256(body).hexdigest() == probe['dex_sha256'], 'Probe DEX SHA differs')
    return row


def fresh_nonce(lock):
    consumed = lock.get('consumed_nonces')
    require(isinstance(consumed, list) and consumed and len(consumed) == len(set(consumed))
            and all(type(n) is str and re.fullmatch(r'[0-9a-f]{32}', n) is not None for n in consumed),
            'Common consumed-nonce ledger is missing or malformed')
    nonce = secrets.token_hex(16)
    require(nonce not in consumed, 'Generated nonce is already consumed; no automatic regeneration')
    return nonce


def binary_readback(context, label, remote, max_bytes, timeout):
    """One quiet uncompressed ADB sync read; retain exact bounded bytes as evidence."""
    require(re.fullmatch(r'[a-z0-9-]+', label) is not None and type(max_bytes) is int
            and 0 <= max_bytes <= OwnedTree.MAX_FILE, 'Invalid bounded read request')
    require(re.fullmatch(r'/data/local/tmp/waex-art-cache-probe-[a-f0-9]{32}/(?:ownership\.json|probe\.jar|oat/x86_64/probe\.(?:odex|vdex))', remote)
            is not None, 'Readback escaped the new cache fixture')
    folder = context.out / (label + '-data'); folder.mkdir()
    target, stdout, stderr = folder / 'payload.bin', folder / 'stdout.log', folder / 'stderr.log'
    command = [str(context.adb), '-s', context.serial, 'pull', '-q', '-Z', remote, str(target)]
    record = {'schema': 'WAEX_CACHE_BOUNDED_SYNC_READ_V1', 'status': 'BLOCKED', 'command': command,
              'method': 'adb_pull_sync_uncompressed', 'max_bytes': max_bytes, 'attempts': 1,
              'timeout_seconds': timeout, 'stdin': 'closed', 'payload_retained': True}
    started, process = time.monotonic(), None
    limits = ((target, max_bytes), (stdout, MAX_LOG), (stderr, MAX_LOG))
    def bounded():
        for path, bound in limits:
            require(not path.is_symlink(), 'Readback destination redirected')
            if path.exists():
                require(path.is_file() and path.stat().st_size <= bound, 'Readback exceeded its byte bound')
    try:
        with stdout.open('xb') as output, stderr.open('xb') as errors:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=output, stderr=errors,
                                       env=context.env, start_new_session=True)
            while process.poll() is None:
                bounded()
                remaining = timeout - (time.monotonic() - started)
                require(remaining > 0, 'Readback deadline exceeded')
                try:
                    process.wait(timeout=min(0.05, remaining))
                except subprocess.TimeoutExpired:
                    pass
            bounded()
        record['returncode'] = process.returncode
        require(process.returncode == 0 and stdout.stat().st_size == 0 and stderr.stat().st_size == 0,
                'Quiet sync read failed or emitted diagnostics')
        require(target.is_file() and not target.is_symlink(), 'Readback file absent or redirected')
        raw = target.read_bytes()
        require(len(raw) == max_bytes, 'Readback differs from measured lstat size')
        record.update(status='PASS', bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        return raw
    except Exception as error:
        record['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        if process is not None and process.poll() is None:
            pilot.stop_owned(process)
        record['retained'] = {}
        for path, bound in limits:
            if path.exists() and path.is_file() and not path.is_symlink():
                original_bytes = path.stat().st_size
                if original_bytes > bound:
                    with path.open('r+b') as stream: stream.truncate(bound)
                record['retained'][path.name] = {'path': path.relative_to(context.out).as_posix(),
                    'observed_bytes': original_bytes, 'retained_bytes': path.stat().st_size,
                    'sha256': digest(path), 'truncated_prefix': original_bytes > bound}
        record['seconds'] = round(time.monotonic() - started, 3)
        save(context.out / (label + '-readback.json'), record)


def cache_action(bundle, manifest_sha, producer, nonce):
    def execute(context):
        require(context.serial == 'emulator-5580' and context.target in admission.CACHE_TARGETS
                and context.guest['abi'] == 'x86_64' and context.api == int(context.target[3:])
                and context.minor == 0 and context.application_page_size_bytes == 4096,
                'Unexpected owned cache BootContext')
        phase = {'schema': 'WAEX_ART_CACHE_LIFECYCLE_RUNTIME_V1', 'status': 'BLOCKED',
                 'scope': 'NEW_CACHE_FIXTURE_AND_OWNED_CLEANUP_ONLY', 'target': context.target,
                 'nonce': nonce, 'nonce_reuse_allowed': False, 'producer': producer['producer'],
                 'producer_manifest_sha256': manifest_sha, 'canonical_workloads_invoked': 0,
                 'launch_attempted': False, 'normal_process_return_confirmed': False,
                 'owned_directory_absent': False, 'historical_cleanup_reclassified': False}
        save(context.out / 'cache-nonce-claim.json', {'nonce': nonce, 'target': context.target,
             'producer': producer['producer'], 'schema': 'WAEX_NEW_CACHE_NONCE_CLAIM_V1', 'reuse_allowed': False})
        started = time.monotonic()
        cleaning, seq = False, 0
        tree, failure = None, None
        def budget(maximum):
            left = (PHASE_SECONDS if cleaning else WORK_SECONDS) - (time.monotonic() - started)
            require(left > 0, 'Cache phase time budget exhausted')
            return min(maximum, left)
        def adb(label, *args, timeout=10, required=True):
            return pilot.invoke(context.out, label, [str(context.adb), '-s', context.serial, *args],
                                context.env, timeout=budget(timeout), required=required)
        def command(label, script, timeout=10):
            return adb(label, 'shell', script, timeout=timeout)[1]
        def read_boot():
            nonlocal seq
            seq += 1
            raw = command('cache-boot-%03d' % seq, 'cat /proc/sys/kernel/random/boot_id')
            value = raw.strip()
            require(re.fullmatch(r'[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}', value) is not None,
                    'Malformed actual kernel boot')
            return value
        def read_file(label, path, max_bytes):
            return binary_readback(context, label, path, max_bytes, budget(30))
        try:
            boot = read_boot()
            phase['boot_id_before'] = boot
            pin = {'bytes': producer['probe']['jar_bytes'], 'sha256': producer['probe']['jar_sha256']}
            tree = OwnedTree(command=command, read_file=read_file, read_boot=read_boot,
                             nonce=nonce, boot=boot, prefix='waex-art-cache-probe', inputs={'probe.jar': pin},
                             producer={**producer['producer'], 'manifest_sha256': manifest_sha})
            phase['initial_inventory'] = tree.create()
            path = tree.path + '/probe.jar'
            require(read_boot() == boot, 'Boot changed before push')
            phase['push_attempted'] = True
            adb('cache-probe-push', 'push', str(bundle / 'cache-probe.jar'), path, timeout=30)
            command('cache-probe-readonly', 'chmod 444 -- ' + shlex.quote(path))
            phase['before_launch_inventory'] = tree.inventory(require_inputs=True)
            expected = {'target': context.target, 'nonce': nonce, 'boot_id': boot,
                        'fingerprint': context.guest['fingerprint'], 'jar_path': path,
                        'jar_bytes': pin['bytes'], 'jar_sha256': pin['sha256'], 'producer': producer['producer']}
            args = [context.target, nonce, boot, expected['fingerprint'], path, pin['sha256'], str(pin['bytes']),
                    producer['producer']['run_id'], producer['producer']['attempt'], producer['producer']['workflow_commit']]
            shell = 'CLASSPATH=' + shlex.quote(path) + ' exec /system/bin/app_process64 /system/bin ' + CLASS + ' ' + shlex.join(args)
            require(budget(30) >= 30, 'Insufficient work budget for one full launch')
            require(PHASE_SECONDS - (time.monotonic() - started) >= 150, 'Cleanup reserve not available')
            require(read_boot() == boot, 'Boot changed at launch gate')
            save(context.out / 'cache-launch-intent.json', {'attempts': 1, 'nonce': nonce, 'shell': shell,
                 'producer': producer['producer'], 'canonical_workloads_invoked': 0})
            phase['launch_attempted'] = True
            result, _ = adb('cache-probe-execute', 'shell', shell, timeout=30, required=False)
            phase['normal_process_return_confirmed'] = result.get('failure') is None and result.get('returncode') == 0
            require(phase['normal_process_return_confirmed'], 'Probe completion is not an unambiguous return0')
            raw = (context.out / 'cache-probe-execute.log').read_bytes()
            validation = validate_output(raw, expected)
            save(context.out / 'cache-probe-validated.json', validation)
            phase['process_identity'] = validation['identity']
            require(read_boot() == boot, 'Boot changed after probe')
            phase['after_launch_inventory'] = tree.inventory(require_inputs=True)
        except Exception as error:
            failure = error
            phase['error'] = type(error).__name__ + ': ' + str(error)
        finally:
            cleaning = True
            eligible = (tree is not None and tree.root_identity is not None and tree.marker_identity is not None
                        and (not phase['launch_attempted'] or phase['normal_process_return_confirmed']))
            if eligible:
                try:
                    phase['cleanup'] = tree.clean()
                    phase['owned_directory_absent'] = phase['cleanup']['root_absent']
                except Exception as error:
                    phase['cleanup_error'] = type(error).__name__ + ': ' + str(error)
                    if failure is None: failure = error
            else:
                phase['cleanup_deferred'] = 'No complete ownership marker or uncertain process completion; preserve and rely on owned outer AVD reaping'
            if tree is not None:
                phase['ownership_events'] = tree.events
            if failure is None and phase['owned_directory_absent']:
                phase['status'] = 'PASS'
                observed = phase['cleanup']['cache_descendants']
                phase['cache_observation'] = 'LOCAL_CACHE_DESCENDANTS_OBSERVED' if observed else 'NO_LOCAL_CACHE_DESCENDANTS_OBSERVED'
                phase['historical_oat_hypothesis'] = 'CORROBORATED_IN_NEW_FIXTURE_ONLY' if observed else 'NOT_REPRODUCED_BY_NEW_FIXTURE'
            phase['seconds'] = round(time.monotonic() - started, 3)
            save(context.out / 'cache-lifecycle-phase.json', phase)
        if failure is not None:
            raise RuntimeError('New cache fixture or cleanup blocked: ' + str(failure)) from failure
        require(phase['status'] == 'PASS', 'Cache phase lacks verified cleanup')
        return phase
    return execute


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=('api27', 'api28'), required=True)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    lock = admission.context_check(os.environ)
    producer = verified_bundle(args.artifact.resolve(), args.manifest_sha256, lock, os.environ)
    nonce = fresh_nonce(lock)  # No regeneration/retry; reject a historical collision before boot/ADB.
    return pilot.main(['--target', args.target, '--lock', str(admission.ROOT / 'qa/android_emulator_lab_matrix_lock.json'),
                       '--out', str(args.out)], targets=admission.CACHE_TARGETS, read_lock=admission.checked_matrix,
                      boot_action=cache_action(args.artifact.resolve(), args.manifest_sha256, producer, nonce),
                      phase='new_art_cache_lifecycle_only', result_name='art-cache-lifecycle-result.json',
                      limits='New minimal cache fixture on API27/28 only; no canonical workloads, historical cleanup reclassification, '
                             'WAEX app, Motorola, DSU or physical ARM64 claims.')


if __name__ == '__main__':
    raise SystemExit(main())
