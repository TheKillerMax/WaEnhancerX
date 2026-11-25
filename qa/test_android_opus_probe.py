#!/usr/bin/env python3
"""Host controls for the Opus parser/decoder; simulated logs are not Android evidence."""
import argparse
import base64
import copy
import ctypes
import importlib.util
import io
import json
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest

import validate_android_opus_probe as validator

NONCE = '0123456789abcdef0123456789abcdef'
LIBRARY = None
LIBRARY_SHA256 = None
POSITIVE_REPORTS = {}


def bit_crc(raw):
    """Separate slow bitwise implementation, not the validator's lookup table."""
    crc = 0
    for byte in raw:
        crc ^= byte << 24
        for _ in range(8):
            crc = ((crc << 1) ^ (0x04C11DB7 if crc & 0x80000000 else 0)) & 0xffffffff
    return crc


def checksum_page(raw):
    raw = bytearray(raw)
    raw[22:26] = b'\0' * 4
    struct.pack_into('<I', raw, 22, bit_crc(raw))
    return bytes(raw)


def page(sequence, flags, granule, packets=(), *, serial=0x13572468, lacing=None, body=None):
    if lacing is None:
        lacing = []
        for packet in packets:
            lacing.extend([255] * (len(packet) // 255) + [len(packet) % 255])
        body = b''.join(packets)
    if len(lacing) > 255 or sum(lacing) != len(body):
        raise RuntimeError('Test page construction outside bounds')
    header = b'OggS' + bytes([0, flags]) + struct.pack('<QIII', granule, serial, sequence, 0)
    return checksum_page(header + bytes([len(lacing)]) + bytes(lacing) + body)


def split_pages(raw):
    result = []
    offset = 0
    while offset < len(raw):
        segments = raw[offset + 26]
        end = offset + 27 + segments + sum(raw[offset + 27:offset + 27 + segments])
        result.append(raw[offset:end]); offset = end
    return result


def replace_page(raw, index, offset, value):
    pages = split_pages(raw)
    changed = bytearray(pages[index]); changed[offset:offset + len(value)] = value
    pages[index] = checksum_page(changed)
    return b''.join(pages)


def host_packets(name):
    """Encode the same PCM with public libopus API only, never the Android JNI wrapper."""
    checked = validator.PinnedOpus(LIBRARY, LIBRARY_SHA256)
    lib = checked.lib
    lib.opus_encoder_create.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
    lib.opus_encoder_create.restype = ctypes.c_void_p
    lib.opus_encoder_destroy.argtypes = [ctypes.c_void_p]
    lib.opus_encoder_destroy.restype = None
    lib.opus_encoder_ctl.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.opus_encoder_ctl.restype = ctypes.c_int
    lib.opus_encode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int16), ctypes.c_int,
                               ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int]
    lib.opus_encode.restype = ctypes.c_int
    spec = validator.CASE_SPECS[name]
    error = ctypes.c_int(-1)
    state = lib.opus_encoder_create(spec['rate'], 1, 2049, ctypes.byref(error))
    validator.require(bool(state) and error.value == 0, 'Host reference encoder create')
    packets = []
    try:
        validator.require(lib.opus_encoder_ctl(state, 4002, ctypes.c_int(32000)) == 0, 'Host reference bitrate')
        lookahead = ctypes.c_int(-1)
        validator.require(lib.opus_encoder_ctl(state, 4027, ctypes.byref(lookahead)) == 0,
                          'Host reference lookahead')
        pre_skip = lookahead.value * (48000 // spec['rate'])
        raw = validator.pcm_fixture(name)
        pcm = list(struct.unpack('<' + str(spec['samples']) + 'h', raw))
        total = ((len(pcm) + lookahead.value + spec['frame'] - 1) // spec['frame']) * spec['frame']
        pcm.extend([0] * (total - len(pcm)))
        for start in range(0, total, spec['frame']):
            if name == 'pcm48k' and start == 48000:
                validator.require(lib.opus_encoder_ctl(state, 4002, ctypes.c_int(64000)) == 0,
                                  'Host reference bitrate switch')
            frame = (ctypes.c_int16 * spec['frame'])(*pcm[start:start + spec['frame']])
            output = (ctypes.c_ubyte * 4096)()
            count = lib.opus_encode(state, frame, spec['frame'], output, len(output))
            validator.require(0 < count <= len(output), 'Host reference encoding')
            packets.append(bytes(output[:count]))
    finally:
        lib.opus_encoder_destroy(state)
    checked.verify_identity()
    return packets, pre_skip


def container(name, packets, pre_skip, *, vendor=b'WAEX host controls libopus 1.5.2', split_tags=False):
    spec = validator.CASE_SPECS[name]
    header = b'OpusHead' + struct.pack('<BBHIhB', 1, 1, pre_skip, spec['rate'], 0, 0)
    tags = b'OpusTags' + struct.pack('<I', len(vendor)) + vendor + struct.pack('<I', 0)
    pages = [page(0, 2, 0, [header])]
    if split_tags:
        pages.append(page(1, 0, 2**64 - 1, lacing=[255], body=tags[:255]))
        remainder = tags[255:]
        pages.append(page(2, 1, 0, [remainder]))
    else:
        pages.append(page(1, 0, 0, [tags]))
    completed = 0
    for start in range(0, len(packets), 10):
        group = packets[start:start + 10]
        completed += len(group) * 960
        final = start + len(group) == len(packets)
        granule = pre_skip + spec['decoded_samples'] if final else completed
        pages.append(page(len(pages), 4 if final else 0, granule, group))
    return b''.join(pages)


def transport(payloads, nonce=NONCE, pages=4096):
    receipt = {'schema': 'WAEX_ANDROID_OPUS_PROBE_V1', 'run_nonce': nonce,
               'package': validator.PACKAGE, 'status': 'PASS_ENCODE_ONLY',
               'native_sha256': validator.NATIVE_SHA256,
               'wrapper': 'io.element.android.opusencoder.OggOpusEncoder',
               'sdk': 35, 'release': '15', 'application_page_size_bytes': pages,
               'hardware': 'ranchu', 'supported_abis': ['x86_64'],
               'process_is_64bit': True, 'test_only': True, 'own_directory_absent': True,
               'debuggable': False, 'requested_permissions': [], 'uid': 10123, 'pid': 1234,
               'elapsed_ms': 1000, 'checks': 189, 'cases': []}
    chunks = []
    for name in validator.CASE_ORDER:
        spec = validator.CASE_SPECS[name]
        raw = payloads[name]
        count = (len(raw) + validator.CHUNK_BYTES - 1) // validator.CHUNK_BYTES
        receipt['cases'].append({'name': name, 'asset': spec['asset'], 'pcm_sha256': validator.PCM_SHA256[name],
            'input_rate': spec['rate'], 'input_samples': spec['samples'], 'frame_samples': spec['frame'],
            'init_rc': 0, 'release_attempts': 1, 'release_completed': 1,
            'encode_rc': [0] * (spec['samples'] // spec['frame']),
            'bitrate_events': copy.deepcopy(spec['bitrate_events']),
            'output_name': name + '-' + nonce + '.ogg', 'ogg_bytes': len(raw),
            'ogg_sha256': validator.digest(raw), 'chunk_count': count})
        for index in range(count):
            body = raw[index * validator.CHUNK_BYTES:(index + 1) * validator.CHUNK_BYTES]
            chunks.append({'schema': 'WAEX_OPUS_CHUNK_V1', 'run_nonce': nonce, 'name': name,
                           'index': index, 'total': count, 'bytes': len(body),
                           'sha256': validator.digest(body), 'data': base64.b64encode(body).decode()})
    return receipt, chunks


def log_bytes(receipt, chunks):
    lines = []
    for chunk in chunks:
        lines.extend(['INSTRUMENTATION_STATUS: waex_opus_chunk=' + json.dumps(chunk, separators=(',', ':')),
                      'INSTRUMENTATION_STATUS_CODE: 0'])
    lines.extend(['INSTRUMENTATION_RESULT: waex_opus_receipt=' + json.dumps(receipt, separators=(',', ':')),
                  'INSTRUMENTATION_CODE: -1'])
    return ('\n'.join(lines) + '\n').encode()


class OpusControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = {name: host_packets(name) for name in validator.CASE_ORDER}
        cls.payloads = {name: container(name, *cls.reference[name]) for name in validator.CASE_ORDER}
        cls.decoder = validator.PinnedOpus(LIBRARY, LIBRARY_SHA256)

    def reject_ogg(self, body, message):
        with self.assertRaisesRegex(validator.ProbeError, message):
            validator.parse_ogg(body, 'pcm48k')

    def reject_receipt(self, change, message):
        receipt, chunks = transport(self.payloads)
        change(receipt)
        with self.assertRaisesRegex(validator.ProbeError, message):
            validator.parse_instrumentation(log_bytes(receipt, chunks), NONCE, 35, 4096)

    def reject_chunks(self, change, message):
        receipt, chunks = transport(self.payloads)
        change(chunks)
        with self.assertRaisesRegex(validator.ProbeError, message):
            validator.parse_instrumentation(log_bytes(receipt, chunks), NONCE, 35, 4096)

    def test_complete_real_decode_two_profiles(self):
        for pages in (4096, 16384):
            receipt, chunks = transport(self.payloads, pages=pages)
            report, recovered = validator.validate_probe(log_bytes(receipt, chunks), NONCE, 35, pages,
                                                          LIBRARY, LIBRARY_SHA256)
            self.assertEqual(recovered, self.payloads)
            self.assertEqual(report['transport']['jni_calls'], 157)
            self.assertEqual(report['cases']['pcm48k']['decoded']['samples'], 96000)
            self.assertEqual(report['cases']['pcm16k']['decoded']['samples'], 48000)
            self.assertGreater(report['cases']['pcm48k']['decoded']['pre_skip_removed'], 0)
            self.assertGreater(report['cases']['pcm48k']['decoded']['end_trim_removed'], 0)
            POSITIVE_REPORTS[str(pages)] = report

    def test_pcm_assets_pins_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            records = validator.write_pcm_assets(folder)
            self.assertEqual([records[name]['bytes'] for name in validator.CASE_ORDER], [192000, 32000])
            with self.assertRaisesRegex(validator.ProbeError, 'already exists'):
                validator.write_pcm_assets(folder)

    def test_valid_continued_tags(self):
        body = container('pcm48k', *self.reference['pcm48k'], vendor=b'v' * 700, split_tags=True)
        parsed = validator.parse_ogg(body, 'pcm48k')
        self.assertEqual(parsed['tags']['vendor'], 'v' * 700)
        self.assertEqual(self.decoder.decode(parsed, 'pcm48k')['samples'], 96000)

    def test_transport_multiple_chunks(self):
        bodies = dict(self.payloads, pcm48k=b'x' * (validator.CHUNK_BYTES * 2 + 13))
        receipt, chunks = transport(bodies)
        _, recovered, metadata = validator.parse_instrumentation(log_bytes(receipt, chunks), NONCE, 35, 4096)
        self.assertEqual(recovered, bodies)
        self.assertGreaterEqual(metadata['chunk_count'], 4)

    def test_container_integrity_controls(self):
        raw = self.payloads['pcm48k']; pages = split_pages(raw)
        variants = {
            'crc': (raw[:-1] + bytes([raw[-1] ^ 1]), 'CRC'),
            'truncated_header': (b'OggS', 'Truncated'),
            'truncated_payload': (raw[:-1], 'Truncated'),
            'trailing_bytes': (raw + b'x', 'EOS'),
            'duplicate_page': (b''.join(pages[:3] + [pages[2]] + pages[3:]), 'sequence'),
            'missing_page': (b''.join(pages[:3] + pages[4:]), 'sequence'),
            'serial': (replace_page(raw, 2, 14, struct.pack('<I', 1)), 'serial'),
            'sequence': (replace_page(raw, 2, 18, struct.pack('<I', 8)), 'sequence'),
            'version': (replace_page(raw, 0, 4, b'\x01'), 'capture/version'),
            'capture': (replace_page(raw, 0, 0, b'Nope'), 'capture/version'),
            'reserved_flags': (replace_page(raw, 2, 5, b'\x08'), 'flags'),
            'missing_bos': (replace_page(raw, 0, 5, b'\x00'), 'BOS'),
            'later_bos': (replace_page(raw, 2, 5, b'\x02'), 'BOS'),
            'missing_eos': (replace_page(raw, -1, 5, b'\x00'), 'Missing EOS'),
            'early_eos': (replace_page(raw, 2, 5, b'\x04'), 'EOS'),
            'spurious_continuation': (replace_page(raw, 2, 5, b'\x01'), 'continuation'),
            'missing_granule': (replace_page(raw, 2, 6, struct.pack('<Q', 2**64 - 1)), 'Granule presence'),
            'wrong_duration': (replace_page(raw, -1, 6, struct.pack('<Q', 96000)), 'duration'),
            'oversize': (b'x' * (validator.MAX_OGG + 1), 'byte bound'),
        }
        for label, (body, message) in variants.items():
            with self.subTest(control=label): self.reject_ogg(body, message)

    def test_header_and_tag_controls(self):
        raw = self.payloads['pcm48k']
        for offset, data in ((8,b'\x02'), (9,b'\x02'), (12,struct.pack('<I',16000)),
                             (16,b'\x01\x00'), (18,b'\x01')):
            with self.subTest(header_offset=offset):
                self.reject_ogg(replace_page(raw, 0, 28 + offset, data), 'profile')
        self.reject_ogg(replace_page(raw, 1, 28 + 8, struct.pack('<I', 9000)), 'string bound')
        self.reject_ogg(replace_page(raw, 1, 28 + 12, b'\xff'), 'not UTF8')
        self.reject_ogg(replace_page(raw, 1, 6, struct.pack('<Q', 1)), 'Comment header')

    def test_headers_cannot_share_partial_next_packet(self):
        raw = self.payloads['pcm48k']; pages = split_pages(raw)
        header = validator.parse_ogg(raw, 'pcm48k')['packets'][0]
        illegal = page(0, 2, 0, lacing=[19,255], body=header + b'x' * 255)
        second = page(1, 1, 0, [b'x'])
        self.reject_ogg(illegal + second + b''.join(pages[2:]), 'Identification header')
        tags = validator.parse_ogg(raw, 'pcm48k')['packets'][1]
        illegal = page(1, 0, 0, lacing=[len(tags),255], body=tags + b'x' * 255)
        following = bytearray(pages[2]); following[5] |= 1
        self.reject_ogg(pages[0] + illegal + checksum_page(following) + b''.join(pages[3:]), 'Comment header')

    def test_packet_bound(self):
        pages = split_pages(self.payloads['pcm48k'])
        huge = page(2, 0, 2**64 - 1, lacing=[255] * 255, body=b'x' * 65025)
        end = page(3, 5, 96312, [b'x' * 513])
        self.reject_ogg(b''.join(pages[:2]) + huge + end, 'Packet bound')

    def test_granule_and_decode_controls(self):
        raw = self.payloads['pcm48k']
        broken = replace_page(raw, 2, 6, struct.pack('<Q', 9601))
        with self.assertRaisesRegex(validator.ProbeError, 'granule discontinuity'):
            self.decoder.decode(validator.parse_ogg(broken, 'pcm48k'), 'pcm48k')
        packets, skip = self.reference['pcm48k']
        excess = container('pcm48k', packets + [packets[-1]] * 2, skip)
        with self.assertRaisesRegex(validator.ProbeError, 'EOS trim'):
            self.decoder.decode(validator.parse_ogg(excess, 'pcm48k'), 'pcm48k')
        overskip = container('pcm48k', packets, skip + 960)
        with self.assertRaisesRegex(validator.ProbeError, 'EOS trim'):
            self.decoder.decode(validator.parse_ogg(overskip, 'pcm48k'), 'pcm48k')
        invalid = container('pcm48k', [b'\x03'] + packets[1:], skip)
        with self.assertRaisesRegex(validator.ProbeError, 'Invalid Opus packet duration'):
            self.decoder.decode(validator.parse_ogg(invalid, 'pcm48k'), 'pcm48k')

    def test_receipt_identity_controls(self):
        variants = {'run_nonce': 'f'*32, 'package': 'other', 'native_sha256': '0'*64,
                    'wrapper': 'other', 'sdk': 34, 'application_page_size_bytes': 16384,
                    'hardware': 'physical', 'supported_abis': ['arm64-v8a'], 'process_is_64bit': False,
                    'test_only': False, 'own_directory_absent': False, 'debuggable': True,
                    'requested_permissions': ['android.permission.RECORD_AUDIO'], 'uid': True,
                    'pid': 0, 'elapsed_ms': 120001, 'checks': 188, 'status': 'PASS'}
        for key, value in variants.items():
            with self.subTest(field=key):
                self.reject_receipt(lambda receipt: receipt.__setitem__(key, value), '.')

    def test_jni_receipt_controls(self):
        variants = {'init_rc': -1, 'release_attempts': 2, 'release_completed': 0,
                    'input_samples': 95999, 'frame_samples': 480, 'pcm_sha256': '0'*64,
                    'output_name': '../foreign.ogg', 'ogg_sha256': '0'*64, 'chunk_count': 0,
                    'release_failure': 'error', 'encode_rc': [0]*99,
                    'bitrate_events': [{'at_sample':0,'bps':32000,'rc':0}]}
        for key, value in variants.items():
            with self.subTest(field=key):
                self.reject_receipt(lambda receipt: receipt['cases'][0].__setitem__(key,value), '.')
        self.reject_receipt(lambda receipt: receipt['cases'][0]['encode_rc'].__setitem__(50, True), 'encode')
        self.reject_receipt(lambda receipt: receipt['cases'][0]['bitrate_events'][1].__setitem__('rc', -1), 'Bitrate')
        self.reject_receipt(lambda receipt: receipt['cases'].reverse(), 'order')

    def test_chunk_controls(self):
        variants = {'run_nonce':'f'*32, 'name':'other', 'index':1, 'total':True,
                    'bytes':0, 'sha256':'0'*64, 'data':'@invalid', 'schema':'other'}
        for key, value in variants.items():
            with self.subTest(field=key):
                self.reject_chunks(lambda chunks: chunks[0].__setitem__(key,value), '.')
        self.reject_chunks(lambda chunks: chunks.insert(1,copy.deepcopy(chunks[0])), 'repeated')
        self.reject_chunks(lambda chunks: chunks.pop(), 'Incomplete')
        self.reject_chunks(lambda chunks: chunks.reverse(), 'order|index|Incomplete')

    def test_protocol_envelope_controls(self):
        receipt, chunks = transport(self.payloads); raw = log_bytes(receipt, chunks)
        variants = [raw.replace(b'INSTRUMENTATION_CODE: -1', b'INSTRUMENTATION_CODE: 0'),
                    raw + b'INSTRUMENTATION_CODE: -1\n',
                    raw.replace(b'INSTRUMENTATION_STATUS_CODE: 0', b'INSTRUMENTATION_STATUS_CODE: 1',1),
                    raw + b'INSTRUMENTATION_RESULT: waex_opus_error=failed\n',
                    raw.replace(b'"schema":', b'"schema":"duplicate","schema":',1),
                    raw.replace(b'"uid":10123', b'"uid":NaN'),
                    raw + b'\xff', b'x'*(validator.MAX_LOG+1)]
        for index, body in enumerate(variants):
            with self.subTest(control=index):
                with self.assertRaises(validator.ProbeError):
                    validator.parse_instrumentation(body, NONCE, 35, 4096)

    def test_tone_oracles(self):
        original = list(struct.unpack('<96000h', validator.pcm_fixture('pcm48k')))
        self.assertEqual(len(validator.tone_measurements(original,'pcm48k')),2)
        variants = {'silence':[0]*96000, 'dc':[10000]*96000,
                    'wrong_frequency':original[48000:]*2,
                    'clipping':[32767 if sample >= 0 else -32768 for sample in original],
                    'short':original[:-1], 'weak':[int(sample/10) for sample in original]}
        for name, pcm in variants.items():
            with self.subTest(control=name):
                with self.assertRaises(validator.ProbeError): validator.tone_measurements(pcm,'pcm48k')

    def test_decoder_identity_rejected_before_load(self):
        with self.assertRaisesRegex(validator.ProbeError,'SHA256 differs before load'):
            validator.PinnedOpus(LIBRARY,'0'*64)
        with tempfile.TemporaryDirectory() as folder:
            alias = Path(folder)/'alias.so'; alias.symlink_to(Path(LIBRARY).resolve())
            with self.assertRaisesRegex(validator.ProbeError,'Regular bounded'):
                validator.PinnedOpus(alias,LIBRARY_SHA256)
        original = self.decoder.sha256
        try:
            self.decoder.sha256 = '0'*64
            with self.assertRaisesRegex(validator.ProbeError,'identity changed'):
                self.decoder.verify_identity()
        finally:
            self.decoder.sha256 = original

    def test_decoder_source_archive_guards(self):
        path = Path(__file__).parent/'android_opus_probe'/'prepare_decoder.py'
        spec = importlib.util.spec_from_file_location('decoder_prepare_controls',path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        for name, kind in [('opus-1.5.2/../../escape',tarfile.REGTYPE),
                           ('/opus-1.5.2/file',tarfile.REGTYPE),
                           ('opus-1.5.2/link',tarfile.SYMTYPE),
                           ('opus-1.5.2/hard',tarfile.LNKTYPE)]:
            with self.subTest(entry=name):
                output = io.BytesIO()
                with tarfile.open(fileobj=output,mode='w:gz') as archive:
                    entry = tarfile.TarInfo(name); entry.type=kind
                    entry.linkname='../../outside' if kind != tarfile.REGTYPE else ''
                    archive.addfile(entry,io.BytesIO())
                lock={'source_root':'opus-1.5.2','source_entries':1,'source_expanded_bytes':0}
                with self.assertRaisesRegex(RuntimeError,'Unsafe'):
                    module.safe_members(output.getvalue(),lock)


class CountingResult(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self.subtests=0
    def addSubTest(self,test,subtest,error):
        self.subtests += 1
        super().addSubTest(test,subtest,error)


def main():
    global LIBRARY, LIBRARY_SHA256
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--libopus',type=Path,required=True)
    parser.add_argument('--libopus-sha256',required=True)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args(); LIBRARY=args.libopus; LIBRARY_SHA256=args.libopus_sha256
    if args.out: args.out.mkdir(parents=True,exist_ok=False)
    result=unittest.TextTestRunner(verbosity=2,resultclass=CountingResult).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(OpusControls))
    report={'schema':'WAEX_OPUS_HOST_CONTROLS_V1','status':'PASS' if result.wasSuccessful() else 'FAIL',
            'tests':result.testsRun,'subtests':result.subtests,'failures':len(result.failures),
            'errors':len(result.errors),'libopus_sha256':LIBRARY_SHA256,
            'scope':'Host real libopus controls plus simulated instrumentation transport; no Android execution'}
    if args.out:
        (args.out/'host-controls.json').write_text(json.dumps(report,indent=2)+'\n')
        (args.out/'simulated-positive-reports.json').write_text(json.dumps({
            'warning':'Simulated Android receipts; these are host validator tests only',
            'profiles':POSITIVE_REPORTS},indent=2)+'\n')
    print(json.dumps(report))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':
    raise SystemExit(main())
