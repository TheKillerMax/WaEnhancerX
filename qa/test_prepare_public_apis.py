#!/usr/bin/env python3
"""Check Core-archive and direct-JAR acquisition boundaries using synthetic bytes.

These loopback fixtures are not the real dependencies. Pinned real API compilation
remains a separate consumer; acquisition controls never substitute for its cases.
"""
import argparse
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
import unittest
from unittest import mock

import prepare_public_apis as bootstrap
from test_prepare_dexkit import Handler, archive, digest

OUT = None
BODY = b'synthetic public API classes\n'


class PublicApiPreparationControls(unittest.TestCase):
    def setUp(self):
        self.work = OUT / self._testMethodName; self.work.mkdir()
        self.cache, self.report = self.work/'cache', self.work/'receipt.json'
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.requests, self.server.responses, self.server.slow = [], [], False
        self.server.body = archive([('classes.jar', BODY)])
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()
        url = f'http://127.0.0.1:{self.server.server_port}/'
        self.configs = {
            'core': {'cache': 'fixture-core', 'source': {'name': 'core.aar', 'bytes': len(self.server.body),
                'sha256': digest(self.server.body), 'url': url+'core.aar'},
                'jar': {'name': 'core.jar', 'bytes': len(BODY), 'sha256': digest(BODY)}, 'member': 'classes.jar'},
            'okhttp': {'cache': 'fixture-http', 'source': {'name': 'http.jar', 'bytes': len(BODY),
                'sha256': digest(BODY), 'url': url+'http.jar'}},
        }
        for patch in (mock.patch.object(bootstrap, 'CONFIGS', self.configs),
                      mock.patch.object(bootstrap.transport, 'load_lock', side_effect=AssertionError('No framework graph')),
                      mock.patch.object(bootstrap.transport, 'prepare', side_effect=AssertionError('No SDK preparation'))):
            patch.start(); self.addCleanup(patch.stop)

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=1)
        (self.work/'http-requests.json').write_text(json.dumps(self.server.requests, indent=2)+'\n')

    def prepare(self, artifact='core', **kwargs):
        return bootstrap.prepare(artifact, self.cache, self.report, timeout=10, **kwargs)

    def receipt(self):
        return json.loads(self.report.read_bytes())

    def assert_no_output(self, artifact='core'):
        config=self.configs[artifact];target=config.get('jar',config['source'])
        self.assertFalse((self.cache/target['name']).exists())
        self.assertEqual([],list(self.cache.glob('.sdk-download-*')))
        self.assertFalse(self.receipt()['accepted'])
        self.assertEqual(0,self.receipt()['consumer_invocations'])

    def test_core_archive_extracts_exact_member_then_offline_cache_uses_no_transport(self):
        first=self.prepare()
        self.assertTrue(first['accepted']);self.assertEqual(1,first['network_requests'])
        self.assertEqual(BODY,(self.cache/'core.jar').read_bytes())
        self.report=self.work/'offline.json';second=self.prepare(offline=True)
        self.assertTrue(second['accepted']);self.assertEqual(0,second['network_requests'])
        self.assertFalse(second['framework_graph_resolved']);self.assertEqual(0,second['consumer_invocations'])
        self.assertEqual(1,len(self.server.requests))

    def test_direct_jar_download_and_offline_cache_do_not_extract_an_archive(self):
        self.server.body=BODY
        first=self.prepare('okhttp')
        self.assertTrue(first['accepted']);self.assertEqual(1,len(first['files']))
        self.assertEqual(BODY,(self.cache/'http.jar').read_bytes())
        self.report=self.work/'offline.json';second=self.prepare('okhttp',offline=True)
        self.assertTrue(second['accepted']);self.assertEqual(0,second['network_requests'])
        self.assertEqual(1,len(self.server.requests))

    def test_direct_jar_rate_limit_retries_transport_and_keeps_exact_pin(self):
        self.server.body=BODY;self.server.responses=[(429,{'Retry-After':'0'},b'rate limited')]
        result=self.prepare('okhttp')
        self.assertTrue(result['accepted']);self.assertEqual(2,result['network_requests'])
        self.assertEqual([429,200],[x['http_status'] for x in result['files'][0]['attempts']])
        self.assertEqual(BODY,(self.cache/'http.jar').read_bytes())
        self.assertEqual(0,result['consumer_invocations'])

    def test_corrupt_cached_archive_is_not_ignored_when_jar_is_valid(self):
        self.cache.mkdir();(self.cache/'core.aar').write_bytes(b'bad cached bytes');(self.cache/'core.jar').write_bytes(BODY)
        with self.assertRaisesRegex(ValueError,'identity mismatch'):self.prepare()
        self.assertEqual(b'bad cached bytes',(self.cache/'core.aar').read_bytes())
        self.assertEqual(BODY,(self.cache/'core.jar').read_bytes())
        self.assertEqual(0,self.receipt()['network_requests']);self.assertEqual([],self.server.requests)

    def test_invalid_core_members_never_publish_a_jar(self):
        for index,members in enumerate([[('wrong.jar',BODY)],[('classes.jar',BODY),('classes.jar',BODY)],
                                        [('classes.jar',BODY+b'oversize')],[('classes.jar',b'X'*len(BODY))]]):
            with self.subTest(index=index):
                self.cache,self.report=self.work/str(index),self.work/(str(index)+'.json');self.cache.mkdir()
                payload=archive(members);self.configs['core']['source'].update(bytes=len(payload),sha256=digest(payload))
                (self.cache/'core.aar').write_bytes(payload)
                with self.assertRaises(ValueError):self.prepare(offline=True)
                self.assert_no_output();self.assertEqual(0,self.receipt()['network_requests'])

    def test_nontransient_or_corrupt_direct_download_is_never_retried(self):
        for index,(code,payload) in enumerate([(404,b'missing'),(200,b'X'*len(BODY)),(200,BODY+b'oversize')]):
            with self.subTest(code=code,bytes=len(payload)):
                self.cache,self.report=self.work/str(index),self.work/(str(index)+'.json')
                self.server.responses=[(code,{},payload)]
                with self.assertRaises((RuntimeError,ValueError)):self.prepare('okhttp')
                self.assert_no_output('okhttp');self.assertEqual(1,self.receipt()['network_requests'])
        self.assertEqual(3,len(self.server.requests))

    def test_offline_missing_or_mixed_cache_fails_before_network(self):
        with self.assertRaisesRegex(ValueError,'missing in offline mode'):self.prepare('okhttp',offline=True)
        self.assert_no_output('okhttp')
        self.report=self.work/'mixed.json';(self.cache/'other.jar').write_bytes(b'foreign')
        with self.assertRaisesRegex(ValueError,'Unexpected files'):self.prepare('okhttp')
        self.assertEqual(b'foreign',(self.cache/'other.jar').read_bytes());self.assertEqual([],self.server.requests)

    def test_existing_evidence_is_preserved(self):
        self.report.write_text('previous attempt\n')
        with self.assertRaisesRegex(ValueError,'new receipt'):self.prepare()
        self.assertEqual('previous attempt\n',self.report.read_text());self.assertEqual([],self.server.requests)


def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();OUT=args.out.resolve();OUT.mkdir(parents=True,exist_ok=False)
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(PublicApiPreparationControls)
    with (OUT/'test.log').open('w') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    record={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'accepted':result.wasSuccessful(),'real_api_compilation':False,'consumer_invocations':0}
    (OUT/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
    if not record['accepted']:raise SystemExit(1)


if __name__=='__main__':main()
