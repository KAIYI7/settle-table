"""Experimental synthetic checkout demo: real SQLite and a loopback stub bridge.

The stub (``checkout_demo_stub``) follows the KP-SETTLETABLE-TNG-01 v2.1 wire
contract. All credentials are disposable random test tokens.
"""
from dataclasses import asdict
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import patch
import uuid

from settletable import checkout_demo as demo
from settletable.authority import (Authority, AuthorityError, AssignParticipantQuantity, Finalize, Participant,
    Receipt, ReceiptItem, RecordContribution, RecordTransfer, ReplaceReceipt, ReportTransfer, ReviewReceipt)
from settletable.checkout_demo import (CheckoutDemoClient, CheckoutDemoConfig, checkout_reference,
    checkout_demo_status, display_status, request_checkout_demo, validate_checkout)
from settletable.transport import SettleTableApp
from checkout_demo_stub import StubBridge
from test_transport import TransportTestClient

NAMESPACE = '6f1d7a52-3c8e-4f0b-9a51-2d7e6b9c4a10'
REPO = Path(__file__).resolve().parent.parent
# SHA-256 of settletable/payment_simulation.py at main 9e63178: must stay byte-identical.
I06_SHA256 = '0a35e36e2458fcb4b587cf5899b52890c94b4bf2a4d401c16d06f2fbd8349ab0'
FINANCIAL_TABLES = ('meals', 'participants', 'commands', 'payer_contributions', 'peer_transfers',
                    'pending_contributions', 'pending_transfers', 'payment_simulations')


def token():
    return secrets.token_urlsafe(32)


class RecordingClient:
    def __init__(self, *outcomes):
        self.calls = []
        self.outcomes = list(outcomes) or [{'transport': 'REQUEST_UNKNOWN', 'retry_after': None}]

    def request(self, method, reference, amount):
        self.calls.append((method, reference, amount))
        return self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]


class DemoFixture(unittest.TestCase):
    """Organizer A paid the whole bill; diners B (RM8.63) and C (RM5.00) owe A."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'demo.sqlite'
        self.now = 1000.0
        self.authority = Authority(self.path, clock=lambda: self.now)
        self.addCleanup(lambda: self.authority.close())
        grants = self.authority.bootstrap('meal', (Participant('A', 'Organizer', True),
            Participant('B', 'Demo Diner'), Participant('C', 'Other Diner')))
        self.cred = {s.participant_id: s.credential for s in grants.sessions}
        self.bridge_token = token()
        self.bridge = StubBridge(self.bridge_token)
        self.addCleanup(self.bridge.close)
        self.cfg = CheckoutDemoConfig(NAMESPACE, self.bridge.base_url, self.bridge_token)
        self.client = CheckoutDemoClient(self.cfg)

    def snap(self, who='A'):
        return self.authority.snapshot(self.cred[who], 'meal')

    def apply(self, command, who='A'):
        return self.authority.apply(self.cred[who], 'meal', command)

    def finalize(self, payer='A'):
        s = self.snap()
        items = (ReceiptItem('a', 'Organizer dish', 1, 1000), ReceiptItem('b', 'Diner dish', 1, 863),
                 ReceiptItem('c', 'Other dish', 1, 500))
        self.apply(ReplaceReceipt('receipt', s.revision, s.financial_revision, Receipt(items, 2363, 2363)))
        for item, person in (('a', 'A'), ('b', 'B'), ('c', 'C')):
            s = self.snap()
            revision = {i.item_id: i.item_revision for i in s.items}[item]
            self.apply(AssignParticipantQuantity('assign-' + item, person, item, Fraction(1), revision,
                                                 s.financial_revision))
        s = self.snap()
        self.apply(ReviewReceipt('review', s.revision, s.financial_revision, s.receipt_digest))
        s = self.snap()
        self.apply(Finalize('final', s.revision, s.financial_revision))
        s = self.snap()
        self.apply(RecordContribution('pay', s.revision, payer, 2363, 'card'))

    def record_transfer(self, command_id, sender, amount, receiver='A'):
        self.apply(RecordTransfer(command_id, self.snap().revision, sender, receiver, amount))

    def request(self, sender='B', amount=863, who='A', client=None):
        return request_checkout_demo(self.authority, self.cred[who], 'meal', self.cfg, client or self.client,
                                     sender, amount)

    def status(self, who='A', client=None):
        return checkout_demo_status(self.authority, self.cred[who], 'meal', self.cfg, client or self.client)

    def financial_state(self):
        db = self.authority._db
        tables = {name: db.execute(f'SELECT * FROM {name} ORDER BY rowid').fetchall() for name in FINANCIAL_TABLES}
        return tables, asdict(self.snap()).get('settlement'), asdict(self.snap()).get('funding')

    def code(self, call):
        with self.assertRaises(AuthorityError) as caught:
            call()
        return caught.exception.code

    def rows(self):
        return self.authority._db.execute('SELECT attempt,state,dispatch_count FROM checkout_demos ORDER BY attempt').fetchall()

    def wire(self):
        return [(m, p.rsplit('/', 1)[-1]) for m, p, _, _ in self.bridge.calls]


class ConfigurationTests(unittest.TestCase):
    def env(self, **extra):
        base = {'SETTLETABLE_CHECKOUT_DEMO_ENABLED': '1', 'SETTLETABLE_CHECKOUT_DEMO_NAMESPACE': NAMESPACE,
                'SETTLETABLE_CHECKOUT_DEMO_BASE_URL': 'http://127.0.0.1:28082',
                'SETTLETABLE_CHECKOUT_DEMO_CREDENTIAL': 'x' * 40}
        base.update(extra)
        return {k: v for k, v in base.items() if v is not None}

    def test_disabled_by_default_and_malformed_values_fail_startup(self):
        self.assertIsNone(CheckoutDemoConfig.from_env({}))
        self.assertIsNone(CheckoutDemoConfig.from_env({'SETTLETABLE_CHECKOUT_DEMO_ENABLED': '0'}))
        self.assertEqual(CheckoutDemoConfig.from_env(self.env()).base_url, 'http://127.0.0.1:28082')
        for bad in ({'SETTLETABLE_CHECKOUT_DEMO_ENABLED': 'true'},
                    {'SETTLETABLE_CHECKOUT_DEMO_NAMESPACE': None},
                    {'SETTLETABLE_CHECKOUT_DEMO_NAMESPACE': NAMESPACE.upper()},
                    {'SETTLETABLE_CHECKOUT_DEMO_BASE_URL': None},
                    {'SETTLETABLE_CHECKOUT_DEMO_CREDENTIAL': None},
                    {'SETTLETABLE_CHECKOUT_DEMO_CREDENTIAL': 'short'},
                    {'SETTLETABLE_CHECKOUT_DEMO_CREDENTIAL': 'x' * 39 + ' '},
                    {'SETTLETABLE_KAIPAY_NAMESPACE': NAMESPACE},
                    {'SETTLETABLE_CHECKOUT_DEMO_CA_FILE': 'ca.pem'},
                    {'SETTLETABLE_CHECKOUT_DEMO_CA_FILE': ''},
                    {'SETTLETABLE_CHECKOUT_DEMO_CREDENTIALS_FILE': 'also-set.json'}):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, 'invalid_checkout_demo_configuration'):
                CheckoutDemoConfig.from_env(self.env(**bad))

    def test_destination_rules(self):
        for url in ('http://example.org', 'http://10.0.0.1:28082', 'http://127.0.0.1:28082/api',
                    'https://user:pass@example.org', 'https://example.org?q=1', 'ftp://127.0.0.1',
                    'http://127.0.0.1:0', 'http://127.0.0.1#frag'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                CheckoutDemoConfig(NAMESPACE, url, 'x' * 40)
        CheckoutDemoConfig(NAMESPACE, 'http://localhost:28082', 'x' * 40)
        CheckoutDemoConfig(NAMESPACE, 'https://bridge.example.org', 'x' * 40, ca_file='ca.pem')
        config = CheckoutDemoConfig(NAMESPACE, 'http://[::1]:28082', 'secret-' + 'x' * 40)
        self.assertNotIn('secret-', repr(config))

    def test_container_credentials_file(self):
        with tempfile.TemporaryDirectory() as folder:
            good = Path(folder) / 'demo.json'
            good.write_text(json.dumps({'credential': 'y' * 40}))
            env = self.env(SETTLETABLE_CHECKOUT_DEMO_CREDENTIAL=None,
                           SETTLETABLE_CHECKOUT_DEMO_CREDENTIALS_FILE=str(good))
            self.assertEqual(CheckoutDemoConfig.from_env(env).credential, 'y' * 40)
            for content in ('{"credential":"' + 'y' * 40 + '","extra":1}', '{"credential":1}',
                            '{"credential":"a","credential":"' + 'y' * 40 + '"}', 'not json', '[]'):
                good.write_text(content)
                with self.subTest(content=content), self.assertRaises(ValueError):
                    CheckoutDemoConfig.from_env(env)
            missing = dict(env, SETTLETABLE_CHECKOUT_DEMO_CREDENTIALS_FILE=str(Path(folder) / 'missing.json'))
            with self.assertRaises(ValueError):
                CheckoutDemoConfig.from_env(missing)

    def test_https_client_uses_only_its_own_ca_file(self):
        with patch('ssl.create_default_context') as context, \
                patch('socket.getaddrinfo', return_value=[(None, None, None, None, ('203.0.113.9', 443))]):
            CheckoutDemoClient(CheckoutDemoConfig(NAMESPACE, 'https://bridge.example.org', 'x' * 40, 'demo-ca.pem'))
        context.assert_called_once_with(cafile='demo-ca.pem')
        self.assertNotIn('SSL_CERT_FILE', os.environ)
        with patch('socket.getaddrinfo', return_value=[(None, None, None, None, ('203.0.113.9', 80))]):
            with self.assertRaises(ValueError):
                CheckoutDemoClient(CheckoutDemoConfig(NAMESPACE, 'http://localhost:28082', 'x' * 40))

    def test_app_startup_fails_when_enabled_but_malformed(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, self.env(
                SETTLETABLE_CHECKOUT_DEMO_BASE_URL='http://example.org'), clear=False):
            with self.assertRaisesRegex(ValueError, 'invalid_checkout_demo_configuration'):
                SettleTableApp(Path(folder) / 'x.sqlite')


class PureContractTests(unittest.TestCase):
    def test_golden_reference_basis_and_amount_exclusion(self):
        basis = ('meal-demo-01', 'p-organizer', 'finalize-01', 'p-diner', 'p-organizer')
        ref = checkout_reference(NAMESPACE, *basis, 1)
        expected = str(uuid.uuid5(uuid.UUID(NAMESPACE), json.dumps(
            ['checkout-demo-v1', *basis, 1], separators=(',', ':'))))
        self.assertEqual(ref, expected)
        self.assertEqual(ref, '3ba5430c-9e6e-5ab7-9425-13c92f02164b')
        self.assertNotEqual(ref, checkout_reference(NAMESPACE, *basis, 2))
        self.assertNotEqual(ref, checkout_reference(str(uuid.uuid4()), *basis, 1))
        for index in range(len(basis)):
            changed = list(basis)
            changed[index] = changed[index].upper()
            self.assertNotEqual(ref, checkout_reference(NAMESPACE, *changed, 1))
        for attempt in (0, True, 51, '1'):
            with self.assertRaises(AuthorityError):
                checkout_reference(NAMESPACE, *basis, attempt)

    def test_display_mapping_checks_evidence_first(self):
        statuses = ('AWAITING_PAYMENT', 'PAYMENT_DETECTED', 'AWAITING_VERIFICATION', 'MANUALLY_CONFIRMED',
                    'AMBIGUOUS', 'EXPIRED', 'REVIEW_EXPIRED', 'REFUNDED')
        expected = {
            ('AWAITING_PAYMENT', 'NONE'): 'AWAITING_EVIDENCE',
            ('PAYMENT_DETECTED', 'SYNTHETIC'): 'EVIDENCE_DETECTED',
            ('AWAITING_VERIFICATION', 'SYNTHETIC'): 'EVIDENCE_DETECTED',
            ('AMBIGUOUS', 'NONE'): 'NEEDS_REVIEW', ('AMBIGUOUS', 'SYNTHETIC'): 'NEEDS_REVIEW',
            ('MANUALLY_CONFIRMED', 'SYNTHETIC'): 'MANUALLY_CONFIRMED',
            ('EXPIRED', 'NONE'): 'EXPIRED', ('EXPIRED', 'SYNTHETIC'): 'EXPIRED',
            ('REVIEW_EXPIRED', 'NONE'): 'EXPIRED', ('REVIEW_EXPIRED', 'SYNTHETIC'): 'EXPIRED',
        }
        for status in statuses:
            for evidence in ('NONE', 'SYNTHETIC', 'NOTIFICATION_UNVERIFIED', 'GENUINE'):
                with self.subTest(status=status, evidence=evidence):
                    self.assertEqual(display_status(status, evidence),
                                     expected.get((status, evidence), 'UNEXPECTED_STATUS'))

    def test_checkout_body_is_an_exact_allowlist(self):
        good = {'reference': str(uuid.uuid4()), 'checkoutId': str(uuid.uuid4()), 'amountMinor': 863,
                'status': 'AWAITING_PAYMENT', 'evidence': 'NONE', 'createdAt': '2026-11-17T04:00:00.123456789Z',
                'expiresAt': '2026-11-17T04:10:00Z', 'reviewExpiresAt': None, 'revision': 1}
        self.assertEqual(validate_checkout(dict(good)), good)
        validate_checkout(dict(good, reviewExpiresAt='2026-11-17T04:30:00+08:00', revision=0))
        broken = [dict(good, payerToken='x'), {k: v for k, v in good.items() if k != 'revision'},
                  dict(good, amountMinor=True), dict(good, amountMinor='863'), dict(good, amountMinor=0),
                  dict(good, revision=-1), dict(good, revision=1.0), dict(good, checkoutId=good['checkoutId'].upper()),
                  dict(good, status='paid<script>'), dict(good, evidence=None),
                  dict(good, createdAt='2026-11-17T04:00:00'), dict(good, expiresAt='yesterday'),
                  dict(good, reviewExpiresAt=0)]
        for body in broken:
            with self.subTest(body=body), self.assertRaises(ValueError):
                validate_checkout(body)

    def test_i06_module_is_byte_identical(self):
        data = (REPO / 'settletable' / 'payment_simulation.py').read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), I06_SHA256)


class EligibilityTests(DemoFixture):
    def test_draft_meal_creates_nothing_and_sends_nothing(self):
        client = RecordingClient()
        self.assertEqual(self.code(lambda: self.request(client=client)), 'meal_not_finalized')
        self.assertEqual(self.code(lambda: self.status(client=client)), 'meal_not_finalized')
        self.assertEqual((client.calls, self.rows()), ([], []))

    def test_only_organizer_reads_or_initiates(self):
        self.finalize()
        client = RecordingClient()
        for who in ('B', 'C'):
            self.assertEqual(self.code(lambda: self.request(who=who, client=client)), 'forbidden')
            self.assertEqual(self.code(lambda: self.status(who=who, client=client)), 'forbidden')
        self.assertEqual((client.calls, self.rows()), ([], []))

    def test_target_must_be_a_current_suggestion_to_the_organizer(self):
        self.finalize(payer='B')  # B paid: A and C now owe B, nothing is owed to the organizer.
        client = RecordingClient()
        suggestions = {(s.sender_id, s.receiver_id) for s in self.snap().settlement.suggested_transfers}
        self.assertIn(('C', 'B'), suggestions)
        self.assertEqual(self.status(client=client)['eligible'], [])
        for sender, amount in (('C', 500), ('A', 1000), ('B', 863)):
            self.assertEqual(self.code(lambda: self.request(sender, amount, client=client)), 'checkout_demo_stale')
        self.assertEqual((client.calls, self.rows()), ([], []))

    def test_amount_must_match_and_one_open_intent_per_meal(self):
        self.finalize()
        eligible = self.status()['eligible']
        self.assertEqual(eligible, [
            {'senderId': 'B', 'receiverId': 'A', 'amountSen': 863, 'action': 'NEW'},
            {'senderId': 'C', 'receiverId': 'A', 'amountSen': 500, 'action': 'NEW'}])
        self.assertEqual(self.code(lambda: self.request('B', 862)), 'checkout_demo_stale')
        self.assertEqual(self.request()['intent']['state'], 'AWAITING_EVIDENCE')
        self.assertEqual(self.status()['eligible'], [])
        self.assertEqual(self.code(lambda: self.request('C', 500)), 'checkout_demo_active')
        self.assertEqual(self.code(lambda: self.request('B', 863)), 'checkout_demo_active')
        self.assertEqual([m for m, _ in self.wire()].count('PUT'), 1)


class LifecycleTests(DemoFixture):
    def test_full_synthetic_flow_wire_contract_and_financial_invariance(self):
        self.finalize()
        before = self.financial_state()
        result = self.request()
        intent = result['intent']
        method, path, headers, body = self.bridge.calls[0]
        self.assertEqual((method, path), ('PUT', '/api/integrations/checkouts/' + intent['reference']))
        self.assertEqual(body, b'{"amountMinor":863,"currency":"MYR"}')
        self.assertEqual(headers['Authorization'], 'Bearer ' + self.bridge_token)
        self.assertEqual(headers['Content-Type'], 'application/json')
        self.assertNotIn('Cookie', headers)
        self.assertEqual(intent['reference'], checkout_reference(NAMESPACE, 'meal', 'A', 'final', 'B', 'A', 1))
        self.assertEqual((intent['state'], intent['revision'], intent['possibleDispatches']), ('AWAITING_EVIDENCE', 1, 1))
        self.assertTrue(result['synthetic'])
        self.assertNotIn(self.bridge_token, json.dumps(result))
        self.assertEqual(self.financial_state(), before)
        self.bridge.simulate_candidate(intent['reference'])
        self.assertEqual(self.status()['intent']['state'], 'EVIDENCE_DETECTED')
        self.assertEqual(self.financial_state(), before)
        self.bridge.transition(intent['reference'], 'AMBIGUOUS')
        self.assertEqual(self.status()['intent']['state'], 'NEEDS_REVIEW')
        self.bridge.transition(intent['reference'], 'AWAITING_VERIFICATION')
        self.bridge.confirm(intent['reference'])
        done = self.status()
        self.assertEqual((done['intent']['state'], done['intent']['terminal']), ('MANUALLY_CONFIRMED', True))
        self.assertEqual(self.financial_state(), before)
        self.assertFalse(self.snap().settlement.is_settled)
        self.assertEqual(self.wire(), [('PUT', intent['reference'])] + [('GET', intent['reference'])] * 3)

    def test_no_repeat_after_confirm_for_unchanged_suggestion(self):
        self.finalize()
        reference = self.request()['intent']['reference']
        self.bridge.confirm(reference)
        status = self.status()
        self.assertEqual([e['senderId'] for e in status['eligible']], ['C'])
        self.assertEqual(self.code(lambda: self.request('B', 863)), 'checkout_demo_already_confirmed')
        second = self.request('C', 500)['intent']
        self.assertEqual((second['attempt'], second['senderId']), (2, 'C'))
        self.bridge.expire(second['reference'])
        self.assertEqual(self.status()['intent']['state'], 'EXPIRED')
        # Even with a later intent in between, the confirmed debt stays non-repeatable.
        self.assertEqual(self.code(lambda: self.request('B', 863)), 'checkout_demo_already_confirmed')
        self.assertEqual(self.rows(), [(1, 'OBSERVED', 1), (2, 'OBSERVED', 1)])

    def test_expired_allows_a_new_attempt_with_a_new_reference(self):
        self.finalize()
        first = self.request()['intent']
        self.bridge.expire(first['reference'])
        status = self.status()
        self.assertEqual(status['intent']['state'], 'EXPIRED')
        self.assertEqual(status['eligible'][0], {'senderId': 'B', 'receiverId': 'A', 'amountSen': 863, 'action': 'NEW'})
        second = self.request()['intent']
        self.assertEqual(second['attempt'], 2)
        self.assertNotEqual(second['reference'], first['reference'])
        self.assertEqual(second['reference'], checkout_reference(NAMESPACE, 'meal', 'A', 'final', 'B', 'A', 2))

    def test_invisible_revision_rise_is_a_new_observation(self):
        self.finalize()
        reference = self.request()['intent']['reference']
        self.bridge.expire(reference)
        self.assertEqual(self.status()['intent']['revision'], 2)
        self.bridge.transition(reference)  # paymentClosed latch: revision only.
        status = self.status()['intent']
        self.assertEqual((status['state'], status['revision']), ('EXPIRED', 3))


class NotCreatedAndStaleTests(DemoFixture):
    def test_same_amount_held_is_not_created_and_allows_identical_reput(self):
        self.finalize()
        self.bridge.other_holds.add(863)
        before = self.financial_state()
        held = self.request()['intent']
        self.assertEqual((held['state'], held['notCreatedReason'], held['checkoutId']),
                         ('NOT_CREATED', 'SAME_AMOUNT_HELD', None))
        self.assertEqual(self.status()['eligible'][0]['action'], 'RETRY')
        again = self.request()['intent']
        self.assertEqual((again['state'], again['reference'], again['possibleDispatches']),
                         ('NOT_CREATED', held['reference'], 2))
        self.bridge.other_holds.clear()
        created = self.request()['intent']
        self.assertEqual((created['state'], created['reference'], created['attempt']),
                         ('AWAITING_EVIDENCE', held['reference'], 1))
        self.assertEqual([m for m, _ in self.wire()], ['PUT', 'GET', 'PUT', 'PUT'])
        self.assertEqual(self.financial_state(), before)

    def test_stale_not_created_intent_is_abandoned_with_next_attempt(self):
        self.finalize()
        self.bridge.other_holds.add(863)
        held = self.request()['intent']
        self.record_transfer('partial', 'B', 500)
        status = self.status()
        self.assertTrue(status['intent']['stale'])
        self.assertIn({'senderId': 'B', 'receiverId': 'A', 'amountSen': 363, 'action': 'NEW'}, status['eligible'])
        puts_before = [m for m, _ in self.wire()].count('PUT')
        self.assertEqual(self.code(lambda: self.request('B', 863)), 'checkout_demo_stale')
        self.assertEqual([m for m, _ in self.wire()].count('PUT'), puts_before)
        fresh = self.request('B', 363)['intent']
        self.assertEqual((fresh['attempt'], fresh['amountSen'], fresh['state'], fresh['stale']),
                         (2, 363, 'AWAITING_EVIDENCE', False))
        self.assertNotEqual(fresh['reference'], held['reference'])

    def test_stale_intent_that_never_reached_the_bridge_does_not_block_the_meal(self):
        self.finalize()
        self.bridge.fail = 'drop'
        lost = self.request()['intent']
        self.assertEqual(lost['state'], 'REQUEST_UNKNOWN')
        self.bridge.fail = None
        self.record_transfer('full', 'B', 863)  # Suggestion disappears entirely.
        status = self.status()
        self.assertEqual((status['intent']['state'], status['intent']['notCreatedReason'], status['intent']['stale']),
                         ('NOT_CREATED', 'REFERENCE_NOT_FOUND', True))
        self.assertEqual([(e['senderId'], e['action']) for e in status['eligible']], [('C', 'NEW')])
        self.assertEqual(self.request('C', 500)['intent']['attempt'], 2)

    def test_stale_open_checkout_gets_no_further_put(self):
        self.finalize()
        reference = self.request()['intent']['reference']
        self.record_transfer('partial', 'B', 100)
        for _ in range(2):
            status = self.status()
            self.assertEqual((status['intent']['state'], status['intent']['stale']), ('AWAITING_EVIDENCE', True))
        self.assertEqual(self.code(lambda: self.request('B', 763)), 'checkout_demo_active')
        self.assertEqual(self.code(lambda: self.request('B', 863)), 'checkout_demo_stale')
        self.assertEqual(self.wire(), [('PUT', reference), ('GET', reference), ('GET', reference)])

    def test_unrelated_transfer_does_not_mark_intent_stale(self):
        self.finalize()
        self.request()
        self.record_transfer('other', 'C', 200)
        self.apply(ReportTransfer('pending', self.snap().revision, 'B', 'A', 100), who='B')
        self.assertFalse(self.status()['intent']['stale'])


class RecoveryTests(DemoFixture):
    def test_put_uncertainty_is_followed_by_get_then_absence_rule(self):
        self.finalize()
        for failure in ('store', 'drop', (500, {'error': 'INTERNAL'})):
            with self.subTest(failure=failure):
                self.authority._db.execute('DELETE FROM checkout_demos')
                self.bridge.calls.clear()
                self.bridge.fail = failure
                result = self.request()
                self.assertEqual((result['intent']['state'], result['lastCheck']), ('REQUEST_UNKNOWN', 'REQUEST_UNKNOWN'))
                self.bridge.fail = None
                checked = self.request()['intent']  # Explicit retry: a GET, never a PUT.
                self.assertEqual((checked['state'], checked['notCreatedReason']), ('NOT_CREATED', 'REFERENCE_NOT_FOUND'))
                created = self.request()['intent']
                self.assertEqual((created['state'], created['possibleDispatches']), ('AWAITING_EVIDENCE', 2))
                self.assertEqual([m for m, _ in self.wire()], ['PUT', 'GET', 'PUT'])
                self.bridge.lose_snapshot()

    def test_delayed_put_that_did_arrive_is_bound_by_get(self):
        self.finalize()
        client = RecordingClient({'transport': 'REQUEST_UNKNOWN', 'retry_after': None})
        reference = self.request(client=client)['intent']['reference']
        self.bridge._put(reference, b'{"amountMinor":863,"currency":"MYR"}')  # It reached the bridge.
        found = self.status()['intent']
        self.assertEqual((found['state'], found['checkoutId']), ('AWAITING_EVIDENCE', self.bridge.only()[1]['checkoutId']))
        self.assertEqual([m for m, _ in self.wire()], ['GET'])

    def test_snapshot_loss_with_bound_checkout_is_unavailable_and_never_recreated(self):
        self.finalize()
        reference = self.request()['intent']['reference']
        saved = self.bridge.only()[1]
        self.bridge.lose_snapshot()
        lost = self.status()['intent']
        self.assertEqual((lost['state'], lost['referenceLost'], lost['terminal']), ('UNAVAILABLE', True, False))
        self.assertEqual(self.code(lambda: self.request()), 'checkout_demo_active')
        self.assertEqual(self.status()['eligible'], [])
        self.assertEqual([m for m, _ in self.wire()].count('PUT'), 1)
        self.bridge.checkouts[reference] = saved  # Operator restores the snapshot backup.
        self.assertEqual(self.status()['intent']['state'], 'AWAITING_EVIDENCE')

    def test_other_404s_and_malformed_bodies_are_transient_unavailable(self):
        self.finalize()
        self.request()
        for failure in ((404, {'error': 'NOT_FOUND'}), (404, {'error': 'EXPERIMENT_DISABLED'}),
                        (404, {'error': 'REFERENCE_NOT_FOUND', 'x': 1}), (404, b'REFERENCE_NOT_FOUND'),
                        'malformed', (200, b'{"a":1,"a":2}'), (503, {'error': 'STORE_UNAVAILABLE'})):
            with self.subTest(failure=failure):
                self.bridge.fail = failure
                status = self.status()['intent']
                self.assertEqual((status['state'], status['lastKnownState'], status['referenceLost']),
                                 ('UNAVAILABLE', 'AWAITING_EVIDENCE', False))
        self.bridge.fail = None
        self.assertEqual(self.status()['intent']['state'], 'AWAITING_EVIDENCE')

    def test_reference_conflict_and_different_checkout_id_fail_closed(self):
        self.finalize()
        self.bridge.fail = (409, {'error': 'REFERENCE_CONFLICT'})
        conflicted = self.request()['intent']
        self.assertEqual((conflicted['state'], conflicted['terminal'], conflicted['latched']), ('CONFLICT', True, True))
        calls = len(self.bridge.calls)
        self.assertEqual(self.status()['intent']['state'], 'CONFLICT')
        self.assertEqual(len(self.bridge.calls), calls)  # Automatic actions stop.
        self.bridge.fail = None
        second = self.request()['intent']
        self.assertEqual((second['attempt'], second['state']), (2, 'AWAITING_EVIDENCE'))
        self.bridge.checkouts[second['reference']]['checkoutId'] = str(uuid.uuid4())
        self.assertEqual(self.status()['intent']['state'], 'CONFLICT')

    def test_revision_ordering(self):
        self.finalize()
        reference = self.request()['intent']['reference']
        self.bridge.simulate_candidate(reference)
        self.assertEqual(self.status()['intent']['revision'], 2)
        self.bridge.checkouts[reference].update(status='AWAITING_PAYMENT', evidence='NONE', revision=1)
        older = self.status()['intent']
        self.assertEqual((older['state'], older['revision']), ('EVIDENCE_DETECTED', 2))  # Lower revision ignored.
        self.bridge.checkouts[reference].update(status='AMBIGUOUS', evidence='SYNTHETIC', revision=2)
        self.assertEqual(self.status()['intent']['state'], 'CONFLICT')  # Equal revision, different content.

    def test_terminal_status_cannot_change_and_unverified_evidence_latches(self):
        self.finalize()
        reference = self.request()['intent']['reference']
        self.bridge.confirm(reference)
        self.assertEqual(self.status()['intent']['state'], 'MANUALLY_CONFIRMED')
        self.bridge.transition(reference, 'AWAITING_PAYMENT', 'NONE')
        self.assertEqual(self.status()['intent']['state'], 'UNEXPECTED_STATUS')
        self.authority._db.execute('DELETE FROM checkout_demos')
        self.bridge.lose_snapshot()
        reference = self.request()['intent']['reference']
        self.bridge.transition(reference, 'MANUALLY_CONFIRMED', 'NOTIFICATION_UNVERIFIED')
        unexpected = self.status()
        self.assertEqual((unexpected['intent']['state'], unexpected['intent']['latched']), ('UNEXPECTED_STATUS', True))
        self.assertEqual(unexpected['eligible'], [])
        calls = len(self.bridge.calls)
        self.bridge.transition(reference, 'MANUALLY_CONFIRMED', 'SYNTHETIC')
        self.assertEqual(self.status()['intent']['state'], 'UNEXPECTED_STATUS')
        self.assertEqual(len(self.bridge.calls), calls)

    def test_wrong_amount_or_reference_in_bridge_body_fails_closed(self):
        self.finalize()
        reference = self.request()['intent']['reference']
        self.bridge.checkouts[reference]['amountMinor'] = 864
        self.assertEqual(self.status()['intent']['state'], 'CONFLICT')

    def test_frozen_basis_tamper_and_namespace_change_fail_closed(self):
        self.finalize()
        self.request()
        self.authority._db.execute("UPDATE checkout_demos SET sender_id='C'")
        self.assertEqual(self.code(lambda: self.status()), 'checkout_demo_conflict')
        self.authority._db.execute("UPDATE checkout_demos SET sender_id='B'")
        self.status()
        self.cfg = CheckoutDemoConfig(str(uuid.uuid4()), self.bridge.base_url, self.bridge_token)
        self.assertEqual(self.code(lambda: self.status()), 'checkout_demo_conflict')

    def test_suspension_cooldown_and_busy_slot(self):
        self.finalize()
        self.bridge.fail = (401, {'error': 'UNAUTHORIZED'})
        self.assertEqual(self.request()['intent']['state'], 'UNAVAILABLE')
        self.bridge.fail = None
        calls = len(self.bridge.calls)
        self.assertEqual(self.status()['lastCheck'], 'UNAVAILABLE')
        self.assertEqual(len(self.bridge.calls), calls)  # Suspended until restart.
        client = CheckoutDemoClient(self.cfg)
        self.bridge.fail = (429, {'error': 'RATE_LIMITED'})
        self.assertEqual(self.status(client=client)['lastCheck'], 'UNAVAILABLE')
        calls = len(self.bridge.calls)
        self.assertGreaterEqual(self.status(client=client)['retryAfter'], 1)
        self.assertEqual(len(self.bridge.calls), calls)
        recording = RecordingClient()
        with demo._wire_slot:
            busy = self.status(client=recording)
            busy_request = self.request('C', 500, client=recording)
        self.assertEqual((busy['lastCheck'], busy['retryAfter'], busy_request['lastCheck']), ('BUSY', 2, 'BUSY'))
        self.assertEqual(recording.calls, [])
        self.assertEqual(self.rows(), [(1, 'REQUEST_UNKNOWN', 1)])

    def test_failure_injection_around_the_intent_commit(self):
        self.finalize()
        recording = RecordingClient()
        self.authority._failure_hook = lambda stage: (_ for _ in ()).throw(OSError()) \
            if stage == 'checkout_demo_before_intent_commit' else None
        self.assertEqual(self.code(lambda: self.request(client=recording)), 'storage_error')
        self.assertEqual((self.rows(), recording.calls), ([], []))
        self.authority._failure_hook = lambda stage: (_ for _ in ()).throw(OSError()) \
            if stage == 'checkout_demo_after_intent_commit' else None
        self.assertEqual(self.code(lambda: self.request(client=recording)), 'commit_uncertain')
        self.assertEqual((self.rows(), recording.calls), ([(1, 'REQUEST_UNKNOWN', 1)], []))
        self.authority._failure_hook = None
        self.assertEqual(self.request()['intent']['state'], 'NOT_CREATED')  # The retry is a GET.
        self.assertEqual([m for m, _ in self.wire()], ['GET'])

    def test_revoked_organizer_session_sends_nothing(self):
        self.finalize()
        recording = RecordingClient()
        self.authority._failure_hook = lambda stage: self.authority._db.execute(
            'UPDATE sessions SET revoked=1 WHERE participant_id=?', ('A',)) \
            if stage == 'checkout_demo_after_intent_commit' else None
        self.assertEqual(self.code(lambda: self.request(client=recording)), 'invalid_session')
        self.assertEqual(recording.calls, [])


class SuggestionParityTests(DemoFixture):
    def test_recomputed_suggestions_match_the_meal_snapshot(self):
        self.finalize()
        for step in range(4):
            authority = self.authority
            authority._db.execute('BEGIN')
            state = json.loads(authority._db.execute("SELECT state FROM meals WHERE id='meal'").fetchone()[0])
            ours = demo.current_suggestions(authority, 'meal', state)
            authority._db.execute('COMMIT')
            theirs = tuple((s.sender_id, s.receiver_id, s.amount_sen) for s in self.snap().settlement.suggested_transfers)
            self.assertEqual(ours, theirs)
            if step == 0:
                self.record_transfer('t1', 'B', 300)
            elif step == 1:
                self.apply(ReportTransfer('pending', self.snap().revision, 'C', 'A', 100), who='C')
            elif step == 2:
                self.record_transfer('t2', 'C', 400)


class HttpRouteTests(DemoFixture):
    def app(self, **kwargs):
        app = SettleTableApp(self.path, clock=lambda: self.now, **kwargs)
        self.addCleanup(app.close)
        return TransportTestClient(app)

    def test_routes_access_body_csrf_and_secret_projection(self):
        self.finalize()
        client = self.app(checkout_demo_config=self.cfg, checkout_demo_client=self.client)
        path = '/api/meals/meal/checkout-demo'
        org = {'HTTP_AUTHORIZATION': 'Bearer ' + self.cred['A']}
        diner = {'HTTP_AUTHORIZATION': 'Bearer ' + self.cred['B']}
        self.assertEqual(client.get(path)['status'], 401)
        self.assertEqual(client.get(path, diner)['status'], 403)
        self.assertEqual(client.post(path, {'sender_id': 'B', 'amount_sen': 863}, diner)['status'], 403)
        for body in ({}, {'sender_id': 'B'}, {'sender_id': 'B', 'amount_sen': True},
                     {'sender_id': 'B', 'amount_sen': 863, 'currency': 'MYR'}, {'sender_id': 'B', 'amount_sen': 0},
                     {'sender_id': '', 'amount_sen': 863}, [1]):
            with self.subTest(body=body):
                self.assertEqual(client.post(path, body, org)['status'], 400)
        self.assertEqual(client.post(path, {'sender_id': 'B', 'amount_sen': 863}, {
            'HTTP_COOKIE': 'settletable_session=' + self.cred['A'], 'HTTP_ORIGIN': 'http://attacker.invalid'})['status'], 403)
        self.assertEqual(self.bridge.calls, [])
        created = client.post(path, {'sender_id': 'B', 'amount_sen': 863}, org)
        self.assertEqual(created['status'], 200)
        payload = json.loads(created['body'])
        self.assertEqual(payload['checkout_demo']['intent']['state'], 'AWAITING_EVIDENCE')
        self.assertNotIn(self.bridge_token, created['body'].decode())
        self.assertEqual(client.post(path, {'sender_id': 'B', 'amount_sen': 863}, org)['status'], 409)
        self.assertEqual(client.get(path, org)['status'], 200)
        snapshot = json.loads(client.get('/api/meals/meal/snapshot', org)['body'])
        self.assertTrue(snapshot['checkout_demo_enabled'])
        self.assertNotIn('checkout_demo', snapshot)
        self.assertFalse(json.loads(client.get('/api/meals/meal/snapshot', diner)['body'])['checkout_demo_enabled'])
        self.bridge.fail = 'store'
        self.authority._db.execute('DELETE FROM checkout_demos')
        self.assertEqual(client.post(path, {'sender_id': 'B', 'amount_sen': 863}, org)['status'], 202)

    def test_snapshot_polling_never_touches_the_bridge(self):
        self.finalize()
        client = self.app(checkout_demo_config=self.cfg, checkout_demo_client=self.client)
        org = {'HTTP_AUTHORIZATION': 'Bearer ' + self.cred['A']}
        client.post('/api/meals/meal/checkout-demo', {'sender_id': 'B', 'amount_sen': 863}, org)
        calls = len(self.bridge.calls)
        for _ in range(3):
            client.get('/api/meals/meal/snapshot', org)
        self.assertEqual(len(self.bridge.calls), calls)

    def test_disabled_feature_authenticates_first(self):
        self.finalize()
        with patch.dict(os.environ, {'SETTLETABLE_CHECKOUT_DEMO_ENABLED': '0'}):
            client = self.app()
        path = '/api/meals/meal/checkout-demo'
        self.assertEqual(client.get(path)['status'], 401)
        self.assertEqual(client.get(path, {'HTTP_AUTHORIZATION': 'Bearer ' + 'Z' * 43})['status'], 401)
        disabled = client.get(path, {'HTTP_AUTHORIZATION': 'Bearer ' + self.cred['A']})
        self.assertEqual((disabled['status'], json.loads(disabled['body'])['error']), (503, 'checkout_demo_disabled'))
        self.assertFalse(json.loads(client.get('/api/meals/meal/snapshot',
            {'HTTP_AUTHORIZATION': 'Bearer ' + self.cred['A']})['body'])['checkout_demo_enabled'])


class WireClientTests(unittest.TestCase):
    def setUp(self):
        self.bridge_token = token()
        self.bridge = StubBridge(self.bridge_token)
        self.addCleanup(self.bridge.close)
        self.client = CheckoutDemoClient(CheckoutDemoConfig(NAMESPACE, self.bridge.base_url, self.bridge_token))
        self.reference = str(uuid.uuid4())

    def test_put_replay_while_holding_own_amount_and_conflict(self):
        first = self.client.request('PUT', self.reference, 863)
        replay = self.client.request('PUT', self.reference, 863)
        self.assertEqual(replay['checkout'], first['checkout'])
        self.assertEqual(self.client.request('PUT', self.reference, 864), {'error': 'REFERENCE_CONFLICT'})
        self.assertEqual(self.client.request('PUT', str(uuid.uuid4()), 863), {'error': 'SAME_AMOUNT_HELD'})
        self.assertEqual(self.client.request('GET', str(uuid.uuid4()), 863), {'error': 'REFERENCE_NOT_FOUND'})
        self.assertEqual(self.client.request('GET', self.reference, 863)['checkout']['revision'], 1)
        _, _, headers, body = self.bridge.calls[-1]
        self.assertEqual(body, b'')
        self.assertNotIn('Content-Type', headers)

    def test_framing_redirect_size_and_wrong_method_codes(self):
        cases = [((307, b''), 'REQUEST_UNKNOWN', 'UNAVAILABLE'),
                 ((200, b'{"error":"x"}'), 'REQUEST_UNKNOWN', 'UNAVAILABLE'),
                 ((404, {'error': 'REFERENCE_NOT_FOUND'}), 'REQUEST_UNKNOWN', None),
                 ((409, {'error': 'SAME_AMOUNT_HELD'}), None, 'UNAVAILABLE'),
                 ((409, {'error': 'REQUEST_CAPACITY'}), 'REQUEST_UNKNOWN', 'UNAVAILABLE'),
                 ((200, b'x' * 9000), 'REQUEST_UNKNOWN', 'UNAVAILABLE')]
        for failure, put, get in cases:
            self.bridge.fail = failure
            with self.subTest(failure=failure):
                if put:
                    self.assertEqual(self.client.request('PUT', self.reference, 1)['transport'], put)
                if get:
                    self.assertEqual(self.client.request('GET', self.reference, 1)['transport'], get)
        self.bridge.fail = (201, {'unused': True})
        self.assertEqual(self.client.request('GET', self.reference, 1)['transport'], 'UNAVAILABLE')
        self.bridge.fail = None
        self.bridge._put(self.reference, b'{"amountMinor":5,"currency":"MYR"}')
        with patch.object(self.bridge, 'fail', None):
            body = self.bridge._get(self.reference)[1]
        self.bridge.fail = (201, body)  # 201 on GET is not part of the contract.
        self.assertEqual(self.client.request('GET', self.reference, 5)['transport'], 'UNAVAILABLE')
        self.bridge.fail = (200, json.dumps(body).encode())
        self.assertEqual(self.client.request('GET', self.reference, 5)['checkout'], body)
        with self.assertRaises(ValueError):
            self.client.request('POST', self.reference, 5)
        with self.assertRaises(ValueError):
            self.client.request('GET', self.reference.upper(), 5)

    def test_wrong_content_type_and_proxy_environment_are_ignored(self):
        body = self.client.request('PUT', self.reference, 7)['checkout']
        self.bridge.fail = (200, json.dumps(body).encode(), 'text/plain')
        self.assertEqual(self.client.request('GET', self.reference, 7)['transport'], 'UNAVAILABLE')
        self.bridge.fail = None
        with patch.dict(os.environ, {'HTTP_PROXY': 'http://127.0.0.1:9', 'http_proxy': 'http://127.0.0.1:9'}):
            self.assertIn('checkout', self.client.request('GET', self.reference, 7))


if __name__ == '__main__':
    unittest.main()
