"""Comprehensive unit, boundary, security, and integration tests for settletable.transport."""
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unicodedata
import unittest

from settletable.transport import SettleTableApp, redact_log_string


class TransportTestClient:
    def __init__(self, app, origin='http://localhost:8000', host='localhost:8000'):
        self.app = app
        self.origin = origin
        self.host = host

    def request(self, method, path, body=None, headers=None, remote_addr='127.0.0.1'):
        hdrs = headers.copy() if headers else {}
        environ = {
            'REQUEST_METHOD': method,
            'PATH_INFO': path,
            'REMOTE_ADDR': remote_addr,
            'HTTP_HOST': self.host,
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': 'http',
            'wsgi.input': BytesIO(b''),
            'wsgi.errors': BytesIO(),
            'wsgi.multithread': False,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
        }

        # Apply default origin & action header for POST if not explicitly overridden
        if method == 'POST':
            if 'HTTP_ORIGIN' not in hdrs and 'HTTP_REFERER' not in hdrs and 'HTTP_AUTHORIZATION' not in hdrs:
                hdrs['HTTP_ORIGIN'] = self.origin
            if 'HTTP_X_SETTLETABLE_ACTION' not in hdrs:
                hdrs['HTTP_X_SETTLETABLE_ACTION'] = '1'

        if body is not None:
            if isinstance(body, (dict, list)):
                raw_body = json.dumps(body).encode('utf-8')
            elif isinstance(body, str):
                raw_body = body.encode('utf-8')
            else:
                raw_body = body
            environ['wsgi.input'] = BytesIO(raw_body)
            if 'CONTENT_LENGTH' not in hdrs and 'HTTP_TRANSFER_ENCODING' not in hdrs:
                environ['CONTENT_LENGTH'] = str(len(raw_body))

        for k, v in hdrs.items():
            environ[k] = v

        response_status = [None]
        response_headers = [None]

        def start_response(status, response_hdrs):
            response_status[0] = status
            response_headers[0] = dict(response_hdrs)

        chunks = self.app(environ, start_response)
        body_out = b''.join(chunks)

        status_code = int(response_status[0].split()[0])
        parsed_json = None
        try:
            parsed_json = json.loads(body_out.decode('utf-8'))
        except Exception:
            pass

        return {
            'status': status_code,
            'headers': response_headers[0],
            'body': body_out,
            'json': parsed_json,
        }

    def get(self, path, headers=None):
        return self.request('GET', path, headers=headers)

    def post(self, path, body=None, headers=None, remote_addr='127.0.0.1'):
        return self.request('POST', path, body=body, headers=headers, remote_addr=remote_addr)


class TransportTests(unittest.TestCase):
    def setUp(self):
        scratch = Path('.local/tests')
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / 'transport.sqlite'
        self.clock_val = 1000.0
        self.app = SettleTableApp(self.db_path, clock=lambda: self.clock_val)
        self.addCleanup(self.app.close)
        self.client = TransportTestClient(self.app)

    def test_missing_content_length_on_post(self):
        res = self.client.request('POST', '/api/meals/m1/bootstrap', body=b'foo', headers={'CONTENT_LENGTH': ''})
        self.assertEqual(res['status'], 411)
        self.assertEqual(res['json']['error'], 'missing_content_length')

    def test_payload_boundary_too_large(self):
        huge_body = b'a' * (1_048_576 + 1)
        res = self.client.post('/api/meals/m1/bootstrap', body=huge_body)
        self.assertEqual(res['status'], 413)
        self.assertEqual(res['json']['error'], 'payload_too_large')

    def test_smuggling_desync_both_length_and_chunked_rejected(self):
        res = self.client.request('POST', '/api/meals/m1/bootstrap', body=b'data',
                                  headers={'CONTENT_LENGTH': '4', 'HTTP_TRANSFER_ENCODING': 'chunked'})
        self.assertEqual(res['status'], 400)
        self.assertEqual(res['json']['error'], 'malformed_request')

    def test_duplicate_json_keys_rejected(self):
        raw_json = '{"kind": "ReplaceReceipt", "command_id": "c1", "command_id": "c2"}'
        res = self.client.post('/api/meals/m1/apply', body=raw_json,
                               headers={'HTTP_AUTHORIZATION': 'Bearer ' + 'A'*43})
        self.assertEqual(res['status'], 400)
        self.assertEqual(res['json']['error'], 'duplicate_key')

    def test_float_number_rejected(self):
        raw_json = '{"kind": "Finalize", "command_id": "c1", "expected_revision": 1.0}'
        res = self.client.post('/api/meals/m1/apply', body=raw_json,
                               headers={'HTTP_AUTHORIZATION': 'Bearer ' + 'A'*43})
        self.assertEqual(res['status'], 400)
        self.assertEqual(res['json']['error'], 'invalid_number')

    def test_huge_integer_rejected(self):
        raw_json = f'{{"kind": "Finalize", "command_id": "c1", "expected_revision": {10**25}}}'
        res = self.client.post('/api/meals/m1/apply', body=raw_json,
                               headers={'HTTP_AUTHORIZATION': 'Bearer ' + 'A'*43})
        self.assertEqual(res['status'], 400)
        self.assertEqual(res['json']['error'], 'invalid_number')

    def test_csrf_origin_mismatch(self):
        res = self.client.post('/api/meals/m1/bootstrap', body={'participants': []},
                               headers={'HTTP_ORIGIN': 'https://evil.com'})
        self.assertEqual(res['status'], 403)
        self.assertEqual(res['json']['error'], 'origin_mismatch')

        # Origin: null (sandboxed iframe) rejected
        res2 = self.client.post('/api/meals/m1/bootstrap', body={'participants': []},
                                headers={'HTTP_ORIGIN': 'null'})
        self.assertEqual(res2['status'], 403)
        self.assertEqual(res2['json']['error'], 'origin_mismatch')

    def test_csrf_missing_action_header(self):
        res = self.client.request('POST', '/api/meals/m1/bootstrap', body={'participants': []},
                                  headers={'HTTP_X_SETTLETABLE_ACTION': ''})
        self.assertEqual(res['status'], 400)
        self.assertEqual(res['json']['error'], 'missing_action_header')

    def test_host_header_validation(self):
        bad_client = TransportTestClient(self.app, host='attacker.com')
        res = bad_client.get('/api/invitations/' + 'A'*43)
        self.assertEqual(res['status'], 400)
        self.assertEqual(res['json']['error'], 'invalid_host')

    def test_bootstrap_loopback_enforcement(self):
        res = self.client.post('/api/meals/m1/bootstrap', body={'participants': []},
                               remote_addr='198.51.100.1')
        self.assertEqual(res['status'], 403)
        self.assertEqual(res['json']['error'], 'forbidden')

    def test_actor_role_spoofing_rejected(self):
        res = self.client.post('/api/meals/m1/apply',
                               body={'kind': 'Finalize', 'command_id': 'c1', 'actor': 'hacker'},
                               headers={'HTTP_AUTHORIZATION': 'Bearer ' + 'A'*43})
        self.assertEqual(res['status'], 400)
        self.assertEqual(res['json']['error'], 'invalid_input')

    def test_conflicting_credentials_rejected(self):
        res = self.client.get('/api/meals/m1/snapshot',
                              headers={'HTTP_COOKIE': 'settletable_session=' + 'A'*43,
                                       'HTTP_AUTHORIZATION': 'Bearer ' + 'B'*43})
        self.assertEqual(res['status'], 400)
        self.assertEqual(res['json']['error'], 'conflicting_credentials')

    def test_unauthenticated_landing_get_is_idempotent_and_nonmutating(self):
        # 1. Bootstrap
        boot_res = self.client.post('/api/meals/m1/bootstrap', body={
            'participants': [{'id': 'O', 'name': 'Organizer', 'organizer': True},
                             {'id': 'D', 'name': 'Diner', 'organizer': False}]
        })
        self.assertEqual(boot_res['status'], 201)
        org_cred = boot_res['json']['sessions'][0]['credential']

        # 2. Issue invitation
        inv_res = self.client.post('/api/meals/m1/invitations',
                                   body={'participant_id': 'D', 'invite_ttl': 3600},
                                   headers={'HTTP_AUTHORIZATION': f'Bearer {org_cred}'})
        self.assertEqual(inv_res['status'], 201)
        token = inv_res['json']['token']

        # Snapshot before landing GETs
        snap_before = self.client.get('/api/meals/m1/snapshot',
                                      headers={'HTTP_AUTHORIZATION': f'Bearer {org_cred}'})
        rev_before = snap_before['json']['revision']

        # 3. GET landing multiple times -> all return valid=True, revision does NOT advance
        for _ in range(5):
            get_res = self.client.get(f'/api/invitations/{token}')
            self.assertEqual(get_res['status'], 200)
            self.assertTrue(get_res['json']['valid'])
            self.assertEqual(get_res['json']['meal_id'], 'm1')
            self.assertEqual(get_res['json']['participant_name'], 'Diner')

        snap_after = self.client.get('/api/meals/m1/snapshot',
                                     headers={'HTTP_AUTHORIZATION': f'Bearer {org_cred}'})
        self.assertEqual(snap_after['json']['revision'], rev_before)

    def test_end_to_end_http_meal_lifecycle(self):
        # 1. Bootstrap via loopback POST
        boot_res = self.client.post('/api/meals/m1/bootstrap', body={
            'participants': [
                {'id': 'O', 'name': 'Organizer', 'organizer': True},
                {'id': 'B', 'name': 'Bob', 'organizer': False},
            ]
        })
        self.assertEqual(boot_res['status'], 201)
        self.assertIn('Set-Cookie', boot_res['headers'])
        self.assertIn('HttpOnly; Secure; SameSite=Strict', boot_res['headers']['Set-Cookie'])
        org_cred = boot_res['json']['sessions'][0]['credential']

        # 2. Organizer issues invitation for Bob
        inv_res = self.client.post('/api/meals/m1/invitations',
                                   body={'participant_id': 'B', 'invite_ttl': 3600},
                                   headers={'HTTP_AUTHORIZATION': f'Bearer {org_cred}'})
        self.assertEqual(inv_res['status'], 201)
        token = inv_res['json']['token']

        # 3. Unauthenticated landing GET
        land_res = self.client.get(f'/api/invitations/{token}')
        self.assertEqual(land_res['status'], 200)
        self.assertTrue(land_res['json']['valid'])
        self.assertEqual(land_res['json']['participant_name'], 'Bob')

        # 4. Bob redeems invitation via POST
        redeem_res = self.client.post(f'/api/meals/m1/invitations/{token}/redeem', body={})
        self.assertEqual(redeem_res['status'], 200)
        self.assertEqual(redeem_res['json']['participant_id'], 'B')
        self.assertIn('Set-Cookie', redeem_res['headers'])
        cookie_hdr = redeem_res['headers']['Set-Cookie'].split(';')[0]
        bob_cred = cookie_hdr.split('=')[1]

        # Second redemption attempt fails with 400
        redeem_repeat = self.client.post(f'/api/meals/m1/invitations/{token}/redeem', body={})
        self.assertEqual(redeem_repeat['status'], 400)
        self.assertEqual(redeem_repeat['json']['error'], 'invalid_invitation')

        # 5. Organizer replaces receipt
        rcpt_cmd = {
            'kind': 'ReplaceReceipt',
            'command_id': 'cmd-rcpt',
            'expected_revision': 2,
            'expected_financial_revision': 0,
            'receipt': {
                'items': [
                    {'id': 'item-1', 'label': 'Shared Pizza', 'quantity': 1, 'line_sen': 3000},
                ],
                'adjustments': [],
            }
        }
        apply_res = self.client.post('/api/meals/m1/apply', body=rcpt_cmd,
                                     headers={'HTTP_AUTHORIZATION': f'Bearer {org_cred}'})
        self.assertEqual(apply_res['status'], 200)
        self.assertEqual(apply_res['json']['revision'], 3)

        # 6. Bob claims quantity 1 via cookie authentication
        claim_cmd = {
            'kind': 'SetOwnQuantity',
            'command_id': 'cmd-claim-bob',
            'item_id': 'item-1',
            'quantity': 1,
            'expected_item_revision': 1,
            'expected_financial_revision': 1,
        }
        bob_claim_res = self.client.post('/api/meals/m1/apply', body=claim_cmd,
                                         headers={'HTTP_COOKIE': f'settletable_session={bob_cred}'})
        self.assertEqual(bob_claim_res['status'], 200)
        self.assertEqual(bob_claim_res['json']['revision'], 4)

        # 7. Bob rotates session
        rotate_res = self.client.post('/api/meals/m1/session/rotate', body={},
                                      headers={'HTTP_COOKIE': f'settletable_session={bob_cred}'})
        self.assertEqual(rotate_res['status'], 200)
        new_bob_cred = rotate_res['json']['credential']
        self.assertNotEqual(bob_cred, new_bob_cred)

        # Old Bob credential returns 401
        old_cred_res = self.client.get('/api/meals/m1/snapshot',
                                       headers={'HTTP_COOKIE': f'settletable_session={bob_cred}'})
        self.assertEqual(old_cred_res['status'], 401)
        self.assertEqual(old_cred_res['json']['error'], 'invalid_session')

        # New Bob credential succeeds
        new_cred_res = self.client.get('/api/meals/m1/snapshot',
                                       headers={'HTTP_COOKIE': f'settletable_session={new_bob_cred}'})
        self.assertEqual(new_cred_res['status'], 200)
        self.assertEqual(new_cred_res['json']['meal_id'], 'm1')

        # 8. Organizer rotates session -> MUST return 403 Forbidden
        org_rotate = self.client.post('/api/meals/m1/session/rotate', body={},
                                      headers={'HTTP_AUTHORIZATION': f'Bearer {org_cred}'})
        self.assertEqual(org_rotate['status'], 403)
        self.assertEqual(org_rotate['json']['error'], 'forbidden')

    def test_single_header_line_too_large(self):
        huge_val = 'A' * 4097
        res = self.client.get('/api/meals/m1/snapshot', headers={'HTTP_X_CUSTOM': huge_val})
        self.assertEqual(res['status'], 431)
        self.assertEqual(res['json']['error'], 'header_too_large')

    def test_total_headers_block_too_large(self):
        hdrs = {f'HTTP_X_HEADER_{i}': 'B' * 1000 for i in range(18)}
        res = self.client.get('/api/meals/m1/snapshot', headers=hdrs)
        self.assertEqual(res['status'], 431)
        self.assertEqual(res['json']['error'], 'header_too_large')

    def test_unhandled_key_error_returns_invalid_input(self):
        # 1. Bootstrap with participant missing 'id'
        res = self.client.post('/api/meals/m1/bootstrap', body={
            'participants': [{'name': 'NoID', 'organizer': True}]
        })
        self.assertEqual(res['status'], 400)
        self.assertEqual(res['json']['error'], 'invalid_input')

        # 2. Bootstrap properly
        boot = self.client.post('/api/meals/m1/bootstrap', body={
            'participants': [{'id': 'O', 'name': 'Org', 'organizer': True}]
        })
        org_cred = boot['json']['sessions'][0]['credential']

        # 3. ReplaceReceipt with item missing required field 'id'
        res = self.client.post('/api/meals/m1/apply', body={
            'kind': 'ReplaceReceipt',
            'command_id': 'cmd-bad-item',
            'receipt': {
                'items': [{'label': 'NoID', 'line_sen': 1000}],
            }
        }, headers={'HTTP_AUTHORIZATION': f'Bearer {org_cred}'})
        self.assertEqual(res['status'], 400)
        self.assertEqual(res['json']['error'], 'invalid_input')

    def test_logging_and_secret_redaction(self):
        logs = []
        app_with_logger = SettleTableApp(self.db_path, clock=lambda: self.clock_val, logger=logs.append)
        self.addCleanup(app_with_logger.close)
        client = TransportTestClient(app_with_logger)

        # GET request with token in URL
        token = 'A' * 43
        res = client.get(f'/api/invitations/{token}')
        self.assertEqual(res['status'], 200)
        self.assertTrue(any('/api/invitations/[REDACTED]' in log for log in logs))
        self.assertFalse(any(token in log for log in logs))

        # Test redact_log_string directly
        raw = f"GET /api/meals/m1/invitations/{token} Bearer secret123 settletable_session=secret456"
        redacted = redact_log_string(raw)
        self.assertNotIn('secret123', redacted)
        self.assertNotIn('secret456', redacted)
        self.assertNotIn(token, redacted)
        self.assertIn('[REDACTED]', redacted)

    def test_case_insensitive_bearer_header(self):
        boot = self.client.post('/api/meals/m1/bootstrap', body={
            'participants': [{'id': 'O', 'name': 'Org', 'organizer': True}]
        })
        org_cred = boot['json']['sessions'][0]['credential']

        res = self.client.get('/api/meals/m1/snapshot',
                              headers={'HTTP_AUTHORIZATION': f'bearer {org_cred}'})
        self.assertEqual(res['status'], 200)
        self.assertEqual(res['json']['meal_id'], 'm1')

    def test_unicode_nfc_duplicate_keys_rejected(self):
        # 'e\u0301' (decomposed é) vs '\u00e9' (composed é)
        decomposed = "e\u0301"
        composed = "\u00e9"
        self.assertNotEqual(decomposed, composed)
        self.assertEqual(unicodedata.normalize('NFC', decomposed), unicodedata.normalize('NFC', composed))

        body_str = f'{{"{decomposed}": 1, "{composed}": 2}}'
        res = self.client.post('/api/meals/m1/bootstrap', body=body_str)
        self.assertEqual(res['status'], 400)
        self.assertEqual(res['json']['error'], 'duplicate_key')

    def test_json_nesting_depth_limit(self):
        # 11 levels of nesting
        nested = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": {"j": {"k": 1}}}}}}}}}}}
        res = self.client.post('/api/meals/m1/bootstrap', body=nested)
        self.assertEqual(res['status'], 400)
        self.assertEqual(res['json']['error'], 'malformed_json')


if __name__ == '__main__':
    unittest.main()
