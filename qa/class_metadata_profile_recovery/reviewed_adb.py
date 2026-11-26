#!/usr/bin/env python3
"""Recover the reviewed Linux ADB bytes into an owned lab directory only."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import stat
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

URL = 'https://dl.google.com/android/repository/platform-tools_r37.0.1-linux.zip'
ARCHIVE_BYTES = 9054187
ARCHIVE_SHA256 = 'd230f13842f60f782a8645f9c813f8f845bf36089ea7289f28c48f17979313f1'
# The ADB pin is the original reviewed preflight pin, not a second accepted version.
MEMBERS = {
    'adb': (10642368, 'a902be8f45c6c62e76c9efaf6947a0fa747c9cabd89a2ac8e0d16ecb30b3ed01', 0o755),
    'lib64/libc++.so': (1533896, '6cb165d671ced6a719b153b72e5d1b0a9cfd488badccc92d0aee55eda294f8ff', 0o755),
    'NOTICE.txt': (1175837, 'c29da8f704720fa1d3d802b834b86d9c023f20ae2596a8f2a4e17ed5490b17ae', 0o644),
    'source.properties': (38, '2dccd788c0234d8cf7f7457377e57f57527a86a629c6ed54feb8af0f549dac38', 0o644),
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def verified_bytes(raw, size, digest, label):
    require(len(raw) == size, label + ' size differs')
    require(hashlib.sha256(raw).hexdigest() == digest, label + ' SHA256 differs')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('Pinned ADB URL redirected')


def download_archive():
    # The controller also enforces a 90-second whole-worker deadline and reaps it.
    request = Request(URL, headers={'User-Agent': 'WAEX-reviewed-ADB-lab/1'})
    with build_opener(NoRedirect()).open(request, timeout=20) as response:
        require(response.status == 200 and response.geturl() == URL, 'Unexpected ADB download origin/status')
        declared = response.headers.get('Content-Length')
        require(declared is None or declared == str(ARCHIVE_BYTES), 'ADB download Content-Length differs')
        raw = response.read(ARCHIVE_BYTES + 1)
    verified_bytes(raw, ARCHIVE_BYTES, ARCHIVE_SHA256, 'ADB archive')
    return raw


def installed_identity(destination):
    require(destination.is_dir() and not destination.is_symlink(), 'Owned ADB directory is invalid')
    result = {}
    for name, (size, digest, mode) in MEMBERS.items():
        path = destination / name
        require(path.is_file() and not path.is_symlink() and
                path.resolve().is_relative_to(destination.resolve()) and
                not any(parent.is_symlink() for parent in path.parents if parent != destination.parent),
                'Owned ADB member is missing or redirected: ' + name)
        require(path.stat().st_size == size, 'Owned ADB member size differs: ' + name)
        verified_bytes(path.read_bytes(), size, digest, name)
        require(stat.S_IMODE(path.stat().st_mode) == mode, 'Owned ADB member mode differs: ' + name)
        result[name] = {'bytes': size, 'sha256': digest, 'mode': oct(mode)}
    return result


def extract_archive(raw, destination):
    require(not destination.exists() and not destination.is_symlink(), 'Owned ADB destination already exists')
    verified_bytes(raw, ARCHIVE_BYTES, ARCHIVE_SHA256, 'ADB archive')
    payloads = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        for name, (size, digest, mode) in MEMBERS.items():
            member = 'platform-tools/' + name
            require(names.count(member) == 1, 'ADB archive member missing or duplicated: ' + name)
            info = archive.getinfo(member)
            require(info.file_size == size and stat.S_ISREG(info.external_attr >> 16) and
                    stat.S_IMODE(info.external_attr >> 16) == mode,
                    'ADB archive member size/type/mode differs: ' + name)
            payloads[name] = archive.read(info)
            verified_bytes(payloads[name], size, digest, name)
    # Paths come only from the fixed member map, never from arbitrary ZIP names.
    destination.mkdir()
    (destination / 'lib64').mkdir()
    for name, raw_member in payloads.items():
        path = destination / name
        with path.open('xb') as stream:
            stream.write(raw_member)
        path.chmod(MEMBERS[name][2])
    return installed_identity(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    # Import here: the extraction primitives can be checked without a Linux SDK.
    from class_metadata_profile_recovery.recovery_contract import context_check
    context_check(os.environ)
    report = {'schema_version': 1, 'status': 'BLOCKED', 'version': '37.0.1',
              'url': URL, 'archive_bytes': ARCHIVE_BYTES, 'archive_sha256': ARCHIVE_SHA256,
              'sdk_modified': False, 'adb_executed': False, 'destination': str(args.out)}
    try:
        require(not args.out.exists() and not args.out.is_symlink(), 'Owned ADB destination already exists')
        report['members'] = extract_archive(download_archive(), args.out)
        report['status'] = 'PASS'
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
