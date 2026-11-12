"""Tests for collaborative payment confirmation: diner reporting, recipient/organizer confirmation,
authorization isolation, concurrency protection, and balance invariance.
"""
from fractions import Fraction
import os
import tempfile
import unittest

from settletable import calculation as calc
from settletable.authority import (
    Authority, AuthorityError, Participant, ReplaceReceipt, ReviewReceipt, Finalize,
    SetOwnQuantity, RecordContribution, ReverseContribution, RecordTransfer, ReverseTransfer,
    ReportContribution, ConfirmContribution, DeclineContribution, CancelContribution,
    ReportTransfer, ConfirmTransfer, DeclineTransfer, CancelTransfer,
    Receipt, ReceiptItem,
)
from settletable.transport import SettleTableApp


class TestCollaborativePaymentBackend(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False)
        self.tmp.close()
        self.auth = Authority(self.tmp.name)
        self.meal_id = 'test-meal-collab-payment'

        # Alice = Organizer, Bob = Diner 1, Charlie = Diner 2
        p1 = Participant('alice', 'Alice', True)
        p2 = Participant('bob', 'Bob', False)
        p3 = Participant('charlie', 'Charlie', False)
        res = self.auth.bootstrap(self.meal_id, (p1, p2, p3))
        self.alice_cred = res.sessions[0].credential
        self.bob_cred = res.sessions[1].credential
        self.charlie_cred = res.sessions[2].credential

    def tearDown(self):
        self.auth.close()
        try:
            os.remove(self.tmp.name)
        except OSError:
            pass

    def _setup_finalized_meal(self):
        # Alice consumed RM 20.00, Bob consumed RM 30.00, Charlie consumed RM 50.00. Total = RM 100.00 (10000 sen)
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        rcpt = Receipt(
            items=(
                ReceiptItem('item-1', 'Alice dish', Fraction(1), 2000),
                ReceiptItem('item-2', 'Bob dish', Fraction(1), 3000),
                ReceiptItem('item-3', 'Charlie dish', Fraction(1), 5000),
            ),
            subtotal_sen=10000,
            total_sen=10000,
        )
        self.auth.apply(self.alice_cred, self.meal_id, ReplaceReceipt('cmd-rcpt', snap.revision, snap.financial_revision, rcpt))

        # Claim items
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        item_rev = {i.item_id: i.item_revision for i in snap.items}
        self.auth.apply(self.alice_cred, self.meal_id, SetOwnQuantity('cmd-claim-a', 'item-1', Fraction(1), item_rev['item-1'], snap.financial_revision))
        self.auth.apply(self.bob_cred, self.meal_id, SetOwnQuantity('cmd-claim-b', 'item-2', Fraction(1), item_rev['item-2'], snap.financial_revision))
        self.auth.apply(self.charlie_cred, self.meal_id, SetOwnQuantity('cmd-claim-c', 'item-3', Fraction(1), item_rev['item-3'], snap.financial_revision))

        # Review & Finalize
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, ReviewReceipt('cmd-rev', snap.revision, snap.financial_revision, snap.receipt_digest))
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, Finalize('cmd-fin', snap.revision, snap.financial_revision))

    def test_restaurant_payment_diner_report_and_organizer_confirm(self):
        self._setup_finalized_meal()
        snap = self.auth.snapshot(self.bob_cred, self.meal_id)
        self.assertEqual(snap.funding.status, 'not_funded')
        self.assertEqual(snap.funding.unfunded_sen, 10000)

        # Bob reports paying RM 60.00 (6000 sen) at counter via card
        cmd = ReportContribution('cmd-pcontrib-1', snap.revision, 'bob', 6000, 'card')
        res = self.auth.apply(self.bob_cred, self.meal_id, cmd)
        self.assertEqual(res.kind, 'ReportContribution')
        report_id = res.report_id
        self.assertTrue(report_id.startswith('pcontrib-'))

        # Balance invariant: Pending report must NOT affect funding or balances
        snap_after_report = self.auth.snapshot(self.bob_cred, self.meal_id)
        self.assertEqual(snap_after_report.funding.status, 'not_funded')
        self.assertEqual(snap_after_report.funding.total_contributed_sen, 0)
        self.assertEqual(snap_after_report.funding.unfunded_sen, 10000)
        self.assertEqual(len(snap_after_report.pending_contributions), 1)
        p_rec = snap_after_report.pending_contributions[0]
        self.assertEqual(p_rec.status, 'pending')
        self.assertEqual(p_rec.amount_sen, 6000)
        self.assertEqual(p_rec.participant_id, 'bob')
        self.assertEqual(p_rec.created_by, 'bob')

        # Bob cannot confirm his own restaurant payment (requires organizer)
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.bob_cred, self.meal_id, ConfirmContribution('cmd-conf-bob', snap_after_report.revision, report_id))
        self.assertEqual(ctx.exception.code, 'forbidden')

        # Organizer (Alice) confirms Bob's contribution
        snap_org = self.auth.snapshot(self.alice_cred, self.meal_id)
        conf_cmd = ConfirmContribution('cmd-conf-org', snap_org.revision, report_id)
        conf_res = self.auth.apply(self.alice_cred, self.meal_id, conf_cmd)
        self.assertEqual(conf_res.kind, 'ConfirmContribution')
        self.assertIsNotNone(conf_res.contribution_id)

        # After confirmation: authoritative ledger updated exactly once
        snap_final = self.auth.snapshot(self.bob_cred, self.meal_id)
        self.assertEqual(snap_final.funding.status, 'partially_funded')
        self.assertEqual(snap_final.funding.total_contributed_sen, 6000)
        self.assertEqual(snap_final.funding.unfunded_sen, 4000)
        self.assertEqual(len(snap_final.contributions), 1)
        contrib = snap_final.contributions[0]
        self.assertEqual(contrib.amount_sen, 6000)
        self.assertEqual(contrib.participant_id, 'bob')
        # Audit attribution: reported by Bob, confirmed by Alice
        self.assertEqual(contrib.reported_by, 'bob')
        self.assertEqual(contrib.reported_by_name, 'Bob')
        self.assertEqual(contrib.confirmed_by, 'alice')
        self.assertEqual(contrib.confirmed_by_name, 'Alice')

    def test_restaurant_payment_decline_and_cancel(self):
        self._setup_finalized_meal()
        snap = self.auth.snapshot(self.bob_cred, self.meal_id)

        # Bob reports RM 20.00
        cmd = ReportContribution('cmd-p1', snap.revision, 'bob', 2000, 'cash')
        res = self.auth.apply(self.bob_cred, self.meal_id, cmd)
        report_id = res.report_id

        # Bob cancels his own pending report
        snap = self.auth.snapshot(self.bob_cred, self.meal_id)
        cancel_cmd = CancelContribution('cmd-cancel', snap.revision, report_id)
        self.auth.apply(self.bob_cred, self.meal_id, cancel_cmd)

        snap = self.auth.snapshot(self.bob_cred, self.meal_id)
        p_rec = snap.pending_contributions[0]
        self.assertEqual(p_rec.status, 'cancelled')

        # Cannot confirm or decline a cancelled report
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.alice_cred, self.meal_id, ConfirmContribution('cmd-conf-fail', snap.revision, report_id))
        self.assertEqual(ctx.exception.code, 'invalid_report_status')

        # Charlie reports RM 30.00
        cmd2 = ReportContribution('cmd-p2', snap.revision, 'charlie', 3000, 'cash')
        res2 = self.auth.apply(self.charlie_cred, self.meal_id, cmd2)
        report2_id = res2.report_id

        # Bob cannot cancel Charlie's report
        snap = self.auth.snapshot(self.bob_cred, self.meal_id)
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.bob_cred, self.meal_id, CancelContribution('cmd-cancel-bad', snap.revision, report2_id))
        self.assertEqual(ctx.exception.code, 'forbidden')

        # Organizer declines Charlie's report
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        decline_cmd = DeclineContribution('cmd-dec', snap.revision, report2_id, 'Not received at counter')
        self.auth.apply(self.alice_cred, self.meal_id, decline_cmd)

        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        declined_rec = next(r for r in snap.pending_contributions if r.report_id == report2_id)
        self.assertEqual(declined_rec.status, 'declined')
        self.assertEqual(declined_rec.rejection_reason, 'Not received at counter')

    def test_restaurant_payment_cannot_report_for_others_or_exceed_bill(self):
        self._setup_finalized_meal()
        snap = self.auth.snapshot(self.bob_cred, self.meal_id)

        # Bob cannot report payment for Charlie
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.bob_cred, self.meal_id, ReportContribution('cmd-bad-payer', snap.revision, 'charlie', 1000))
        self.assertEqual(ctx.exception.code, 'not_the_payer')

        # Bob cannot report amount greater than unfunded bill (10000 sen)
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.bob_cred, self.meal_id, ReportContribution('cmd-over', snap.revision, 'bob', 15000))
        self.assertEqual(ctx.exception.code, 'amount_exceeds_unfunded')

        # Bob reports 8000 sen (valid)
        self.auth.apply(self.bob_cred, self.meal_id, ReportContribution('cmd-valid', snap.revision, 'bob', 8000))

        # Bob tries reporting another 5000 sen while 8000 sen is pending (8000 + 5000 = 13000 > 10000)
        snap = self.auth.snapshot(self.bob_cred, self.meal_id)
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.bob_cred, self.meal_id, ReportContribution('cmd-over-pending', snap.revision, 'bob', 5000))
        self.assertEqual(ctx.exception.code, 'amount_exceeds_unfunded')

    def test_peer_reimbursement_collaborative_workflow(self):
        self._setup_finalized_meal()
        # Alice (Organizer) directly records funding the whole RM 100.00 bill
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, RecordContribution('cmd-fund-all', snap.revision, 'alice', 10000, 'card'))

        # Alice: paid 10000, consumed 2000 -> Creditor (+8000)
        # Bob: paid 0, consumed 3000 -> Debtor (-3000)
        # Charlie: paid 0, consumed 5000 -> Debtor (-5000)
        snap = self.auth.snapshot(self.bob_cred, self.meal_id)
        self.assertTrue(snap.funding.status, 'fully_funded')
        self.assertEqual(len(snap.settlement.suggested_transfers), 2)

        # Bob reports "I've Sent Payment" of RM 30.00 (3000 sen) to Alice
        cmd = ReportTransfer('cmd-xfer-b', snap.revision, 'bob', 'alice', 3000, 'DuitNow ref 1234')
        res = self.auth.apply(self.bob_cred, self.meal_id, cmd)
        report_id = res.report_id
        self.assertTrue(report_id.startswith('pxfer-'))

        # Balance check: Pending transfer does NOT update outstanding balances
        snap_after = self.auth.snapshot(self.bob_cred, self.meal_id)
        b_bob = next(b for b in snap_after.settlement.outstanding_net_balances if b.participant_id == 'bob')
        self.assertEqual(b_bob.outstanding_net_balance_sen, -3000)  # still owes 3000

        # Bob (sender) CANNOT confirm his own payment!
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.bob_cred, self.meal_id, ConfirmTransfer('cmd-self-conf', snap_after.revision, report_id))
        self.assertEqual(ctx.exception.code, 'not_the_recipient')

        # Charlie (unauthorized third party) CANNOT confirm Bob's payment to Alice!
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.charlie_cred, self.meal_id, ConfirmTransfer('cmd-charlie-conf', snap_after.revision, report_id))
        self.assertEqual(ctx.exception.code, 'not_the_recipient')

        # Alice (recipient creditor) confirms received
        snap_alice = self.auth.snapshot(self.alice_cred, self.meal_id)
        conf_res = self.auth.apply(self.alice_cred, self.meal_id, ConfirmTransfer('cmd-alice-conf', snap_alice.revision, report_id))
        self.assertEqual(conf_res.kind, 'ConfirmTransfer')
        self.assertIsNotNone(conf_res.transfer_id)

        # Balances after confirmation: Bob is now fully settled!
        snap_final = self.auth.snapshot(self.bob_cred, self.meal_id)
        b_bob_final = next(b for b in snap_final.settlement.outstanding_net_balances if b.participant_id == 'bob')
        self.assertEqual(b_bob_final.outstanding_net_balance_sen, 0)
        self.assertEqual(b_bob_final.confirmed_sent_sen, 3000)

        # Audit attribution: reported by Bob, confirmed by Alice
        xfer = snap_final.transfers[0]
        self.assertEqual(xfer.amount_sen, 3000)
        self.assertEqual(xfer.reported_by, 'bob')
        self.assertEqual(xfer.reported_by_name, 'Bob')
        self.assertEqual(xfer.confirmed_by, 'alice')
        self.assertEqual(xfer.confirmed_by_name, 'Alice')

    def test_peer_reimbursement_decline_and_cancel(self):
        self._setup_finalized_meal()
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, RecordContribution('cmd-fund', snap.revision, 'alice', 10000, 'card'))

        # Charlie owes 5000. Charlie reports sending 2000 to Alice.
        snap = self.auth.snapshot(self.charlie_cred, self.meal_id)
        res = self.auth.apply(self.charlie_cred, self.meal_id, ReportTransfer('cmd-c-rep', snap.revision, 'charlie', 'alice', 2000))
        report_id = res.report_id

        # Charlie cancels his own report
        snap = self.auth.snapshot(self.charlie_cred, self.meal_id)
        self.auth.apply(self.charlie_cred, self.meal_id, CancelTransfer('cmd-c-cancel', snap.revision, report_id))

        snap = self.auth.snapshot(self.charlie_cred, self.meal_id)
        p_rec = next(r for r in snap.pending_transfers if r.report_id == report_id)
        self.assertEqual(p_rec.status, 'cancelled')

        # Charlie reports sending 5000 to Alice
        snap = self.auth.snapshot(self.charlie_cred, self.meal_id)
        res2 = self.auth.apply(self.charlie_cred, self.meal_id, ReportTransfer('cmd-c-rep2', snap.revision, 'charlie', 'alice', 5000))
        report2_id = res2.report_id

        # Alice declines (marks "Not Received")
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, DeclineTransfer('cmd-a-dec', snap.revision, report2_id, 'Not in my account'))

        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        p_rec2 = next(r for r in snap.pending_transfers if r.report_id == report2_id)
        self.assertEqual(p_rec2.status, 'declined')
        self.assertEqual(p_rec2.rejection_reason, 'Not in my account')

    def test_peer_reimbursement_restrictions(self):
        self._setup_finalized_meal()
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, RecordContribution('cmd-fund', snap.revision, 'alice', 10000, 'card'))

        snap = self.auth.snapshot(self.bob_cred, self.meal_id)
        # Cannot report transfer to self
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.bob_cred, self.meal_id, ReportTransfer('cmd-self', snap.revision, 'bob', 'bob', 1000))
        self.assertEqual(ctx.exception.code, 'self_transfer_prohibited')

        # Cannot report transfer from Alice (creditor) to Bob (debtor)
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.alice_cred, self.meal_id, ReportTransfer('cmd-cred-send', snap.revision, 'alice', 'bob', 1000))
        self.assertEqual(ctx.exception.code, 'not_a_debtor')

        # Bob owes 3000. Cannot report 4000 (exceeds debt)
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.bob_cred, self.meal_id, ReportTransfer('cmd-over-debt', snap.revision, 'bob', 'alice', 4000))
        self.assertEqual(ctx.exception.code, 'over_settlement_prohibited')

    def test_organizer_manual_recording_and_reversals_preserved(self):
        self._setup_finalized_meal()
        # Direct manual contribution by organizer
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        contrib_res = self.auth.apply(self.alice_cred, self.meal_id, RecordContribution('cmd-m-contrib', snap.revision, 'alice', 10000, 'card'))
        contrib_id = contrib_res.contribution_id

        # Direct manual transfer by organizer on behalf of diners
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        xfer_res = self.auth.apply(self.alice_cred, self.meal_id, RecordTransfer('cmd-m-xfer', snap.revision, 'bob', 'alice', 3000, 'cash at table'))
        transfer_id = xfer_res.transfer_id

        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        # Manual records have reported_by = None (indicating organizer manual attestation)
        c = snap.contributions[0]
        self.assertIsNone(c.reported_by)
        t = snap.transfers[0]
        self.assertIsNone(t.reported_by)

        # Organizer can reverse manual transfer
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, ReverseTransfer('cmd-rev-xfer', snap.revision, transfer_id, 'Mistake'))

        # Organizer can reverse manual contribution
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, ReverseContribution('cmd-rev-contrib', snap.revision, contrib_id, 'Mistake'))

        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.assertEqual(snap.funding.status, 'not_funded')


from tests.test_transport import TransportTestClient


class TestCollaborativePaymentTransport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False)
        self.tmp.close()
        self.auth = Authority(self.tmp.name)
        self.app = SettleTableApp(self.tmp.name, allowed_hosts=['127.0.0.1:8000', 'localhost'])
        self.client = TransportTestClient(self.app)
        self.meal_id = 'test-meal-collab-transport'

        p1 = Participant('alice', 'Alice', True)
        p2 = Participant('bob', 'Bob', False)
        res = self.auth.bootstrap(self.meal_id, (p1, p2))
        self.alice_cred = res.sessions[0].credential
        self.bob_cred = res.sessions[1].credential

        # Finalize meal: total 5000 sen (RM 50.00). Alice consumed 2000, Bob consumed 3000.
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        rcpt = Receipt(
            items=(
                ReceiptItem('item-1', 'Dish 1', Fraction(1), 2000),
                ReceiptItem('item-2', 'Dish 2', Fraction(1), 3000),
            ),
            subtotal_sen=5000,
            total_sen=5000,
        )
        self.auth.apply(self.alice_cred, self.meal_id, ReplaceReceipt('cmd-r', snap.revision, snap.financial_revision, rcpt))
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        item_rev = {i.item_id: i.item_revision for i in snap.items}
        self.auth.apply(self.alice_cred, self.meal_id, SetOwnQuantity('cmd-c1', 'item-1', Fraction(1), item_rev['item-1'], snap.financial_revision))
        self.auth.apply(self.bob_cred, self.meal_id, SetOwnQuantity('cmd-c2', 'item-2', Fraction(1), item_rev['item-2'], snap.financial_revision))
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, ReviewReceipt('cmd-t-rev', snap.revision, snap.financial_revision, snap.receipt_digest))
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, Finalize('cmd-t-fin', snap.revision, snap.financial_revision))

    def tearDown(self):
        self.auth.close()
        self.app.close()
        try:
            os.remove(self.tmp.name)
        except OSError:
            pass

    def _call(self, method, path, cred, body=None):
        import json
        headers = {'HTTP_HOST': '127.0.0.1:8000'}
        if cred:
            headers['HTTP_COOKIE'] = f'settletable_session={cred}'
        if body is not None:
            headers['CONTENT_TYPE'] = 'application/json'
            raw_body = json.dumps(body)
        else:
            raw_body = None
        res = self.client.request(method, path, body=raw_body, headers=headers)
        return res['status'], res['json']

    def test_transport_collaborative_payment_flow(self):
        # Bob reports contribution via POST /api/meals/{meal_id}/apply
        snap_code, snap = self._call('GET', f'/api/meals/{self.meal_id}/snapshot', self.bob_cred)
        self.assertEqual(snap_code, 200)

        code, res = self._call('POST', f'/api/meals/{self.meal_id}/apply', self.bob_cred, {
            'kind': 'ReportContribution',
            'command_id': 'cmd-t-report',
            'expected_revision': snap['revision'],
            'participant_id': 'bob',
            'amount_sen': 5000,
            'payment_method': 'card',
        })
        self.assertEqual(code, 200)
        self.assertTrue(res['ok'])
        report_id = res['report_id']

        # Non-organizer (Bob) cannot confirm
        snap_code, snap = self._call('GET', f'/api/meals/{self.meal_id}/snapshot', self.bob_cred)
        code, err = self._call('POST', f'/api/meals/{self.meal_id}/apply', self.bob_cred, {
            'kind': 'ConfirmContribution',
            'command_id': 'cmd-t-conf-fail',
            'expected_revision': snap['revision'],
            'report_id': report_id,
        })
        self.assertEqual(code, 403)
        self.assertEqual(err['error'], 'forbidden')

        # Organizer (Alice) confirms
        snap_code, snap = self._call('GET', f'/api/meals/{self.meal_id}/snapshot', self.alice_cred)
        code, res = self._call('POST', f'/api/meals/{self.meal_id}/apply', self.alice_cred, {
            'kind': 'ConfirmContribution',
            'command_id': 'cmd-t-conf-ok',
            'expected_revision': snap['revision'],
            'report_id': report_id,
        })
        self.assertEqual(code, 200)
        self.assertTrue(res['ok'])

        # Check snapshot
        snap_code, snap = self._call('GET', f'/api/meals/{self.meal_id}/snapshot', self.alice_cred)
        self.assertEqual(snap['funding']['status'], 'fully_funded')
        self.assertEqual(len(snap['contributions']), 1)
        self.assertEqual(snap['contributions'][0]['reported_by'], 'bob')
        self.assertEqual(snap['contributions'][0]['confirmed_by'], 'alice')

    def test_transport_peer_reimbursement_flow(self):
        # Alice funds meal directly with RM 50.00
        snap_code, snap = self._call('GET', f'/api/meals/{self.meal_id}/snapshot', self.alice_cred)
        self._call('POST', f'/api/meals/{self.meal_id}/apply', self.alice_cred, {
            'kind': 'RecordContribution',
            'command_id': 'cmd-t-fund',
            'expected_revision': snap['revision'],
            'participant_id': 'alice',
            'amount_sen': 5000,
            'payment_method': 'card',
        })

        # Bob owes 3000 to Alice. Bob reports sending 3000 to Alice via transport
        snap_code, snap = self._call('GET', f'/api/meals/{self.meal_id}/snapshot', self.bob_cred)
        code, res = self._call('POST', f'/api/meals/{self.meal_id}/apply', self.bob_cred, {
            'kind': 'ReportTransfer',
            'command_id': 'cmd-t-xfer-report',
            'expected_revision': snap['revision'],
            'sender_id': 'bob',
            'receiver_id': 'alice',
            'amount_sen': 3000,
            'note': 'DuitNow',
        })
        self.assertEqual(code, 200)
        report_id = res['report_id']

        # Bob cannot confirm his own payment
        snap_code, snap = self._call('GET', f'/api/meals/{self.meal_id}/snapshot', self.bob_cred)
        code, err = self._call('POST', f'/api/meals/{self.meal_id}/apply', self.bob_cred, {
            'kind': 'ConfirmTransfer',
            'command_id': 'cmd-t-xfer-conf-self',
            'expected_revision': snap['revision'],
            'report_id': report_id,
        })
        self.assertEqual(code, 403)

        # Alice confirms receipt
        snap_code, snap = self._call('GET', f'/api/meals/{self.meal_id}/snapshot', self.alice_cred)
        code, res = self._call('POST', f'/api/meals/{self.meal_id}/apply', self.alice_cred, {
            'kind': 'ConfirmTransfer',
            'command_id': 'cmd-t-xfer-conf-ok',
            'expected_revision': snap['revision'],
            'report_id': report_id,
        })
        self.assertEqual(code, 200)

        # Balances settled
        snap_code, snap = self._call('GET', f'/api/meals/{self.meal_id}/snapshot', self.bob_cred)
        self.assertTrue(snap['settlement']['is_settled'])
        xfer = snap['transfers'][0]
        self.assertEqual(xfer['reported_by'], 'bob')
        self.assertEqual(xfer['confirmed_by'], 'alice')

    def test_concurrent_confirmations_prevent_overpayment(self):
        # Bob reports RM 50.00 and Charlie reports RM 50.00 when only RM 50.00 is needed
        # (simulating two diners concurrently reporting)
        # First confirmation brings unfunded to 0. Second confirmation must fail with overpayment_prohibited!
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        res_b = self.auth.apply(self.bob_cred, self.meal_id, ReportContribution('cmd-c-b', snap.revision, 'bob', 5000, 'cash'))
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        res_a = self.auth.apply(self.alice_cred, self.meal_id, ReportContribution('cmd-c-a', snap.revision, 'alice', 5000, 'card'))

        # Alice confirms Bob's report
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, ConfirmContribution('cmd-conf-1', snap.revision, res_b.report_id))

        # Alice attempts to confirm Alice's report -> Must fail with overpayment_prohibited!
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.alice_cred, self.meal_id, ConfirmContribution('cmd-conf-2', snap.revision, res_a.report_id))
        self.assertEqual(ctx.exception.code, 'overpayment_prohibited')


if __name__ == '__main__':
    unittest.main()
