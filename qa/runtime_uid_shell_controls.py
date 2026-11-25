"""Execute emitted UID shell fragments with a pidof function and owned status files only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess


def run_shell_controls(out: Path, shell: str):
    proc = out / 'proc-fixture'
    proc.mkdir()
    cwd = out / 'glob-fixture'
    cwd.mkdir()
    (cwd / '123').write_text('controlled glob candidate', encoding='utf-8')
    function = '''pidof() {
 case "$1" in
  com.whatsapp) printf '%s' "$FAKE_TARGET_PIDS"; return "$FAKE_TARGET_CODE";;
  com.whatsapp.w4b) printf '%s' "$FAKE_BUSINESS_PIDS"; return "$FAKE_BUSINESS_CODE";;
  com.waenhancer) printf '%s' "$FAKE_MANAGER_PIDS"; return "$FAKE_MANAGER_CODE";;
  *) return 127;;
 esac
}
'''
    end = 'END|FIXTURE_UID_PROBE'
    cases = [
        ('primary-owned-and-foreign', 0, '123 456', 0, None, '123'),
        ('work-owned-and-foreign', 1000000, '123 456', 0, None, '123'),
        ('primary-no-target', 0, '', 1, None, ''),
        ('work-no-target', 1000000, '', 1, None, ''),
        ('duplicate-owned-pids', 0, '123 123', 0, None, '123 123'),
        ('multiline-pids', 0, '123\n456', 0, None, '123'),
        ('success-without-pids', 0, '', 0, None, None),
        ('absence-with-pids', 0, '123', 1, None, None),
        ('pidof-unavailable', 0, '', 127, None, None),
        ('invalid-pid-text', 0, 'abc', 0, None, None),
        ('nonpositive-pid', 0, '0', 0, None, None),
        ('negative-pid', 0, '-1', 0, None, None),
        ('pid-glob-not-expanded', 0, '*', 0, None, None),
        ('missing-status', 0, '789', 0, None, None),
        ('missing-uid-row', 0, '123', 0, 'Name:\tfixture\n', None),
        ('empty-uid-row', 0, '123', 0, 'Uid:\n', None),
        ('nonnumeric-uid', 0, '123', 0, 'Uid:\tx x x x\n', None),
        ('negative-uid', 0, '123', 0, 'Uid:\t-1 -1 -1 -1\n', None),
        ('extra-uid-field', 0, '123', 0, 'Uid:\t10200 10200 10200 10200 10200\n', None),
        ('missing-uid-field', 0, '123', 0, 'Uid:\t10200 10200 10200\n', None),
        ('real-uid-mismatch', 0, '123', 0, 'Uid:\t1 10200 10200 10200\n', None),
        ('effective-uid-mismatch', 0, '123', 0, 'Uid:\t10200 1 10200 10200\n', None),
        ('saved-uid-mismatch', 0, '123', 0, 'Uid:\t10200 10200 1 10200\n', None),
        ('filesystem-uid-mismatch', 0, '123', 0, 'Uid:\t10200 10200 10200 1\n', None),
    ]
    hashes = {}
    for name, profile, pids, code, status, expected in cases:
        command_path = out / ('command-work.sh' if profile else 'command.sh')
        original = command_path.read_text(encoding='utf-8')
        boundary = '"/proc/$pid/status"'
        substitute = '"$FIXTURE_PROC/$pid/status"'
        assert original.count(boundary) == 3, 'Production proc boundary changed'
        command = original.replace(boundary, substitute)
        assert command.replace(substitute, boundary) == original
        hashes[command_path.name] = hashlib.sha256(original.encode()).hexdigest()
        for pid, uid in ((123, profile + 10200), (456, 1010200 if not profile else 10200),
                         (1, profile + 10100)):
            path = proc / str(pid) / 'status'
            path.parent.mkdir(exist_ok=True)
            value = status if pid == 123 and status is not None else f'Name:\tfixture\nUid:\t{uid} {uid} {uid} {uid}\n'
            path.write_bytes(value.encode('utf-8'))
        env = os.environ | {
            'FIXTURE_PROC': proc.as_posix(), 'FAKE_TARGET_PIDS': pids,
            'FAKE_TARGET_CODE': str(code), 'FAKE_BUSINESS_PIDS': '',
            'FAKE_BUSINESS_CODE': '1', 'FAKE_MANAGER_PIDS': '1', 'FAKE_MANAGER_CODE': '0',
        }
        result = subprocess.run([shell, '-c', function + original.replace(boundary, substitute)
                                 + "\nprintf '" + end + "\\n'"],
                                cwd=cwd, env=env, text=True, capture_output=True, timeout=10)
        if expected is None:
            assert result.returncode != 0 and end not in result.stdout, (name, result)
        else:
            output = (f'PID|com.whatsapp|{profile + 10200}|{expected}\n'
                      f'PID|com.whatsapp.w4b|{profile + 10300}|\n'
                      f'PID|com.waenhancer|{profile + 10100}|1\n{end}\n')
            assert result.returncode == 0 and result.stdout == output, (name, result, output)
    print(f'PASS: {len(cases)} emitted UID shell controls; host={os.name}; shell={shell}')
    print('UID_SHELL_SOURCE_SHA256=' + json.dumps(hashes, sort_keys=True))
