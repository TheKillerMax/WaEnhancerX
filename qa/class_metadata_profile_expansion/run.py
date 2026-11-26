#!/usr/bin/env python3
"""Consume one current driver producer and run only the seventeen pending ART cells."""
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
from expansion_contract import (CANONICAL, MATRIX_SHA, ROOT, TARGETS, TARGET_NAMES, VARIANTS,
                                context_check, digest, minor, require)
from validate_expansion import validate_output
from expansion_pilot import main as boot_main, invoke, save

MAX_JAR_BYTES = 8 * 1024 ** 2
MAX_STDERR_BYTES = 65536
CONSUMED_NONCES = {
    '0a3bd30603d4905b684119820dcd0ea3', '2608ac25fe42cfffe8b6b49d9f4b3f9c',
    '70e24cf0783a030b998e889e8b3ee59e', 'eea754cbd049bd9653a8f30c226fd741',
    '32b459cfc083a4cb9068f714c7cff49d', 'b0a8704d2663b3ad04e752542f36ad51',
    'fb90547c97957f64315b7f356f3a755c',
    '8e3a9daf4ae606f4a4ba2d32fcc7c6bc',
}

def capture_pull(command,target,output,errors,env,timeout=60):
    """Use ADB sync framing, with bounded files, closed stdin and the owned server."""
    require(not target.exists() and not target.is_symlink(),'Readback payload already exists')
    start=time.monotonic();process=None
    def bounded():
        for path,limit in ((target,MAX_JAR_BYTES),(output,MAX_STDERR_BYTES),(errors,MAX_STDERR_BYTES)):
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

def jar_readback(adb,serial,path,pin,out,label,env):
    """Fresh full sync read before execution/removal; failed bytes remain evidence."""
    require(serial=='emulator-5580' and re.fullmatch(
        r'/data/local/tmp/waex-art-expansion-[a-f0-9]{32}/(?:driver|baseline|candidate)\.jar',path),
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
            'payload_retained':False,'returncode':None,'attempts':1}
    start=time.monotonic()
    try:
        record['returncode']=capture_pull(command,target,output,errors,env)
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
    values = {'schema': 'WAEX_ART_PROFILE_EXPANSION_BUILD_V1', 'status': 'PASS_DRIVER_BUILD_CANONICAL_REUSE',
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


def checked_matrix(path, target):
    # This calls the qualified checker without altering any constants or source bytes.
    from android_emulator_lab_matrix import checked_lock
    require(path.resolve() == (ROOT / 'qa/android_emulator_lab_matrix_lock.json').resolve() and
            digest(path) == MATRIX_SHA and target in TARGETS, 'Matrix path or target outside reviewed admission')
    value, entry = checked_lock(path, target)
    api, image_path, pages = TARGETS[target]
    require((entry['image']['path'], entry['image']['api'], entry['image']['minor'],
             entry['application_page_size_bytes']) == (image_path, api, minor(target), pages),
            'Selected expansion image differs from the historical matrix')
    return value, entry


def fresh_nonce(used):
    for _ in range(8):
        value = secrets.token_hex(16)
        if value not in used and value not in CONSUMED_NONCES:
            used.add(value)
            return value
    raise RuntimeError('Could not reserve a fresh invocation nonce')


def art_action(bundle, manifest_sha, producer):
    def execute(context):
        require(context.serial == 'emulator-5580' and context.target in TARGETS and
                context.guest['abi'] == 'x86_64' and context.api == TARGETS[context.target][0] and
                context.minor == minor(context.target) and
                context.application_page_size_bytes == TARGETS[context.target][2], 'Unexpected owned BootContext')
        out, used = context.out, set()
        phase_nonce = fresh_nonce(used)
        directory = '/data/local/tmp/waex-art-expansion-' + phase_nonce
        phase = {'schema': 'WAEX_ART_PROFILE_EXPANSION_RUNTIME_V1', 'status': 'BLOCKED',
                 'target': context.target, 'phase_nonce': phase_nonce, 'canonical_producer': CANONICAL,
                 'current_producer_manifest_sha256': manifest_sha, 'variants': {},
                 'jar_push_attempts': [], 'cleanup': {}, 'owned_directory_absent': False,
                 'canonical_workload_modified': False, 'apk_installed': False,
                 'x86_64_16k_simulation': context.application_page_size_bytes == 16384,
                 'real_arm64_16k_validated': False, 'identity_counts_are_separate': True}
        inputs = {'driver': {'source': bundle / 'identity-driver.jar', 'pin': producer['driver']},
                  **{v: {'source': bundle / (v + '-art-probe.jar'), 'pin': CANONICAL['variants'][v]} for v in VARIANTS}}
        mkdir_attempted = False
        boot_before = None

        def adb(label, *args, timeout=30, required=True):
            return invoke(out, label, [str(context.adb), '-s', context.serial, *args],
                          context.env, timeout=timeout, required=required)

        def shell(label, command, **kwargs):
            return adb(label, 'shell', command, **kwargs)

        def boot(label):
            _, text = adb(label, 'shell', 'cat', '/proc/sys/kernel/random/boot_id')
            value = text.strip()
            require(re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', value),
                    'Invalid observed boot ID')
            return value

        def presence(label, path):
            require(re.fullmatch(r'/data/local/tmp/waex-art-expansion-[0-9a-f]{32}(?:/(?:driver|baseline|candidate)\.jar)?', path),
                    'Presence query outside owned paths')
            quoted = shlex.quote(path)
            _, text = shell(label, 'if [ -L ' + quoted + ' ]; then echo REDIRECTED; elif [ -f ' + quoted +
                            ' ]; then echo FILE; elif [ -d ' + quoted + ' ]; then echo DIRECTORY; elif [ -e ' + quoted +
                            ' ]; then echo OTHER; else echo ABSENT; fi')
            require(text.strip() in ('ABSENT', 'FILE', 'DIRECTORY', 'REDIRECTED', 'OTHER'), 'Unrecognized path state')
            return text.strip()

        try:
            context_check(os.environ)
            for label, arguments, expected in (
                ('art-qemu', ('getprop', 'ro.kernel.qemu'), '1'),
                ('art-uid', ('id', '-u'), '2000'),
                ('art-abi', ('getprop', 'ro.product.cpu.abi'), 'x86_64'),
                ('art-api', ('getprop', 'ro.build.version.sdk'), str(context.api))):
                _, text = adb(label, 'shell', *arguments)
                require(text.strip() == expected, 'Fresh guest control differs: ' + label)
            boot_before = boot('art-boot-before')
            phase['boot_id_before'] = boot_before
            require(presence('art-directory-before', directory) == 'ABSENT', 'Invocation directory already exists')
            mkdir_attempted = True
            adb('art-directory-create', 'shell', 'mkdir', '--', directory)
            require(presence('art-directory-created', directory) == 'DIRECTORY', 'Owned directory creation ambiguous')
            for name, row in inputs.items():
                path = directory + '/' + name + '.jar'
                require(presence('art-' + name + '-before', path) == 'ABSENT', 'Probe input already exists')
                phase['jar_push_attempts'].append(name)
                save(out, 'art-expansion-phase.json', phase)
                adb('art-' + name + '-push', 'push', str(row['source']), path, timeout=60)
                jar_readback(context.adb, context.serial, path, row['pin'], out, 'art-' + name + '-pushed', context.env)
                adb('art-' + name + '-readonly', 'shell', 'chmod', '0444', path)
            for variant in VARIANTS:
                nonce = fresh_nonce(used)
                invocation = {'nonce': nonce, 'status': 'CLAIMED_BEFORE_EXECUTION', 'attempts': 0}
                phase['variants'][variant] = invocation
                save(out, 'art-expansion-phase.json', phase)
                require(boot('art-' + variant + '-boot-before') == boot_before, 'Boot changed before workload')
                for name in ('driver', variant):
                    path = directory + '/' + name + '.jar'
                    require(presence('art-' + variant + '-' + name + '-before-exec', path) == 'FILE',
                            'Execution input is not a regular owned file')
                    jar_readback(context.adb, context.serial, path, inputs[name]['pin'], out,
                                 'art-' + variant + '-' + name + '-exec', context.env)
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
                invocation.update(status='EXECUTION_ATTEMPTED', attempts=1, expected=expected)
                save(out, 'art-expansion-phase.json', phase)
                adb('art-' + variant + '-execute', 'shell', command, timeout=90)
                require(boot('art-' + variant + '-boot-after') == boot_before, 'Boot changed during workload')
                transcript = (out / ('art-' + variant + '-execute.log')).read_text(encoding='utf-8', errors='strict')
                result = validate_output(transcript, expected)
                save(out, 'art-' + variant + '-validated.json', result)
                invocation.update(status='PASS', workload_checks=result['workload_checks'], identity_checks=13,
                                  runtime_log_sha256=digest(out / ('art-' + variant + '-execute.log')),
                                  validated_sha256=digest(out / ('art-' + variant + '-validated.json')))
            phase['both_workloads_returned_pass'] = True
        except Exception as error:
            phase['execution_error'] = type(error).__name__ + ': ' + str(error)
            raise
        finally:
            try:
                if boot_before is not None:
                    require(boot('art-boot-before-cleanup') == boot_before, 'Boot changed before cleanup')
                for name in reversed(phase['jar_push_attempts']):
                    path = directory + '/' + name + '.jar'
                    state = presence('art-' + name + '-before-cleanup', path)
                    require(state in ('ABSENT', 'FILE'), 'Cleanup refuses a redirected or unexpected input')
                    if state == 'FILE':
                        jar_readback(context.adb, context.serial, path, inputs[name]['pin'], out,
                                     'art-' + name + '-cleanup', context.env)
                        adb('art-' + name + '-remove', 'shell', 'rm', '--', path)
                    require(presence('art-' + name + '-after-cleanup', path) == 'ABSENT', 'Owned input remains')
                    phase['cleanup'][name] = {'absent': True, 'identity_verified_before_removal': state == 'FILE'}
                if mkdir_attempted:
                    state = presence('art-directory-before-cleanup', directory)
                    require(state in ('ABSENT', 'DIRECTORY'), 'Cleanup refuses a redirected directory')
                    if state == 'DIRECTORY':
                        adb('art-directory-remove', 'shell', 'rmdir', '--', directory)
                    require(presence('art-directory-after-cleanup', directory) == 'ABSENT', 'Owned directory remains')
                    phase['owned_directory_absent'] = True
                if boot_before is not None:
                    phase['boot_id_after'] = boot('art-boot-after-cleanup')
                    require(phase['boot_id_after'] == boot_before, 'Boot changed after cleanup')
                phase['status'] = ('PASS' if phase.get('both_workloads_returned_pass') is True and
                                   phase['owned_directory_absent'] and len(phase['cleanup']) == 3 and
                                   'execution_error' not in phase else 'BLOCKED')
            except Exception as error:
                phase['cleanup_error'] = type(error).__name__ + ': ' + str(error)
                phase['status'] = 'BLOCKED'
                raise
            finally:
                phase['nonce_claims'] = sorted(used)
                phase['nonce_reuse_allowed'] = False
                save(out, 'art-expansion-phase.json', phase)
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
                     boot_action=art_action(args.artifact.resolve(), args.manifest_sha256, producer),
                     phase='class_metadata_art_pending_profile_expansion',
                     result_name='class-metadata-art-expansion-result.json',
                     limits='Historical workload JARs on seventeen previously untested x86_64 ART profiles; '
                            'own process major/minor/ELF/pages and cleanup. Six ps16k profiles are simulated. '
                            'No WAEX app, hook/account, physical ARM64 16 KiB or global Android compatibility claim.')


if __name__ == '__main__':
    raise SystemExit(main())
