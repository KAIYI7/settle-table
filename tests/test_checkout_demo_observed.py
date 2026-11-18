"""Observed-evidence mode of the experimental checkout demo (KP-SETTLETABLE-TNG-02 D2).

Real SQLite and a loopback stub of the G1 bridge contract (``checkout_demo_stub`` with
``observed_amount`` set). Display only: no outcome writes a financial record. All
credentials are disposable random test tokens. The synthetic tests in
``test_checkout_demo.py`` are unchanged and cover the flag-absent behaviour.
"""
from fractions import Fraction
import hashlib
import http.client
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from settletable import checkout_demo as demo
from settletable.authority import (Authority, AssignParticipantQuantity, Finalize, Participant, Receipt,
    ReceiptItem, RecordContribution, ReplaceReceipt, ReviewReceipt)
from settletable.checkout_demo import (CHECKOUT_FIELDS, CheckoutDemoClient, CheckoutDemoConfig, checkout_reference,
    display_status, validate_checkout)
from settletable.transport import SettleTableApp
from checkout_demo_stub import StubBridge
from test_checkout_demo import DemoFixture, FINANCIAL_TABLES, I06_SHA256, NAMESPACE, REPO, RecordingClient, token
from test_transport import TransportTestClient

FLAG = 'SETTLETABLE_CHECKOUT_DEMO_OBSERVED_EVIDENCE'
STATUSES = ('AWAITING_PAYMENT', 'PAYMENT_DETECTED', 'AWAITING_VERIFICATION', 'MANUALLY_CONFIRMED',
            'AMBIGUOUS', 'EXPIRED', 'REVIEW_EXPIRED', 'REFUNDED')
EVIDENCE = ('NONE', 'SYNTHETIC', 'NOTIFICATION_UNVERIFIED', 'GENUINE')


def raw_exchange(port, method, path, credential, body=None):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    headers = {'Authorization': 'Bearer ' + credential}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response.status, data


class ObservedConfigurationTests(unittest.TestCase):
    def env(self, **extra):
        base = {'SETTLETABLE_CHECKOUT_DEMO_ENABLED': '1', 'SETTLETABLE_CHECKOUT_DEMO_NAMESPACE': NAMESPACE,
                'SETTLETABLE_CHECKOUT_DEMO_BASE_URL': 'http://127.0.0.1:28082',
                'SETTLETABLE_CHECKOUT_DEMO_CREDENTIAL': 'x' * 40}
        base.update(extra)
        return {k: v for k, v in base.items() if v is not None}

    def test_flag_absent_is_the_synthetic_configuration(self):
        config = CheckoutDemoConfig.from_env(self.env())
        self.assertFalse(config.observed)
        self.assertEqual(config, CheckoutDemoConfig(NAMESPACE, 'http://127.0.0.1:28082', 'x' * 40))
        self.assertIsNone(CheckoutDemoConfig.from_env({}))

    def test_flag_accepts_exactly_true_and_fails_closed_otherwise(self):
        self.assertTrue(CheckoutDemoConfig.from_env(self.env(**{FLAG: 'true'})).observed)
        for value in ('1', 'TRUE', 'True', 'false', '0', '', ' true', 'yes'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'invalid_checkout_demo_configuration'):
                CheckoutDemoConfig.from_env(self.env(**{FLAG: value}))
        for enabled in (None, '0'):
            with self.subTest(enabled=enabled), self.assertRaisesRegex(ValueError, 'invalid_checkout_demo_configuration'):
                CheckoutDemoConfig.from_env(self.env(**{FLAG: 'true', 'SETTLETABLE_CHECKOUT_DEMO_ENABLED': enabled}))
        for observed in ('true', 1, None):
            with self.subTest(observed=observed), self.assertRaises(ValueError):
                CheckoutDemoConfig(NAMESPACE, 'http://127.0.0.1:28082', 'x' * 40, observed=observed)

    def test_app_startup_reads_the_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, self.env(**{FLAG: 'yes'}), clear=False):
                with self.assertRaisesRegex(ValueError, 'invalid_checkout_demo_configuration'):
                    SettleTableApp(Path(folder) / 'x.sqlite')
            with patch.dict(os.environ, self.env(**{FLAG: 'true'}), clear=False):
                app = SettleTableApp(Path(folder) / 'y.sqlite')
                self.addCleanup(app.close)
                self.assertTrue(app.checkout_demo_config.observed)


class ObservedPureContractTests(unittest.TestCase):
    def test_observed_display_mapping_checks_evidence_first(self):
        expected = {
            ('AWAITING_PAYMENT', 'NONE'): 'AWAITING_EVIDENCE',
            ('PAYMENT_DETECTED', 'NOTIFICATION_UNVERIFIED'): 'EVIDENCE_DETECTED',
            ('AWAITING_VERIFICATION', 'NOTIFICATION_UNVERIFIED'): 'EVIDENCE_DETECTED',
            ('MANUALLY_CONFIRMED', 'NOTIFICATION_UNVERIFIED'): 'MANUALLY_CONFIRMED',
            ('AMBIGUOUS', 'NONE'): 'NEEDS_REVIEW', ('AMBIGUOUS', 'NOTIFICATION_UNVERIFIED'): 'NEEDS_REVIEW',
            ('EXPIRED', 'NONE'): 'EXPIRED', ('EXPIRED', 'NOTIFICATION_UNVERIFIED'): 'EXPIRED',
            ('REVIEW_EXPIRED', 'NONE'): 'EXPIRED', ('REVIEW_EXPIRED', 'NOTIFICATION_UNVERIFIED'): 'EXPIRED',
        }
        for status in STATUSES:
            for evidence in EVIDENCE:
                with self.subTest(status=status, evidence=evidence):
                    self.assertEqual(display_status(status, evidence, observed=True),
                                     expected.get((status, evidence), 'UNEXPECTED_STATUS'))
        # SYNTHETIC evidence is never shown as an observed outcome.
        self.assertTrue(all(display_status(s, 'SYNTHETIC', True) == 'UNEXPECTED_STATUS' for s in STATUSES))

    def test_synthetic_mapping_is_unchanged_by_default(self):
        for status in STATUSES:
            for evidence in EVIDENCE:
                self.assertEqual(display_status(status, evidence), display_status(status, evidence, False))
        self.assertEqual(display_status('MANUALLY_CONFIRMED', 'NOTIFICATION_UNVERIFIED'), 'UNEXPECTED_STATUS')

    def test_allowlist_gains_only_the_evidence_mode_key_in_observed_mode(self):
        good = {'reference': str(uuid.uuid4()), 'checkoutId': str(uuid.uuid4()), 'amountMinor': 1,
                'status': 'AWAITING_PAYMENT', 'evidence': 'NONE', 'createdAt': '2026-11-17T04:00:00Z',
                'expiresAt': '2026-11-17T04:10:00Z', 'reviewExpiresAt': None, 'revision': 1}
        marked = dict(good, evidenceMode='OBSERVED_NOTIFICATION')
        with self.assertRaises(ValueError):
            validate_checkout(dict(marked))  # Flag absent: the extra key is rejected, as at 4caf012.
        self.assertEqual(validate_checkout(dict(good)), good)
        self.assertEqual(validate_checkout(dict(marked), observed=True), marked)
        # A missing or foreign marker passes the allowlist so the store step can latch it.
        self.assertEqual(validate_checkout(dict(good), observed=True), good)
        validate_checkout(dict(good, evidenceMode=None), observed=True)
        for body in (dict(marked, extra=1), dict(marked, amountMinor='1'), {k: v for k, v in marked.items()
                                                                            if k != 'revision'}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                validate_checkout(body, observed=True)

    def test_i06_module_is_byte_identical(self):
        data = (REPO / 'settletable' / 'payment_simulation.py').read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), I06_SHA256)


class StubContractTests(unittest.TestCase):
    """The stub is the in-process stand-in for the G1 contract: check its two shapes on the wire."""
    def test_synthetic_bytes_unchanged_and_observed_adds_one_key(self):
        reference = str(uuid.uuid4())
        bodies = {}
        for observed_amount in (None, 863):
            credential = token()
            stub = StubBridge(credential, observed_amount=observed_amount)
            self.addCleanup(stub.close)
            status, raw = raw_exchange(stub.server.server_port, 'PUT', '/api/integrations/checkouts/' + reference,
                                       credential, b'{"amountMinor":863,"currency":"MYR"}')
            self.assertEqual(status, 201)
            bodies[observed_amount] = json.loads(raw)
        synthetic, observed = bodies[None], bodies[863]
        self.assertEqual(set(synthetic), CHECKOUT_FIELDS)
        self.assertEqual(set(observed), CHECKOUT_FIELDS | {'evidenceMode'})
        self.assertEqual(observed['evidenceMode'], 'OBSERVED_NOTIFICATION')
        expected = json.dumps({'reference': reference, 'checkoutId': synthetic['checkoutId'], 'amountMinor': 863,
                               'status': 'AWAITING_PAYMENT', 'evidence': 'NONE',
                               'createdAt': '2026-11-17T04:00:00.123456789Z',
                               'expiresAt': '2026-11-17T04:10:00.123456789Z', 'reviewExpiresAt': None,
                               'revision': 1}).encode()
        stub = StubBridge(token())
        self.addCleanup(stub.close)
        status, raw = raw_exchange(stub.server.server_port, 'PUT', '/api/integrations/checkouts/' + reference,
                                   stub.token, b'{"amountMinor":863,"currency":"MYR"}')
        self.assertEqual(raw, expected.replace(synthetic['checkoutId'].encode(), json.loads(raw)['checkoutId'].encode()))

    def test_observed_put_order_mismatch_then_spent_then_replay(self):
        credential = token()
        stub = StubBridge(credential, observed_amount=1)
        self.addCleanup(stub.close)
        port = stub.server.server_port
        first, second = str(uuid.uuid4()), str(uuid.uuid4())
        put = lambda ref, amount: raw_exchange(port, 'PUT', '/api/integrations/checkouts/' + ref, credential,
                                               json.dumps({'amountMinor': amount, 'currency': 'MYR'}).encode())
        self.assertEqual(put(first, 2), (409, b'{"error": "OBSERVED_AMOUNT_MISMATCH"}'))
        self.assertEqual(put(first, 1)[0], 201)
        self.assertEqual(put(second, 2), (409, b'{"error": "OBSERVED_AMOUNT_MISMATCH"}'))
        self.assertEqual(put(second, 1), (409, b'{"error": "OBSERVED_CHECKOUT_SPENT"}'))
        self.assertEqual(put(first, 1)[0], 200)  # The bound reference still replays.


class ObservedWireClientTests(unittest.TestCase):
    def setUp(self):
        self.credential = token()
        self.bridge = StubBridge(self.credential, observed_amount=7)
        self.addCleanup(self.bridge.close)
        self.observed = CheckoutDemoClient(CheckoutDemoConfig(NAMESPACE, self.bridge.base_url, self.credential,
                                                              observed=True))
        self.synthetic = CheckoutDemoClient(CheckoutDemoConfig(NAMESPACE, self.bridge.base_url, self.credential))

    def test_observed_client_reads_the_marker_and_the_new_409_codes(self):
        reference = str(uuid.uuid4())
        created = self.observed.request('PUT', reference, 7)['checkout']
        self.assertEqual(created['evidenceMode'], 'OBSERVED_NOTIFICATION')
        self.assertEqual(self.observed.request('GET', reference, 7)['checkout'], created)
        self.assertEqual(self.observed.request('PUT', str(uuid.uuid4()), 7), {'error': 'OBSERVED_CHECKOUT_SPENT'})
        self.assertEqual(self.observed.request('PUT', str(uuid.uuid4()), 8), {'error': 'OBSERVED_AMOUNT_MISMATCH'})
        # The new codes are PUT-only: on a GET they are a transient failure.
        self.bridge.fail = (409, {'error': 'OBSERVED_CHECKOUT_SPENT'})
        self.assertEqual(self.observed.request('GET', reference, 7)['transport'], 'UNAVAILABLE')

    def test_flag_absent_client_fails_closed_against_an_observed_bridge(self):
        reference = str(uuid.uuid4())
        self.assertEqual(self.synthetic.request('PUT', reference, 7)['transport'], 'REQUEST_UNKNOWN')
        self.assertEqual(len(self.bridge.checkouts), 1)  # Created on the bridge: the store is spent.
        self.assertEqual(self.synthetic.request('GET', reference, 7)['transport'], 'UNAVAILABLE')
        for amount in (7, 8):
            with self.subTest(amount=amount):
                self.assertEqual(self.synthetic.request('PUT', str(uuid.uuid4()), amount)['transport'],
                                 'REQUEST_UNKNOWN')


class ObservedFixture(DemoFixture):
    """The B2 meal (B owes the organizer RM8.63, C RM5.00) against an observed bridge pinned at 863."""
    observed_amount = 863

    def setUp(self):
        super().setUp()
        self.synthetic_bridge = self.bridge
        self.bridge = StubBridge(self.bridge_token, observed_amount=self.observed_amount)
        self.addCleanup(self.bridge.close)
        self.cfg = CheckoutDemoConfig(NAMESPACE, self.bridge.base_url, self.bridge_token, observed=True)
        self.client = CheckoutDemoClient(self.cfg)

    def puts(self):
        return [m for m, _ in self.wire()].count('PUT')

    def checkout_rows(self):
        return self.authority._db.execute('SELECT * FROM checkout_demos ORDER BY attempt').fetchall()

    def assert_no_further_attempt(self):
        """Neither NEW nor RETRY is offered, and an explicit request sends no PUT."""
        status = self.status()
        self.assertEqual(status['eligible'], [])
        puts = self.puts()
        for sender, amount in (('B', 863), ('C', 500)):
            with self.subTest(sender=sender):
                self.assertIn(self.code(lambda: self.request(sender, amount)),
                              ('resource_limit', 'checkout_demo_active', 'checkout_demo_already_confirmed'))
        self.assertEqual(self.puts(), puts)
        self.assertEqual(len(self.rows()), 1)
        return status


class ObservedLifecycleTests(ObservedFixture):
    def test_full_observed_flow_projection_and_financial_invariance(self):
        self.finalize()
        before = self.financial_state()
        result = self.request()
        intent = result['intent']
        self.assertEqual((result['synthetic'], result['observed'], result['evidenceMode']),
                         (False, True, 'OBSERVED_NOTIFICATION'))
        method, path, headers, body = self.bridge.calls[0]
        self.assertEqual((method, path, body), ('PUT', '/api/integrations/checkouts/' + intent['reference'],
                                                b'{"amountMinor":863,"currency":"MYR"}'))
        self.assertEqual(intent['reference'], checkout_reference(NAMESPACE, 'meal', 'A', 'final', 'B', 'A', 1))
        self.assertEqual((intent['state'], intent['terminal'], intent['latched']), ('AWAITING_EVIDENCE', False, False))
        self.assertNotIn(self.bridge_token, json.dumps(result))
        self.assertEqual(self.financial_state(), before)
        self.bridge.observe_notification(intent['reference'])
        self.assertEqual(self.status()['intent']['state'], 'EVIDENCE_DETECTED')
        self.bridge.transition(intent['reference'], 'AWAITING_VERIFICATION')
        self.assertEqual(self.status()['intent']['state'], 'EVIDENCE_DETECTED')
        self.bridge.confirm(intent['reference'])
        done = self.status()
        self.assertEqual((done['intent']['state'], done['intent']['evidence'], done['intent']['terminal']),
                         ('MANUALLY_CONFIRMED', 'NOTIFICATION_UNVERIFIED', True))
        self.assertEqual(self.financial_state(), before)
        self.assertFalse(self.snap().settlement.is_settled)
        # Never NEW after the first PUT, even for the other diner's unrelated suggestion.
        self.assert_no_further_attempt()
        self.assertEqual(self.puts(), 1)

    def test_ambiguous_is_open_and_offers_nothing(self):
        self.finalize()
        reference = self.request()['intent']['reference']
        self.bridge.observe_notification(reference)
        self.bridge.ambiguous(reference)
        status = self.status()['intent']
        self.assertEqual((status['state'], status['terminal'], status['latched']), ('NEEDS_REVIEW', False, False))
        self.assert_no_further_attempt()

    def test_expiry_and_review_expiry_end_without_a_new_attempt(self):
        for ending in ('expire', 'review_expire'):
            with self.subTest(ending=ending):
                self.authority._db.execute('DELETE FROM checkout_demos')
                self.bridge.lose_snapshot()
                self.bridge.calls.clear()
                if not self.rows() and self.snap().calculation is None:
                    self.finalize()
                reference = self.request()['intent']['reference']
                getattr(self.bridge, ending)(reference)
                status = self.status()['intent']
                self.assertEqual((status['state'], status['terminal']), ('EXPIRED', True))
                self.assertIsNotNone(status['checkoutId'])
                self.assert_no_further_attempt()

    def test_synthetic_evidence_in_observed_mode_latches(self):
        self.finalize()
        reference = self.request()['intent']['reference']
        self.bridge.simulate_candidate(reference)  # Evidence SYNTHETIC with the observed marker present.
        latched = self.status()['intent']
        self.assertEqual((latched['state'], latched['latched']), ('UNEXPECTED_STATUS', True))
        calls = len(self.bridge.calls)
        self.assertEqual(self.status()['intent']['state'], 'UNEXPECTED_STATUS')
        self.assertEqual(len(self.bridge.calls), calls)
        self.assert_no_further_attempt()


class ObservedRetryTests(ObservedFixture):
    def test_retry_only_after_checked_absence_while_unbound(self):
        self.finalize()
        self.bridge.fail = 'drop'
        lost = self.request()['intent']
        self.assertEqual((lost['state'], lost['checkoutId']), ('REQUEST_UNKNOWN', None))
        self.assertEqual(self.status()['eligible'], [])  # Open: the next action is a GET, never a PUT.
        self.bridge.fail = None
        checked = self.request()['intent']
        self.assertEqual((checked['state'], checked['notCreatedReason'], checked['checkoutId']),
                         ('NOT_CREATED', 'REFERENCE_NOT_FOUND', None))
        self.assertEqual(self.status()['eligible'],
                         [{'senderId': 'B', 'receiverId': 'A', 'amountSen': 863, 'action': 'RETRY'}])
        # Only the same target may be retried; any other target would be a NEW attempt.
        self.assertEqual(self.code(lambda: self.request('C', 500)), 'resource_limit')
        created = self.request()['intent']
        self.assertEqual((created['state'], created['reference'], created['attempt'], created['possibleDispatches']),
                         ('AWAITING_EVIDENCE', lost['reference'], 1, 2))
        self.assertIsNotNone(created['checkoutId'])
        # After binding: no RETRY in any later state.
        self.assert_no_further_attempt()
        self.bridge.expire(created['reference'])
        self.assertEqual(self.status()['intent']['state'], 'EXPIRED')
        self.assert_no_further_attempt()
        self.assertEqual([m for m, _ in self.wire()].count('PUT'), 2)

    def test_retry_never_follows_a_bound_snapshot_loss(self):
        self.finalize()
        self.request()
        self.bridge.lose_snapshot()
        lost = self.status()['intent']
        self.assertEqual((lost['state'], lost['referenceLost']), ('UNAVAILABLE', True))
        self.assert_no_further_attempt()

    def test_same_amount_held_is_not_created_without_retry(self):
        self.finalize()
        self.bridge.other_holds.add(863)
        held = self.request()['intent']
        self.assertEqual((held['state'], held['notCreatedReason']), ('NOT_CREATED', 'SAME_AMOUNT_HELD'))
        self.assert_no_further_attempt()

    def test_mutation_guard_a_bound_not_created_row_is_never_retried(self):
        """Defence in depth: even a NOT_CREATED/REFERENCE_NOT_FOUND row with a bound id is refused."""
        self.finalize()
        self.bridge.fail = 'drop'
        self.request()
        self.bridge.fail = None
        self.request()
        self.assertEqual(self.status()['eligible'][0]['action'], 'RETRY')
        self.authority._db.execute("UPDATE checkout_demos SET checkout_id=?", (str(uuid.uuid4()),))
        # A bridge that cannot be reached keeps the row as it is, so only the binding rule decides.
        quiet = RecordingClient({'transport': 'UNAVAILABLE', 'retry_after': None})
        status = self.status(client=quiet)
        self.assertEqual((status['intent']['lastKnownState'], status['eligible']), ('NOT_CREATED', []))
        self.assertEqual(self.code(lambda: self.request(client=quiet)), 'resource_limit')
        self.assertEqual([m for m, _, _ in quiet.calls], ['GET'])


class ObservedLatchTests(ObservedFixture):
    def spend_store(self):
        self.bridge._put(str(uuid.uuid4()), b'{"amountMinor":863,"currency":"MYR"}')

    def assert_refusal_latched(self, intent, code):
        self.assertEqual((intent['state'], intent['notCreatedReason'], intent['terminal'], intent['latched'],
                          intent['checkoutId']), ('CONFLICT', code, True, True, None))
        calls = len(self.bridge.calls)
        again = self.status()['intent']
        self.assertEqual((again['state'], again['notCreatedReason']), ('CONFLICT', code))
        self.assertEqual(len(self.bridge.calls), calls)  # Latched: no further I/O for this intent.
        self.assert_no_further_attempt()

    def test_checkout_spent_is_a_latched_refusal(self):
        self.finalize()
        self.spend_store()
        before = self.financial_state()
        self.assert_refusal_latched(self.request()['intent'], 'OBSERVED_CHECKOUT_SPENT')
        self.assertEqual(self.financial_state(), before)

    def test_amount_mismatch_is_a_latched_refusal(self):
        self.finalize()
        self.bridge.observed_amount = 1
        self.assert_refusal_latched(self.request('C', 500)['intent'], 'OBSERVED_AMOUNT_MISMATCH')

    def test_retry_that_meets_a_spent_store_latches_and_ends_retries(self):
        self.finalize()
        self.bridge.fail = 'drop'
        self.request()
        self.bridge.fail = None
        self.assertEqual(self.request()['intent']['state'], 'NOT_CREATED')
        self.spend_store()
        self.assert_refusal_latched(self.request()['intent'], 'OBSERVED_CHECKOUT_SPENT')

    def test_mode_mismatch_on_put_latches_without_binding(self):
        self.finalize()
        self.cfg = CheckoutDemoConfig(NAMESPACE, self.synthetic_bridge.base_url, self.bridge_token, observed=True)
        self.client = CheckoutDemoClient(self.cfg)
        self.bridge = self.synthetic_bridge
        before = self.financial_state()
        intent = self.request()['intent']
        self.assertEqual((intent['state'], intent['notCreatedReason'], intent['latched'], intent['checkoutId']),
                         ('UNEXPECTED_STATUS', 'EVIDENCE_MODE_MISMATCH', True, None))
        calls = len(self.bridge.calls)
        self.assertEqual(self.status()['intent']['notCreatedReason'], 'EVIDENCE_MODE_MISMATCH')
        self.assertEqual(len(self.bridge.calls), calls)
        self.assert_no_further_attempt()
        self.assertEqual(self.financial_state(), before)

    def test_mode_mismatch_on_a_later_get_latches(self):
        for marker in (None, 'SYNTHETIC', 'observed_notification', 5, 'drop'):
            with self.subTest(marker=marker):
                self.authority._db.execute('DELETE FROM checkout_demos')
                self.bridge.lose_snapshot()
                if self.snap().calculation is None:
                    self.finalize()
                reference = self.request()['intent']['reference']
                bound = self.status()['intent']['checkoutId']
                if marker == 'drop':
                    del self.bridge.checkouts[reference]['evidenceMode']
                else:
                    self.bridge.checkouts[reference]['evidenceMode'] = marker
                latched = self.status()['intent']
                self.assertEqual((latched['state'], latched['notCreatedReason'], latched['checkoutId']),
                                 ('UNEXPECTED_STATUS', 'EVIDENCE_MODE_MISMATCH', bound))
                self.assert_no_further_attempt()


class FlagAbsentAgainstObservedBridgeTests(ObservedFixture):
    def test_flag_absent_never_shows_waiting_and_stays_synthetic(self):
        self.finalize()
        self.cfg = CheckoutDemoConfig(NAMESPACE, self.bridge.base_url, self.bridge_token)
        self.client = CheckoutDemoClient(self.cfg)
        result = self.request()
        self.assertNotIn('observed', result)
        self.assertNotIn('evidenceMode', result)
        self.assertTrue(result['synthetic'])
        self.assertEqual((result['intent']['state'], result['lastCheck']), ('REQUEST_UNKNOWN', 'REQUEST_UNKNOWN'))
        self.assertEqual(len(self.bridge.checkouts), 1)  # The observed store is spent anyway.
        status = self.status()
        self.assertEqual((status['intent']['state'], status['intent']['lastKnownState'], status['lastCheck']),
                         ('UNAVAILABLE', 'REQUEST_UNKNOWN', 'UNAVAILABLE'))


class FinancialInvarianceTests(ObservedFixture):
    """Every observed outcome leaves every financial table and the snapshot settlement byte-identical."""
    def outcome(self, name):
        if name == 'spent':
            self.bridge._put(str(uuid.uuid4()), b'{"amountMinor":863,"currency":"MYR"}')
        if name == 'mismatch':
            self.bridge.observed_amount = 1
        if name == 'held':
            self.bridge.other_holds.add(863)
        if name == 'unknown':
            self.bridge.fail = 'drop'
        if name == 'conflict':
            self.bridge.fail = (409, {'error': 'REFERENCE_CONFLICT'})
        reference = self.request()['intent']['reference']
        self.bridge.fail = None
        if name in ('detected', 'confirmed', 'ambiguous', 'review_expired'):
            self.bridge.observe_notification(reference)
        if name == 'confirmed':
            self.bridge.confirm(reference)
        if name == 'ambiguous':
            self.bridge.ambiguous(reference)
        if name == 'review_expired':
            self.bridge.review_expire(reference)
        if name == 'expired':
            self.bridge.expire(reference)
        if name == 'lost':
            self.bridge.lose_snapshot()
        if name == 'synthetic_evidence':
            self.bridge.simulate_candidate(reference)
        if name == 'mode_mismatch':
            del self.bridge.checkouts[reference]['evidenceMode']
        if name == 'unknown':
            self.request()  # GET → checked absence
            self.request()  # RETRY
        return self.status()['intent']['state']

    def test_all_outcomes(self):
        self.finalize()
        expected = {'awaiting': 'AWAITING_EVIDENCE', 'detected': 'EVIDENCE_DETECTED', 'confirmed': 'MANUALLY_CONFIRMED',
                    'ambiguous': 'NEEDS_REVIEW', 'expired': 'EXPIRED', 'review_expired': 'EXPIRED',
                    'lost': 'UNAVAILABLE', 'spent': 'CONFLICT', 'mismatch': 'CONFLICT', 'held': 'NOT_CREATED',
                    'unknown': 'AWAITING_EVIDENCE', 'conflict': 'CONFLICT', 'synthetic_evidence': 'UNEXPECTED_STATUS',
                    'mode_mismatch': 'UNEXPECTED_STATUS'}
        before = self.financial_state()
        accepted = self.authority._db.execute('SELECT command_id,body,result FROM commands ORDER BY rowid').fetchall()
        for name, state in expected.items():
            with self.subTest(outcome=name):
                self.authority._db.execute('DELETE FROM checkout_demos')
                self.bridge.lose_snapshot()
                self.bridge.observed_amount = 863
                self.bridge.other_holds.clear()
                self.assertEqual(self.outcome(name), state)
                self.assertEqual(self.financial_state(), before)
                self.assertEqual(self.authority._db.execute(
                    'SELECT command_id,body,result FROM commands ORDER BY rowid').fetchall(), accepted)
        for table in FINANCIAL_TABLES:
            self.assertIn(table, before[0])


class OneSenSuggestionTests(DemoFixture):
    """D3: an RM0.02 item shared by the organizer and the test counterparty, paid by the organizer."""
    def setUp(self):
        unittest.TestCase.setUp(self)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'one-sen.sqlite'
        self.now = 1000.0
        self.authority = Authority(self.path, clock=lambda: self.now)
        self.addCleanup(lambda: self.authority.close())
        grants = self.authority.bootstrap('meal', (Participant('A', 'Organizer', True),
                                                   Participant('B', "Owner's other wallet (test)")))
        self.cred = {s.participant_id: s.credential for s in grants.sessions}
        self.bridge_token = token()
        self.bridge = StubBridge(self.bridge_token, observed_amount=1)
        self.addCleanup(self.bridge.close)
        self.cfg = CheckoutDemoConfig(NAMESPACE, self.bridge.base_url, self.bridge_token, observed=True)
        self.client = CheckoutDemoClient(self.cfg)

    def finalize(self, payer='A'):
        s = self.snap()
        self.apply(ReplaceReceipt('receipt', s.revision, s.financial_revision,
                                  Receipt((ReceiptItem('shared', 'Shared test item', 1, 2),), 2, 2)))
        for person in ('A', 'B'):
            s = self.snap()
            revision = {i.item_id: i.item_revision for i in s.items}['shared']
            self.apply(AssignParticipantQuantity('assign-' + person, person, 'shared', Fraction(1, 2), revision,
                                                 s.financial_revision))
        s = self.snap()
        self.apply(ReviewReceipt('review', s.revision, s.financial_revision, s.receipt_digest))
        s = self.snap()
        self.apply(Finalize('final', s.revision, s.financial_revision))
        s = self.snap()
        self.apply(RecordContribution('pay', s.revision, payer, 2, 'card'))

    def test_one_sen_suggestion_reaches_the_bridge_and_changes_nothing(self):
        self.finalize()
        suggestions = [(t.sender_id, t.receiver_id, t.amount_sen) for t in self.snap().settlement.suggested_transfers]
        self.assertEqual(suggestions, [('B', 'A', 1)])
        self.assertEqual(self.status()['eligible'], [{'senderId': 'B', 'receiverId': 'A', 'amountSen': 1,
                                                      'action': 'NEW'}])
        before = self.financial_state()
        intent = self.request('B', 1)['intent']
        self.assertEqual(self.bridge.calls[0][3], b'{"amountMinor":1,"currency":"MYR"}')
        self.assertEqual((intent['state'], intent['amountSen']), ('AWAITING_EVIDENCE', 1))
        self.bridge.observe_notification(intent['reference'])
        self.bridge.confirm(intent['reference'])
        self.assertEqual(self.status()['intent']['state'], 'MANUALLY_CONFIRMED')
        self.assertEqual(self.financial_state(), before)
        self.assertEqual([(t.sender_id, t.receiver_id, t.amount_sen)
                          for t in self.snap().settlement.suggested_transfers], [('B', 'A', 1)])
        self.assertEqual(self.status()['eligible'], [])


class ObservedHttpRouteTests(ObservedFixture):
    def app(self, **kwargs):
        app = SettleTableApp(self.path, clock=lambda: self.now, **kwargs)
        self.addCleanup(app.close)
        return TransportTestClient(app)

    def test_snapshot_flag_and_projection(self):
        self.finalize()
        org = {'HTTP_AUTHORIZATION': 'Bearer ' + self.cred['A']}
        diner = {'HTTP_AUTHORIZATION': 'Bearer ' + self.cred['B']}
        client = self.app(checkout_demo_config=self.cfg, checkout_demo_client=self.client)
        snapshot = json.loads(client.get('/api/meals/meal/snapshot', org)['body'])
        self.assertEqual((snapshot['checkout_demo_enabled'], snapshot['checkout_demo_observed']), (True, True))
        dsnap = json.loads(client.get('/api/meals/meal/snapshot', diner)['body'])
        self.assertEqual((dsnap['checkout_demo_enabled'], dsnap['checkout_demo_observed']), (False, False))
        self.assertEqual(client.get('/api/meals/meal/checkout-demo', diner)['status'], 403)
        created = client.post('/api/meals/meal/checkout-demo', {'sender_id': 'B', 'amount_sen': 863}, org)
        payload = json.loads(created['body'])['checkout_demo']
        self.assertEqual((created['status'], payload['observed'], payload['intent']['state']),
                         (200, True, 'AWAITING_EVIDENCE'))
        self.assertNotIn(self.bridge_token, created['body'].decode())
        # A second meal-level attempt is refused after the first PUT.
        self.bridge.expire(payload['intent']['reference'])
        client.get('/api/meals/meal/checkout-demo', org)
        refused = client.post('/api/meals/meal/checkout-demo', {'sender_id': 'C', 'amount_sen': 500}, org)
        self.assertEqual((refused['status'], json.loads(refused['body'])['error']), (429, 'resource_limit'))
        self.assertEqual(self.puts(), 1)

    def test_flag_absent_snapshot_has_no_observed_key(self):
        self.finalize()
        org = {'HTTP_AUTHORIZATION': 'Bearer ' + self.cred['A']}
        synthetic = CheckoutDemoConfig(NAMESPACE, self.bridge.base_url, self.bridge_token)
        client = self.app(checkout_demo_config=synthetic, checkout_demo_client=CheckoutDemoClient(synthetic))
        snapshot = json.loads(client.get('/api/meals/meal/snapshot', org)['body'])
        self.assertTrue(snapshot['checkout_demo_enabled'])
        self.assertNotIn('checkout_demo_observed', snapshot)


if __name__ == '__main__':
    unittest.main()
