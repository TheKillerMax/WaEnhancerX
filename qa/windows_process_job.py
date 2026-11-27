"""Bound the descendants of an explicitly requested Windows QA process.

The Python bootstrap waits for its argument payload until the parent assigns
it to a kill-on-close Windows Job Object. Failed assignment never starts Maven.
No system-wide taskkill, PID enumeration, elevation or network is used here.
"""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


class BasicLimits(ctypes.Structure):
    _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong),
                ('PerJobUserTimeLimit', ctypes.c_longlong),
                ('LimitFlags', wintypes.DWORD),
                ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t),
                ('ActiveProcessLimit', wintypes.DWORD),
                ('Affinity', ctypes.c_size_t),
                ('PriorityClass', wintypes.DWORD),
                ('SchedulingClass', wintypes.DWORD)]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        'ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
        'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [('BasicLimitInformation', BasicLimits), ('IoInfo', IoCounters),
                ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]


# Only this bootstrap executes until the job is established. Closing stdin
# without a complete JSON object does not start the requested command.
WORKER = r"""
import json, pathlib, subprocess, sys
payload = json.loads(sys.stdin.buffer.read())
try:
    rc = subprocess.call(payload['argv'], stdin=subprocess.DEVNULL)
except OSError as exc:
    pathlib.Path(payload['error']).write_text(str(exc), encoding='utf-8')
    print(str(exc), file=sys.stderr, flush=True)
    raise SystemExit(126)
raise SystemExit(rc)
"""


class WindowsProcessJob:
    def __init__(self):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel = kernel
        for name, args, result in (
            ('CreateJobObjectW', [wintypes.LPVOID, wintypes.LPCWSTR], wintypes.HANDLE),
            ('SetInformationJobObject', [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD], wintypes.BOOL),
            ('AssignProcessToJobObject', [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            ('OpenProcess', [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            ('CloseHandle', [wintypes.HANDLE], wintypes.BOOL),
        ):
            call = getattr(kernel, name)
            call.argtypes, call.restype = args, result
        self.handle = kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.process = None
        self.assigned = False
        self.temp = None
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            kernel.CloseHandle(self.handle)
            self.handle = None
            raise error

    def start(self, argv, output):
        executable = shutil.which(argv[0])
        if executable is None:
            raise FileNotFoundError('Maven launcher not found: ' + argv[0])
        # Windows may invoke batch files through cmd.exe even with shell=False.
        # Refuse shell syntax in batch launcher arguments instead of interpreting it.
        command = [executable, *argv[1:]]
        if Path(executable).suffix.lower() in ('.cmd', '.bat') and any(
                any(c in value for c in '&|<>^%\"\r\n!') for value in command):
            raise ValueError('Unsafe batch launcher argument')
        self.temp = tempfile.TemporaryDirectory(prefix='waex-maven-start-')
        self.error_path = Path(self.temp.name) / 'error.txt'
        self.process = subprocess.Popen([sys.executable, '-I', '-B', '-c', WORKER],
                                        stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT)
        target = self.kernel.OpenProcess(0x0100 | 0x0001, False, self.process.pid)
        if not target:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.kernel.AssignProcessToJobObject(self.handle, target):
                raise ctypes.WinError(ctypes.get_last_error())
            self.assigned = True
        finally:
            self.kernel.CloseHandle(target)
        payload = json.dumps({'argv': command, 'error': str(self.error_path)}).encode('utf-8')
        self.process.stdin.write(payload)
        self.process.stdin.close()
        return self.process

    def start_error(self):
        return self.error_path.read_text(encoding='utf-8') if self.error_path.is_file() else None

    def close(self):
        # On assignment failure, only the gated bootstrap could exist. Close
        # it without releasing the gate. Once assigned, the job owns all children.
        if self.process is not None and not self.assigned and self.process.poll() is None:
            self.process.kill()
        if self.handle is not None:
            handle, self.handle = self.handle, None
            if not self.kernel.CloseHandle(handle):
                raise ctypes.WinError(ctypes.get_last_error())
        if self.process is not None:
            if self.process.stdin is not None and not self.process.stdin.closed:
                self.process.stdin.close()
            self.process.wait(timeout=1)
        if self.temp is not None:
            self.temp.cleanup()
            self.temp = None
