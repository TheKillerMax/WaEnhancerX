#!/usr/bin/env python3
"""Build a self-contained ART pixel probe; never install, connect ADB or download.

Uses the existing public runner's renderer extraction and compile bindings. The
source fixture supplies the two pixel assertions and row geometry helpers.
Project Gradle, production files, dependency pins and CI defaults are untouched.
"""
import argparse
import ast
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import zipfile

HERE = Path(__file__).resolve().parent
PACKAGE = 'org.waex.qa.presence.host'
METHODS = ('nativeCanvasContainsGreenDotAndClearsOffline', 'invalidationClearsTheNativeGreenPixel')
JAVA_PRODUCTION = (
    'app/src/main/java/com/waenhancer/xposed/features/automation/PresenceStateStore.java',
    'app/src/main/java/com/waenhancer/xposed/utils/HostResourceIds.java',
    'app/src/main/java/com/waenhancer/utils/UiText.java',
    'app/src/main/java/com/waenhancer/utils/DisplayLocalePolicy.java',
)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8', newline='\n')

def assertions(body):
    return re.findall(r'assert(?:Equals|NotEquals)\([^\n]+', body)

def adapt_oracle(module, source, name):
    original = module.extract(source, 'fun ' + name + '(')
    body = original[original.index('{')+1:-1]
    stages = [x.strip().strip(';').strip() for x in body.split('pump()')]
    if len(stages) != 3 or body.count('val r = row()') != 1:
        raise ValueError('Pixel fixture staging changed: '+name)
    stages[0] = stages[0].replace('val r = row()', 'r = row(); attach(r)')
    required = ('val (x, y) = centerInRow(r, dot(r))',
                'val bitmap = Bitmap.createBitmap(400, 80, Bitmap.Config.ARGB_8888)')
    if any(stages[1].count(x) != 1 for x in required):
        raise ValueError('Pixel fixture coordinates/bitmap changed: '+name)
    stages[1] = stages[1].replace(required[0],
        'val center = centerInRow(r, dot(r)); x = center.first; y = center.second')
    stages[1] = stages[1].replace(required[1],
        'bitmap = Bitmap.createBitmap(400, 80, Bitmap.Config.ARGB_8888)')
    for i, phase in ((1,'online'),(2,'offline' if name==METHODS[0] else 'invalidated')):
        marker='r.draw(Canvas(bitmap));'
        if stages[i].count(marker)!=1:
            raise ValueError('Expected one unchanged row draw per phase: '+name)
        stages[i]=stages[i].replace(marker, marker+f' capture(bitmap, "{phase}", x, y);')
    adapted='private fun '+name+'() {\n'+'\n        pump()\n'.join(
        '        onMain {\n            '+stage.replace('\n','\n            ')+'\n        }'
        for stage in stages)+'\n    }'
    if assertions(original) != assertions(adapted):
        raise ValueError('Pixel assertion text changed: '+name)
    if len(assertions(original)) != 2:
        raise ValueError('Expected two original pixel assertions: '+name)
    return original, adapted

def compile_bindings(runner_text):
    values=[]
    for node in ast.walk(ast.parse(runner_text)):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='write_text' and node.args:
            value=node.args[0]
            if isinstance(value,ast.Constant) and isinstance(value.value,str):values.append(value.value)
    prefixes={'androidx/annotation/NonNull.java':'package androidx.annotation; public @interface NonNull',
              'com/waenhancer/app/R.java':'package com.waenhancer.app; public final class R'}
    result={}
    for name,prefix in prefixes.items():
        found=[x for x in values if x.startswith(prefix)]
        if len(found)!=1:raise ValueError('Expected one existing compile binding: '+name)
        result[name]=found[0]
    return result

def validate_producer(value):
    if (set(value) != {'workflow_commit', 'run_id', 'attempt'}
            or not re.fullmatch(r'[a-f0-9]{40}', value['workflow_commit'])
            or not re.fullmatch(r'[1-9][0-9]*', value['run_id']) or value['attempt'] != '1'):
        raise RuntimeError('Exact new producer commit/run/first attempt required')
    return value


def generate(root,out,variant,reference,producer):
    validate_producer(producer)
    runner=root/'qa/android_presence_row_test.py'
    fixture=root/'qa/fixtures/PresenceRowRenderingTest.kt'
    spec=importlib.util.spec_from_file_location('existing_presence_runner',runner)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    renderer=root/module.RENDERER
    source=renderer.read_text(encoding='utf-8')
    harness=module.harness(source)
    if reference and reference.read_text(encoding='utf-8')!=harness:
        raise ValueError('Extracted harness differs from the already executed Robolectric harness')
    reference_hash=sha(harness.encode())
    if variant!='positive':
        mutations={
            'wrong-dot-color':('setColor(Color.rgb(37, 211, 102))','setColor(Color.rgb(211, 37, 102))'),
            'keep-dot-visible':('dot?.visibility = if (isOnline) View.VISIBLE else View.GONE','dot?.visibility = View.VISIBLE'),
        }
        old,new=mutations[variant]
        if harness.count(old)!=1:raise ValueError('Ambiguous causal mutation: '+variant)
        harness=harness.replace(old,new)
    write(out/'generated/RendererHarness.kt',harness)
    fixture_text=fixture.read_text(encoding='utf-8')
    helper_markers=('row','resize','layoutHost','centerInRow','dot')
    helpers=[module.extract(fixture_text,'private fun '+name+'(') for name in helper_markers]
    dp=[line.strip() for line in fixture_text.splitlines() if line.strip().startswith('private fun px(')]
    if len(dp)!=1:raise ValueError('Expected the unchanged density helper')
    helpers.insert(0,dp[0])
    original_methods=[];adapted_methods=[];oracles=[]
    for name in METHODS:
        original,adapted=adapt_oracle(module,fixture_text,name)
        original_methods.append(original);adapted_methods.append(adapted)
        oracles.append({'name':name,'original_sha256':sha(original.encode()),
            'adapted_sha256':sha(adapted.encode()),'assertions':assertions(original),
            'assertion_text_preserved':True})
    template=(HERE/'PresenceInstrumentation.kt.in').read_text(encoding='utf-8')
    for token,value in [('__ORIGINAL_HELPERS__','\n\n'.join(helpers)),('__ART_ORACLES__','\n\n'.join(adapted_methods))]:
        if template.count(token)!=1:raise ValueError('Template token changed: '+token)
        template=template.replace(token,value)
    for token,value in [('__PRODUCER_COMMIT__',producer['workflow_commit']),
                        ('__PRODUCER_RUN_ID__',producer['run_id']),('__PRODUCER_ATTEMPT__',producer['attempt'])]:
        if template.count(token)!=1:raise ValueError('Producer template token changed: '+token)
        template=template.replace(token,value)
    template=template.replace('.put("cases", results).put("scope",',
                              '.put("candidate_variant", "'+variant+'").put("cases", results).put("scope",')
    write(out/'generated/PresenceInstrumentation.kt',template)
    write(out/'original-pixel-oracles.kt','\n\n'.join(original_methods)+'\n')
    bindings=compile_bindings(runner.read_text(encoding='utf-8'))
    for name,value in bindings.items():write(out/'generated'/name,value)
    sources=[runner,fixture,renderer,*[root/x for x in JAVA_PRODUCTION]]
    inputs={str(p.relative_to(root)).replace('\\','/'):{'raw_sha256':sha(p.read_bytes()),
            'lf_sha256':sha(p.read_bytes().replace(b'\r\n',b'\n'))} for p in sources}
    extracted={name:sha(module.extract(source,'private fun '+name+'(').encode()) for name in module.RENDER_METHODS}
    return {'producer_identity':producer,'inputs':inputs,'oracles':oracles,'renderer_method_sha256':extracted,
            'positive_extracted_harness_sha256':reference_hash,
            'compiled_harness_sha256':sha(harness.encode()),
            'reference_harness_compared':str(reference) if reference else None,
            'compile_bindings':{name:sha(value.encode()) for name,value in bindings.items()},
            'variant':variant,'scope':'Methods/fields/companion copied by the unchanged public renderer extractor; four complete production Java classes; original pixel expectations unchanged. Discovery/Xposed installation remains outside this test.'}

def argfile(path,values):
    def token(value):
        s=str(value).replace('\\','/')
        return '"'+s.replace('"','\\"')+'"'
    write(path,'\n'.join(token(x) for x in values)+'\n')

def compiler_contract():
    """Reuse the reviewed ClassValue recipe without selecting a runner Kotlin installation."""
    root = HERE.parents[2]
    lock = json.loads((HERE.parent / 'lock.json').read_bytes())
    pins = lock['toolchain_source_sha256']
    expected = {'qa/class_metadata_art_probe/toolchain.py',
                'qa/class_metadata_art_probe/toolchain-lock.json'}
    if set(pins) != expected:
        raise RuntimeError('Unexpected compiler recipe source closure')
    for relative, expected_sha in pins.items():
        path = root / relative
        if path.is_symlink() or not path.is_file() or sha(path.read_bytes()) != expected_sha:
            raise RuntimeError('Compiler recipe source changed: ' + relative)
    path = root / 'qa/class_metadata_art_probe/toolchain.py'
    spec = importlib.util.spec_from_file_location('presence_reviewed_kotlin_toolchain', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, module.checked_lock()


def verify_compiler_home(home, recipe):
    lib = Path(home) / 'lib'
    rows = recipe['artifacts']
    if not lib.is_dir() or {p.name for p in lib.iterdir()} != {row['file'] for row in rows}:
        raise RuntimeError('Compiler home must contain exactly the nine pinned JARs')
    identities = {}
    for row in rows:
        path = lib / row['file']
        if path.is_symlink() or not path.is_file() or path.stat().st_size != row['bytes']:
            raise RuntimeError('Compiler JAR size/type differs: ' + row['file'])
        actual = sha(path.read_bytes())
        if actual != row['sha256']:
            raise RuntimeError('Compiler JAR hash differs: ' + row['file'])
        identities[row['file']] = {'bytes': path.stat().st_size, 'sha256': actual}
    return identities


def compiler_command(java, home, recipe):
    return [str(java), '-XX:ActiveProcessorCount=2', '-Xmx512M', '-Xms128M', '--add-opens=java.base/java.util=ALL-UNNAMED',
            '-Dkotlin.home=' + str(home), '-cp',
            os.pathsep.join(str(Path(home) / 'lib' / row['file']) for row in recipe['artifacts']),
            'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler', '-kotlin-home', str(home)]


def clean_java_environment(java_home, option_names):
    env = dict(os.environ)
    removed = [name for name in option_names if name in env]
    for name in option_names:
        env.pop(name, None)
    env['JAVA_HOME'] = str(java_home)
    env['PATH'] = str(Path(java_home) / 'bin') + os.pathsep + env.get('PATH', '')
    return env, removed


def java_properties(text):
    return dict(re.findall(r'^[ \t]*(java\.[a-z.]+) = ([^\r\n]+)\r?$', text, re.M))


def require_quiet_d8(out):
    streams = {}
    for stream in ('stdout', 'stderr'):
        path = out / ('d8.' + stream + '.log')
        raw = path.read_bytes()
        streams[stream] = {'file': path.name, 'bytes': len(raw), 'sha256': sha(raw)}
    if any(row['bytes'] for row in streams.values()):
        raise RuntimeError('D8 must have empty stdout and stderr; retained diagnostics are not filtered')
    return streams


def run_build_command(out, commands, name, command, env, timeout=120):
    start = time.monotonic()
    command = list(map(str, command))
    timeout_error = None
    code = None
    with (out / (name + '.stdout.log')).open('wb') as stdout, (out / (name + '.stderr.log')).open('wb') as stderr:
        try:
            process = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                     env=env, timeout=timeout)
            code = process.returncode
        except subprocess.TimeoutExpired as error:
            timeout_error = error
    receipt = {'name': name, 'command': command, 'exit_code': code,
               'seconds': round(time.monotonic() - start, 3), 'stdin': 'closed',
               'failure': 'deadline exceeded' if timeout_error else None}
    for stream in ('stdout', 'stderr'):
        raw = (out / (name + '.' + stream + '.log')).read_bytes()
        receipt[stream] = {'bytes': len(raw), 'sha256': sha(raw)}
    commands.append(receipt)
    write(out / 'commands.json', json.dumps(commands, indent=2) + '\n')
    print(name + ' exit=' + str(code), flush=True)
    if timeout_error:
        raise timeout_error
    if code != 0:
        raise RuntimeError(name + ' failed; see retained stdout/stderr logs')
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--sdk',type=Path,required=True)
    p.add_argument('--java-home',type=Path,required=True)
    p.add_argument('--kotlin-home',type=Path,required=True)
    p.add_argument('--deps',type=Path,required=True,help='Read-only existing junit-4.13.2.jar and hamcrest-core-1.3.jar directory')
    p.add_argument('--reference-harness',type=Path)
    p.add_argument('--variant',choices=('positive','wrong-dot-color','keep-dot-visible'),default='positive')
    p.add_argument('--generate-only',action='store_true')
    p.add_argument('--producer-commit',required=True)
    p.add_argument('--producer-run-id',required=True)
    p.add_argument('--producer-attempt',required=True)
    a=p.parse_args()
    root=a.source_root.resolve();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    if shutil.disk_usage(out).free<20*1024**3:raise RuntimeError('Preserve at least 20 GiB of free disk')
    producer={'workflow_commit':a.producer_commit,'run_id':a.producer_run_id,'attempt':a.producer_attempt}
    report=generate(root,out,a.variant,a.reference_harness,producer)
    report.update(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        package=PACKAGE,min_sdk=24,target_sdk=28,expected_tests=4,
        candidate_files={str(x.relative_to(HERE)).replace('\\','/'):sha(x.read_bytes()) for x in HERE.rglob('*') if x.is_file() and '__pycache__' not in str(x)})
    write(out/'source-manifest.json',json.dumps(report,indent=2)+'\n')
    if a.generate_only:
        print(json.dumps({'generated':str(out),'source_contracts':'PASS','installed':False}));return
    recipe_module, recipe = compiler_contract()
    compiler_files = verify_compiler_home(a.kotlin_home, recipe)
    suffix='.exe' if os.name=='nt' else ''
    java=a.java_home/'bin'/('java'+suffix);javac=a.java_home/'bin'/('javac'+suffix)
    jar=a.java_home/'bin'/('jar'+suffix);keytool=a.java_home/'bin'/('keytool'+suffix)
    bt=a.sdk/'build-tools/36.0.0';android=a.sdk/'platforms/android-36/android.jar'
    kotlin_stdlib=a.kotlin_home/'lib/kotlin-stdlib.jar'
    jars=[kotlin_stdlib,a.deps/'junit-4.13.2.jar',a.deps/'hamcrest-core-1.3.jar']
    required=[java,javac,jar,keytool,bt/('aapt2'+suffix),bt/('zipalign'+suffix),bt/'lib/d8.jar',bt/'lib/apksigner.jar',android,*jars]
    if any(not x.is_file() for x in required):raise RuntimeError('Missing offline build input: '+str([str(x) for x in required if not x.is_file()]))
    report['build_input_sha256']={str(x):sha(x.read_bytes()) for x in required}
    env, cleared_options = clean_java_environment(a.java_home.resolve(), recipe_module.JAVA_ENV_OPTIONS)
    commands=[]
    def run(name,cmd,timeout=120):
        return run_build_command(out, commands, name, cmd, env, timeout)
    run('java-version', [java, '-XX:ActiveProcessorCount=2', '-XshowSettings:properties', '-version'])
    java_text = ((out / 'java-version.stdout.log').read_bytes() + (out / 'java-version.stderr.log').read_bytes()).decode('utf-8')
    properties = java_properties(java_text)
    if properties.get('java.specification.version') != '21' or Path(properties.get('java.home', '')).resolve() != a.java_home.resolve():
        raise RuntimeError('Offline builder must use the selected JDK21')
    run('javac-version', [javac, '-J-XX:ActiveProcessorCount=2', '-version'])
    javac_version = ((out / 'javac-version.stdout.log').read_bytes() + (out / 'javac-version.stderr.log').read_bytes()).decode('utf-8').strip()
    if not re.fullmatch(r'javac 21(?:\.[^\s]+)?', javac_version):
        raise RuntimeError('Offline builder javac must be version21')
    kotlin_command = compiler_command(java, a.kotlin_home, recipe)
    run('kotlin-version', kotlin_command + ['-version'])
    kotlin_version = ((out / 'kotlin-version.stdout.log').read_bytes() + (out / 'kotlin-version.stderr.log').read_bytes()).decode('utf-8').strip()
    if not re.fullmatch(r'info: kotlinc-jvm 2\.0\.20 \(JRE 21(?:[.+][^)]*)?\)', kotlin_version):
        raise RuntimeError('Offline Kotlin compiler or JRE version differs')
    report['compiler'] = {'recipe_sha256': recipe_module.digest(recipe_module.LOCK),
                          'helper_sha256': recipe_module.digest(Path(recipe_module.__file__)),
                          'kotlin_version': kotlin_version, 'javac_version': javac_version,
                          'java_home': str(a.java_home.resolve()), 'java_properties': properties,
                          'files': compiler_files, 'cleared_environment_names': cleared_options,
                          'command_prefix': kotlin_command}
    classes=out/'classes';classes.mkdir();dex=out/'dex';dex.mkdir()
    run('aapt2-compile',[bt/('aapt2'+suffix),'compile','--dir',HERE/'res','-o',out/'resources.zip'])
    unsigned=out/'resources.apk'
    run('aapt2-link',[bt/('aapt2'+suffix),'link','--manifest',HERE/'AndroidManifest.xml','-I',android,'-o',unsigned,out/'resources.zip'])
    java_sources=[root/x for x in JAVA_PRODUCTION]+list((out/'generated').rglob('*.java'))+[HERE/'PresenceActivity.java']
    argfile(out/'javac.args',['--release','17','-encoding','UTF-8','-classpath',android,'-d',classes,*java_sources])
    run('javac',[javac,'-J-XX:ActiveProcessorCount=2','@'+str(out/'javac.args')])
    argfile(out/'kotlinc.args',[out/'generated/RendererHarness.kt',out/'generated/PresenceInstrumentation.kt',
        '-jvm-target','17','-no-stdlib','-no-reflect','-classpath',os.pathsep.join(map(str,[android,classes,*jars])),'-d',classes])
    run('kotlinc',kotlin_command + ['@'+str(out/'kotlinc.args')])
    run('jar',[jar,'-J-XX:ActiveProcessorCount=2','--create','--file',out/'app-classes.jar','-C',classes,'.'])
    run('d8',[java,'-XX:ActiveProcessorCount=2','-cp',bt/'lib/d8.jar','com.android.tools.r8.D8','--min-api','24','--lib',android,'--output',dex,out/'app-classes.jar',*jars])
    report['d8_diagnostics'] = require_quiet_d8(out)
    unaligned=out/'unaligned.apk';shutil.copyfile(unsigned,unaligned)
    with zipfile.ZipFile(unaligned,'a',compression=zipfile.ZIP_DEFLATED) as z:
        dexes=sorted(dex.glob('classes*.dex'))
        if not dexes:raise RuntimeError('D8 emitted no dex files')
        for f in dexes:z.write(f,f.name)
    run('zipalign',[bt/('zipalign'+suffix),'-f','4',unaligned,out/'aligned.apk'])
    apk=out/('presence-art-'+a.variant+'.apk')
    key=out/'qa-only.jks'
    try:
        run('qa-only-key',[keytool,'-J-XX:ActiveProcessorCount=2','-genkeypair','-noprompt','-keystore',key,'-storetype','JKS',
            '-storepass','android','-keypass','android','-alias','androiddebugkey','-dname','CN=WAEX Public QA,O=Android,C=US',
            '-keyalg','RSA','-keysize','2048','-validity','3650'])
        run('sign',[java,'-XX:ActiveProcessorCount=2','-jar',bt/'lib/apksigner.jar','sign','--ks',key,'--ks-key-alias','androiddebugkey',
            '--ks-pass','pass:android','--key-pass','pass:android','--out',apk,out/'aligned.apk'])
    finally:
        key.unlink(missing_ok=True)
    run('verify',[java,'-XX:ActiveProcessorCount=2','-jar',bt/'lib/apksigner.jar','verify','--verbose','--print-certs',apk])
    run('badging',[bt/('aapt2'+suffix),'dump','badging',apk])
    after={path:sha((root/path).read_bytes()) for path in report['inputs']}
    report['source_changes']=[path for path in report['inputs'] if report['inputs'][path]['raw_sha256']!=after[path]]
    if report['source_changes']:raise RuntimeError('Inputs changed during APK build')
    if report['build_input_sha256'] != {str(path):sha(path.read_bytes()) for path in required}:
        raise RuntimeError('Offline build tools or dependency inputs changed during build')
    if verify_compiler_home(a.kotlin_home, recipe) != compiler_files:
        raise RuntimeError('Compiler inputs changed during build')
    after_module, after_recipe = compiler_contract()
    if after_recipe != recipe or after_module.digest(Path(after_module.__file__)) != report['compiler']['helper_sha256']:
        raise RuntimeError('Compiler recipe changed during build')
    report.update(build_status='PASS',installed=False,art_execution='NOT_RUN',qa_signing_key_retained=key.exists(),apk=str(apk),apk_bytes=apk.stat().st_size,
                  apk_sha256=sha(apk.read_bytes()),commands=commands,free_bytes_after=shutil.disk_usage(out).free)
    write(out/'build-result.json',json.dumps(report,indent=2)+'\n')
    print(json.dumps({'build':'PASS','apk':str(apk),'bytes':apk.stat().st_size,'sha256':report['apk_sha256'],'installed':False,'art_execution':'NOT_RUN'},indent=2))

if __name__=='__main__':main()
