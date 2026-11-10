"""Tests for peer transfer suggestions, partial reimbursements, and settlement tracking."""
from fractions import Fraction
import json
import sqlite3
import tempfile
import unittest

from settletable import calculation as calc
from settletable.authority import (
    Authority, AuthorityError, Participant, ReplaceReceipt, ReviewReceipt, Finalize,
    SetOwnQuantity, AssignParticipantQuantity, RecordContribution, ReverseContribution,
    RecordTransfer, ReverseTransfer, Receipt, ReceiptItem
)
from settletable.funding import (
    PayerContributionRecord,
    ParticipantNetBalance,
    compute_net_balances,
)
from settletable.settlement import (
    PeerTransferRecord,
    SuggestedTransfer,
    ParticipantOutstandingBalance,
    SettlementSnapshot,
    compute_settlement,
    derive_transfer_id,
)
from settletable.transport import SettleTableApp


class TestSettlementUnit(unittest.TestCase):
    def test_suggested_transfers_spec_example(self):
        # Spec example:
        # Restaurant bill: RM 60.48 (6048 sen)
        # Alice contributes RM 40.00 (4000 sen), consumed RM 30.00 (3000 sen) -> BaseNet: +1000 sen
        # Bob contributes RM 20.48 (2048 sen), consumed RM 30.48 (3048 sen) -> BaseNet: -1000 sen
        # Bill is fully funded (unfunded = 0).
        balances = (
            ParticipantNetBalance('alice', 'Alice', True, 4000, 3000, 1000),
            ParticipantNetBalance('bob', 'Bob', True, 2048, 3048, -1000),
        )
        snap = compute_settlement(base_net_balances=balances, transfers=(), unfunded_sen=0)
        self.assertFalse(snap.is_settled)
        self.assertEqual(len(snap.suggested_transfers), 1)
        st = snap.suggested_transfers[0]
        self.assertEqual(st.sender_id, 'bob')
        self.assertEqual(st.receiver_id, 'alice')
        self.assertEqual(st.amount_sen, 1000)

    def test_multi_party_greedy_matching(self):
        # Alice: +4000 (creditor)
        # Bob: -2500 (debtor)
        # Charlie: -1500 (debtor)
        # Fully funded
        balances = (
            ParticipantNetBalance('alice', 'Alice', True, 7000, 3000, 4000),
            ParticipantNetBalance('bob', 'Bob', True, 0, 2500, -2500),
            ParticipantNetBalance('charlie', 'Charlie', True, 0, 1500, -1500),
        )
        snap = compute_settlement(base_net_balances=balances, transfers=(), unfunded_sen=0)
        self.assertEqual(len(snap.suggested_transfers), 2)
        # Bob pays Alice 2500, Charlie pays Alice 1500
        self.assertEqual(snap.suggested_transfers[0], SuggestedTransfer('bob', 'alice', 2500))
        self.assertEqual(snap.suggested_transfers[1], SuggestedTransfer('charlie', 'alice', 1500))

    def test_unfunded_blocker_suggestions(self):
        # Total bill 6000 sen.
        # Alice contributed 4000, consumed 2000 -> BaseNet: +2000
        # Bob contributed 0, consumed 4000 -> BaseNet: -4000
        # Unfunded: 2000 sen.
        balances = (
            ParticipantNetBalance('alice', 'Alice', True, 4000, 2000, 2000),
            ParticipantNetBalance('bob', 'Bob', True, 0, 4000, -4000),
        )
        snap = compute_settlement(base_net_balances=balances, transfers=(), unfunded_sen=2000)
        # Total outstanding = -2000 == -unfunded
        # Bob owes 4000, but Alice can only receive 2000 because 2000 is missing restaurant funding
        self.assertEqual(len(snap.suggested_transfers), 1)
        self.assertEqual(snap.suggested_transfers[0], SuggestedTransfer('bob', 'alice', 2000))
        self.assertEqual(snap.unfunded_blocker_sen, 2000)
        self.assertFalse(snap.is_settled)

    def test_partial_reimbursements_and_settlement(self):
        # Alice: +1000, Bob: -1000. Fully funded.
        balances = (
            ParticipantNetBalance('alice', 'Alice', True, 4000, 3000, 1000),
            ParticipantNetBalance('bob', 'Bob', True, 2000, 3000, -1000),
        )
        # Partial transfer of 400 sen from Bob to Alice
        t1 = PeerTransferRecord('xfer-1', 'cmd-1', 'bob', 'alice', 400, 'part 1', 100.0, 'alice', 'confirmed')
        snap1 = compute_settlement(base_net_balances=balances, transfers=(t1,), unfunded_sen=0)
        self.assertFalse(snap1.is_settled)
        # Outstanding balances:
        b_map1 = {b.participant_id: b.outstanding_net_balance_sen for b in snap1.outstanding_net_balances}
        self.assertEqual(b_map1['alice'], 600)
        self.assertEqual(b_map1['bob'], -600)
        self.assertEqual(len(snap1.suggested_transfers), 1)
        self.assertEqual(snap1.suggested_transfers[0], SuggestedTransfer('bob', 'alice', 600))

        # Second transfer of 600 sen settles the debt
        t2 = PeerTransferRecord('xfer-2', 'cmd-2', 'bob', 'alice', 600, 'part 2', 105.0, 'alice', 'confirmed')
        snap2 = compute_settlement(base_net_balances=balances, transfers=(t1, t2), unfunded_sen=0)
        self.assertTrue(snap2.is_settled)
        b_map2 = {b.participant_id: b.outstanding_net_balance_sen for b in snap2.outstanding_net_balances}
        self.assertEqual(b_map2['alice'], 0)
        self.assertEqual(b_map2['bob'], 0)
        self.assertEqual(len(snap2.suggested_transfers), 0)


class TestAuthoritySettlement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False)
        self.tmp.close()
        self.auth = Authority(self.tmp.name)
        self.meal_id = 'test-meal-settlement'
        self.p_alice = Participant('alice', 'Alice', True)
        self.p_bob = Participant('bob', 'Bob', False)
        self.p_charlie = Participant('charlie', 'Charlie', False)
        res = self.auth.bootstrap(self.meal_id, (self.p_alice, self.p_bob, self.p_charlie))
        self.alice_cred = res.sessions[0].credential
        # Issue invitations for Bob and Charlie
        g_bob = self.auth.issue_invitation(self.alice_cred, self.meal_id, 'bob')
        self.bob_cred = self.auth.redeem_invitation(g_bob.token, self.meal_id).credential

    def tearDown(self):
        self.auth.close()

    def _setup_finalized_and_funded_meal(self):
        # Receipt: RM 60.00
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        rcpt = Receipt(items=(ReceiptItem('i1', 'Pasta', Fraction(1), 6000),), subtotal_sen=6000, total_sen=6000)
        self.auth.apply(self.alice_cred, self.meal_id, ReplaceReceipt('c-r1', snap.revision, snap.financial_revision, rcpt))
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        # Allocate: Alice 3000, Bob 3000
        item_rev = {i.item_id: i.item_revision for i in snap.items}
        self.auth.apply(self.alice_cred, self.meal_id, SetOwnQuantity('c-q1', 'i1', Fraction(1, 2), item_rev['i1'], snap.financial_revision))
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        item_rev = {i.item_id: i.item_revision for i in snap.items}
        self.auth.apply(self.alice_cred, self.meal_id, AssignParticipantQuantity('c-q2', 'bob', 'i1', Fraction(1, 2), item_rev['i1'], snap.financial_revision))
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, ReviewReceipt('c-rev', snap.revision, snap.financial_revision, snap.receipt_digest))
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, Finalize('c-fin', snap.revision, snap.financial_revision))

        # Alice pays RM 50.00, Bob pays RM 10.00 -> Total 6000 (Fully funded)
        # Alice consumed 3000, paid 5000 -> Base Net +2000
        # Bob consumed 3000, paid 1000 -> Base Net -2000
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, RecordContribution('c-pay1', snap.revision, 'alice', 5000, 'card'))
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, RecordContribution('c-pay2', snap.revision, 'bob', 1000, 'cash'))

    def test_record_transfer_and_settlement_lifecycle(self):
        self._setup_finalized_and_funded_meal()
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.assertIsNotNone(snap.settlement)
        self.assertFalse(snap.settlement.is_settled)
        self.assertEqual(len(snap.settlement.suggested_transfers), 1)
        self.assertEqual(snap.settlement.suggested_transfers[0], SuggestedTransfer('bob', 'alice', 2000))

        # Bob pays Alice partial RM 8.00 (800 sen)
        cmd_xfer1 = RecordTransfer('cmd-x1', snap.revision, 'bob', 'alice', 800, 'DuitNow transfer')
        res1 = self.auth.apply(self.alice_cred, self.meal_id, cmd_xfer1)
        self.assertIsNotNone(res1.transfer_id)
        self.assertTrue(res1.transfer_id.startswith('xfer-'))

        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.assertEqual(len(snap.transfers), 1)
        self.assertEqual(snap.transfers[0].amount_sen, 800)
        self.assertEqual(snap.transfers[0].note, 'DuitNow transfer')
        self.assertFalse(snap.settlement.is_settled)
        self.assertEqual(len(snap.settlement.suggested_transfers), 1)
        self.assertEqual(snap.settlement.suggested_transfers[0], SuggestedTransfer('bob', 'alice', 1200))

        # Bob pays remaining RM 12.00 (1200 sen)
        cmd_xfer2 = RecordTransfer('cmd-x2', snap.revision, 'bob', 'alice', 1200, 'Final settlement')
        res2 = self.auth.apply(self.alice_cred, self.meal_id, cmd_xfer2)

        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.assertEqual(len(snap.transfers), 2)
        self.assertTrue(snap.settlement.is_settled)
        self.assertEqual(len(snap.settlement.suggested_transfers), 0)

    def test_over_settlement_prohibited(self):
        self._setup_finalized_and_funded_meal()
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        # Bob owes 2000 sen. Attempt to transfer 2001 sen
        cmd_over = RecordTransfer('cmd-over', snap.revision, 'bob', 'alice', 2001)
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.alice_cred, self.meal_id, cmd_over)
        self.assertEqual(ctx.exception.code, 'over_settlement_prohibited')

    def test_non_debtor_and_non_creditor_rejected(self):
        self._setup_finalized_and_funded_meal()
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        # Alice is creditor (+2000), Bob is debtor (-2000), Charlie is even (0)
        # Alice sending money -> not_a_debtor
        cmd1 = RecordTransfer('cmd-bad1', snap.revision, 'alice', 'bob', 1000)
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.alice_cred, self.meal_id, cmd1)
        self.assertEqual(ctx.exception.code, 'not_a_debtor')

        # Charlie sending money -> not_a_debtor
        cmd2 = RecordTransfer('cmd-bad2', snap.revision, 'charlie', 'alice', 100)
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.alice_cred, self.meal_id, cmd2)
        self.assertEqual(ctx.exception.code, 'not_a_debtor')

        # Bob sending to Charlie (not a creditor) -> not_a_creditor
        cmd3 = RecordTransfer('cmd-bad3', snap.revision, 'bob', 'charlie', 500)
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.alice_cred, self.meal_id, cmd3)
        self.assertEqual(ctx.exception.code, 'not_a_creditor')

    def test_self_transfer_prohibited(self):
        self._setup_finalized_and_funded_meal()
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        cmd = RecordTransfer('cmd-self', snap.revision, 'bob', 'bob', 500)
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.alice_cred, self.meal_id, cmd)
        self.assertEqual(ctx.exception.code, 'self_transfer_prohibited')

    def test_diner_authorization_forbidden(self):
        self._setup_finalized_and_funded_meal()
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        # Bob (diner) attempts to record transfer
        cmd = RecordTransfer('cmd-diner', snap.revision, 'bob', 'alice', 1000)
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.bob_cred, self.meal_id, cmd)
        self.assertEqual(ctx.exception.code, 'forbidden')

        # Organizer records a transfer
        cmd_xfer = RecordTransfer('cmd-org-xfer', snap.revision, 'bob', 'alice', 1000)
        res_xfer = self.auth.apply(self.alice_cred, self.meal_id, cmd_xfer)
        snap2 = self.auth.snapshot(self.alice_cred, self.meal_id)

        # Bob (diner) attempts to reverse transfer
        cmd_rev = ReverseTransfer('cmd-diner-rev', snap2.revision, res_xfer.transfer_id, 'Diner trying to reverse')
        with self.assertRaises(AuthorityError) as ctx2:
            self.auth.apply(self.bob_cred, self.meal_id, cmd_rev)
        self.assertEqual(ctx2.exception.code, 'forbidden')

    def test_transfer_reversal_lifecycle(self):
        self._setup_finalized_and_funded_meal()
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        cmd_xfer = RecordTransfer('cmd-x1', snap.revision, 'bob', 'alice', 1000)
        res = self.auth.apply(self.alice_cred, self.meal_id, cmd_xfer)
        xfer_id = res.transfer_id

        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.assertEqual(snap.transfers[0].status, 'confirmed')

        # Reverse transfer
        cmd_rev = ReverseTransfer('cmd-rev-xfer', snap.revision, xfer_id, 'Wrong transaction proof')
        self.auth.apply(self.alice_cred, self.meal_id, cmd_rev)

        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.assertEqual(snap.transfers[0].status, 'reversed')
        self.assertEqual(snap.transfers[0].reversal_reason, 'Wrong transaction proof')
        # Balances restored: Bob still owes 2000
        self.assertEqual(snap.settlement.suggested_transfers[0].amount_sen, 2000)

        # Attempt to reverse already reversed transfer -> invalid_transfer_status
        cmd_rev2 = ReverseTransfer('cmd-rev-xfer2', snap.revision, xfer_id)
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.alice_cred, self.meal_id, cmd_rev2)
        self.assertEqual(ctx.exception.code, 'invalid_transfer_status')

    def test_reverse_contribution_guard_active_peer_transfers(self):
        self._setup_finalized_and_funded_meal()
        # Alice contributed 5000, Bob contributed 1000.
        # Bob pays Alice 1500 sen reimbursement.
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        cmd_xfer = RecordTransfer('cmd-x1', snap.revision, 'bob', 'alice', 1500)
        res_xfer = self.auth.apply(self.alice_cred, self.meal_id, cmd_xfer)

        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        # Find Alice's contribution (5000 sen)
        alice_contrib = next(c for c in snap.contributions if c.participant_id == 'alice')

        # Attempt to reverse Alice's RM 50.00 contribution:
        # Reversing would reduce active contributions to 0, which is < 1500 confirmed received!
        cmd_rev_c = ReverseContribution('cmd-rev-c', snap.revision, alice_contrib.contribution_id)
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.alice_cred, self.meal_id, cmd_rev_c)
        self.assertEqual(ctx.exception.code, 'active_peer_transfers_exist')

        # Reverse the peer transfer first
        cmd_rev_x = ReverseTransfer('cmd-rev-x', snap.revision, res_xfer.transfer_id)
        self.auth.apply(self.alice_cred, self.meal_id, cmd_rev_x)

        # Now reversing Alice's contribution succeeds cleanly
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        cmd_rev_c2 = ReverseContribution('cmd-rev-c2', snap.revision, alice_contrib.contribution_id)
        self.auth.apply(self.alice_cred, self.meal_id, cmd_rev_c2)
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.assertEqual(snap.funding.total_contributed_sen, 1000)

    def test_peer_transfers_sqlite_triggers(self):
        self._setup_finalized_and_funded_meal()
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        cmd_xfer = RecordTransfer('cmd-trig', snap.revision, 'bob', 'alice', 1000)
        res = self.auth.apply(self.alice_cred, self.meal_id, cmd_xfer)
        xfer_id = res.transfer_id

        # Direct deletion prohibited
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.auth._db.execute('DELETE FROM peer_transfers WHERE meal_id=? AND transfer_id=?',
                                  (self.meal_id, xfer_id))
        self.assertIn('peer_transfers rows cannot be deleted', str(ctx.exception))

        # Tampering with immutable column (amount_sen) on update prohibited
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.auth._db.execute("""
                UPDATE peer_transfers
                SET status='reversed', amount_sen=999
                WHERE meal_id=? AND transfer_id=?
            """, (self.meal_id, xfer_id))
        self.assertIn('immutable transfer columns cannot be modified', str(ctx.exception))

    def test_record_transfer_replay_and_conflict(self):
        self._setup_finalized_and_funded_meal()
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        cmd = RecordTransfer('cmd-rep', snap.revision, 'bob', 'alice', 1000, 'Replay test')
        res1 = self.auth.apply(self.alice_cred, self.meal_id, cmd)

        # Replaying identical command returns identical cached result without duplicate transfer
        res2 = self.auth.apply(self.alice_cred, self.meal_id, cmd)
        self.assertEqual(res1.transfer_id, res2.transfer_id)
        self.assertEqual(res1.revision, res2.revision)

        # Submitting same command_id with different payload raises command_conflict
        cmd_bad = RecordTransfer('cmd-rep', snap.revision, 'bob', 'alice', 500, 'Different amount')
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.alice_cred, self.meal_id, cmd_bad)
        self.assertEqual(ctx.exception.code, 'command_conflict')

    def test_record_transfer_revision_conflict(self):
        self._setup_finalized_and_funded_meal()
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        # Advance revision
        self.auth.apply(self.alice_cred, self.meal_id, RecordTransfer('cmd-adv', snap.revision, 'bob', 'alice', 500))

        # Stale command with old revision
        stale_cmd = RecordTransfer('cmd-stale', snap.revision, 'bob', 'alice', 500)
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.alice_cred, self.meal_id, stale_cmd)
        self.assertEqual(ctx.exception.code, 'revision_conflict')

    def test_historical_database_reopening_settlement(self):
        db_path = tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False).name
        con = sqlite3.connect(db_path)
        con.execute('CREATE TABLE meals (id TEXT PRIMARY KEY, state BLOB NOT NULL)')
        con.execute('''CREATE TABLE participants (
            meal_id TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL,
            organizer INTEGER NOT NULL, active INTEGER NOT NULL, PRIMARY KEY(meal_id, id))''')
        con.execute('''CREATE TABLE sessions (
            verifier BLOB PRIMARY KEY, meal_id TEXT NOT NULL, participant_id TEXT NOT NULL,
            expires REAL NOT NULL, revoked INTEGER NOT NULL)''')
        con.execute('''CREATE TABLE commands (
            meal_id TEXT NOT NULL, participant_id TEXT NOT NULL, command_id TEXT NOT NULL,
            body BLOB NOT NULL, digest BLOB NOT NULL, result BLOB NOT NULL, security INTEGER NOT NULL,
            PRIMARY KEY(meal_id, participant_id, command_id))''')
        con.close()

        # Reopen with Authority
        auth = Authority(db_path)
        row = auth._db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='peer_transfers'").fetchone()
        self.assertIsNotNone(row)
        auth.close()


class TestTransportSettlement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False)
        self.tmp.close()
        self.app = SettleTableApp(self.tmp.name, allowed_hosts=('localhost:8000', '127.0.0.1:8000', 'testserver'))
        self.auth = self.app.get_authority()
        self.meal_id = 'test-meal-transport-settle'
        p1 = Participant('alice', 'Alice', True)
        p2 = Participant('bob', 'Bob', False)
        res = self.auth.bootstrap(self.meal_id, (p1, p2))
        self.alice_cred = res.sessions[0].credential
        self.bob_cred = res.sessions[1].credential

        # Finalize meal & fund
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        rcpt = Receipt(items=(ReceiptItem('i1', 'Food', Fraction(1), 5000),), subtotal_sen=5000, total_sen=5000)
        self.auth.apply(self.alice_cred, self.meal_id, ReplaceReceipt('c-r1', snap.revision, snap.financial_revision, rcpt))
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        item_rev = {i.item_id: i.item_revision for i in snap.items}
        self.auth.apply(self.alice_cred, self.meal_id, AssignParticipantQuantity('c-q1', 'bob', 'i1', Fraction(1), item_rev['i1'], snap.financial_revision))
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, ReviewReceipt('c-rv1', snap.revision, snap.financial_revision, snap.receipt_digest))
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, Finalize('c-fin', snap.revision, snap.financial_revision))
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, RecordContribution('c-pay', snap.revision, 'alice', 5000, 'cash'))

    def test_transport_record_and_reverse_transfer(self):
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        # Alice paid 5000, Bob consumed 5000 -> Bob owes Alice 5000

        # Post RecordTransfer
        body = {
            'command_id': 'cmd-trans-x1',
            'kind': 'RecordTransfer',
            'expected_revision': snap.revision,
            'sender_id': 'bob',
            'receiver_id': 'alice',
            'amount_sen': 2000,
            'note': 'Cash paid at counter',
        }
        res = self._post(f'/api/meals/{self.meal_id}/apply', body)
        self.assertEqual(res['code'], 200)
        self.assertTrue(res['data']['ok'])
        xfer_id = res['data']['transfer_id']
        self.assertTrue(xfer_id.startswith('xfer-'))

        # Check snapshot
        snap_res = self._get(f'/api/meals/{self.meal_id}/snapshot')
        self.assertEqual(snap_res['code'], 200)
        settle = snap_res['data']['settlement']
        self.assertFalse(settle['is_settled'])
        self.assertEqual(len(settle['suggested_transfers']), 1)
        self.assertEqual(settle['suggested_transfers'][0]['amount_sen'], 3000)

        # Reverse transfer
        rev_body = {
            'command_id': 'cmd-trans-rev',
            'kind': 'ReverseTransfer',
            'expected_revision': snap_res['data']['revision'],
            'transfer_id': xfer_id,
            'reason': 'Returned cash',
        }
        rev_res = self._post(f'/api/meals/{self.meal_id}/apply', rev_body)
        self.assertEqual(rev_res['code'], 200)

        snap_res2 = self._get(f'/api/meals/{self.meal_id}/snapshot')
        settle2 = snap_res2['data']['settlement']
        self.assertEqual(settle2['suggested_transfers'][0]['amount_sen'], 5000)

    def test_transport_diner_record_and_reverse_transfer_forbidden(self):
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)

        # 1. Diner attempts RecordTransfer via transport -> 403
        body_rec = {
            'command_id': 'cmd-diner-wire-xfer',
            'kind': 'RecordTransfer',
            'expected_revision': snap.revision,
            'sender_id': 'bob',
            'receiver_id': 'alice',
            'amount_sen': 2000,
        }
        res_rec = self._post(f'/api/meals/{self.meal_id}/apply', body_rec, cred=self.bob_cred)
        self.assertEqual(res_rec['code'], 403)
        self.assertEqual(res_rec['data'].get('error'), 'forbidden')

        # Organizer records transfer
        res_org = self._post(f'/api/meals/{self.meal_id}/apply', body_rec, cred=self.alice_cred)
        self.assertEqual(res_org['code'], 200)
        xfer_id = res_org['data']['transfer_id']

        snap2 = self.auth.snapshot(self.alice_cred, self.meal_id)

        # 2. Diner attempts ReverseTransfer via transport -> 403
        body_rev = {
            'command_id': 'cmd-diner-wire-rev',
            'kind': 'ReverseTransfer',
            'expected_revision': snap2.revision,
            'transfer_id': xfer_id,
            'reason': 'Diner reverse attempt',
        }
        res_rev = self._post(f'/api/meals/{self.meal_id}/apply', body_rev, cred=self.bob_cred)
        self.assertEqual(res_rev['code'], 403)
        self.assertEqual(res_rev['data'].get('error'), 'forbidden')

    def _post(self, path, body, cred=None):
        import io
        raw = json.dumps(body).encode('utf-8')
        environ = {
            'REQUEST_METHOD': 'POST',
            'PATH_INFO': path,
            'HTTP_HOST': '127.0.0.1:8000',
            'HTTP_ORIGIN': 'http://127.0.0.1:8000',
            'HTTP_X_SETTLETABLE_ACTION': '1',
            'HTTP_AUTHORIZATION': f'Bearer {cred or self.alice_cred}',
            'CONTENT_LENGTH': str(len(raw)),
            'CONTENT_TYPE': 'application/json',
            'wsgi.input': io.BytesIO(raw),
        }
        status_box = []
        headers_box = []
        body_parts = []
        def start_response(s, h):
            status_box.append(s)
            headers_box.append(h)
        for chunk in self.app(environ, start_response):
            body_parts.append(chunk)
        code = int(status_box[0].split()[0])
        data = json.loads(b''.join(body_parts).decode('utf-8'))
        return {'code': code, 'headers': dict(headers_box[0]), 'data': data}

    def _get(self, path):
        import io
        environ = {
            'REQUEST_METHOD': 'GET',
            'PATH_INFO': path,
            'HTTP_HOST': '127.0.0.1:8000',
            'HTTP_AUTHORIZATION': f'Bearer {self.alice_cred}',
            'wsgi.input': io.BytesIO(b''),
        }
        status_box = []
        headers_box = []
        body_parts = []
        def start_response(s, h):
            status_box.append(s)
            headers_box.append(h)
        for chunk in self.app(environ, start_response):
            body_parts.append(chunk)
        code = int(status_box[0].split()[0])
        data = json.loads(b''.join(body_parts).decode('utf-8'))
        return {'code': code, 'headers': dict(headers_box[0]), 'data': data}


if __name__ == '__main__':
    unittest.main()
