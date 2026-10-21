"""Comprehensive unit, boundary, security, and integration tests for settletable.transport."""
from io import BytesIO
import http.cookies
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

        # 7. Bob rotates session via cookie
        rotate_res = self.client.post('/api/meals/m1/session/rotate', body={},
                                      headers={'HTTP_COOKIE': f'settletable_session={bob_cred}'})
        self.assertEqual(rotate_res['status'], 200)
        # Defense: Cookie-authenticated browser rotation does NOT expose credential in JSON
        self.assertNotIn('credential', rotate_res['json'])
        self.assertEqual(rotate_res['json']['participant_id'], 'B')
        self.assertIn('Set-Cookie', rotate_res['headers'])
        cookie_parsed = http.cookies.SimpleCookie(rotate_res['headers']['Set-Cookie'])
        new_bob_cred = cookie_parsed['settletable_session'].value
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

    def test_replace_receipt_with_adjustments_missing_rationale_and_negative_rounding(self):
        boot = self.client.post('/api/meals/m-adj/bootstrap', body={
            'participants': [{'id': 'O', 'name': 'Org', 'organizer': True}]
        })
        org_cred = boot['json']['sessions'][0]['credential']

        # ReplaceReceipt with adjustments missing 'rationale' and including BNM negative rounding
        res = self.client.post('/api/meals/m-adj/apply', body={
            'kind': 'ReplaceReceipt',
            'command_id': 'cmd-adj-test',
            'expected_revision': 0,
            'expected_financial_revision': 0,
            'receipt': {
                'items': [
                    {'id': 'it-1', 'label': 'Chicken Rice', 'quantity': 1, 'line_sen': 1200},
                    {'id': 'it-2', 'label': 'Ice Lemon Tea', 'quantity': 1, 'line_sen': 320},
                ],
                'subtotal_sen': 1520,
                'total_sen': 1670,
                'adjustments': [
                    {'id': 'adj-1', 'label': 'Service Charge', 'kind': 'service', 'amount_sen': 152},
                    {'id': 'adj-2', 'label': 'Rounding Adjustment', 'kind': 'rounding', 'amount_sen': -2},
                ],
                'included_tax_sen': 0,
            }
        }, headers={'HTTP_AUTHORIZATION': f'Bearer {org_cred}'})
        self.assertEqual(res['status'], 200)
        self.assertEqual(res['json']['revision'], 1)
        self.assertEqual(res['json']['financial_revision'], 1)

        # Snapshot check to confirm adjustments have valid non-empty rationale and correct eligible_item_ids
        snap = self.client.get('/api/meals/m-adj/snapshot', headers={'HTTP_AUTHORIZATION': f'Bearer {org_cred}'})
        self.assertEqual(snap['status'], 200)
        rcpt = snap['json']['receipt']
        self.assertEqual(len(rcpt['adjustments']), 2)
        adj_service = next(a for a in rcpt['adjustments'] if a['kind'] == 'service')
        adj_rounding = next(a for a in rcpt['adjustments'] if a['kind'] == 'rounding')
        self.assertEqual(adj_service['amount_sen'], 152)
        self.assertEqual(adj_service['rationale'], 'Service Charge adjustment')
        self.assertEqual(sorted(adj_service['eligible_item_ids']), ['it-1', 'it-2'])
        self.assertEqual(adj_rounding['amount_sen'], -2)
        self.assertEqual(adj_rounding['rationale'], 'Rounding Adjustment adjustment')
        self.assertEqual(sorted(adj_rounding['eligible_item_ids']), ['it-1', 'it-2'])

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

    def test_bootstrap_proxy_forwarding_headers_rejected(self):
        # A reverse proxy forwarding remote traffic to 127.0.0.1 must NOT bypass loopback restriction
        proxy_hdrs = [
            {'HTTP_X_FORWARDED_FOR': '203.0.113.195'},
            {'HTTP_X_REAL_IP': '203.0.113.195'},
            {'HTTP_FORWARDED': 'for=203.0.113.195;proto=http'},
            {'HTTP_X_FORWARDED_HOST': 'external-tunnel.example.com'},
            {'HTTP_X_FORWARDED_PROTO': 'https'},
        ]
        for h in proxy_hdrs:
            res = self.client.post('/api/meals/m1/bootstrap', body={
                'participants': [{'id': 'O', 'name': 'Org', 'organizer': True}]
            }, headers=h, remote_addr='127.0.0.1')
            self.assertEqual(res['status'], 403)
            self.assertEqual(res['json']['error'], 'forbidden')

    def test_bootstrap_never_leaks_all_participant_credentials(self):
        # Even if multiple participants are declared at bootstrap, only the organizer session is returned
        boot = self.client.post('/api/meals/m1/bootstrap', body={
            'participants': [
                {'id': 'O', 'name': 'Organizer', 'organizer': True},
                {'id': 'D1', 'name': 'Diner 1', 'organizer': False},
                {'id': 'D2', 'name': 'Diner 2', 'organizer': False},
            ]
        })
        self.assertEqual(boot['status'], 201)
        sessions = boot['json']['sessions']
        self.assertEqual(len(sessions), 1)
        session_participants = [s['participant_id'] for s in sessions]
        self.assertEqual(session_participants, ['O'])
        self.assertNotIn('D1', session_participants)
        self.assertNotIn('D2', session_participants)

    def test_session_rotation_bearer_returns_credential_in_json(self):
        boot = self.client.post('/api/meals/m1/bootstrap', body={
            'participants': [
                {'id': 'O', 'name': 'Org', 'organizer': True},
                {'id': 'D', 'name': 'Diner', 'organizer': False},
            ]
        })
        org_cred = boot['json']['sessions'][0]['credential']

        # Issue and redeem invitation for D
        inv = self.client.post('/api/meals/m1/invitations', body={'participant_id': 'D'},
                               headers={'HTTP_AUTHORIZATION': f'Bearer {org_cred}'})
        token = inv['json']['token']
        redeem = self.client.post(f'/api/meals/m1/invitations/{token}/redeem', body={})
        cookie_header = redeem['headers']['Set-Cookie']
        diner_cred = http.cookies.SimpleCookie(cookie_header)['settletable_session'].value

        # Rotate using Bearer header (programmatic client context)
        rotate_res = self.client.post('/api/meals/m1/session/rotate', body={},
                                      headers={'HTTP_AUTHORIZATION': f'Bearer {diner_cred}'})
        self.assertEqual(rotate_res['status'], 200)
        self.assertIn('credential', rotate_res['json'])
        self.assertEqual(rotate_res['json']['participant_id'], 'D')
        self.assertNotEqual(rotate_res['json']['credential'], diner_cred)

    def test_session_clear_endpoint_clears_cookie_safely(self):
        # 1. Bootstrap to get a valid session
        boot = self.client.post('/api/meals/m-clear/bootstrap', body={
            'participants': [{'id': 'O', 'name': 'Org', 'organizer': True}]
        })
        self.assertEqual(boot['status'], 201)
        cookie_header = boot['headers']['Set-Cookie']
        self.assertIn('settletable_session=', cookie_header)
        org_cred = boot['json']['sessions'][0]['credential']

        # 2. Verify snapshot works with cookie
        snap = self.client.get('/api/meals/m-clear/snapshot', headers={'HTTP_COOKIE': f'settletable_session={org_cred}'})
        self.assertEqual(snap['status'], 200)
        self.assertEqual(snap['json']['current_participant_id'], 'O')

        # 3. Call POST /api/session/clear
        clear_res = self.client.post('/api/session/clear', body={}, headers={'HTTP_COOKIE': f'settletable_session={org_cred}'})
        self.assertEqual(clear_res['status'], 200)
        self.assertEqual(clear_res['json'], {'ok': True, 'cleared': True})
        set_cookie = clear_res['headers']['Set-Cookie']
        self.assertIn('settletable_session=', set_cookie)
        self.assertIn('Max-Age=0', set_cookie)
        self.assertIn('HttpOnly', set_cookie)
        self.assertIn('SameSite=Strict', set_cookie)

        # 4. Also test POST /api/meals/{meal_id}/session/exit
        exit_res = self.client.post('/api/meals/m-clear/session/exit', body={}, headers={'HTTP_COOKIE': f'settletable_session={org_cred}'})
        self.assertEqual(exit_res['status'], 200)
        self.assertEqual(exit_res['json'], {'ok': True, 'cleared': True})
        self.assertIn('Max-Age=0', exit_res['headers']['Set-Cookie'])

        # 5. Snapshot without cookie fails with 401
        unauth_snap = self.client.get('/api/meals/m-clear/snapshot')
        self.assertEqual(unauth_snap['status'], 401)

    def test_static_index_html_serving(self):
        res = self.client.get('/')
        self.assertEqual(res['status'], 200)
        self.assertEqual(res['headers']['Content-Type'], 'text/html; charset=utf-8')
        self.assertEqual(res['headers']['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(res['headers']['Referrer-Policy'], 'no-referrer')
        self.assertEqual(res['headers']['Cache-Control'], 'no-store, no-cache, must-revalidate')
        self.assertIn("default-src 'self'", res['headers']['Content-Security-Policy'])
        self.assertIn(b'<!DOCTYPE html>', res['body'])
        self.assertIn(b'SettleTable', res['body'])

    def test_static_invite_shell_serving(self):
        # 43-character invitation token path serves HTML shell for client-side routing
        dummy_token = 'A' * 43
        res = self.client.get(f'/invite/{dummy_token}')
        self.assertEqual(res['status'], 200)
        self.assertEqual(res['headers']['Content-Type'], 'text/html; charset=utf-8')
        self.assertEqual(res['headers']['Cache-Control'], 'no-store, no-cache, must-revalidate')
        self.assertIn(b'<!DOCTYPE html>', res['body'])

        # Invalid token format returns 404
        bad_res = self.client.get('/invite/short_token')
        self.assertEqual(bad_res['status'], 404)

    def test_static_asset_serving_and_mimes(self):
        # style.css
        res_css = self.client.get('/static/style.css')
        self.assertEqual(res_css['status'], 200)
        self.assertEqual(res_css['headers']['Content-Type'], 'text/css; charset=utf-8')
        self.assertEqual(res_css['headers']['X-Content-Type-Options'], 'nosniff')
        self.assertIn(b':root', res_css['body'])

        # app.js
        res_js = self.client.get('/static/app.js')
        self.assertEqual(res_js['status'], 200)
        self.assertEqual(res_js['headers']['Content-Type'], 'application/javascript; charset=utf-8')
        self.assertEqual(res_js['headers']['X-Content-Type-Options'], 'nosniff')
        self.assertIn(b'SettleTable', res_js['body'])

        # favicon.svg & /favicon.ico
        res_fav = self.client.get('/static/favicon.svg')
        self.assertEqual(res_fav['status'], 200)
        self.assertEqual(res_fav['headers']['Content-Type'], 'image/svg+xml')
        self.assertIn(b'<svg', res_fav['body'])

        res_ico = self.client.get('/favicon.ico')
        self.assertEqual(res_ico['status'], 200)
        self.assertEqual(res_ico['headers']['Content-Type'], 'image/svg+xml')

    def test_static_path_traversal_and_unknown_file_rejected(self):
        # Unknown file in static allowlist returns 404
        res_unknown = self.client.get('/static/unknown.txt')
        self.assertEqual(res_unknown['status'], 404)
        self.assertEqual(res_unknown['json']['error'], 'not_found')

        # Path traversal attempts fail regex matching and return 404
        res_trav1 = self.client.get('/static/../transport.py')
        self.assertEqual(res_trav1['status'], 404)

        res_trav2 = self.client.get('/static/%2e%2e%2ftransport.py')
        self.assertEqual(res_trav2['status'], 404)

    def test_snapshot_returns_authenticated_participant_context(self):
        boot = self.client.post('/api/meals/m1/bootstrap', body={
            'participants': [
                {'id': 'O', 'name': 'Organizer', 'organizer': True},
                {'id': 'D', 'name': 'Diner', 'organizer': False},
            ]
        })
        org_cred = boot['json']['sessions'][0]['credential']

        # Organizer snapshot
        snap_org = self.client.get('/api/meals/m1/snapshot',
                                   headers={'HTTP_AUTHORIZATION': f'Bearer {org_cred}'})
        self.assertEqual(snap_org['status'], 200)
        self.assertTrue(snap_org['json']['ok'])
        self.assertEqual(snap_org['json']['current_participant_id'], 'O')
        self.assertTrue(snap_org['json']['is_organizer'])

        # Invite and redeem for Diner
        inv = self.client.post('/api/meals/m1/invitations', body={'participant_id': 'D'},
                               headers={'HTTP_AUTHORIZATION': f'Bearer {org_cred}'})
        token = inv['json']['token']
        redeem = self.client.post(f'/api/meals/m1/invitations/{token}/redeem', body={})
        cookie_header = redeem['headers']['Set-Cookie']
        cookie_val = http.cookies.SimpleCookie(cookie_header)['settletable_session'].value

        # Diner snapshot via cookie
        snap_diner = self.client.get('/api/meals/m1/snapshot',
                                     headers={'HTTP_COOKIE': f'settletable_session={cookie_val}'})
        self.assertEqual(snap_diner['status'], 200)
        self.assertTrue(snap_diner['json']['ok'])
        self.assertEqual(snap_diner['json']['current_participant_id'], 'D')
        self.assertFalse(snap_diner['json']['is_organizer'])

    def test_assign_participant_quantity_endpoint(self):
        boot = self.client.post('/api/meals/m1/bootstrap', body={
            'participants': [
                {'id': 'O', 'name': 'Organizer', 'organizer': True},
                {'id': 'D', 'name': 'Diner', 'organizer': False},
            ]
        })
        org_cred = boot['json']['sessions'][0]['credential']

        # Organizer sets receipt
        rcpt_cmd = {
            'kind': 'ReplaceReceipt',
            'command_id': 'cmd-rcpt',
            'expected_revision': 0,
            'expected_financial_revision': 0,
            'receipt': {
                'items': [{'id': 'item-1', 'label': 'Noodles', 'quantity': 2, 'line_sen': 1200}],
                'subtotal_sen': 1200,
                'total_sen': 1200,
            }
        }
        self.client.post('/api/meals/m1/apply', body=rcpt_cmd,
                         headers={'HTTP_AUTHORIZATION': f'Bearer {org_cred}'})

        # Diner obtains session via invite
        inv = self.client.post('/api/meals/m1/invitations', body={'participant_id': 'D'},
                               headers={'HTTP_AUTHORIZATION': f'Bearer {org_cred}'})
        token = inv['json']['token']
        redeem = self.client.post(f'/api/meals/m1/invitations/{token}/redeem', body={})
        diner_cookie = http.cookies.SimpleCookie(redeem['headers']['Set-Cookie'])['settletable_session'].value

        # 1. Diner attempting AssignParticipantQuantity is rejected with 403
        bad_assign = self.client.post('/api/meals/m1/apply', body={
            'kind': 'AssignParticipantQuantity',
            'command_id': 'cmd-bad',
            'participant_id': 'O',
            'item_id': 'item-1',
            'quantity': 1,
            'expected_item_revision': 1,
            'expected_financial_revision': 1,
        }, headers={'HTTP_COOKIE': f'settletable_session={diner_cookie}'})
        self.assertEqual(bad_assign['status'], 403)

        # 2. Organizer assigns quantity 1 to Diner D
        assign_d = self.client.post('/api/meals/m1/apply', body={
            'kind': 'AssignParticipantQuantity',
            'command_id': 'cmd-assign-d',
            'participant_id': 'D',
            'item_id': 'item-1',
            'quantity': 1,
            'expected_item_revision': 1,
            'expected_financial_revision': 1,
        }, headers={'HTTP_AUTHORIZATION': f'Bearer {org_cred}'})
        self.assertEqual(assign_d['status'], 200)
        self.assertEqual(assign_d['json']['changed_claims'][0]['participant_id'], 'D')
        self.assertEqual(assign_d['json']['changed_claims'][0]['assigned_by'], 'O')

        # 3. Check snapshot reflects auditability
        snap = self.client.get('/api/meals/m1/snapshot',
                               headers={'HTTP_AUTHORIZATION': f'Bearer {org_cred}'})
        claim = snap['json']['claims'][0]
        self.assertEqual(claim['participant_id'], 'D')
        self.assertEqual(claim['assigned_by'], 'O')



if __name__ == '__main__':
    unittest.main()
