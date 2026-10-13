#!/usr/bin/env python3
"""Compile a production IPC policy and check its fail-closed provider integration.

JDK tests only; does not establish Android Binder/runtime authorization.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
PROVIDER=ROOT/'app/src/main/java/com/waenhancer/xposed/bridge/HookProvider.java'
POLICY=ROOT/'app/src/main/java/com/waenhancer/xposed/bridge/ProviderDerivedKeyPolicy.java'
TEST=ROOT/'qa/java/TestProviderDerivedKeyPolicy.java'
source=PROVIDER.read_text(encoding='utf-8')
assert 'ProviderDerivedKeyPolicy.allowsGenericWrite(key)' in source
assert source.index('ProviderDerivedKeyPolicy.allowsGenericWrite(key)') < source.index('SharedPreferences.Editor editor = prefs.edit()',source.index('private Bundle applyPreferenceChanges('))
assert 'callerOwnsPackage(context, callerUid, pkg)' in source
assert source.index('isTrustedCaller(context, callerUid)') < source.index('Binder.clearCallingIdentity()')
with tempfile.TemporaryDirectory(prefix='waex_provider_policy_') as temp:
    subprocess.run(['javac','--release','17','-d',temp,str(POLICY),str(TEST)],check=True)
    subprocess.run(['java','-cp',temp,'com.waenhancer.xposed.bridge.TestProviderDerivedKeyPolicy'],check=True)
