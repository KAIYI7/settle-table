"""Synthetic fixtures: real SQLite races/restarts and bounded loopback HTTP."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

from settletable.authority import (Authority, AuthorityError, Participant, Receipt, ReceiptItem,
    ReplaceReceipt, ReviewReceipt, SetOwnQuantity, Finalize, RevokeSession)
from settletable.payment_simulation import (SimulationConfig, KaiPayClient, client_reference,
    perform_simulation, validate_remote)
from settletable.transport import SettleTableApp
from test_transport import TransportTestClient

NAMESPACE = 'c580f82e-977b-419c-9979-fb78d6b5fe6e'
INTEGRATION = '8e90d4a1-a3a8-447e-b001-44791735d331'
PAYMENT = '250d3eba-40eb-4f48-afcf-5a13131ac544'


def config(base_url='http://127.0.0.1:1'):
    return SimulationConfig(INTEGRATION, NAMESPACE, base_url, 'kp_int_fixture.' + 'A' * 43)


class RecordingClient:
    def __init__(self, outcome=None):
        self.calls = []
        self.outcome = outcome or {'outcome': 'REQUEST_UNKNOWN'}

    def request(self, method, reference, amount):
        self.calls.append((method, reference, amount))
        return self.outcome


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'simulation.sqlite'
        self.now = 1000
        self.authority = Authority(self.path, clock=lambda: self.now)
        grants = self.authority.bootstrap('meal', (Participant('A', 'Organizer', True),
            Participant('B', 'Diner'), Participant('C', 'Managed')))
        self.credentials = {s.participant_id: s.credential for s in grants.sessions}
        self.cfg = config()

    def tearDown(self):
        self.authority.close()
        self.temp.cleanup()

    def finalize(self):
        a, b = self.credentials['A'], self.credentials['B']
        self.authority.apply(a, 'meal', ReplaceReceipt('receipt', 0, 0,
            Receipt((ReceiptItem('dish', 'Synthetic item', 1, 1234),), 1234, 1234)))
        digest = self.authority.snapshot(a, 'meal').receipt_digest
        self.authority.apply(a, 'meal', ReviewReceipt('review', 1, 1, digest))
        self.authority.apply(b, 'meal', SetOwnQuantity('claim', 'dish', 1, 1, 1))
        return self.authority.apply(a, 'meal', Finalize('final', 3, 1))

    def intent(self, target='B', credential=None, create=True):
        return self.authority.payment_simulation(credential or self.credentials['A'], 'meal', target,
                                                 self.cfg, create=create)

    def remote(self, reference, version=2, status='AUTHORIZED'):
        return {'clientReference': reference, 'paymentId': PAYMENT, 'amountCents': 1234,
                'currency': 'MYR', 'status': status, 'version': version, 'simulation': True,
                'updatedAt': f'2026-10-28T04:00:{version:02d}Z'}

    def observe(self, remote):
        return self.authority.observe_payment_simulation(self.credentials['A'], 'meal', 'B', self.cfg,
                                                         {'remote': remote})

    def test_golden_reference_exact_case_and_namespace(self):
        basis = {'meal_id': 'meal-demo-01', 'finalize_actor_id': 'p-organizer',
                 'finalize_command_id': 'finalize-01', 'participant_id': 'p-ada'}
        ref = client_reference(NAMESPACE, basis)
        self.assertEqual(ref, '27b7b67c-4b28-5980-9590-323b95d1fe33')
        self.assertNotEqual(ref, client_reference(str(uuid.uuid4()), basis))
        for key in basis:
            self.assertNotEqual(ref, client_reference(NAMESPACE, dict(basis, **{key: basis[key].upper()})))

    def test_config_disabled_missing_binding_and_safe_destination(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(SimulationConfig.from_env())
        with patch.dict(os.environ, {'SETTLETABLE_KAIPAY_ENABLED': '1'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'invalid_simulation_configuration'):
                SimulationConfig.from_env()
        for url in ('http://example.org', 'http://10.0.0.1', 'http://127.0.0.1/path',
                    'https://user:pass@example.org', 'https://example.org?q=x'):
            with self.assertRaises(ValueError):
                config(url)
        self.assertNotIn('A' * 43, repr(config()))

    def test_draft_no_intent_or_network(self):
        client = RecordingClient()
        with self.assertRaises(AuthorityError) as caught:
            perform_simulation(self.authority, self.credentials['A'], 'meal', 'B', self.cfg, client, initiate=True)
        self.assertEqual(caught.exception.code, 'meal_not_finalized')
        self.assertEqual(client.calls, [])
        self.assertEqual(self.authority._db.execute('SELECT count(*) FROM payment_simulations').fetchone()[0], 0)

    def test_accepted_basis_financial_bytes_and_security_revision(self):
        accepted = self.finalize()
        before = self.authority._db.execute('SELECT * FROM commands ORDER BY command_id').fetchall()
        snapshot = self.authority.snapshot(self.credentials['A'], 'meal')
        intent = self.intent()
        self.assertEqual(intent['basis']['revision'], accepted.revision)
        self.assertEqual(intent['basis']['amountCents'], 1234)
        self.authority.apply(self.credentials['A'], 'meal', RevokeSession('revoke-c', 4, 'C'))
        self.assertEqual(self.intent()['clientReference'], intent['clientReference'])
        self.assertEqual(self.intent()['basis'], intent['basis'])
        self.assertEqual(self.authority._db.execute('SELECT * FROM commands WHERE security=0 ORDER BY command_id').fetchall(), before)
        self.observe(self.remote(intent['clientReference']))
        after = self.authority.snapshot(self.credentials['A'], 'meal')
        self.assertEqual(after.calculation, snapshot.calculation)
        self.assertEqual(after.financial_revision, snapshot.financial_revision)

    def test_zero_managed_diner_no_session_or_remote_payment(self):
        self.finalize()
        client = RecordingClient()
        result = perform_simulation(self.authority, self.credentials['A'], 'meal', 'C', self.cfg, client, initiate=True)
        self.assertEqual(result['state'], 'NO_PAYMENT_NEEDED')
        self.assertEqual(client.calls, [])

    def test_organizer_initiation_self_read_expiry_cross_meal(self):
        self.finalize()
        with self.assertRaises(AuthorityError) as denied:
            self.intent(credential=self.credentials['B'])
        self.assertEqual(denied.exception.code, 'forbidden')
        self.intent()
        self.assertTrue(self.intent(credential=self.credentials['B'], create=False)['exists'])
        with self.assertRaises(AuthorityError):
            self.intent('A', credential=self.credentials['B'], create=False)
        with self.assertRaises(AuthorityError):
            self.authority.payment_simulation(self.credentials['A'], 'other-meal', 'B', self.cfg)
        self.now = 4600
        with self.assertRaises(AuthorityError) as expired:
            self.intent(create=False)
        self.assertEqual(expired.exception.code, 'invalid_session')

    def test_missing_ambiguous_corrupt_finalize_fail_closed(self):
        self.finalize()
        final = self.authority._db.execute("SELECT * FROM commands WHERE command_id='final'").fetchone()
        self.authority._db.execute("DELETE FROM commands WHERE command_id='final'")
        with self.assertRaises(AuthorityError):
            self.intent()
        self.authority._db.execute('INSERT INTO commands VALUES (?,?,?,?,?,?,?)', final)
        self.authority._db.execute('INSERT INTO commands VALUES (?,?,?,?,?,?,?)', ('meal', 'B', *final[2:]))
        with self.assertRaises(AuthorityError):
            self.intent()
        self.authority._db.execute("DELETE FROM commands WHERE participant_id='B' AND command_id='final'")
        self.authority._db.execute("UPDATE commands SET result=? WHERE command_id='final'", (b'{}',))
        with self.assertRaises(AuthorityError):
            self.intent()
        self.assertEqual(self.authority._db.execute('SELECT count(*) FROM payment_simulations').fetchone()[0], 0)

    def test_concurrent_same_reference_one_sqlite_intent(self):
        self.finalize()
        barrier = threading.Barrier(6)
        def create(_):
            authority = Authority(self.path, clock=lambda: 1000)
            try:
                barrier.wait(timeout=10)
                return authority.payment_simulation(self.credentials['A'], 'meal', 'B', self.cfg, create=True)
            finally:
                authority.close()
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(create, range(6)))
        self.assertEqual(len({r['clientReference'] for r in results}), 1)
        self.assertEqual(self.authority._db.execute('SELECT count(*) FROM payment_simulations').fetchone()[0], 1)

    def test_sqlite_busy_no_dispatch_uncertain_commit_reuses_intent(self):
        self.finalize()
        lock = sqlite3.connect(self.path, isolation_level=None)
        lock.execute('BEGIN IMMEDIATE')
        client = RecordingClient()
        try:
            with self.assertRaises(AuthorityError) as busy:
                perform_simulation(self.authority, self.credentials['A'], 'meal', 'B', self.cfg, client, initiate=True)
            self.assertEqual(busy.exception.code, 'busy')
            self.assertFalse(client.calls)
        finally:
            lock.execute('ROLLBACK')
            lock.close()
        def failure(stage):
            if stage == 'simulation_after_intent_commit':
                raise RuntimeError()
        self.authority._failure_hook = failure
        with self.assertRaises(AuthorityError) as uncertain:
            self.intent()
        self.assertEqual(uncertain.exception.code, 'commit_uncertain')
        self.authority._failure_hook = None
        self.assertTrue(self.intent()['exists'])
        self.assertEqual(self.authority._db.execute('SELECT count(*) FROM payment_simulations').fetchone()[0], 1)

    def test_fresh_process_recovers_frozen_reference(self):
        self.finalize()
        intent = self.intent()
        self.authority.close()
        script = '''import json,sys
from settletable.authority import Authority
from settletable.payment_simulation import SimulationConfig
x=json.load(sys.stdin)
a=Authority(x['path'],clock=lambda:1000)
try: print(json.dumps(a.payment_simulation(x['credential'],'meal','B',SimulationConfig(**x['config']),create=True)))
finally: a.close()
'''
        payload = {'path': str(self.path), 'credential': self.credentials['A'], 'config': asdict(self.cfg)}
        completed = subprocess.run([sys.executable, '-B', '-c', script], input=json.dumps(payload),
                                   capture_output=True, text=True, check=True, timeout=20)
        self.assertEqual(json.loads(completed.stdout)['clientReference'], intent['clientReference'])
        self.authority = Authority(self.path, clock=lambda: 1000)

    def test_no_write_lock_during_network_midflight_revocation(self):
        self.finalize()
        self.intent()
        entered, released = threading.Event(), threading.Event()
        class BlockedClient:
            def request(inner, method, reference, amount):
                entered.set()
                released.wait(timeout=10)
                return {'remote': self.remote(reference)}
        def read():
            authority = Authority(self.path, clock=lambda: 1000)
            try:
                return perform_simulation(authority, self.credentials['B'], 'meal', 'B', self.cfg, BlockedClient())
            finally:
                authority.close()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(read)
            self.assertTrue(entered.wait(timeout=10))
            self.authority.apply(self.credentials['A'], 'meal', RevokeSession('revoke-b', 4, 'B'))
            released.set()
            with self.assertRaises(AuthorityError) as revoked:
                future.result(timeout=10)
            self.assertEqual(revoked.exception.code, 'invalid_session')
        self.assertIsNone(self.intent(create=False)['paymentId'])

    def test_monotonic_equal_version_identity_and_unsupported_status(self):
        self.finalize()
        reference = self.intent()['clientReference']
        self.observe(self.remote(reference, 2))
        self.observe(self.remote(reference, 1, 'PROCESSING'))
        self.assertEqual(self.intent(create=False)['paymentVersion'], 2)
        self.observe(self.remote(reference, 2))
        for changed in (dict(self.remote(reference), status='DECLINED'),
                        dict(self.remote(reference), paymentId=str(uuid.uuid4()))):
            with self.assertRaises(AuthorityError) as conflict:
                self.observe(changed)
            self.assertEqual(conflict.exception.code, 'simulation_conflict')
        self.authority.observe_payment_simulation(self.credentials['A'], 'meal', 'B', self.cfg, {'outcome': 'UNAVAILABLE'})
        self.assertEqual(self.intent(create=False)['state'], 'AUTHORIZED')
        self.assertEqual(self.observe(self.remote(reference, 3, 'CAPTURED'))['state'], 'UNEXPECTED_STATUS')

    def test_processing_failed_and_declined_distinct(self):
        self.finalize()
        reference = self.intent()['clientReference']
        self.assertEqual(self.observe(self.remote(reference, 1, 'PROCESSING'))['state'], 'PENDING')
        self.assertEqual(self.observe(self.remote(reference, 2, 'FAILED'))['state'], 'FAILED')
        with self.assertRaises(AuthorityError):
            self.observe(self.remote(reference, 3, 'DECLINED'))

    def test_concurrent_observations_cannot_overwrite_newer_version(self):
        self.finalize()
        reference = self.intent()['clientReference']
        barrier = threading.Barrier(2)
        def observe(version):
            authority = Authority(self.path, clock=lambda: 1000)
            try:
                barrier.wait(timeout=10)
                return authority.observe_payment_simulation(self.credentials['A'], 'meal', 'B', self.cfg,
                    {'remote': self.remote(reference, version, 'AUTHORIZED' if version == 2 else 'PROCESSING')})
            finally:
                authority.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(observe, (1, 2)))
        self.assertEqual((self.intent(create=False)['paymentVersion'], self.intent(create=False)['state']), (2, 'AUTHORIZED'))

    def test_frozen_basis_conflict_and_observation_rollback(self):
        self.finalize()
        intent = self.intent()
        self.authority._db.execute("UPDATE payment_simulations SET basis=?", (b'{}',))
        with self.assertRaises(AuthorityError) as conflict:
            self.intent()
        self.assertEqual(conflict.exception.code, 'simulation_conflict')
        from settletable.authority import _wire
        self.authority._db.execute('UPDATE payment_simulations SET basis=?', (_wire(intent['basis']),))
        def failure(stage):
            if stage == 'simulation_before_observation_commit':
                raise RuntimeError()
        self.authority._failure_hook = failure
        with self.assertRaises(AuthorityError) as storage:
            self.observe(self.remote(intent['clientReference']))
        self.assertEqual(storage.exception.code, 'storage_error')
        self.authority._failure_hook = None
        self.assertIsNone(self.intent(create=False)['paymentVersion'])
        self.assertEqual(self.observe(self.remote(intent['clientReference']))['state'], 'AUTHORIZED')

    def test_uncertain_retry_get_first_same_put_and_get_never_creates(self):
        self.finalize()
        client = RecordingClient()
        first = perform_simulation(self.authority, self.credentials['A'], 'meal', 'B', self.cfg, client, initiate=True)
        self.assertEqual(first['state'], 'REQUEST_UNKNOWN')
        client.outcome = {'outcome': 'NOT_SENT', 'checked': True}
        checked = perform_simulation(self.authority, self.credentials['A'], 'meal', 'B', self.cfg, client, initiate=True)
        self.assertEqual([c[0] for c in client.calls], ['PUT', 'GET'])
        self.assertEqual(checked['state'], 'REQUEST_UNKNOWN')
        self.assertTrue(checked['retryReady'])
        client.outcome = {'remote': self.remote(first['clientReference'])}
        done = perform_simulation(self.authority, self.credentials['A'], 'meal', 'B', self.cfg, client, initiate=True)
        self.assertEqual([c[0] for c in client.calls], ['PUT', 'GET', 'PUT'])
        self.assertEqual(done['state'], 'AUTHORIZED')
        self.assertEqual(len({c[1] for c in client.calls}), 1)
        absent = perform_simulation(self.authority, self.credentials['A'], 'meal', 'A', self.cfg, client)
        self.assertFalse(absent['exists'])
        self.assertEqual(len(client.calls), 3)

    def test_response_strict_types_and_immutable_amount(self):
        self.finalize()
        reference = self.intent()['clientReference']
        good = self.remote(reference)
        self.assertEqual(validate_remote(good, reference, 1234), good)
        for key, value in [('simulation', 1), ('amountCents', '1234'), ('amountCents', True),
                           ('currency', 'USD'), ('version', True), ('version', -1),
                           ('clientReference', str(uuid.uuid4())), ('updatedAt', '2026-10-28T04:00:00'),
                           ('paymentId', PAYMENT.upper()), ('status', 'AUTHORIZED<script>')]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_remote(dict(good, **{key: value}), reference, 1234)

    def test_http_route_csrf_access_empty_body_and_secret_projection(self):
        self.finalize()
        remote_client = RecordingClient()
        app = SettleTableApp(self.path, clock=lambda: 1000, simulation_config=self.cfg, simulation_client=remote_client)
        try:
            client = TransportTestClient(app)
            path = '/api/meals/meal/participants/B/payment-simulation'
            diner = {'HTTP_AUTHORIZATION': 'Bearer ' + self.credentials['B']}
            organizer = {'HTTP_AUTHORIZATION': 'Bearer ' + self.credentials['A']}
            self.assertEqual(client.get(path)['status'], 401)
            self.assertEqual(client.post(path, {}, diner)['status'], 403)
            self.assertEqual(client.post(path, {'amountCents': 1}, organizer)['status'], 400)
            result = client.post(path, {}, organizer)
            self.assertEqual(result['status'], 202)
            self.assertNotIn(self.cfg.credential, result['body'].decode())
            self.assertEqual(client.get(path, diner)['status'], 202)
            self.assertEqual(client.get('/api/meals/meal/participants/A/payment-simulation', diner)['status'], 403)
            self.assertEqual(client.post(path, {}, {'HTTP_COOKIE': 'settletable_session=' + self.credentials['A'],
                'HTTP_ORIGIN': 'http://attacker.invalid'})['status'], 403)
        finally:
            app.close()


class HttpClientTests(unittest.TestCase):
    def serve(self, handler):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return KaiPayClient(config(f'http://127.0.0.1:{server.server_port}'))

    def test_real_http_exact_body_no_redirect_proxy(self):
        calls = []
        reference = str(uuid.uuid4())
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_PUT(self):
                calls.append((self.path, dict(self.headers), self.rfile.read(int(self.headers.get('Content-Length', 0)))))
                self.send_response(307)
                self.send_header('Location', 'http://example.invalid/credential-sink')
                self.end_headers()
        client = self.serve(Handler)
        with patch.dict(os.environ, {'HTTP_PROXY': 'http://example.invalid:1'}):
            result = client.request('PUT', reference, 1234)
        self.assertEqual(result['outcome'], 'REQUEST_UNKNOWN')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], '/v1/integrations/payments/' + reference)
        self.assertEqual(json.loads(calls[0][2]), {'amountCents': 1234, 'currency': 'MYR'})
        self.assertEqual(set(calls[0][1]) & {'Cookie', 'X-Merchant-Id', 'X-Participant-Id'}, set())

    def test_response_size_duplicate_content_and_whole_request_deadline(self):
        reference = str(uuid.uuid4())
        mode = ['oversized']
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                try:
                    if mode[0] == 'slow':
                        self.wfile.write(b'HTTP/1.1 200 OK\r\nX-Slow: ')
                        self.wfile.flush()
                        for _ in range(15):
                            time.sleep(0.5)
                            self.wfile.write(b'x')
                            self.wfile.flush()
                        return
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html' if mode[0] == 'type' else 'application/json')
                    self.end_headers()
                    self.wfile.write(b'x' * 8193 if mode[0] == 'oversized' else b'{"success":true,"success":true,"data":{}}')
                except OSError:
                    pass
        client = self.serve(Handler)
        for name in ('oversized', 'duplicate', 'type', 'slow'):
            mode[0] = name
            started = time.monotonic()
            self.assertEqual(client.request('GET', reference, 1234)['outcome'], 'UNAVAILABLE')
            self.assertLess(time.monotonic() - started, 5.8)

    def test_truncated_valid_json_rejected_auth_suspends_and_retry_after_honored(self):
        reference = str(uuid.uuid4())
        mode = ['truncated']
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                calls.append(mode[0])
                raw = json.dumps({'success': True, 'data': {'clientReference': reference,
                    'paymentId': PAYMENT, 'amountCents': 1234, 'currency': 'MYR', 'status': 'AUTHORIZED',
                    'version': 2, 'simulation': True, 'updatedAt': '2026-10-28T04:00:02Z'}}).encode()
                self.send_response(401 if mode[0] == 'auth' else 429 if mode[0] == 'quota' else 200)
                self.send_header('Content-Type', 'application/json')
                if mode[0] in ('truncated', 'valid'): self.send_header('Content-Length', str(len(raw) + (10 if mode[0] == 'truncated' else 0)))
                if mode[0] == 'quota': self.send_header('Retry-After', '1')
                self.end_headers()
                self.wfile.write(raw)
        client = self.serve(Handler)
        self.assertEqual(client.request('GET', reference, 1234)['outcome'], 'UNAVAILABLE')
        mode[0] = 'quota'
        self.assertEqual(client.request('GET', reference, 1234)['retry_after'], 1)
        self.assertEqual(client.request('GET', reference, 1234)['outcome'], 'UNAVAILABLE')
        self.assertEqual(calls, ['truncated', 'quota'])
        time.sleep(1.05)
        mode[0] = 'valid'
        self.assertEqual(client.request('GET', reference, 1234)['remote']['status'], 'AUTHORIZED')
        mode[0] = 'auth'
        self.assertEqual(client.request('GET', reference, 1234)['outcome'], 'UNAVAILABLE')
        self.assertEqual(client.request('GET', reference, 1234)['outcome'], 'UNAVAILABLE')
        self.assertEqual(calls, ['truncated', 'quota', 'valid', 'auth'])


if __name__ == '__main__':
    unittest.main()
