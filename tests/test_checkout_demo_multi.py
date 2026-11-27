"""Multi-diner observed checkout demo (SETTLETABLE_CHECKOUT_DEMO_OBSERVED_MULTI=true).

Real SQLite and a loopback stub of the bridge's multi-checkout observed mode
(``checkout_demo_stub`` with ``observed_count`` set). Each diner who owes the organizer
gets one single-use observed checkout at their share minus a sen offset that keeps the
meal's held amounts distinct. Display only: no outcome writes a financial record. All
credentials are disposable random test tokens. With the variable absent the synthetic
and single observed suites (``test_checkout_demo.py``, ``test_checkout_demo_observed.py``)
cover the unchanged behaviour.
"""
from dataclasses import asdict, replace as dc_replace
from datetime import datetime, timezone
from fractions import Fraction
import json
import os
from pathlib import Path
import random
import tempfile
import threading
import unittest
from unittest.mock import patch

from settletable import checkout_demo as demo
from settletable.authority import (Authority, AuthorityError, AssignParticipantQuantity, Finalize, Participant,
    Receipt, ReceiptItem, RecordContribution, ReplaceReceipt, ReviewReceipt)
from settletable.checkout_demo import (CheckoutDemoClient, CheckoutDemoConfig, allocate_offset, checkout_reference,
    checkout_demo_status, excluded_amounts, holds_amount, request_checkout_demo)
from settletable.transport import SettleTableApp
from checkout_demo_stub import StubBridge
from test_checkout_demo import FINANCIAL_TABLES, NAMESPACE, token
from test_transport import TransportTestClient

OBSERVED = 'SETTLETABLE_CHECKOUT_DEMO_OBSERVED_EVIDENCE'
MULTI = 'SETTLETABLE_CHECKOUT_DEMO_OBSERVED_MULTI'
# The stub bridge clock starts at 2026-11-17T04:00:00Z; SettleTable's clock starts 5 s later.
T0 = datetime(2026, 11, 17, 4, 0, 0, tzinfo=timezone.utc).timestamp()


class MultiConfigurationTests(unittest.TestCase):
    def env(self, **extra):
        base = {'SETTLETABLE_CHECKOUT_DEMO_ENABLED': '1', 'SETTLETABLE_CHECKOUT_DEMO_NAMESPACE': NAMESPACE,
                'SETTLETABLE_CHECKOUT_DEMO_BASE_URL': 'http://127.0.0.1:28082',
                'SETTLETABLE_CHECKOUT_DEMO_CREDENTIAL': 'x' * 40}
        base.update(extra)
        return {k: v for k, v in base.items() if v is not None}

    def test_absent_is_the_single_observed_configuration(self):
        config = CheckoutDemoConfig.from_env(self.env(**{OBSERVED: 'true'}))
        self.assertEqual((config.observed, config.multi), (True, False))
        self.assertEqual(config, CheckoutDemoConfig(NAMESPACE, 'http://127.0.0.1:28082', 'x' * 40, observed=True))
        self.assertFalse(CheckoutDemoConfig.from_env(self.env()).multi)

    def test_accepts_exactly_true_and_requires_the_observed_flag(self):
        config = CheckoutDemoConfig.from_env(self.env(**{OBSERVED: 'true', MULTI: 'true'}))
        self.assertEqual((config.observed, config.multi), (True, True))
        for value in ('1', 'TRUE', 'True', 'false', '0', '', ' true', 'yes'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'invalid_checkout_demo_configuration'):
                CheckoutDemoConfig.from_env(self.env(**{OBSERVED: 'true', MULTI: value}))
        for extra in ({MULTI: 'true'}, {MULTI: 'true', 'SETTLETABLE_CHECKOUT_DEMO_ENABLED': '0'},
                      {MULTI: 'true', 'SETTLETABLE_CHECKOUT_DEMO_ENABLED': None},
                      {MULTI: 'true', OBSERVED: 'true', 'SETTLETABLE_CHECKOUT_DEMO_ENABLED': '0'}):
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, 'invalid_checkout_demo_configuration'):
                CheckoutDemoConfig.from_env(self.env(**extra))
        for kwargs in ({'multi': True}, {'multi': 'true', 'observed': True}, {'multi': 1, 'observed': True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                CheckoutDemoConfig(NAMESPACE, 'http://127.0.0.1:28082', 'x' * 40, **kwargs)

    def test_app_startup_reads_the_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, self.env(**{OBSERVED: 'true', MULTI: 'yes'}), clear=False):
                with self.assertRaisesRegex(ValueError, 'invalid_checkout_demo_configuration'):
                    SettleTableApp(Path(folder) / 'x.sqlite')
            with patch.dict(os.environ, self.env(**{MULTI: 'true'}), clear=False):
                os.environ.pop(OBSERVED, None)
                with self.assertRaisesRegex(ValueError, 'invalid_checkout_demo_configuration'):
                    SettleTableApp(Path(folder) / 'y.sqlite')
            with patch.dict(os.environ, self.env(**{OBSERVED: 'true', MULTI: 'true'}), clear=False):
                app = SettleTableApp(Path(folder) / 'z.sqlite')
                self.addCleanup(app.close)
                self.assertTrue(app.checkout_demo_config.multi)


class AllocatorTests(unittest.TestCase):
    """The offset rule itself (M-3), independent of storage."""
    def test_smallest_free_offset(self):
        self.assertEqual(allocate_offset(863, set()), 0)
        self.assertEqual(allocate_offset(863, {863}), 1)
        self.assertEqual(allocate_offset(863, {863, 862, 860}), 2)
        self.assertEqual(allocate_offset(863, {862}), 0)  # Unrelated holds change nothing.

    def test_one_sen_floor(self):
        self.assertEqual(allocate_offset(1, set()), 0)
        self.assertIsNone(allocate_offset(1, {1}))
        self.assertEqual(allocate_offset(2, {2}), 1)
        self.assertIsNone(allocate_offset(2, {2, 1}))
        self.assertIsNone(allocate_offset(3, {3, 2, 1}))  # Would need 0 sen: never offered.

    def test_nine_sen_ceiling(self):
        self.assertEqual(allocate_offset(1000, set(range(992, 1001))), 9)
        self.assertIsNone(allocate_offset(1000, set(range(991, 1001))))
        self.assertIsNone(allocate_offset(1000, set(range(991, 1001)) - {990}))  # 990 would be k=10.

    def test_randomized_properties(self):
        # The repository has no property-testing library; a seeded randomized sweep instead.
        rng = random.Random(20261127)
        for _ in range(5000):
            share = rng.choice((1, 2, 3, 5, 9, 10, 11, rng.randint(1, 2000), rng.randint(1, 1_000_000)))
            excluded = {share - rng.randint(-3, 12) for _ in range(rng.randint(0, 14))}
            offset = allocate_offset(share, excluded)
            candidates = [k for k in range(10) if share - k >= 1 and share - k not in excluded]
            self.assertEqual(offset, candidates[0] if candidates else None, (share, sorted(excluded)))
            if offset is not None:
                self.assertTrue(0 <= offset <= 9 and 1 <= share - offset <= share)


class HoldRuleTests(unittest.TestCase):
    """Exclusion set (a): a superset of the bridge's Held rule from stored state."""
    def row(self, state, **values):
        base = {'state': state, 'not_created_reason': None, 'checkout_id': None, 'bridge_status': None,
                'expires_at': None, 'pay_sen': 5}
        base.update(values)
        return base

    def test_states(self):
        expires = '2026-11-17T04:10:00Z'
        window = T0 + 300
        after = T0 + 600 + demo.HOLD_SKEW_MARGIN_SECONDS
        bound = {'checkout_id': 'c'}
        cases = [
            (self.row('REQUEST_UNKNOWN'), window, True),
            (self.row('NOT_CREATED', not_created_reason='REFERENCE_NOT_FOUND'), after, True),
            (self.row('NOT_CREATED', not_created_reason='SAME_AMOUNT_HELD'), window, False),
            (self.row('CONFLICT', not_created_reason='OBSERVED_CHECKOUT_SPENT'), window, False),
            (self.row('CONFLICT', not_created_reason='OBSERVED_AMOUNT_MISMATCH'), window, False),
            (self.row('CONFLICT', **bound), after, True),
            (self.row('CONFLICT'), after, True),  # REFERENCE_CONFLICT: the reference exists on the bridge.
            (self.row('UNEXPECTED_STATUS', not_created_reason='EVIDENCE_MODE_MISMATCH'), after, True),
            (self.row('REFERENCE_LOST', **bound), after, True),
        ]
        for status in ('AWAITING_PAYMENT', 'PAYMENT_DETECTED', 'AWAITING_VERIFICATION', 'AMBIGUOUS'):
            cases.append((self.row('OBSERVED', bridge_status=status, expires_at=expires, **bound), after + 9999, True))
        for status in ('EXPIRED', 'REVIEW_EXPIRED'):
            cases.append((self.row('OBSERVED', bridge_status=status, expires_at=expires, **bound), window, False))
        confirmed = self.row('OBSERVED', bridge_status='MANUALLY_CONFIRMED', expires_at=expires, **bound)
        cases += [(confirmed, window, True), (confirmed, after - 0.001, True), (confirmed, after, False)]
        for row, now, expected in cases:
            with self.subTest(row=row, now=now):
                self.assertEqual(holds_amount(row, now), expected)


class MultiFixture(unittest.TestCase):
    """Organizer A paid the whole bill; each diner owes A exactly their own item's price."""
    shares = {'B': 863, 'C': 863, 'D': 500}
    count = 50

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'multi.sqlite'
        self.now = T0 + 5
        self.authority = Authority(self.path, clock=lambda: self.now)
        self.addCleanup(lambda: self.authority.close())
        people = (Participant('A', 'Organizer', True),) + tuple(
            Participant(p, f'Diner {p}') for p in self.shares)
        grants = self.authority.bootstrap('meal', people)
        self.cred = {s.participant_id: s.credential for s in grants.sessions}
        self.bridge_token = token()
        self.bridge = StubBridge(self.bridge_token, observed_count=self.count)
        self.addCleanup(self.bridge.close)
        self.cfg = CheckoutDemoConfig(NAMESPACE, self.bridge.base_url, self.bridge_token, observed=True, multi=True)
        self.client = CheckoutDemoClient(self.cfg)
        self.finalize()

    def snap(self, who='A'):
        return self.authority.snapshot(self.cred[who], 'meal')

    def apply(self, command, who='A'):
        return self.authority.apply(self.cred[who], 'meal', command)

    def finalize(self):
        items = (ReceiptItem('item-A', 'Organizer dish', 1, 1000),) + tuple(
            ReceiptItem('item-' + p, 'Dish ' + p, 1, share) for p, share in self.shares.items())
        total = sum(i.line_sen for i in items)
        s = self.snap()
        self.apply(ReplaceReceipt('receipt', s.revision, s.financial_revision, Receipt(items, total, total)))
        for person in ('A',) + tuple(self.shares):
            s = self.snap()
            revision = {i.item_id: i.item_revision for i in s.items}['item-' + person]
            self.apply(AssignParticipantQuantity('assign-' + person, person, 'item-' + person, Fraction(1), revision,
                                                 s.financial_revision))
        s = self.snap()
        self.apply(ReviewReceipt('review', s.revision, s.financial_revision, s.receipt_digest))
        s = self.snap()
        self.apply(Finalize('final', s.revision, s.financial_revision))
        s = self.snap()
        self.apply(RecordContribution('pay', s.revision, 'A', total, 'card'))

    def request(self, sender, pay, share=None, client=None, authority=None):
        return request_checkout_demo(authority or self.authority, self.cred['A'], 'meal', self.cfg,
                                     client or self.client, sender, self.shares[sender] if share is None else share,
                                     pay)

    def status(self, client=None):
        return checkout_demo_status(self.authority, self.cred['A'], 'meal', self.cfg, client or self.client)

    def code(self, call):
        with self.assertRaises(AuthorityError) as caught:
            call()
        return caught.exception.code

    def offers(self, result=None):
        result = result or self.status()
        return {e['senderId']: (e['amountSen'], e['offsetSen'], e['paySen'], e['action']) for e in result['eligible']}

    def waiting(self, result=None):
        return [e['senderId'] for e in (result or self.status())['noFreeAmount']]

    def intents(self, result=None):
        return {i['senderId']: i for i in (result or self.status())['intents']}

    def reference(self, sender):
        return self.intents()[sender]['reference']

    def puts(self):
        return [(m, json.loads(b)) for m, _, _, b in self.bridge.calls if m == 'PUT']

    def frozen(self):
        return self.authority._db.execute('''SELECT d.sender_id, d.amount_sen, o.offset_sen
            FROM checkout_demos d JOIN checkout_demo_offsets o USING (meal_id, attempt) ORDER BY d.attempt''').fetchall()

    def financial_state(self):
        db = self.authority._db
        tables = {name: db.execute(f'SELECT * FROM {name} ORDER BY rowid').fetchall() for name in FINANCIAL_TABLES}
        return tables, asdict(self.snap()).get('settlement'), asdict(self.snap()).get('funding')


class OffsetAllocationTests(MultiFixture):
    def test_duplicate_shares_never_get_the_plain_share(self):
        result = self.status()
        self.assertEqual((result['multi'], result['observed'], result['synthetic'], result['intents']),
                         (True, True, False, []))
        # B and C owe the same share: neither may pay it plainly. D's share is unique.
        self.assertEqual(self.offers(result), {'B': (863, 1, 862, 'NEW'), 'C': (863, 1, 862, 'NEW'),
                                               'D': (500, 0, 500, 'NEW')})
        before = self.financial_state()
        created = self.request('B', 862)
        intent = created['intent']
        self.assertEqual((intent['senderId'], intent['amountSen'], intent['offsetSen'], intent['paySen'],
                          intent['state']), ('B', 863, 1, 862, 'AWAITING_EVIDENCE'))
        self.assertEqual(self.bridge.calls[-1][3], b'{"amountMinor":862,"currency":"MYR"}')
        # Exclusion set (a): C now skips B's held 862 as well.
        self.assertEqual(self.offers(created)['C'], (863, 2, 861, 'NEW'))
        self.assertEqual(self.request('C', 861)['intents'][-1]['paySen'], 861)
        self.assertEqual(self.request('D', 500)['intents'][-1]['paySen'], 500)
        self.assertEqual(self.frozen(), [('B', 863, 1), ('C', 863, 2), ('D', 500, 0)])
        self.assertEqual([body['amountMinor'] for _, body in self.puts()], [862, 861, 500])
        self.assertEqual(self.financial_state(), before)  # Balances never change.
        self.assertEqual(self.offers(), {})

    def test_consent_to_the_exact_amount(self):
        self.request('B', 862)
        puts = len(self.puts())
        # C was offered 862 before B's checkout existed; the request refuses rather than substitute.
        self.assertEqual(self.code(lambda: self.request('C', 862)), 'checkout_demo_amount_changed')
        self.assertEqual(self.code(lambda: self.request('C', 863)), 'checkout_demo_amount_changed')
        self.assertEqual(self.code(lambda: self.request('C', 861, share=862)), 'checkout_demo_stale')
        self.assertEqual(len(self.puts()), puts)
        self.assertEqual([r[0] for r in self.frozen()], ['B'])
        with self.assertRaises(AuthorityError):
            request_checkout_demo(self.authority, self.cred['A'], 'meal', self.cfg, self.client, 'C', 863)

    def test_exclusion_b_drops_a_diner_with_a_confirmed_checkout(self):
        self.request('B', 862)
        self.bridge.observe_notification(self.reference('B'))
        self.bridge.confirm(self.reference('B'))
        result = self.status()
        self.assertEqual(self.intents(result)['B']['state'], 'MANUALLY_CONFIRMED')
        # B is confirmed, so B's plain share no longer excludes; B's 862 is held through its window.
        self.assertEqual(self.offers(result)['C'], (863, 0, 863, 'NEW'))
        ctx = demo._read(self.authority, self.cred['A'], 'meal', self.cfg)
        self.assertEqual(excluded_amounts(ctx, 'C'), {862, 500})
        self.assertEqual(excluded_amounts(ctx, 'D'), {862, 863})

    def test_a_confirmed_amount_frees_after_its_window_and_the_margin(self):
        self.request('B', 862)
        self.bridge.confirm(self.reference('B'))
        self.status()
        ctx = demo._read(self.authority, self.cred['A'], 'meal', self.cfg)
        self.assertIn(862, excluded_amounts(ctx, 'C'))
        self.now = T0 + 600 + demo.HOLD_SKEW_MARGIN_SECONDS
        ctx = demo._read(self.authority, self.cred['A'], 'meal', self.cfg)
        self.assertNotIn(862, excluded_amounts(ctx, 'C'))


class TinySharesFixture(MultiFixture):
    shares = {'B': 2, 'C': 2}


class NoFitAndReallocationTests(TinySharesFixture):
    def test_no_fit_state_floor_and_reallocation_after_expiry(self):
        self.assertEqual(self.offers(), {'B': (2, 1, 1, 'NEW'), 'C': (2, 1, 1, 'NEW')})
        created = self.request('B', 1)
        # C: 2 is B's plain share and 1 is held; 0 sen is never offered.
        self.assertEqual((self.offers(created), self.waiting(created)), ({}, ['C']))
        puts = len(self.puts())
        for pay in (1, 2):
            self.assertEqual(self.code(lambda: self.request('C', pay)), 'checkout_demo_no_free_amount')
        self.assertEqual(len(self.puts()), puts)
        self.assertEqual([r[0] for r in self.frozen()], ['B'])
        # An open status (here after the bridge's window, before any read shows the end) still holds.
        self.now = T0 + 700
        self.assertEqual(self.waiting(demo._projection(demo._read(self.authority, self.cred['A'], 'meal', self.cfg))),
                         ['C'])
        # The bridge ends B's checkout; the next read frees 1 sen for C. Nothing retries by itself.
        self.bridge.expire(self.reference('B'))
        result = self.status()
        self.assertEqual(self.intents(result)['B']['state'], 'EXPIRED')
        self.assertEqual((self.offers(result), self.waiting(result)), ({'C': (2, 1, 1, 'NEW')}, []))
        self.assertEqual(len(self.puts()), puts)
        self.assertEqual(self.request('C', 1)['intents'][-1]['paySen'], 1)
        # B's single use is spent: no new attempt for B, even though B still owes.
        self.assertNotIn('B', self.offers())
        self.assertEqual(self.code(lambda: self.request('B', 1)), 'resource_limit')


class CeilingFixture(MultiFixture):
    shares = {p: 1000 for p in 'BCDEFGHIJK'}  # Ten diners with one share.


class CeilingTests(CeilingFixture):
    def test_nine_offsets_then_no_fit(self):
        paid = []
        for diner in 'BCDEFGHIJ':
            offer = self.offers()[diner]
            self.request(diner, offer[2])
            paid.append(offer[1])
        self.assertEqual(paid, [1, 2, 3, 4, 5, 6, 7, 8, 9])
        self.assertEqual((self.offers(), self.waiting()), ({}, ['K']))
        amounts = [share - offset for _, share, offset in self.frozen()]
        self.assertEqual(sorted(amounts), list(range(991, 1000)))
        self.assertEqual(len(set(amounts)), 9)


class StubStatusTests(MultiFixture):
    """Every refusal and status of the multi-checkout stub, each shown as a plain state."""
    def test_lifecycle_including_ambiguous_delayed_and_confirmed(self):
        before = self.financial_state()
        self.request('B', 862)
        self.request('C', 861)
        self.request('D', 500)
        b, c, d = (self.reference(x) for x in 'BCD')
        self.bridge.delayed_notification(b)       # Stored DELAYED by the bridge, never matched.
        self.bridge.observe_notification(c)
        self.bridge.observe_notification(d)
        self.bridge.ambiguous(d)
        self.bridge.calls.clear()
        result = self.status()
        # One GET per open intent; no PUT from a status read.
        self.assertEqual(sorted(p.rsplit('/', 1)[1] for m, p, _, _ in self.bridge.calls if m == 'GET'), sorted((b, c, d)))
        self.assertFalse(any(m == 'PUT' for m, _, _, _ in self.bridge.calls))
        shown = {k: (v['state'], v['evidence'], v['terminal'], v['latched']) for k, v in self.intents(result).items()}
        self.assertEqual(shown, {'B': ('AWAITING_EVIDENCE', 'NONE', False, False),
                                 'C': ('EVIDENCE_DETECTED', 'NOTIFICATION_UNVERIFIED', False, False),
                                 'D': ('NEEDS_REVIEW', 'NOTIFICATION_UNVERIFIED', False, False)})
        self.assertIsNotNone(self.intents(result)['C']['reviewExpiresAt'])
        # M-4: an ambiguous match stays ambiguous and offers nothing new.
        self.assertEqual(self.offers(result), {})
        self.bridge.confirm(c)
        self.bridge.expire(b)
        self.bridge.review_expire(d)
        self.bridge.calls.clear()
        result = self.status()
        shown = {k: (v['state'], v['terminal']) for k, v in self.intents(result).items()}
        self.assertEqual(shown, {'B': ('EXPIRED', True), 'C': ('MANUALLY_CONFIRMED', True), 'D': ('EXPIRED', True)})
        self.assertEqual(self.intents(result)['C']['evidence'], 'NOTIFICATION_UNVERIFIED')
        self.assertEqual(len(self.bridge.calls), 3)
        # Finished intents are not read again.
        self.bridge.calls.clear()
        self.status()
        self.assertEqual(self.bridge.calls, [])
        self.assertEqual(self.financial_state(), before)
        self.assertFalse(self.snap().settlement.is_settled)

    def test_checkout_spent_latches_and_holds_nothing(self):
        self.bridge.observed_count = 1
        self.request('B', 862)
        refused = self.request('D', 500)
        intent = self.intents(refused)['D']
        self.assertEqual((intent['state'], intent['notCreatedReason'], intent['latched'], intent['checkoutId']),
                         ('CONFLICT', 'OBSERVED_CHECKOUT_SPENT', True, None))
        self.assertEqual(self.code(lambda: self.request('D', 500)), 'resource_limit')
        ctx = demo._read(self.authority, self.cred['A'], 'meal', self.cfg)
        self.assertNotIn(500, {r['pay_sen'] for r in ctx['rows'] if holds_amount(r, ctx['now'])})
        self.bridge.calls.clear()
        self.status()
        self.assertEqual([p.rsplit('/', 1)[1] for _, p, _, _ in self.bridge.calls], [self.reference('B')])

    def test_same_amount_held_is_plain_and_never_retried_with_another_amount(self):
        self.bridge.other_holds.add(500)
        refused = self.request('D', 500)
        intent = self.intents(refused)['D']
        self.assertEqual((intent['state'], intent['notCreatedReason'], intent['terminal']),
                         ('NOT_CREATED', 'SAME_AMOUNT_HELD', True))
        self.assertEqual([body['amountMinor'] for _, body in self.puts()], [500])
        self.assertNotIn('D', self.offers())
        self.assertEqual(self.code(lambda: self.request('D', 499)), 'resource_limit')
        self.assertEqual(len(self.puts()), 1)

    def test_amount_mismatch_from_a_single_checkout_bridge_latches(self):
        single = StubBridge(self.bridge_token, observed_amount=1)
        self.addCleanup(single.close)
        config = CheckoutDemoConfig(NAMESPACE, single.base_url, self.bridge_token, observed=True, multi=True)
        result = request_checkout_demo(self.authority, self.cred['A'], 'meal', config, CheckoutDemoClient(config),
                                       'D', 500, 500)
        intent = self.intents(result)['D']
        self.assertEqual((intent['state'], intent['notCreatedReason'], intent['latched']),
                         ('CONFLICT', 'OBSERVED_AMOUNT_MISMATCH', True))

    def test_mode_mismatch_latches_without_binding(self):
        self.bridge.synthetic_mode()
        intent = self.intents(self.request('D', 500))['D']
        self.assertEqual((intent['state'], intent['notCreatedReason'], intent['checkoutId']),
                         ('UNEXPECTED_STATUS', 'EVIDENCE_MODE_MISMATCH', None))
        # The bridge did create a checkout, so its amount stays held.
        self.assertEqual(self.offers()['B'][2], 862)
        ctx = demo._read(self.authority, self.cred['A'], 'meal', self.cfg)
        self.assertIn(500, excluded_amounts(ctx, 'B'))

    def test_unknown_outcome_then_checked_absence_then_identical_reput(self):
        self.bridge.fail = 'drop'
        unknown = self.request('D', 500)
        self.assertEqual(self.intents(unknown)['D']['state'], 'REQUEST_UNKNOWN')
        self.assertNotIn('D', self.offers(unknown))
        # The unknown amount stays held for everyone else.
        ctx = demo._read(self.authority, self.cred['A'], 'meal', self.cfg)
        self.assertIn(500, excluded_amounts(ctx, 'B'))
        # The next explicit action for D is a GET, never a new PUT.
        self.bridge.fail = None
        self.bridge.calls.clear()
        checked = self.request('D', 500)
        self.assertEqual([m for m, _, _, _ in self.bridge.calls], ['GET'])
        intent = self.intents(checked)['D']
        self.assertEqual((intent['state'], intent['notCreatedReason']), ('NOT_CREATED', 'REFERENCE_NOT_FOUND'))
        self.assertEqual(self.offers(checked)['D'], (500, 0, 500, 'RETRY'))
        ctx = demo._read(self.authority, self.cred['A'], 'meal', self.cfg)
        self.assertIn(500, excluded_amounts(ctx, 'B'))  # Kept for the identical re-PUT.
        reference = intent['reference']
        self.bridge.calls.clear()
        again = self.request('D', 500)
        self.assertEqual([(m, p.rsplit('/', 1)[1], b) for m, p, _, b in self.bridge.calls],
                         [('PUT', reference, b'{"amountMinor":500,"currency":"MYR"}')])
        self.assertEqual((self.intents(again)['D']['state'], self.intents(again)['D']['possibleDispatches']),
                         ('AWAITING_EVIDENCE', 2))

    def test_unavailable_read_keeps_state_and_other_intents(self):
        self.request('B', 862)
        self.request('D', 500)
        self.bridge.fail = 'malformed'
        result = self.status()
        self.assertEqual({k: (v['state'], v['lastKnownState']) for k, v in self.intents(result).items()},
                         {'B': ('UNAVAILABLE', 'AWAITING_EVIDENCE'), 'D': ('UNAVAILABLE', 'AWAITING_EVIDENCE')})
        self.assertEqual(result['lastCheck'], 'UNAVAILABLE')

    def test_bridge_answer_with_another_amount_conflicts(self):
        self.request('B', 862)
        with self.bridge.lock:
            self.bridge.checkouts[self.reference('B')]['amountMinor'] = 863
            self.bridge.checkouts[self.reference('B')]['revision'] += 1
        intent = self.intents()['B']
        self.assertEqual((intent['state'], intent['latched']), ('CONFLICT', True))

    def test_projection_carries_no_names_and_no_credentials(self):
        self.request('B', 862)
        self.bridge.observe_notification(self.reference('B'))
        text = json.dumps(self.status())
        for secret in ('Diner B', 'Diner C', 'Organizer', self.bridge_token, self.cred['A']):
            self.assertNotIn(secret, text)


class FlagAbsentTests(MultiFixture):
    """Without the variable, single observed mode: same keys, one attempt per meal, no offset row."""
    def test_single_observed_mode_is_unchanged(self):
        single = CheckoutDemoConfig(NAMESPACE, self.bridge.base_url, self.bridge_token, observed=True)
        client = CheckoutDemoClient(single)
        status = checkout_demo_status(self.authority, self.cred['A'], 'meal', single, client)
        self.assertEqual(list(status), ['enabled', 'synthetic', 'intent', 'eligible', 'lastCheck', 'retryAfter',
                                        'observed', 'evidenceMode'])
        self.assertEqual(status['eligible'][0], {'senderId': 'B', 'receiverId': 'A', 'amountSen': 863, 'action': 'NEW'})
        with self.assertRaises(AuthorityError):  # No pay_sen outside multi mode.
            request_checkout_demo(self.authority, self.cred['A'], 'meal', single, client, 'B', 863, 862)
        created = request_checkout_demo(self.authority, self.cred['A'], 'meal', single, client, 'B', 863)
        self.assertEqual(self.bridge.calls[-1][3], b'{"amountMinor":863,"currency":"MYR"}')  # The plain share.
        self.assertEqual(list(created['intent']), [
            'attempt', 'reference', 'senderId', 'receiverId', 'amountSen', 'state', 'lastKnownState',
            'notCreatedReason', 'referenceLost', 'checkoutId', 'bridgeStatus', 'evidence', 'revision', 'createdAt',
            'expiresAt', 'reviewExpiresAt', 'observedAt', 'possibleDispatches', 'stale', 'terminal', 'latched'])
        self.assertEqual(created['eligible'], [])  # One attempt per meal, as before.
        self.assertEqual(self.authority._db.execute('SELECT COUNT(*) FROM checkout_demo_offsets').fetchone()[0], 0)


class StorageGuardTests(MultiFixture):
    def test_rows_without_an_offset_or_offsets_outside_multi_mode_fail_closed(self):
        self.request('B', 862)
        single = CheckoutDemoConfig(NAMESPACE, self.bridge.base_url, self.bridge_token, observed=True)
        with self.assertRaises(AuthorityError) as caught:
            demo._read(self.authority, self.cred['A'], 'meal', single)
        self.assertEqual(caught.exception.code, 'checkout_demo_conflict')
        self.authority._db.execute('DELETE FROM checkout_demo_offsets')
        with self.assertRaises(AuthorityError) as caught:
            demo._read(self.authority, self.cred['A'], 'meal', self.cfg)
        self.assertEqual(caught.exception.code, 'checkout_demo_conflict')

    def test_out_of_range_offsets_are_refused_by_storage(self):
        self.request('B', 862)
        with self.assertRaises(Exception):
            self.authority._db.execute('UPDATE checkout_demo_offsets SET offset_sen=10')
        self.authority._db.execute("UPDATE checkout_demo_offsets SET offset_sen=0")
        # A tampered offset changes the reconstructed amount; the next bridge answer conflicts.
        intent = self.intents()['B']
        self.assertEqual((intent['state'], intent['latched']), ('CONFLICT', True))

    def test_attempt_beyond_the_mode_limit_fails_closed_as_a_conflict(self):
        # Multi intents use attempts beyond the single-mode limit; read without multi mode,
        # they are refused as a storage conflict, never as a caller input error.
        self.request('B', 862)
        self.request('C', 861)
        single = dc_replace(self.cfg, multi=False)
        with patch.object(demo, 'MAX_ATTEMPTS', 1):
            with self.assertRaises(AuthorityError) as caught:
                demo._read(self.authority, self.cred['A'], 'meal', single)
        self.assertEqual(caught.exception.code, 'checkout_demo_conflict')

    def test_reference_is_unchanged_by_the_offset(self):
        self.request('B', 862)
        self.assertEqual(self.reference('B'), checkout_reference(NAMESPACE, 'meal', 'A', 'final', 'B', 'A', 1))


class ConcurrencyTests(MultiFixture):
    """M-3 rule 6: two allocations for the same meal never produce the same amount.

    Each thread opens its own connection (SQLite connections are thread-bound) and the
    in-process wire slot is widened, so only the storage write lock serializes them.
    """
    shares = {'B': 863, 'C': 863, 'D': 863, 'E': 863}

    def run_in_thread(self, results, name, work, hook=None):
        def target():
            authority = Authority(self.path, clock=lambda: self.now, failure_hook=hook)
            try:
                results[name] = work(authority)
            except Exception as error:
                results[name] = error
            finally:
                authority.close()
        thread = threading.Thread(target=target)
        thread.start()
        return thread

    def test_overlapping_allocations_are_serialized_by_the_write_lock(self):
        entered, release = threading.Event(), threading.Event()

        def pause(stage):
            if stage == 'checkout_demo_before_intent_commit' and not entered.is_set():
                entered.set()
                release.wait(5)
        results = {}
        offered = self.offers()
        self.assertEqual((offered['B'][2], offered['C'][2]), (862, 862))
        with patch.object(demo, '_wire_slot', threading.Semaphore(4)):
            one = self.run_in_thread(results, 'B', lambda a: self.request('B', 862, client=CheckoutDemoClient(self.cfg),
                                                                          authority=a), pause)
            self.assertTrue(entered.wait(5), results)
            # B's 862 is frozen but not committed. C, also offered 862, waits for the write lock.
            two = self.run_in_thread(results, 'C', lambda a: self.request('C', 862, client=CheckoutDemoClient(self.cfg),
                                                                          authority=a))
            two.join(0.3)
            self.assertTrue(two.is_alive())
            release.set()
            one.join(10)
            two.join(10)
        self.assertEqual(results['B']['intents'][0]['paySen'], 862)
        # C saw B's frozen 862 and refused the stale amount instead of duplicating it.
        self.assertIsInstance(results['C'], AuthorityError)
        self.assertEqual(results['C'].code, 'checkout_demo_amount_changed')
        self.assertEqual(self.frozen(), [('B', 863, 1)])
        self.assertEqual(self.offers()['C'][2], 861)

    def test_many_concurrent_allocations_never_duplicate(self):
        start = threading.Barrier(4)
        results, codes = {}, []

        def work(sender):
            def attempt(authority):
                start.wait(5)
                for _ in range(40):
                    try:
                        offers = demo._eligible_multi(demo._read(authority, self.cred['A'], 'meal', self.cfg))[0]
                        mine = [o for o in offers if o['senderId'] == sender]
                        if not mine:
                            return None
                        return request_checkout_demo(authority, self.cred['A'], 'meal', self.cfg,
                                                     CheckoutDemoClient(self.cfg), sender, mine[0]['amountSen'],
                                                     mine[0]['paySen'])
                    except AuthorityError as error:
                        codes.append(error.code)  # amount_changed after a lost race, or a busy write lock.
                return None
            return attempt
        with patch.object(demo, '_wire_slot', threading.Semaphore(4)):
            threads = [self.run_in_thread(results, s, work(s)) for s in 'BCDE']
            for thread in threads:
                thread.join(60)
        frozen = self.frozen()
        amounts = [share - offset for _, share, offset in frozen]
        self.assertEqual(len(amounts), len(set(amounts)), frozen)
        self.assertEqual(sorted(s for s, _, _ in frozen), ['B', 'C', 'D', 'E'], (results, codes))
        self.assertEqual(sorted(amounts), [859, 860, 861, 862])
        self.assertTrue(set(codes) <= {'checkout_demo_amount_changed', 'storage_error', 'storage_busy'}, codes)
        # The bridge saw each amount once.
        self.assertEqual(sorted(body['amountMinor'] for _, body in self.puts()), [859, 860, 861, 862])

    def test_same_process_requests_are_refused_while_one_is_on_the_wire(self):
        self.assertTrue(demo._wire_slot.acquire(blocking=False))
        try:
            busy = self.request('B', 862)
        finally:
            demo._wire_slot.release()
        self.assertEqual((busy['lastCheck'], busy['intents']), ('BUSY', []))
        self.assertEqual(self.frozen(), [])


class MultiHttpRouteTests(MultiFixture):
    def app(self, config):
        app = SettleTableApp(self.path, clock=lambda: self.now, checkout_demo_config=config,
                             checkout_demo_client=CheckoutDemoClient(config))
        self.addCleanup(app.close)
        return TransportTestClient(app)

    def test_snapshot_flag_body_and_errors(self):
        org = {'HTTP_AUTHORIZATION': 'Bearer ' + self.cred['A']}
        diner = {'HTTP_AUTHORIZATION': 'Bearer ' + self.cred['B']}
        client = self.app(self.cfg)
        snapshot = json.loads(client.get('/api/meals/meal/snapshot', org)['body'])
        self.assertEqual((snapshot['checkout_demo_observed'], snapshot['checkout_demo_multi']), (True, True))
        dsnap = json.loads(client.get('/api/meals/meal/snapshot', diner)['body'])
        self.assertNotIn('checkout_demo_multi', dsnap)
        self.assertEqual(client.get('/api/meals/meal/checkout-demo', diner)['status'], 403)
        for body in ({'sender_id': 'B', 'amount_sen': 863}, {'sender_id': 'B', 'amount_sen': 863, 'pay_sen': 0},
                     {'sender_id': 'B', 'amount_sen': 863, 'pay_sen': 864},
                     {'sender_id': 'B', 'amount_sen': 863, 'pay_sen': '862'},
                     {'sender_id': 'B', 'amount_sen': 863, 'pay_sen': 862, 'x': 1}):
            with self.subTest(body=body):
                self.assertEqual(client.post('/api/meals/meal/checkout-demo', body, org)['status'], 400)
        self.assertEqual(self.bridge.calls, [])
        created = client.post('/api/meals/meal/checkout-demo', {'sender_id': 'B', 'amount_sen': 863, 'pay_sen': 862}, org)
        payload = json.loads(created['body'])['checkout_demo']
        self.assertEqual((created['status'], payload['multi'], payload['intents'][0]['paySen']), (200, True, 862))
        changed = client.post('/api/meals/meal/checkout-demo', {'sender_id': 'C', 'amount_sen': 863, 'pay_sen': 862}, org)
        self.assertEqual((changed['status'], json.loads(changed['body'])['error']), (409, 'checkout_demo_amount_changed'))

    def test_no_free_amount_is_409_and_single_mode_refuses_the_extra_key(self):
        org = {'HTTP_AUTHORIZATION': 'Bearer ' + self.cred['A']}
        client = self.app(self.cfg)
        self.bridge.other_holds.clear()
        with patch.object(demo, 'allocate_offset', return_value=None):
            refused = client.post('/api/meals/meal/checkout-demo', {'sender_id': 'D', 'amount_sen': 500, 'pay_sen': 500}, org)
        self.assertEqual((refused['status'], json.loads(refused['body'])['error']), (409, 'checkout_demo_no_free_amount'))
        single = CheckoutDemoConfig(NAMESPACE, self.bridge.base_url, self.bridge_token, observed=True)
        other = self.app(single)
        body = {'sender_id': 'D', 'amount_sen': 500, 'pay_sen': 500}
        self.assertEqual(other.post('/api/meals/meal/checkout-demo', body, org)['status'], 400)
        snapshot = json.loads(other.get('/api/meals/meal/snapshot', org)['body'])
        self.assertTrue(snapshot['checkout_demo_observed'])
        self.assertNotIn('checkout_demo_multi', snapshot)
        self.assertEqual(self.bridge.calls, [])


class ReviewRegressionTests(MultiFixture):
    """Regressions for the independent review findings."""
    shares = {'B': 863, 'C': 863, 'D': 863}

    def open_three(self):
        self.request('B', 862)
        self.request('C', 861)
        self.request('D', 860)

    def test_a_hung_bridge_costs_one_get_per_status_read(self):
        self.open_three()
        self.bridge.fail = 'drop'
        self.bridge.calls.clear()
        result = self.status()
        self.assertEqual(len(self.bridge.calls), 1)  # Stops after the first transport failure.
        self.assertEqual({k: (v['state'], v['lastKnownState']) for k, v in self.intents(result).items()},
                         {s: ('UNAVAILABLE', 'AWAITING_EVIDENCE') for s in 'BCD'})
        self.assertEqual(result['lastCheck'], 'UNAVAILABLE')
        self.bridge.fail = None
        self.bridge.calls.clear()
        self.assertEqual({v['state'] for v in self.intents().values()}, {'AWAITING_EVIDENCE'})
        self.assertEqual(len(self.bridge.calls), 3)

    def test_the_read_budget_bounds_the_wire_slot(self):
        self.open_three()
        self.bridge.calls.clear()
        with patch.object(demo, 'STATUS_READ_BUDGET_SECONDS', 0):
            result = self.status()
        self.assertEqual(len(self.bridge.calls), 1)
        shown = {k: v['state'] for k, v in self.intents(result).items()}
        self.assertEqual(shown, {'B': 'AWAITING_EVIDENCE', 'C': 'UNAVAILABLE', 'D': 'UNAVAILABLE'})

    def test_a_cooldown_mid_loop_sends_nothing_more(self):
        self.open_three()
        self.bridge.fail = (429, {'error': 'RATE_LIMITED'})
        self.bridge.calls.clear()
        result = self.status()
        self.assertEqual(len(self.bridge.calls), 1)
        self.assertTrue(all(v['state'] == 'UNAVAILABLE' for v in self.intents(result).values()))
        self.assertEqual(result['retryAfter'], 1)

    def test_a_refused_post_marks_open_intents_unavailable_and_freezes_nothing(self):
        self.request('B', 862)
        self.client.suspended = True
        self.bridge.calls.clear()
        result = self.request('C', 861)
        self.assertEqual((result['lastCheck'], self.intents(result)['B']['state']), ('UNAVAILABLE', 'UNAVAILABLE'))
        self.assertEqual(self.intents(result)['B']['lastKnownState'], 'AWAITING_EVIDENCE')
        self.assertEqual(self.bridge.calls, [])
        self.assertEqual([r[0] for r in self.frozen()], ['B'])
        # The admission path still applies the multi-mode refusals.
        self.assertEqual(self.code(lambda: self.request('C', 862)), 'checkout_demo_amount_changed')

    def test_a_confirmed_amount_is_reused_after_its_window_and_the_bridge_accepts_it(self):
        self.request('B', 862)
        self.request('C', 861)
        self.bridge.confirm(self.reference('B'))
        self.assertEqual(self.offers()['D'], (863, 3, 860, 'NEW'))  # 862 held through B's window.
        self.bridge.advance(601)
        self.now = T0 + 600 + demo.HOLD_SKEW_MARGIN_SECONDS
        self.assertEqual(self.offers()['D'], (863, 1, 862, 'NEW'))
        created = self.intents(self.request('D', 862))['D']
        self.assertEqual((created['state'], created['paySen']), ('AWAITING_EVIDENCE', 862))

    def test_route_authenticates_before_judging_the_body(self):
        app = SettleTableApp(self.path, clock=lambda: self.now, checkout_demo_config=self.cfg,
                             checkout_demo_client=self.client)
        self.addCleanup(app.close)
        client = TransportTestClient(app)
        bodies = ({'sender_id': 'B', 'amount_sen': 863}, {'sender_id': 'B', 'amount_sen': 863, 'pay_sen': 862},
                  {'x': 1})
        for who, expected in (('B', 403), ('bogus', 401)):
            headers = {'HTTP_AUTHORIZATION': 'Bearer ' + (self.cred[who] if who in self.cred else 'x' * 43)}
            statuses = {client.post('/api/meals/meal/checkout-demo', body, headers)['status'] for body in bodies}
            self.assertEqual(statuses, {expected}, who)
        self.assertEqual(self.bridge.calls, [])

    def test_202_when_any_intent_outcome_is_unknown(self):
        app = SettleTableApp(self.path, clock=lambda: self.now, checkout_demo_config=self.cfg,
                             checkout_demo_client=self.client)
        self.addCleanup(app.close)
        client = TransportTestClient(app)
        org = {'HTTP_AUTHORIZATION': 'Bearer ' + self.cred['A']}
        self.bridge.fail = 'drop'
        self.request('B', 862)
        self.bridge.fail = None
        response = client.post('/api/meals/meal/checkout-demo', {'sender_id': 'C', 'amount_sen': 863, 'pay_sen': 861}, org)
        payload = json.loads(response['body'])['checkout_demo']
        self.assertEqual(payload['intent']['senderId'], 'C')
        self.assertEqual(payload['intent']['state'], 'AWAITING_EVIDENCE')
        self.assertEqual(response['status'], 202)  # B, not the latest intent, is still unknown.


if __name__ == '__main__':
    unittest.main()
