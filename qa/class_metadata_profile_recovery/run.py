#!/usr/bin/env python3
"""Run only fifteen pending canonical processes; retain earlier PASS evidence without replay."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import struct
import subprocess
import sys
import time
import zipfile

HERE = Path(__file__).resolve().parent
QA = HERE.parent
sys.path.insert(0, str(QA))
from class_metadata_profile_recovery.recovery_contract import (CANONICAL, MATRIX_SHA, ROOT, TARGETS, TARGET_NAMES, VARIANTS,
                                context_check, digest, minor, require, RUNTIME_VARIANTS, consumed_nonces, prior_evidence, checked_matrix)
from class_metadata_profile_recovery.validate_recovery import validate_output
from class_metadata_profile_recovery.recovery_pilot import main as boot_main, invoke, save
from art_cache_recovery.owned_tree import OwnedTree

MAX_JAR_BYTES = 8 * 1024 ** 2
MAX_STDERR_BYTES = 65536
WORK_SECONDS = 300
PHASE_SECONDS = 480
EXECUTION_SECONDS = 90


def capture_pull(command,target,output,errors,env,timeout=60,*,payload_limit=MAX_JAR_BYTES):
    """Use ADB sync framing, with bounded files, closed stdin and the owned server."""
    require(type(payload_limit) is int and 0 <= payload_limit <= MAX_JAR_BYTES, 'Invalid payload bound')
    require(not target.exists() and not target.is_symlink(),'Readback payload already exists')
    start=time.monotonic();process=None
    def bounded():
        for path,limit in ((target,payload_limit),(output,MAX_STDERR_BYTES),(errors,MAX_STDERR_BYTES)):
            require(not path.is_symlink(),'Readback output was redirected')
            if path.exists():
                require(path.is_file() and path.stat().st_size<=limit,'Sync readback exceeded its output bound')
    with output.open('xb') as stdout,errors.open('xb') as stderr:
        try:
            process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=stdout,
                                     stderr=stderr,env=env)
            while process.poll() is None:
                bounded()
                remaining=timeout-(time.monotonic()-start)
                if remaining<=0:raise subprocess.TimeoutExpired(command,timeout)
                try:process.wait(timeout=min(0.05,remaining))
                except subprocess.TimeoutExpired:pass
            bounded()
            return process.returncode
        finally:
            if process is not None and process.poll() is None:
                process.kill();process.wait(timeout=5)

def verify_pull_identity(target,output,errors,returncode,pin):
    require(returncode==0 and output.stat().st_size==0 and errors.stat().st_size==0,
            'Quiet sync readback failed or emitted diagnostics')
    require(target.is_file() and not target.is_symlink(),'Sync readback payload is missing or redirected')
    size=target.stat().st_size
    require(size==pin['jar_bytes'] and 0<size<=MAX_JAR_BYTES,'Guest JAR size differs')
    observed=digest(target)
    require(observed==pin['jar_sha256'],'Guest JAR identity differs')
    return {'bytes':size,'sha256':observed,'matches_producer':True}

def retain_bounded(path,limit,out):
    """Preserve failed evidence; explicitly label a bounded prefix after overflow."""
    if not path.exists() and not path.is_symlink():return {'exists':False}
    require(path.is_file() and not path.is_symlink(),'Readback evidence was redirected')
    observed=path.stat().st_size
    if observed>limit:
        with path.open('r+b') as stream:stream.truncate(limit)
    return {'exists':True,'path':path.relative_to(out).as_posix(),
            'observed_bytes':observed,'retained_bytes':path.stat().st_size,
            'retained_sha256':digest(path),'truncated_to_bound':observed>limit}

def jar_readback(adb,serial,path,pin,out,label,env,*,timeout=60):
    """Fresh full sync read before execution/removal; failed bytes remain evidence."""
    require(serial=='emulator-5580' and re.fullmatch(
        r'/data/local/tmp/waex-art-recovery-[a-f0-9]{32}/(?:driver|baseline|candidate)\.jar',path),
        'Readback outside the owned emulator probe path')
    require(re.fullmatch(r'[a-z0-9-]+',label) and type(pin['jar_bytes']) is int
            and 0<pin['jar_bytes']<=MAX_JAR_BYTES
            and re.fullmatch('[a-f0-9]{64}',pin['jar_sha256']),'Invalid readback identity')
    record_path=out/(label+'-readback.json')
    require(not record_path.exists() and not record_path.is_symlink(),'Readback receipt already exists')
    data=out/(label+'-readback-data');data.mkdir()
    target=data/'payload.bin';output=data/'stdout.log';errors=data/'stderr.log'
    # -q suppresses progress only; -Z selects uncompressed sync, including old adbd.
    command=[str(adb),'-s',serial,'pull','-q','-Z',path,str(target)]
    record={'command':command,'method':'adb_pull_sync_uncompressed','status':'BLOCKED',
            'expected_bytes':pin['jar_bytes'],'expected_sha256':pin['jar_sha256'],
            'stdin':'closed','server_environment':'owned_boot_context',
            'payload_retained':False,'returncode':None,'attempts':1,'timeout_seconds':timeout}
    start=time.monotonic()
    try:
        record['returncode']=capture_pull(command,target,output,errors,env,timeout=timeout)
        record.update(verify_pull_identity(target,output,errors,record['returncode'],pin))
        record['status']='PASS'
    except Exception as exc:
        record['failure']=type(exc).__name__+': '+str(exc)
        raise
    finally:
        try:
            for name,file,limit in [('payload',target,MAX_JAR_BYTES),
                                     ('stdout',output,MAX_STDERR_BYTES),('stderr',errors,MAX_STDERR_BYTES)]:
                record[name+'_retention']=retain_bounded(file,limit,out)
            if record['status']=='PASS':
                require(record['payload_retention']['retained_sha256']==pin['jar_sha256'],
                        'Readback payload changed after verification')
                target.unlink()
                record['payload_retention']['removed_matching_duplicate']=True
            else:
                record['payload_retained']=record['payload_retention']['exists']
        except Exception as exc:
            record['status']='BLOCKED';record['retention_failure']=type(exc).__name__+': '+str(exc)
            record['payload_retained']=target.is_file() and not target.is_symlink()
            raise
        finally:
            record['seconds']=round(time.monotonic()-start,3)
            with record_path.open('x',encoding='utf8') as stream:
                json.dump(record,stream,indent=2);stream.write('\n')
    return record


def verified_bundle(bundle, manifest_sha, lock, env):
    expected_names = {'artifact-manifest.json', 'canonical-artifact-manifest.json',
                      'identity-driver.jar', 'baseline-art-probe.jar', 'candidate-art-probe.jar'}
    require(bundle.is_dir() and not bundle.is_symlink() and
            {p.name for p in bundle.iterdir()} == expected_names, 'Producer artifact members differ')
    for p in bundle.iterdir():
        require(p.is_file() and not p.is_symlink(), 'Artifact member is redirected')
    manifest = bundle / 'artifact-manifest.json'
    require(re.fullmatch(r'[0-9a-f]{64}', manifest_sha) and manifest.stat().st_size <= 256 * 1024 and
            digest(manifest) == manifest_sha, 'Current producer manifest differs')
    row = json.loads(manifest.read_bytes())
    values = {'schema': 'WAEX_ART_PROFILE_RECOVERY_BUILD_V1', 'status': 'PASS_DRIVER_BUILD_CANONICAL_REUSE',
              'workflow_commit': env['GITHUB_SHA'], 'run_id': env['GITHUB_RUN_ID'], 'attempt': env['GITHUB_RUN_ATTEMPT'],
              'lock_sha256': digest(HERE / 'lock.json'), 'canonical_rebuilt': False,
              'historical_host_tests_repeated': False, 'art_executed': False, 'current_workload_tests_executed': 0,
              'current_build_scope': 'IDENTITY_DRIVER_ONLY_WITH_UNCHANGED_HISTORICAL_WORKLOAD_JARS', 'sdk_changed': False}
    for key, value in values.items():
        require(type(row.get(key)) is type(value) and row[key] == value, 'Current producer field differs: ' + key)
    require(row.get('source_sha256') == lock['source_sha256'] and
            row.get('inherited_source_sha256') == lock['inherited_source_sha256'] and
            row.get('canonical_producer') == CANONICAL and
            row.get('sdk_metadata') == lock['build_sdk_metadata_sha256'], 'Producer source/SDK/provenance pins differ')
    require(set(row.get('tools', {})) == set(lock['build_tool_sha256']), 'Producer build tool coverage differs')
    for name, expected_sha in lock['build_tool_sha256'].items():
        observed = row['tools'][name]
        require(observed.get('sha256') == expected_sha and type(observed.get('bytes')) is int and
                observed['bytes'] > 0 and type(observed.get('path')) is str,
                'Producer build tool identity differs: ' + name)
    historical = bundle / 'canonical-artifact-manifest.json'
    require(historical.stat().st_size == CANONICAL['manifest_bytes'] and
            digest(historical) == CANONICAL['manifest_sha256'], 'Copied historical manifest differs')
    for variant, pin in CANONICAL['variants'].items():
        jar = bundle / (variant + '-art-probe.jar')
        require(jar.stat().st_size == pin['jar_bytes'] and digest(jar) == pin['jar_sha256'],
                'Canonical JAR differs: ' + variant)
    driver = row.get('driver', {})
    require(set(driver) == {'jar_bytes', 'jar_sha256', 'dex_sha256', 'class_name', 'source_sha256', 'min_sdk'} and
            type(driver['jar_bytes']) is int and 0 < driver['jar_bytes'] <= 256 * 1024 and
            re.fullmatch(r'[0-9a-f]{64}', driver['jar_sha256']) and
            re.fullmatch(r'[0-9a-f]{64}', driver['dex_sha256']) and
            driver['class_name'] == 'org.lab.waex.qa.classmetadata.expansion.ExpansionMain' and
            driver['source_sha256'] == digest(HERE / 'ExpansionMain.java') and
            type(driver['min_sdk']) is int and driver['min_sdk'] == 25,
            'Current driver metadata is invalid')
    jar = bundle / 'identity-driver.jar'
    require(jar.stat().st_size == driver['jar_bytes'] and digest(jar) == driver['jar_sha256'],
            'Current driver JAR differs')
    with zipfile.ZipFile(jar) as archive:
        require(archive.namelist() == ['classes.dex'], 'Driver archive members differ')
        info = archive.infolist()[0]
        require(info.compress_type == zipfile.ZIP_STORED and 112 <= info.file_size <= 256 * 1024,
                'Driver DEX size/compression differs')
        body = archive.read(info)
    require(hashlib.sha256(body).hexdigest() == driver['dex_sha256'] and body[:4] == b'dex\n' and
            struct.unpack_from('<I', body, 96)[0] == 1 and
            b'Lorg/lab/waex/qa/classmetadata/expansion/ExpansionMain;' in body,
            'Current driver DEX differs')
    return row


def fresh_nonce(used, forbidden):
    for _ in range(8):
        value = secrets.token_hex(16)
        if value not in used and value not in forbidden:
            used.add(value)
            return value
    raise RuntimeError('Could not reserve a fresh invocation nonce')


def owned_readback(adb, serial, path, max_bytes, out, label, env, *, timeout=60):
    """Preserve bounded exact tree bytes for host hashing before any deletion."""
    require(serial == 'emulator-5580' and re.fullmatch(
        r'/data/local/tmp/waex-art-recovery-[a-f0-9]{32}/(?:ownership\.json|(?:driver|baseline|candidate)\.jar|oat/x86_64/(?:driver|baseline|candidate)\.(?:odex|vdex))', path),
        'Tree readback is outside explicit recovery paths')
    require(type(max_bytes) is int and 0 <= max_bytes <= OwnedTree.MAX_FILE
            and re.fullmatch(r'[a-z0-9-]+', label), 'Invalid bounded tree readback')
    data = out / (label + '-data'); data.mkdir()
    target, stdout, stderr = data / 'payload.bin', data / 'stdout.log', data / 'stderr.log'
    command = [str(adb), '-s', serial, 'pull', '-q', '-Z', path, str(target)]
    record = {'status': 'BLOCKED', 'command': command, 'bytes_bound': max_bytes,
              'method': 'owned_adb_pull_sync_uncompressed', 'attempts': 1, 'timeout_seconds': timeout}
    try:
        record['returncode'] = capture_pull(command, target, stdout, stderr, env, timeout=timeout, payload_limit=max_bytes)
        require(record['returncode'] == 0 and stdout.stat().st_size == 0 and stderr.stat().st_size == 0,
                'Tree readback failed or emitted diagnostics')
        require(target.is_file() and not target.is_symlink() and target.stat().st_size == max_bytes,
                'Tree file readback differs from its observed size')
        raw = target.read_bytes()
        record.update(status='PASS', bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                      preserved_payload=target.relative_to(out).as_posix())
        return raw
    except Exception as error:
        record['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        for name, path, limit in (('payload', target, max_bytes),
                                  ('stdout', stdout, MAX_STDERR_BYTES), ('stderr', stderr, MAX_STDERR_BYTES)):
            record[name + '_retention'] = retain_bounded(path, limit, out)
        save(out, label + '-readback.json', record)


def art_action(bundle, manifest_sha, producer, admitted_lock):
    def execute(context):
        require(context.serial == 'emulator-5580' and context.target in TARGETS and
                context.guest['abi'] == 'x86_64' and context.api == TARGETS[context.target][0] and
                context.minor == minor(context.target) and
                context.application_page_size_bytes == TARGETS[context.target][2], 'Unexpected owned BootContext')
        require(context_check(os.environ) == admitted_lock, 'Recovery admission changed before the phase')
        out, used = context.out, set()
        forbidden = consumed_nonces(admitted_lock)
        phase_nonce = fresh_nonce(used, forbidden)
        selected = RUNTIME_VARIANTS[context.target]
        directory = '/data/local/tmp/waex-art-recovery-' + phase_nonce
        historical = prior_evidence()
        preserved = []
        if context.target == 'api35-16k':
            previous = historical['api35-16k-baseline-validated.json']
            preserved.append({'variant': 'baseline', 'status': 'PRIOR_PASS_NOT_REEXECUTED',
                              'run_id': '45742530551', 'workflow_commit': '83012b298e555d8b3c87cbbec67e250582bfdb72',
                              'receipt_sha256': digest(HERE / 'prior-evidence/api35-16k-baseline-validated.json'),
                              'nonce': previous['identity']['nonce'], 'workload_checks': 13,
                              'identity_checks': 13, 'old_cleanup_failure_not_erased': True})
        phase = {'schema': 'WAEX_ART_PROFILE_RECOVERY_RUNTIME_V1', 'status': 'BLOCKED',
                 'target': context.target, 'phase_nonce': phase_nonce, 'canonical_producer': CANONICAL,
                 'current_producer_manifest_sha256': manifest_sha, 'requested_variants': list(selected),
                 'preserved_prior_workloads': preserved, 'variants': {}, 'jar_push_attempts': [],
                 'cleanup': {}, 'owned_directory_absent': False, 'canonical_workload_modified': False,
                 'apk_installed': False, 'x86_64_16k_simulation': context.application_page_size_bytes == 16384,
                 'real_arm64_16k_validated': False, 'identity_counts_are_separate': True,
                 'full_twenty_one_profile_closure_claimed': False,
                 'time_budget_seconds': {'work': WORK_SECONDS, 'total': PHASE_SECONDS,
                                         'cleanup_reserve': PHASE_SECONDS - WORK_SECONDS,
                                         'per_process': EXECUTION_SECONDS}}
        inputs = {'driver': {'source': bundle / 'identity-driver.jar', 'pin': producer['driver']},
                  **{v: {'source': bundle / (v + '-art-probe.jar'), 'pin': CANONICAL['variants'][v]} for v in selected}}
        boot_before, tree = None, None
        guest_execution_inflight = False
        tree_boot_sequence = 0
        started, cleaning = time.monotonic(), False

        def budget(maximum):
            remaining = (PHASE_SECONDS if cleaning else WORK_SECONDS) - (time.monotonic() - started)
            require(remaining > 0, 'Recovery phase time budget exhausted')
            return min(maximum, remaining)

        def adb(label, *args, timeout=30, required=True):
            return invoke(out, label, [str(context.adb), '-s', context.serial, *args],
                          context.env, timeout=budget(timeout), required=required)

        def boot(label):
            _, text = adb(label, 'shell', 'cat', '/proc/sys/kernel/random/boot_id')
            value = text.strip()
            require(re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', value),
                    'Invalid observed boot ID')
            return value

        def tree_boot():
            nonlocal tree_boot_sequence
            tree_boot_sequence += 1
            return boot('art-tree-boot-%03d' % tree_boot_sequence)

        def tree_command(label, script, timeout):
            _, output = adb('art-' + label, 'shell', script, timeout=timeout)
            return output

        def tree_file(label, path, max_bytes):
            return owned_readback(context.adb, context.serial, path, max_bytes,
                                  out, 'art-' + label, context.env, timeout=budget(60))

        try:
            save(out, 'art-recovery-phase.json', phase)
            for label, arguments, expected in (
                ('art-qemu', ('getprop', 'ro.kernel.qemu'), '1'),
                ('art-uid', ('id', '-u'), '2000'),
                ('art-abi', ('getprop', 'ro.product.cpu.abi'), 'x86_64'),
                ('art-api', ('getprop', 'ro.build.version.sdk'), str(context.api))):
                _, text = adb(label, 'shell', *arguments)
                require(text.strip() == expected, 'Fresh guest control differs: ' + label)
            boot_before = boot('art-boot-before')
            phase['boot_id_before'] = boot_before
            tree = OwnedTree(command=tree_command, read_file=tree_file, read_boot=tree_boot,
                             nonce=phase_nonce, boot=boot_before, prefix='waex-art-recovery',
                             inputs={name + '.jar': {'bytes': row['pin']['jar_bytes'], 'sha256': row['pin']['jar_sha256']}
                                     for name, row in inputs.items()},
                             producer={'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
                                       'workflow_commit': os.environ['GITHUB_SHA'], 'manifest_sha256': manifest_sha,
                                       'target': context.target, 'requested_variants': list(selected)})
            require(tree.path == directory, 'Owned-tree path differs from identity driver')
            phase['created_tree'] = tree.create()
            for name, row in inputs.items():
                path = directory + '/' + name + '.jar'
                phase['jar_push_attempts'].append(name)
                save(out, 'art-recovery-phase.json', phase)
                adb('art-' + name + '-push', 'push', str(row['source']), path, timeout=60)
                jar_readback(context.adb, context.serial, path, row['pin'], out, 'art-' + name + '-pushed',
                             context.env, timeout=budget(60))
                adb('art-' + name + '-readonly', 'shell', 'chmod', '0444', path)
            phase['tree_before_execution'] = tree.inventory(require_inputs=True)
            for variant in selected:
                nonce = fresh_nonce(used, forbidden)
                invocation = {'nonce': nonce, 'status': 'CLAIMED_BEFORE_EXECUTION', 'attempts': 0}
                phase['variants'][variant] = invocation
                save(out, 'art-recovery-phase.json', phase)
                require(boot('art-' + variant + '-boot-before') == boot_before, 'Boot changed before workload')
                # This also refuses an unobserved descendant/type before starting another process.
                phase['tree_before_' + variant] = tree.inventory(require_inputs=True)
                for name in ('driver', variant):
                    jar_readback(context.adb, context.serial, directory + '/' + name + '.jar', inputs[name]['pin'],
                                 out, 'art-' + variant + '-' + name + '-exec', context.env, timeout=budget(60))
                expected = {'target': context.target, 'variant': variant, 'nonce': nonce, 'phase_nonce': phase_nonce,
                            'boot_id': boot_before, 'fingerprint': context.guest['fingerprint'],
                            'driver': producer['driver'], 'run_id': os.environ['GITHUB_RUN_ID'],
                            'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'workflow_commit': os.environ['GITHUB_SHA'],
                            'producer_manifest_sha256': manifest_sha}
                arguments = [nonce, variant, context.target, str(context.api), str(context.minor),
                             str(context.application_page_size_bytes), boot_before, expected['run_id'], expected['attempt'],
                             expected['workflow_commit'], manifest_sha, CANONICAL['manifest_sha256'],
                             directory + '/driver.jar', producer['driver']['jar_sha256'],
                             directory + '/' + variant + '.jar', CANONICAL['variants'][variant]['jar_sha256'],
                             base64.b64encode(context.guest['fingerprint'].encode('utf-8')).decode('ascii'), phase_nonce]
                command = 'CLASSPATH=' + shlex.quote(directory + '/driver.jar:' + directory + '/' + variant + '.jar')
                command += ' /system/bin/app_process64 /system/bin ' + producer['driver']['class_name']
                command += ' ' + ' '.join(shlex.quote(value) for value in arguments)
                require(budget(EXECUTION_SECONDS) >= EXECUTION_SECONDS,
                        'Insufficient work budget for one complete pending process')
                require(PHASE_SECONDS - (time.monotonic() - started) >=
                        EXECUTION_SECONDS + (PHASE_SECONDS - WORK_SECONDS),
                        'Exact-cleanup reserve is unavailable before launch')
                invocation.update(status='EXECUTION_ATTEMPTED', attempts=1, expected=expected)
                guest_execution_inflight = True
                save(out, 'art-recovery-phase.json', phase)
                command_result, _ = adb('art-' + variant + '-execute', 'shell', command,
                                        timeout=EXECUTION_SECONDS, required=False)
                require(command_result.get('returncode') == 0 and command_result.get('failure') is None,
                        'Guest process completion was not confirmed; exact cleanup is deferred to owned AVD reaping')
                guest_execution_inflight = False
                invocation['guest_process_completion_confirmed'] = True
                require(boot('art-' + variant + '-boot-after') == boot_before, 'Boot changed during workload')
                transcript = (out / ('art-' + variant + '-execute.log')).read_text(encoding='utf-8', errors='strict')
                result = validate_output(transcript, expected)
                save(out, 'art-' + variant + '-validated.json', result)
                invocation.update(status='PASS', workload_checks=result['workload_checks'], identity_checks=13,
                                  runtime_log_sha256=digest(out / ('art-' + variant + '-execute.log')),
                                  validated_sha256=digest(out / ('art-' + variant + '-validated.json')))
            phase['all_requested_workloads_returned_pass'] = True
        except Exception as error:
            phase['execution_error'] = type(error).__name__ + ': ' + str(error)
            raise
        finally:
            cleaning = True
            try:
                require(not guest_execution_inflight,
                        'Potentially active guest process: files retained, controller must reap its owned AVD')
                if boot_before is not None:
                    require(boot('art-boot-before-cleanup') == boot_before, 'Boot changed before cleanup')
                if tree is not None:
                    phase['cleanup'] = tree.clean()
                    phase['owned_directory_absent'] = phase['cleanup']['root_absent'] is True
                if boot_before is not None:
                    phase['boot_id_after'] = boot('art-boot-after-cleanup')
                    require(phase['boot_id_after'] == boot_before, 'Boot changed after cleanup')
                phase['status'] = ('PASS' if phase.get('all_requested_workloads_returned_pass') is True
                                   and phase['owned_directory_absent'] and 'execution_error' not in phase else 'BLOCKED')
            except Exception as error:
                phase['cleanup_error'] = type(error).__name__ + ': ' + str(error)
                phase['status'] = 'BLOCKED'
                raise
            finally:
                phase['tree_events'] = tree.events if tree is not None else []
                phase['guest_execution_inflight_or_ambiguous'] = guest_execution_inflight
                phase['nonce_claims'] = sorted(used)
                phase['nonce_reuse_allowed'] = False
                phase['seconds'] = round(time.monotonic() - started, 3)
                save(out, 'art-recovery-phase.json', phase)
        return phase
    return execute


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=TARGET_NAMES, required=True)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    lock = context_check(os.environ)
    producer = verified_bundle(args.artifact.resolve(), args.manifest_sha256, lock, os.environ)
    return boot_main(['--target', args.target, '--lock', str(ROOT / 'qa/android_emulator_lab_matrix_lock.json'),
                      '--out', str(args.out)], targets=TARGETS, read_lock=checked_matrix,
                     boot_action=art_action(args.artifact.resolve(), args.manifest_sha256, producer, lock),
                     phase='class_metadata_art_variant_recovery',
                     result_name='class-metadata-art-recovery-result.json',
                     limits='Only fifteen pending canonical processes in eight x86_64 profiles; prior nineteen processes are not repeated; '
                            'own process major/minor/ELF/pages and exact observed-tree cleanup. Four ps16k profiles are simulated. '
                            'No WAEX app, hook/account, physical ARM64 16 KiB or global Android compatibility claim.')


if __name__ == '__main__':
    raise SystemExit(main())
