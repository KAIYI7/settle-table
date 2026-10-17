import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from fractions import Fraction

from tabwise.authority import (Authority, AuthorityError, Participant, Receipt, ReceiptItem,
                               ReplaceReceipt, SetOwnQuantity)


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        scratch = Path('.local/tests')
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.path = Path(self.temp.name) / 'authority.sqlite'
        self.authority = Authority(self.path, clock=lambda: 1000)

    def tearDown(self):
        self.authority.close()
        self.temp.cleanup()

    def bootstrap(self):
        result = self.authority.bootstrap('meal', (Participant('A', 'A', True), Participant('B', 'B')))
        return {session.participant_id: session.credential for session in result.sessions}

    def test_bootstrap_snapshot_and_reject_overwrite(self):
        credentials = self.bootstrap()
        snapshot = self.authority.snapshot(credentials['A'], 'meal')
        self.assertEqual((snapshot.revision, snapshot.financial_revision), (0, 0))
        self.assertIn('missing_receipt', snapshot.issues)
        with self.assertRaises(AuthorityError) as rejected:
            self.bootstrap()
        self.assertEqual(rejected.exception.code, 'meal_exists')
        self.assertEqual(self.authority.snapshot(credentials['B'], 'meal'), snapshot)

    def test_receipt_replacement_is_authorized_durable_and_replayed_exactly(self):
        credentials = self.bootstrap()
        receipt = Receipt((ReceiptItem('dish', 'Rice', 3, 1001),), 1001, 1001)
        command = ReplaceReceipt('entry', 0, 0, receipt)
        with self.assertRaises(AuthorityError) as denied:
            self.authority.apply(credentials['B'], 'meal', command)
        self.assertEqual(denied.exception.code, 'forbidden')
        result = self.authority.apply(credentials['A'], 'meal', command)
        self.assertEqual(result.revision, 1)
        self.assertEqual(self.authority.apply(credentials['A'], 'meal', command).canonical_bytes,
                         result.canonical_bytes)
        self.assertEqual(self.authority.snapshot(credentials['A'], 'meal').receipt, receipt)
        with self.assertRaises(AuthorityError) as conflict:
            self.authority.apply(credentials['A'], 'meal', ReplaceReceipt('entry', 1, 1, receipt))
        self.assertEqual(conflict.exception.code, 'command_conflict')
        self.authority.close()
        self.authority = Authority(self.path, clock=lambda: 1000)
        self.assertEqual(self.authority.apply(credentials['A'], 'meal', command), result)

    def test_own_claim_capacity_stale_items_and_release(self):
        credentials = self.bootstrap()
        receipt = Receipt((ReceiptItem('dish', 'Rice', 3, 1001), ReceiptItem('drink', 'Tea', 1, 100)), 1101, 1101)
        self.authority.apply(credentials['A'], 'meal', ReplaceReceipt('entry', 0, 0, receipt))
        first = self.authority.apply(credentials['A'], 'meal', SetOwnQuantity('a', 'dish', 1, 1, 1))
        self.assertEqual(first.changed_claims[0].participant_id, 'A')
        with self.assertRaises(AuthorityError) as stale:
            self.authority.apply(credentials['B'], 'meal', SetOwnQuantity('stale', 'dish', 2, 1, 1))
        self.assertEqual(stale.exception.code, 'item_revision_conflict')
        with self.assertRaises(AuthorityError) as over:
            self.authority.apply(credentials['B'], 'meal', SetOwnQuantity('over', 'dish', 3, 2, 1))
        self.assertEqual(over.exception.code, 'quantity_capacity')
        self.authority.apply(credentials['B'], 'meal', SetOwnQuantity('b', 'dish', 2, 2, 1))
        self.authority.apply(credentials['B'], 'meal', SetOwnQuantity('tea', 'drink', 1, 1, 1))
        snapshot = self.authority.snapshot(credentials['A'], 'meal')
        self.assertEqual(tuple((c.item_id, c.participant_id, c.quantity) for c in snapshot.claims),
                         (('dish', 'A', 1), ('dish', 'B', 2), ('drink', 'B', 1)))
        self.authority.apply(credentials['A'], 'meal', SetOwnQuantity('release', 'dish', None, 3, 1))
        self.assertEqual(len(self.authority.snapshot(credentials['A'], 'meal').claims), 2)

    def test_receipt_edit_keeps_pending_claims_without_reserving_capacity(self):
        credentials = self.bootstrap()
        receipt = Receipt((ReceiptItem('dish', 'Rice', 2, 1000),), 1000, 1000)
        self.authority.apply(credentials['A'], 'meal', ReplaceReceipt('entry', 0, 0, receipt))
        self.authority.apply(credentials['B'], 'meal', SetOwnQuantity('b', 'dish', 2, 1, 1))
        self.authority.apply(credentials['A'], 'meal', ReplaceReceipt('correction', 2, 1,
            replace(receipt, items=(ReceiptItem('dish', 'Rice corrected', 2, 1001),), subtotal_sen=1001, total_sen=1001)))
        snapshot = self.authority.snapshot(credentials['B'], 'meal')
        self.assertEqual(snapshot.claims[0].status, 'pending')
        self.assertIn('pending_claim', snapshot.issues)
        self.authority.apply(credentials['A'], 'meal', SetOwnQuantity('a', 'dish', 2, 3, 2))
        with self.assertRaises(AuthorityError) as capacity:
            self.authority.apply(credentials['B'], 'meal', SetOwnQuantity('reconfirm', 'dish', 2, 4, 2))
        self.assertEqual(capacity.exception.code, 'quantity_capacity')
        with self.assertRaises(AuthorityError) as deletion:
            self.authority.apply(credentials['A'], 'meal', ReplaceReceipt('delete', 4, 2, Receipt()))
        self.assertEqual(deletion.exception.code, 'claimed_item_deletion')
        self.authority.apply(credentials['B'], 'meal', SetOwnQuantity('release', 'dish', None, 4, 2))
        self.assertEqual(tuple((c.participant_id, c.quantity) for c in self.authority.snapshot(credentials['A'], 'meal').claims),
                         (('A', Fraction(2)),))


if __name__ == '__main__':
    unittest.main()
