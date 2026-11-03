"""End-to-end user journey, contract verification, and regression tests for SettleTable Browser MVP."""
import http.cookies
from io import BytesIO
import json
from pathlib import Path
import re
import tempfile
import unittest

from settletable.transport import SettleTableApp


def parse_sen_py(input_val):
    """Python reference implementation mirroring app.js parseSen strict validation."""
    if not isinstance(input_val, str):
        raise ValueError('Price must be a string')
    s = input_val.strip()
    if s.upper().startswith('RM'):
        s = s[2:].strip()
    if not s or not re.fullmatch(r'[0-9]+(?:\.[0-9]{1,2})?', s):
        raise ValueError(f"Invalid price '{input_val}'. Enter an amount like 12.50 or RM 12.50")
    parts = s.split('.')
    whole = int(parts[0])
    frac_str = (parts[1] if len(parts) > 1 else '').ljust(2, '0')
    frac = int(frac_str)
    total_sen = whole * 100 + frac
    if total_sen < 0 or total_sen > 1_000_000_000:
        raise ValueError('Price out of bounds: maximum RM 10,000,000.00')
    return total_sen


class IsolatedBrowserSession:
    """Simulates an isolated browser context with separate cookies and headers."""

    def __init__(self, app, origin='http://localhost:8000', host='localhost:8000'):
        self.app = app
        self.origin = origin
        self.host = host
        self.cookies = {}

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

        # Attach cookie header if session cookie exists
        if self.cookies and 'HTTP_COOKIE' not in hdrs:
            cookie_strs = [f'{k}={v}' for k, v in self.cookies.items()]
            environ['HTTP_COOKIE'] = '; '.join(cookie_strs)

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
            if 'CONTENT_LENGTH' not in hdrs:
                environ['CONTENT_LENGTH'] = str(len(raw_body))

        for k, v in hdrs.items():
            environ[k] = v

        response_status = [None]
        response_headers = [None]

        def start_response(status, resp_hdrs):
            response_status[0] = status
            response_headers[0] = resp_hdrs

        chunks = self.app(environ, start_response)
        body_out = b''.join(chunks)

        # Store Set-Cookie headers into session cookie jar
        if response_headers[0]:
            for h_name, h_val in response_headers[0]:
                if h_name.lower() == 'set-cookie':
                    cookie = http.cookies.SimpleCookie(h_val)
                    for k, m in cookie.items():
                        self.cookies[k] = m.value

        status_code = int(response_status[0].split()[0])
        parsed_json = None
        try:
            parsed_json = json.loads(body_out.decode('utf-8'))
        except Exception:
            pass

        return {
            'status': status_code,
            'headers': dict(response_headers[0] or []),
            'body': body_out,
            'json': parsed_json,
        }

    def get(self, path, headers=None):
        return self.request('GET', path, headers=headers)

    def post(self, path, body=None, headers=None, remote_addr='127.0.0.1'):
        return self.request('POST', path, body=body, headers=headers, remote_addr=remote_addr)


class BrowserMvpE2ETests(unittest.TestCase):
    def setUp(self):
        scratch = Path('.local/tests')
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / 'e2e.sqlite'
        self.clock_val = 1000.0
        self.app = SettleTableApp(self.db_path, clock=lambda: self.clock_val)
        self.addCleanup(self.app.close)

    def test_strict_myr_input_parsing_contract(self):
        # Valid amounts
        self.assertEqual(parse_sen_py('12'), 1200)
        self.assertEqual(parse_sen_py('12.5'), 1250)
        self.assertEqual(parse_sen_py('12.50'), 1250)
        self.assertEqual(parse_sen_py('RM 12.50'), 1250)
        self.assertEqual(parse_sen_py('rm 0.05'), 5)
        self.assertEqual(parse_sen_py('0.01'), 1)
        self.assertEqual(parse_sen_py('10000000.00'), 1_000_000_000)

        # Invalid amounts must raise ValueError rather than returning 0
        invalid_cases = [
            '', '   ', 'abc', '-5', '12.345', '12.34.56', 'RM', '10000000.01', None, 123
        ]
        for bad in invalid_cases:
            with self.assertRaises(ValueError, msg=f'Expected failure for: {bad!r}'):
                parse_sen_py(bad)

    def test_replace_receipt_contract_complete_monetary_facts(self):
        organizer = IsolatedBrowserSession(self.app)
        boot = organizer.post('/api/meals/m1/bootstrap', body={
            'participants': [{'id': 'O', 'name': 'Organizer', 'organizer': True}]
        })
        self.assertEqual(boot['status'], 201)
        # Store cookie
        org_cred = boot['json']['sessions'][0]['credential']
        organizer.cookies['settletable_session'] = org_cred

        # 1. ReplaceReceipt with complete monetary facts
        subtotal = 3000
        total = 3000
        replace_res = organizer.post('/api/meals/m1/apply', body={
            'kind': 'ReplaceReceipt',
            'command_id': 'rcpt-1',
            'expected_revision': 0,
            'expected_financial_revision': 0,
            'receipt': {
                'items': [
                    {'id': 'item-1', 'label': 'Nasi Lemak', 'quantity': 1, 'line_sen': 2000},
                    {'id': 'item-2', 'label': 'Kopi O', 'quantity': 1, 'line_sen': 1000},
                ],
                'subtotal_sen': subtotal,
                'total_sen': total,
                'adjustments': [],
                'included_tax_sen': 0,
            }
        })
        self.assertEqual(replace_res['status'], 200)

        # Check snapshot shows zero receipt issues
        snap = organizer.get('/api/meals/m1/snapshot')
        self.assertEqual(snap['status'], 200)
        self.assertEqual(snap['json']['issues'], ['incomplete_quantity'])  # only claim issue remains
        receipt_digest = snap['json']['receipt_digest']

        # ReviewReceipt succeeds
        rev_res = organizer.post('/api/meals/m1/apply', body={
            'kind': 'ReviewReceipt',
            'command_id': 'rev-1',
            'expected_revision': snap['json']['revision'],
            'expected_financial_revision': snap['json']['financial_revision'],
            'receipt_digest': receipt_digest,
        })
        self.assertEqual(rev_res['status'], 200)

    def test_two_isolated_browser_contexts_vertical_user_journey(self):
        # Window 1: Organizer (Alice)
        alice = IsolatedBrowserSession(self.app)
        # Window 2: Diner (Bob)
        bob = IsolatedBrowserSession(self.app)

        # 1. Alice creates meal
        boot = alice.post('/api/meals/m-journey/bootstrap', body={
            'participants': [
                {'id': 'A', 'name': 'Alice', 'organizer': True},
                {'id': 'B', 'name': 'Bob', 'organizer': False},
            ]
        })
        self.assertEqual(boot['status'], 201)
        alice_cred = boot['json']['sessions'][0]['credential']
        alice.cookies['settletable_session'] = alice_cred

        # 2. Alice adds two receipt items
        items = [
            {'id': 'item-1', 'label': 'Burger Set', 'quantity': 2, 'line_sen': 2400},
            {'id': 'item-2', 'label': 'Iced Tea', 'quantity': 2, 'line_sen': 600},
        ]
        subtotal = 3000
        total = 3000
        rcpt_res = alice.post('/api/meals/m-journey/apply', body={
            'kind': 'ReplaceReceipt',
            'command_id': 'rcpt-1',
            'expected_revision': 0,
            'expected_financial_revision': 0,
            'receipt': {
                'items': items,
                'subtotal_sen': subtotal,
                'total_sen': total,
                'adjustments': [],
                'included_tax_sen': 0,
            }
        })
        self.assertEqual(rcpt_res['status'], 200)

        # Alice verifies totals and reviews receipt
        snap_alice = alice.get('/api/meals/m-journey/snapshot')
        self.assertEqual(snap_alice['status'], 200)
        self.assertEqual(snap_alice['json']['receipt']['subtotal_sen'], 3000)
        self.assertEqual(snap_alice['json']['receipt']['total_sen'], 3000)
        digest = snap_alice['json']['receipt_digest']

        rev_res = alice.post('/api/meals/m-journey/apply', body={
            'kind': 'ReviewReceipt',
            'command_id': 'rev-1',
            'expected_revision': snap_alice['json']['revision'],
            'expected_financial_revision': snap_alice['json']['financial_revision'],
            'receipt_digest': digest,
        })
        self.assertEqual(rev_res['status'], 200)

        # 3. Alice creates invitation for Bob
        inv_res = alice.post('/api/meals/m-journey/invitations', body={'participant_id': 'B'})
        self.assertEqual(inv_res['status'], 201)
        token = inv_res['json']['token']

        # 4. Bob joins in separate browser context
        # Bob inspects unauthenticated landing
        inspect_res = bob.get(f'/api/invitations/{token}')
        self.assertEqual(inspect_res['status'], 200)
        self.assertTrue(inspect_res['json']['valid'])
        self.assertEqual(inspect_res['json']['participant_name'], 'Bob')

        # Bob redeems invitation, setting HttpOnly cookie in Bob's browser session
        redeem_res = bob.post(f'/api/meals/m-journey/invitations/{token}/redeem', body={})
        self.assertEqual(redeem_res['status'], 200)
        self.assertIn('settletable_session', bob.cookies)
        self.assertNotEqual(bob.cookies['settletable_session'], alice.cookies['settletable_session'])

        # Bob checks snapshot: is diner
        snap_bob = bob.get('/api/meals/m-journey/snapshot')
        self.assertEqual(snap_bob['status'], 200)
        self.assertEqual(snap_bob['json']['current_participant_id'], 'B')
        self.assertFalse(snap_bob['json']['is_organizer'])

        # 5. Bob claims 1 Burger Set
        claim_b = bob.post('/api/meals/m-journey/apply', body={
            'kind': 'SetOwnQuantity',
            'command_id': 'claim-bob-1',
            'item_id': 'item-1',
            'quantity': 1,
            'expected_item_revision': snap_bob['json']['items'][0]['item_revision'],
            'expected_financial_revision': snap_bob['json']['financial_revision'],
        })
        self.assertEqual(claim_b['status'], 200)

        # 6. Alice claims 1 Burger Set and 2 Iced Tea
        snap_alice = alice.get('/api/meals/m-journey/snapshot')
        claim_a1 = alice.post('/api/meals/m-journey/apply', body={
            'kind': 'SetOwnQuantity',
            'command_id': 'claim-alice-1',
            'item_id': 'item-1',
            'quantity': 1,
            'expected_item_revision': snap_alice['json']['items'][0]['item_revision'],
            'expected_financial_revision': snap_alice['json']['financial_revision'],
        })
        self.assertEqual(claim_a1['status'], 200)

        snap_alice = alice.get('/api/meals/m-journey/snapshot')
        claim_a2 = alice.post('/api/meals/m-journey/apply', body={
            'kind': 'SetOwnQuantity',
            'command_id': 'claim-alice-2',
            'item_id': 'item-2',
            'quantity': 2,
            'expected_item_revision': snap_alice['json']['items'][1]['item_revision'],
            'expected_financial_revision': snap_alice['json']['financial_revision'],
        })
        self.assertEqual(claim_a2['status'], 200)

        # Both contexts see updated state (all items claimed)
        snap_alice = alice.get('/api/meals/m-journey/snapshot')
        snap_bob = bob.get('/api/meals/m-journey/snapshot')
        self.assertEqual(snap_alice['json']['issues'], [])
        self.assertEqual(snap_bob['json']['issues'], [])

        # 7. Alice finalizes the meal
        fin_res = alice.post('/api/meals/m-journey/apply', body={
            'kind': 'Finalize',
            'command_id': 'fin-1',
            'expected_revision': snap_alice['json']['revision'],
            'expected_financial_revision': snap_alice['json']['financial_revision'],
        })
        self.assertEqual(fin_res['status'], 200)

        # 8. Both contexts display correct per-person RM totals
        snap_alice_fin = alice.get('/api/meals/m-journey/snapshot')
        snap_bob_fin = bob.get('/api/meals/m-journey/snapshot')
        self.assertTrue(snap_alice_fin['json']['finalized'])
        self.assertTrue(snap_bob_fin['json']['finalized'])

        calc_alice = snap_alice_fin['json']['calculation']
        calc_bob = snap_bob_fin['json']['calculation']
        self.assertEqual(calc_alice, calc_bob)

        # Verify exact consumption structure matches authoritative calculator
        self.assertIn('consumption', calc_alice)
        self.assertIn('items', calc_alice)
        self.assertIn('adjustments', calc_alice)

        consumption_map = {c['participant_id']: c['sen'] for c in calc_alice['consumption']}
        # Burger (2400 sen) split 1:1 between Alice and Bob = 1200 sen each
        # Iced Tea (600 sen) 100% to Alice = 600 sen
        # Alice total: 1800 sen (RM 18.00)
        # Bob total: 1200 sen (RM 12.00)
        self.assertEqual(consumption_map['A'], 1800)
        self.assertEqual(consumption_map['B'], 1200)
        self.assertEqual(sum(consumption_map.values()), 3000)

        # 9. Reloading both contexts preserves the expected finalized state
        reload_alice = alice.get('/api/meals/m-journey/snapshot')
        reload_bob = bob.get('/api/meals/m-journey/snapshot')
        self.assertTrue(reload_alice['json']['finalized'])
        self.assertTrue(reload_bob['json']['finalized'])
        reload_map = {c['participant_id']: c['sen'] for c in reload_alice['json']['calculation']['consumption']}
        self.assertEqual(reload_map, consumption_map)

    def test_stale_claim_conflict_rejection_and_recovery(self):
        alice = IsolatedBrowserSession(self.app)
        bob = IsolatedBrowserSession(self.app)

        boot = alice.post('/api/meals/m-conflict/bootstrap', body={
            'participants': [
                {'id': 'A', 'name': 'Alice', 'organizer': True},
                {'id': 'B', 'name': 'Bob', 'organizer': False},
            ]
        })
        alice.cookies['settletable_session'] = boot['json']['sessions'][0]['credential']

        # Add 1 item with total quantity 2
        alice.post('/api/meals/m-conflict/apply', body={
            'kind': 'ReplaceReceipt',
            'command_id': 'rcpt-1',
            'expected_revision': 0,
            'expected_financial_revision': 0,
            'receipt': {
                'items': [{'id': 'item-1', 'label': 'Pizza', 'quantity': 2, 'line_sen': 4000}],
                'subtotal_sen': 4000,
                'total_sen': 4000,
            }
        })
        snap = alice.get('/api/meals/m-conflict/snapshot')
        alice.post('/api/meals/m-conflict/apply', body={
            'kind': 'ReviewReceipt',
            'command_id': 'rev-1',
            'expected_revision': snap['json']['revision'],
            'expected_financial_revision': snap['json']['financial_revision'],
            'receipt_digest': snap['json']['receipt_digest'],
        })

        # Invite Bob
        inv = alice.post('/api/meals/m-conflict/invitations', body={'participant_id': 'B'})
        bob.post(f"/api/meals/m-conflict/invitations/{inv['json']['token']}/redeem", body={})

        # Both Alice and Bob observe item-1 at revision 1
        alice_snap1 = alice.get('/api/meals/m-conflict/snapshot')
        bob_snap1 = bob.get('/api/meals/m-conflict/snapshot')
        item_rev = alice_snap1['json']['items'][0]['item_revision']
        self.assertEqual(item_rev, 1)

        # Bob claims 1 unit at revision 1 -> succeeds, item revision advances to 2
        res_bob = bob.post('/api/meals/m-conflict/apply', body={
            'kind': 'SetOwnQuantity',
            'command_id': 'claim-bob-1',
            'item_id': 'item-1',
            'quantity': 1,
            'expected_item_revision': 1,
            'expected_financial_revision': bob_snap1['json']['financial_revision'],
        })
        self.assertEqual(res_bob['status'], 200)

        # Alice attempts to claim at stale revision 1 -> fails with HTTP 409
        res_alice_stale = alice.post('/api/meals/m-conflict/apply', body={
            'kind': 'SetOwnQuantity',
            'command_id': 'claim-alice-1',
            'item_id': 'item-1',
            'quantity': 1,
            'expected_item_revision': 1,
            'expected_financial_revision': alice_snap1['json']['financial_revision'],
        })
        self.assertEqual(res_alice_stale['status'], 409)
        self.assertEqual(res_alice_stale['json']['error'], 'item_revision_conflict')

        # Alice refreshes snapshot, sees new revision 2, and retries successfully
        alice_snap2 = alice.get('/api/meals/m-conflict/snapshot')
        self.assertEqual(alice_snap2['json']['items'][0]['item_revision'], 2)
        res_alice_retry = alice.post('/api/meals/m-conflict/apply', body={
            'kind': 'SetOwnQuantity',
            'command_id': 'claim-alice-1',
            'item_id': 'item-1',
            'quantity': 1,
            'expected_item_revision': 2,
            'expected_financial_revision': alice_snap2['json']['financial_revision'],
        })
        self.assertEqual(res_alice_retry['status'], 200)

    def test_multi_payer_contributions_journey(self):
        """Simulate browser MVP journey for recording multi-payer restaurant contributions."""
        alice = IsolatedBrowserSession(self.app)
        bob = IsolatedBrowserSession(self.app)

        # 1. Bootstrap meal
        boot = alice.post('/api/meals/m-funding/bootstrap', body={
            'participants': [
                {'id': 'p-alice', 'name': 'Alice', 'organizer': True},
                {'id': 'p-bob', 'name': 'Bob', 'organizer': False},
            ]
        })
        self.assertEqual(boot['status'], 201)

        # 2. Invite & redeem Bob
        inv = alice.post('/api/meals/m-funding/invitations', body={'participant_id': 'p-bob'})
        token = inv['json']['token']
        redeem = bob.post(f'/api/meals/m-funding/invitations/{token}/redeem', body={})
        self.assertEqual(redeem['status'], 200)

        # 3. Organizer sets receipt: Total RM 50.00
        snap = alice.get('/api/meals/m-funding/snapshot')['json']
        alice.post('/api/meals/m-funding/apply', body={
            'kind': 'ReplaceReceipt',
            'command_id': 'rcpt-1',
            'expected_revision': snap['revision'],
            'expected_financial_revision': snap['financial_revision'],
            'receipt': {
                'items': [{'id': 'item-1', 'label': 'Nasi Lemak', 'quantity': 1, 'line_sen': 5000}],
                'subtotal_sen': 5000,
                'total_sen': 5000,
            }
        })

        # 4. Bob claims item-1
        snap = bob.get('/api/meals/m-funding/snapshot')['json']
        bob.post('/api/meals/m-funding/apply', body={
            'kind': 'SetOwnQuantity',
            'command_id': 'claim-1',
            'item_id': 'item-1',
            'quantity': 1,
            'expected_item_revision': snap['items'][0]['item_revision'],
            'expected_financial_revision': snap['financial_revision'],
        })

        # 5. Review & Finalize
        snap = alice.get('/api/meals/m-funding/snapshot')['json']
        alice.post('/api/meals/m-funding/apply', body={
            'kind': 'ReviewReceipt',
            'command_id': 'rv-1',
            'expected_revision': snap['revision'],
            'expected_financial_revision': snap['financial_revision'],
            'receipt_digest': snap['receipt_digest'],
        })
        snap = alice.get('/api/meals/m-funding/snapshot')['json']
        alice.post('/api/meals/m-funding/apply', body={
            'kind': 'Finalize',
            'command_id': 'fin-1',
            'expected_revision': snap['revision'],
            'expected_financial_revision': snap['financial_revision'],
        })

        # 6. Verify Initial Funding: not_funded
        snap = alice.get('/api/meals/m-funding/snapshot')['json']
        self.assertEqual(snap['funding']['status'], 'not_funded')
        self.assertEqual(snap['funding']['unfunded_sen'], 5000)

        # 7. Bob (diner) attempts to record contribution -> 403 Forbidden
        res_bob_pay = bob.post('/api/meals/m-funding/apply', body={
            'kind': 'RecordContribution',
            'command_id': 'pay-bob-unauth',
            'expected_revision': snap['revision'],
            'participant_id': 'p-bob',
            'amount_sen': 2000,
            'payment_method': 'cash',
        })
        self.assertEqual(res_bob_pay['status'], 403)

        # 8. Alice (organizer) records Bob's payment of RM 20.00 cash
        res_pay1 = alice.post('/api/meals/m-funding/apply', body={
            'kind': 'RecordContribution',
            'command_id': 'pay-bob-1',
            'expected_revision': snap['revision'],
            'participant_id': 'p-bob',
            'amount_sen': 2000,
            'payment_method': 'cash',
        })
        self.assertEqual(res_pay1['status'], 200)
        self.assertTrue(res_pay1['json']['ok'])
        contrib1_id = res_pay1['json']['contribution_id']

        # 9. Verify Partially Funded
        snap = alice.get('/api/meals/m-funding/snapshot')['json']
        self.assertEqual(snap['funding']['status'], 'partially_funded')
        self.assertEqual(snap['funding']['total_contributed_sen'], 2000)
        self.assertEqual(snap['funding']['unfunded_sen'], 3000)

        # 10. Alice records her own payment of RM 30.00 card
        res_pay2 = alice.post('/api/meals/m-funding/apply', body={
            'kind': 'RecordContribution',
            'command_id': 'pay-alice-1',
            'expected_revision': snap['revision'],
            'participant_id': 'p-alice',
            'amount_sen': 3000,
            'payment_method': 'card',
        })
        self.assertEqual(res_pay2['status'], 200)

        # 11. Verify Fully Funded & Net Balances
        snap = alice.get('/api/meals/m-funding/snapshot')['json']
        self.assertEqual(snap['funding']['status'], 'fully_funded')
        self.assertEqual(snap['funding']['total_contributed_sen'], 5000)
        self.assertEqual(snap['funding']['unfunded_sen'], 0)
        # Alice consumed 0, paid 3000 -> net +3000 (creditor)
        # Bob consumed 5000, paid 2000 -> net -3000 (debtor)
        b_map = {b['participant_id']: b['net_sen'] for b in snap['funding']['net_balances']}
        self.assertEqual(b_map['p-alice'], 3000)
        self.assertEqual(b_map['p-bob'], -3000)

        # 12. Reverse Bob's payment
        res_rev = alice.post('/api/meals/m-funding/apply', body={
            'kind': 'ReverseContribution',
            'command_id': 'rev-bob-1',
            'expected_revision': snap['revision'],
            'contribution_id': contrib1_id,
            'reason': 'Customer requested refund',
        })
        self.assertEqual(res_rev['status'], 200)

        snap = alice.get('/api/meals/m-funding/snapshot')['json']
        self.assertEqual(snap['funding']['status'], 'partially_funded')
        self.assertEqual(snap['funding']['total_contributed_sen'], 3000)
        self.assertEqual(snap['funding']['unfunded_sen'], 2000)


if __name__ == '__main__':
    unittest.main()
