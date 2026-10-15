#!/usr/bin/env python3
"""Staging-only V18 runner: preserve the reviewed payload and explicitly apply one QA-only follow-up.

The first validation correctly rejected the broken denial mutant with JUnit
ComparisonFailure, but its result classifier accepted only AssertionError.
No production source or business assertion is changed by this follow-up.
"""
from pathlib import Path
import hashlib
import os
import subprocess

source_path = Path('qa/v18_prepare.py')
assert subprocess.check_output(['git', 'hash-object', str(source_path)], text=True).strip() == '06dafb447d46a7ab2a4d29a954240247bdef991d'
source = source_path.read_text()
followup = Path('qa/v18-assertion-detector.patch').read_text()
assert hashlib.sha256(followup.encode()).hexdigest() == '06c14864acc6a50e312bcc4707e3e447f021fe56c34dd31e4892ea21d03b59b5'

# Positive comparison assertions are failures of tested behavior, not compilation
# errors. Wrong test counts, initialization failures and surviving mutants remain errors.
def recognized(log):
    return (any(kind in log for kind in ('java.lang.AssertionError', 'org.junit.ComparisonFailure'))
            and 'Tests run: 25,' in log and 'initializationError' not in log)
controls = [
    ('java.lang.AssertionError\nTests run: 25, Failures: 1', True),
    ('org.junit.ComparisonFailure\nTests run: 25, Failures: 3', True),
    ('java.lang.AssertionError\nTests run: 0, Failures: 1', False),
    ('java.lang.NoClassDefFoundError\nTests run: 25, Failures: 25', False),
    ('java.lang.AssertionError\ninitializationError\nTests run: 25, Failures: 1', False),
    ('compilation error', False),
    ('OK (25 tests)', False),
]
for log, expected in controls:
    assert recognized(log) == expected

# Preserve the original compressed-payload hash gate. Verify and replace only
# the expected digest of the one changed test-infrastructure file.
replacements = [
    ('payload=json.loads(raw)\n', '''payload=json.loads(raw)
assert payload['files_sha256']['qa/mutate_presence_rows.py'] == '2221042c9e0f91f48f59fb8135a3fbc559220a930277979c5cff2ad9d41382c3'
payload['files_sha256']['qa/mutate_presence_rows.py'] = '3f0cbef34eb3e081a197062f84265cc09aa1d9f36738389237d4c4fcbd583749'
followup = (ROOT/'qa/v18-assertion-detector.patch').read_text()
assert hashlib.sha256(followup.encode()).hexdigest() == '06c14864acc6a50e312bcc4707e3e447f021fe56c34dd31e4892ea21d03b59b5'
(OUT/'assertion-detector.patch').write_text(followup)
'''),
    ("presence=checkout('presence',PINS['presence'][1]);apply(presence,payload['patches']['presence'])\n",
     "presence=checkout('presence',PINS['presence'][1]);apply(presence,payload['patches']['presence']);apply(presence,followup)\n"),
    (" apply(combined,payload['patches'][name])\n",
     " apply(combined,payload['patches'][name])\n if name == 'presence': apply(combined,followup)\n"),
]
for before, after in replacements:
    assert source.count(before) == 1, before
    source = source.replace(before, after, 1)

out = Path(os.environ['RUNNER_TEMP'])/'waex-v18-evidence'
out.mkdir(parents=True, exist_ok=True)
(out/'executed-prepare.py').write_text(source)
(out/'assertion-classifier-controls.log').write_text('PASS: 7 classifier controls; business assertions retained, wrong counts and infrastructure failures rejected.\n')
print('PASS: pinned QA-only result-classifier follow-up and seven controls', flush=True)
exec(compile(source, str(source_path), 'exec'), {'__name__':'__main__', '__file__':str(source_path)})
