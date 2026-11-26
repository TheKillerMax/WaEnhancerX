#!/usr/bin/env python3
"""Resolve the installed Kotlin CLI once and record the distribution actually used.

Framework regression fixtures use the compiler distribution's stdlib/coroutines;
this receipt does not claim equivalence with the application's Gradle dependency graph.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--export-env',type=Path,required=True)
    args=parser.parse_args()
    compiler=shutil.which('kotlinc')
    if not compiler:raise RuntimeError('A complete Kotlin compiler distribution is required')
    compiler=Path(compiler).resolve();home=compiler.parents[1]
    if not (home/'bin/kotlinc').is_file():raise RuntimeError('Resolved compiler distribution lacks bin/kotlinc')
    files=[compiler,home/'lib/kotlin-compiler.jar',home/'lib/kotlin-stdlib.jar',
           home/'lib/kotlinx-coroutines-core-jvm.jar']
    for file in files:
        if not file.is_file():raise RuntimeError('Missing required compiler distribution file: '+str(file))
    if '\n' in str(home) or '\r' in str(home):raise ValueError('Unsupported newline in compiler path')
    if args.report.exists() or args.report.is_symlink():raise ValueError('Use a new toolchain receipt path')
    if args.export_env.is_symlink() or (args.export_env.exists() and not args.export_env.is_file()):
        raise ValueError('Expected a regular environment export file')
    versions={}
    environment=dict(os.environ,KOTLIN_HOME=str(home))
    for label,command in [('kotlin',[str(compiler),'-version']),('java',['java','-version']),('javac',['javac','-version'])]:
        result=subprocess.run(command,capture_output=True,text=True,timeout=30,env=environment)
        if result.returncode:raise RuntimeError(label+' version check failed: '+result.stdout+result.stderr)
        versions[label]=(result.stdout+result.stderr).strip()
    record={'schema':1,'accepted':True,'kotlin_home':str(home),'compiler':str(compiler),
            'versions':versions,'files_sha256':{str(path):digest(path) for path in files},
            'application_gradle_toolchain_equivalence_claimed':False,
            'ci':{key:os.environ.get(key) for key in ('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_SHA')}}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    with args.report.open('x',encoding='utf-8') as stream:json.dump(record,stream,indent=2);stream.write('\n')
    args.export_env.parent.mkdir(parents=True,exist_ok=True)
    with args.export_env.open('a',encoding='utf-8') as stream:stream.write('KOTLIN_HOME='+str(home)+'\n')
    print(json.dumps(record))


if __name__=='__main__':main()
