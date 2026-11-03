"""Tests for multi-payer contributions, funding status, and net balance reconciliation."""
from fractions import Fraction
import sqlite3
import tempfile
import unittest

from settletable import calculation as calc
from settletable.authority import (
    Authority, AuthorityError, Participant, ReplaceReceipt, ReviewReceipt, Finalize,
    SetOwnQuantity, RecordContribution, ReverseContribution, Receipt, ReceiptItem
)
from settletable.funding import (
    PayerContributionRecord,
    compute_funding_status,
    compute_net_balances,
    derive_contribution_id,
)
from settletable.transport import SettleTableApp


class TestFundingUnit(unittest.TestCase):
    def test_compute_funding_status(self):
        self.assertEqual(compute_funding_status(0, 0), 'fully_funded')
        self.assertEqual(compute_funding_status(5000, 0), 'not_funded')
        self.assertEqual(compute_funding_status(5000, 2000), 'partially_funded')
        self.assertEqual(compute_funding_status(5000, 5000), 'fully_funded')
        self.assertEqual(compute_funding_status(5000, 6000), 'fully_funded')

    def test_compute_net_balances_conservation(self):
        # Alice consumed 3000, Bob consumed 2000. Total receipt: 5000.
        consumption = [('alice', 3000), ('bob', 2000)]
        names = {'alice': 'Alice', 'bob': 'Bob'}
        active = {'alice', 'bob'}
        contribs = [
            PayerContributionRecord('c1', 'cmd1', 'alice', 'Alice', 3500, 'card', 1.0, 'alice', 'active'),
            PayerContributionRecord('c2', 'cmd2', 'bob', 'Bob', 1500, 'cash', 2.0, 'alice', 'active'),
        ]
        funding, balances = compute_net_balances(consumption, names, active, contribs, 5000)
        self.assertEqual(funding.status, 'fully_funded')
        self.assertEqual(funding.total_contributed_sen, 5000)
        self.assertEqual(funding.unfunded_sen, 0)
        # Alice: 3500 - 3000 = +500 (creditor)
        # Bob: 1500 - 2000 = -500 (debtor)
        b_dict = {b.participant_id: b.net_sen for b in balances}
        self.assertEqual(b_dict['alice'], 500)
        self.assertEqual(b_dict['bob'], -500)
        self.assertEqual(sum(b.net_sen for b in balances), 0)

    def test_partial_funding_net_sum_equals_negative_unfunded(self):
        consumption = [('alice', 4000), ('bob', 2000)]
        names = {'alice': 'Alice', 'bob': 'Bob'}
        active = {'alice', 'bob'}
        contribs = [
            PayerContributionRecord('c1', 'cmd1', 'alice', 'Alice', 3000, 'card', 1.0, 'alice', 'active'),
        ]
        funding, balances = compute_net_balances(consumption, names, active, contribs, 6000)
        self.assertEqual(funding.status, 'partially_funded')
        self.assertEqual(funding.total_contributed_sen, 3000)
        self.assertEqual(funding.unfunded_sen, 3000)
        self.assertEqual(sum(b.net_sen for b in balances), -3000)

    def test_inactive_participant_conservation(self):
        # Charlie is revoked after finalization. Cent conservation must still hold.
        consumption = [('alice', 2000), ('charlie', 3000)]
        names = {'alice': 'Alice', 'charlie': 'Charlie'}
        active = {'alice'}  # charlie is inactive
        contribs = [
            PayerContributionRecord('c1', 'cmd1', 'charlie', 'Charlie', 5000, 'card', 1.0, 'alice', 'active')
        ]
        funding, balances = compute_net_balances(consumption, names, active, contribs, 5000)
        self.assertEqual(funding.status, 'fully_funded')
        b_charlie = next(b for b in balances if b.participant_id == 'charlie')
        self.assertFalse(b_charlie.is_active)
        self.assertEqual(b_charlie.net_sen, 2000)  # paid 5000, consumed 3000
        self.assertEqual(sum(b.net_sen for b in balances), 0)


class TestAuthorityFunding(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False)
        self.tmp.close()
        self.auth = Authority(self.tmp.name)
        self.meal_id = 'test-meal-funding'
        # Bootstrap meal with Alice (organizer), Bob, Charlie
        p1 = Participant('alice', 'Alice', True)
        p2 = Participant('bob', 'Bob', False)
        p3 = Participant('charlie', 'Charlie', False)
        res = self.auth.bootstrap(self.meal_id, (p1, p2, p3))
        self.alice_cred = res.sessions[0].credential
        self.bob_cred = res.sessions[1].credential

    def tearDown(self):
        self.auth.close()

    def _setup_finalized_meal(self, total_sen=6000):
        # Setup receipt: Item 1 = RM 40.00, Item 2 = RM 20.00
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        rcpt = Receipt(
            items=(
                ReceiptItem('i1', 'Pasta', Fraction(1), 4000),
                ReceiptItem('i2', 'Drinks', Fraction(1), 2000),
            ),
            subtotal_sen=6000,
            total_sen=total_sen,
        )
        self.auth.apply(self.alice_cred, self.meal_id, ReplaceReceipt('cmd-r1', snap.revision, snap.financial_revision, rcpt))
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        item_rev = {i.item_id: i.item_revision for i in snap.items}
        # Alice claims pasta (4000), Bob claims drinks (2000), Charlie claims nothing
        self.auth.apply(self.alice_cred, self.meal_id, SetOwnQuantity('cmd-c1', 'i1', Fraction(1), item_rev['i1'], snap.financial_revision))
        self.auth.apply(self.bob_cred, self.meal_id, SetOwnQuantity('cmd-c2', 'i2', Fraction(1), item_rev['i2'], snap.financial_revision))
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, ReviewReceipt('cmd-rv1', snap.revision, snap.financial_revision, snap.receipt_digest))
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, Finalize('cmd-f1', snap.revision, snap.financial_revision))

    def test_record_contribution_on_unfinalized_meal_fails(self):
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        cmd = RecordContribution('c-early', snap.revision, 'alice', 1000, 'cash')
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.alice_cred, self.meal_id, cmd)
        self.assertEqual(ctx.exception.code, 'not_finalized')

    def test_record_contribution_by_diner_fails(self):
        self._setup_finalized_meal()
        snap = self.auth.snapshot(self.bob_cred, self.meal_id)
        cmd = RecordContribution('c-bob', snap.revision, 'bob', 1000, 'cash')
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.bob_cred, self.meal_id, cmd)
        self.assertEqual(ctx.exception.code, 'forbidden')

    def test_record_contribution_overpayment_prohibited(self):
        self._setup_finalized_meal(total_sen=6000)
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        # Attempt to pay 6001 sen on 6000 sen meal
        cmd = RecordContribution('c-over', snap.revision, 'alice', 6001, 'card')
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.alice_cred, self.meal_id, cmd)
        self.assertEqual(ctx.exception.code, 'overpayment_prohibited')

    def test_multi_payer_contributions_and_net_balances(self):
        self._setup_finalized_meal(total_sen=6000)
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.assertEqual(snap.funding.status, 'not_funded')
        self.assertEqual(snap.funding.unfunded_sen, 6000)

        # Alice pays RM 35.00 via card
        cmd1 = RecordContribution('cmd-pay-1', snap.revision, 'alice', 3500, 'card')
        res1 = self.auth.apply(self.alice_cred, self.meal_id, cmd1)
        self.assertTrue(res1.contribution_id.startswith('contrib-'))

        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.assertEqual(snap.funding.status, 'partially_funded')
        self.assertEqual(snap.funding.total_contributed_sen, 3500)
        self.assertEqual(snap.funding.unfunded_sen, 2500)
        self.assertEqual(len(snap.contributions), 1)

        # Charlie (consumed nothing) contributes RM 10.00 via ewallet
        cmd2 = RecordContribution('cmd-pay-2', snap.revision, 'charlie', 1000, 'ewallet')
        self.auth.apply(self.alice_cred, self.meal_id, cmd2)

        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.assertEqual(snap.funding.total_contributed_sen, 4500)
        self.assertEqual(snap.funding.unfunded_sen, 1500)

        # Bob pays remaining RM 15.00 via cash
        cmd3 = RecordContribution('cmd-pay-3', snap.revision, 'bob', 1500, 'cash')
        self.auth.apply(self.alice_cred, self.meal_id, cmd3)

        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.assertEqual(snap.funding.status, 'fully_funded')
        self.assertEqual(snap.funding.total_contributed_sen, 6000)
        self.assertEqual(snap.funding.unfunded_sen, 0)
        self.assertEqual(len(snap.contributions), 3)

        # Net balances:
        # Alice: consumed 4000, paid 3500 -> net -500 (debtor)
        # Bob: consumed 2000, paid 1500 -> net -500 (debtor)
        # Charlie: consumed 0, paid 1000 -> net +1000 (creditor)
        b_map = {b.participant_id: b.net_sen for b in snap.funding.net_balances}
        self.assertEqual(b_map['alice'], -500)
        self.assertEqual(b_map['bob'], -500)
        self.assertEqual(b_map['charlie'], 1000)
        self.assertEqual(sum(b_map.values()), 0)

    def test_reversal_mechanism_and_recalculation(self):
        self._setup_finalized_meal(total_sen=6000)
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        cmd1 = RecordContribution('cmd-pay-alice', snap.revision, 'alice', 4000, 'card')
        res1 = self.auth.apply(self.alice_cred, self.meal_id, cmd1)
        contrib_id = res1.contribution_id

        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.assertEqual(snap.funding.total_contributed_sen, 4000)

        # Reverse contribution
        rev_cmd = ReverseContribution('cmd-rev-1', snap.revision, contrib_id, 'Mistaken card charge')
        self.auth.apply(self.alice_cred, self.meal_id, rev_cmd)

        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.assertEqual(snap.funding.total_contributed_sen, 0)
        self.assertEqual(snap.funding.status, 'not_funded')
        self.assertEqual(len(snap.contributions), 1)
        self.assertEqual(snap.contributions[0].status, 'reversed')
        self.assertEqual(snap.contributions[0].reversal_reason, 'Mistaken card charge')

        # Reversing an already-reversed contribution must fail
        rev_repeat = ReverseContribution('cmd-rev-2', snap.revision, contrib_id, 'Again')
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.alice_cred, self.meal_id, rev_repeat)
        self.assertEqual(ctx.exception.code, 'invalid_contribution_status')

    def test_database_triggers_prevent_delete_and_tampering(self):
        self._setup_finalized_meal(total_sen=6000)
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        cmd1 = RecordContribution('cmd-trig-1', snap.revision, 'alice', 2000, 'card')
        res1 = self.auth.apply(self.alice_cred, self.meal_id, cmd1)
        contrib_id = res1.contribution_id

        # Direct SQL deletion must be blocked by trigger
        with self.assertRaises(sqlite3.DatabaseError):
            self.auth._db.execute('DELETE FROM payer_contributions WHERE contribution_id=?', (contrib_id,))

        # Direct SQL tampering of immutable fields (amount_sen) must be blocked by trigger
        with self.assertRaises(sqlite3.DatabaseError):
            self.auth._db.execute('UPDATE payer_contributions SET amount_sen=9999 WHERE contribution_id=?', (contrib_id,))

    def test_command_replay_idempotency(self):
        self._setup_finalized_meal(total_sen=6000)
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        cmd1 = RecordContribution('cmd-replay', snap.revision, 'alice', 2000, 'cash')
        res1 = self.auth.apply(self.alice_cred, self.meal_id, cmd1)

        # Replaying identical command returns identical result
        res2 = self.auth.apply(self.alice_cred, self.meal_id, cmd1)
        self.assertEqual(res1.contribution_id, res2.contribution_id)
        self.assertEqual(res1.revision, res2.revision)

        # Submitting same command_id with different payload raises command_conflict
        cmd_conflict = RecordContribution('cmd-replay', snap.revision, 'alice', 3000, 'cash')
        with self.assertRaises(AuthorityError) as ctx:
            self.auth.apply(self.alice_cred, self.meal_id, cmd_conflict)
        self.assertEqual(ctx.exception.code, 'command_conflict')

    def test_historical_database_reopening(self):
        # Create a database with old schema (without payer_contributions table)
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

        # Reopen with new Authority
        auth = Authority(db_path)
        # Should initialize payer_contributions cleanly without error
        row = auth._db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payer_contributions'").fetchone()
        self.assertIsNotNone(row)
        auth.close()


class TestTransportFunding(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False)
        self.tmp.close()
        self.app = SettleTableApp(self.tmp.name, allowed_hosts=('localhost:8000', '127.0.0.1:8000', 'testserver'))
        self.auth = self.app.get_authority()
        self.meal_id = 'test-meal-transport-funding'
        p1 = Participant('alice', 'Alice', True)
        p2 = Participant('bob', 'Bob', False)
        res = self.auth.bootstrap(self.meal_id, (p1, p2))
        self.alice_cred = res.sessions[0].credential

        # Finalize meal
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        rcpt = Receipt(items=(ReceiptItem('i1', 'Steak', Fraction(1), 5000),), subtotal_sen=5000, total_sen=5000)
        self.auth.apply(self.alice_cred, self.meal_id, ReplaceReceipt('cmd-r1', snap.revision, snap.financial_revision, rcpt))
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        item_rev = {i.item_id: i.item_revision for i in snap.items}
        self.auth.apply(self.alice_cred, self.meal_id, SetOwnQuantity('cmd-c1', 'i1', Fraction(1), item_rev['i1'], snap.financial_revision))
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, ReviewReceipt('cmd-rv1', snap.revision, snap.financial_revision, snap.receipt_digest))
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        self.auth.apply(self.alice_cred, self.meal_id, Finalize('cmd-f1', snap.revision, snap.financial_revision))

    def tearDown(self):
        self.app.close()

    def _call(self, method, path, data=None, cred=None):
        import json
        from io import BytesIO
        body_bytes = json.dumps(data).encode('utf-8') if data else b''
        env = {
            'REQUEST_METHOD': method,
            'PATH_INFO': path,
            'HTTP_HOST': '127.0.0.1:8000',
            'HTTP_X_SETTLETABLE_ACTION': '1',
            'HTTP_ORIGIN': 'http://127.0.0.1:8000',
            'CONTENT_LENGTH': str(len(body_bytes)),
            'wsgi.input': BytesIO(body_bytes),
        }
        if cred:
            env['HTTP_AUTHORIZATION'] = f'Bearer {cred}'
        status_box = []
        headers_box = []
        def start_response(status, headers):
            status_box.append(status)
            headers_box.append(headers)
        res = self.app(env, start_response)
        body = b''.join(res)
        return int(status_box[0].split()[0]), json.loads(body.decode('utf-8'))

    def test_transport_record_and_snapshot_funding(self):
        status, snap = self._call('GET', f'/api/meals/{self.meal_id}/snapshot', cred=self.alice_cred)
        self.assertEqual(status, 200)
        self.assertEqual(snap['funding']['status'], 'not_funded')
        self.assertEqual(snap['funding']['unfunded_sen'], 5000)

        # Record contribution via transport
        payload = {
            'kind': 'RecordContribution',
            'command_id': 'http-cmd-1',
            'expected_revision': snap['revision'],
            'participant_id': 'alice',
            'amount_sen': 5000,
            'payment_method': 'card',
        }
        status, res = self._call('POST', f'/api/meals/{self.meal_id}/apply', data=payload, cred=self.alice_cred)
        self.assertEqual(status, 200)
        self.assertTrue(res['ok'])
        self.assertTrue(res['contribution_id'].startswith('contrib-'))

        # Snapshot reflects fully funded
        status, snap = self._call('GET', f'/api/meals/{self.meal_id}/snapshot', cred=self.alice_cred)
        self.assertEqual(status, 200)
        self.assertEqual(snap['funding']['status'], 'fully_funded')
        self.assertEqual(snap['funding']['total_contributed_sen'], 5000)
        self.assertEqual(snap['funding']['unfunded_sen'], 0)
        self.assertEqual(len(snap['contributions']), 1)
        self.assertEqual(snap['contributions'][0]['payment_method'], 'card')

    def test_notion_export_idempotency_preserved_across_contributions(self):
        # Record Notion export on finalized meal
        snap = self.auth.snapshot(self.alice_cred, self.meal_id)
        fin_rev = snap.finalized_revision
        self.auth.record_notion_export_completed(self.meal_id, fin_rev, 'page-123', 'https://notion.so/p123', 'digest-1:photo=0')

        # Check export status via GET endpoint
        status, res = self._call('GET', f'/api/meals/{self.meal_id}/export/notion', cred=self.alice_cred)
        self.assertEqual(status, 200)
        self.assertEqual(res['export']['status'], 'completed')
        self.assertEqual(res['export']['page_id'], 'page-123')

        # Now record a contribution (which advances snapshot revision)
        payload = {
            'kind': 'RecordContribution',
            'command_id': 'http-cmd-notion',
            'expected_revision': snap.revision,
            'participant_id': 'alice',
            'amount_sen': 2000,
            'payment_method': 'cash',
        }
        status, _ = self._call('POST', f'/api/meals/{self.meal_id}/apply', data=payload, cred=self.alice_cred)
        self.assertEqual(status, 200)

        # GET export must STILL return completed page-123 because it is keyed to finalized_revision!
        status, res = self._call('GET', f'/api/meals/{self.meal_id}/export/notion', cred=self.alice_cred)
        self.assertEqual(status, 200)
        self.assertEqual(res['export']['status'], 'completed')
        self.assertEqual(res['export']['page_id'], 'page-123')


if __name__ == '__main__':
    unittest.main()
