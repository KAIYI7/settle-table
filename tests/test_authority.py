import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from fractions import Fraction

from tabwise.authority import (Authority, AuthorityError, Participant, Receipt, ReceiptItem,
                               ReplaceReceipt, SetOwnQuantity, ReviewReceipt, Finalize, ReceiptAdjustment,
                               RevokeSession, RevokeMembership)


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

    def test_review_precedes_claims_and_finalization_uses_actual_calculator(self):
        credentials = self.bootstrap()
        receipt = Receipt((ReceiptItem('dish', 'Rice', 3, 1001),), 1001, 1001)
        self.authority.apply(credentials['A'], 'meal', ReplaceReceipt('entry', 0, 0, receipt))
        digest = self.authority.snapshot(credentials['A'], 'meal').receipt_digest
        self.authority.apply(credentials['A'], 'meal', ReviewReceipt('review', 1, 1, digest))
        reviewed = self.authority.snapshot(credentials['A'], 'meal')
        self.assertEqual((reviewed.review.participant_id, reviewed.review.financial_revision), ('A', 1))
        self.authority.apply(credentials['A'], 'meal', SetOwnQuantity('a', 'dish', 1, 1, 1))
        self.authority.apply(credentials['B'], 'meal', SetOwnQuantity('b', 'dish', 2, 2, 1))
        self.assertEqual(self.authority.snapshot(credentials['A'], 'meal').review, reviewed.review)
        with self.assertRaises(AuthorityError) as stale:
            self.authority.apply(credentials['A'], 'meal', Finalize('stale-final', 2, 1))
        self.assertEqual(stale.exception.code, 'revision_conflict')
        final_command = Finalize('final', 4, 1)
        result = self.authority.apply(credentials['A'], 'meal', final_command)
        self.assertEqual(tuple((p.participant_id, p.sen) for p in result.calculation.consumption), (('A', 334), ('B', 667)))
        self.assertTrue(self.authority.snapshot(credentials['A'], 'meal').finalized)
        with self.assertRaises(AuthorityError) as readonly:
            self.authority.apply(credentials['B'], 'meal', SetOwnQuantity('late', 'dish', None, 3, 1))
        self.assertEqual(readonly.exception.code, 'finalized')
        self.authority.close()
        self.authority = Authority(self.path, clock=lambda: 1000)
        self.assertEqual(self.authority.apply(credentials['A'], 'meal', final_command), result)
        self.assertEqual(self.authority.snapshot(credentials['A'], 'meal').calculation, result.calculation)

    def finalize_receipt(self, credentials, receipt, claims):
        self.authority.apply(credentials['A'], 'meal', ReplaceReceipt('entry', 0, 0, receipt))
        for index, (person, item_id, quantity) in enumerate(claims):
            snapshot = self.authority.snapshot(credentials[person], 'meal')
            item_revision = next(i.item_revision for i in snapshot.items if i.item_id == item_id)
            self.authority.apply(credentials[person], 'meal', SetOwnQuantity(f'claim{index}', item_id, quantity, item_revision, 1))
        snapshot = self.authority.snapshot(credentials['A'], 'meal')
        self.authority.apply(credentials['A'], 'meal', ReviewReceipt('review', snapshot.revision, 1, snapshot.receipt_digest))
        return self.authority.apply(credentials['A'], 'meal', Finalize('final', snapshot.revision + 1, 1))

    def test_scoped_charges_use_accepted_rounded_original_bases(self):
        credentials = self.bootstrap()
        adjustments = tuple(ReceiptAdjustment(id_, label, kind, amount, ('dish',), 'Printed receipt component')
            for id_, label, kind, amount in (('discount', 'Discount', 'discount', -101),
                                           ('sst', 'SST', 'tax', 174),
                                           ('service', 'Service', 'service', 290),
                                           ('round', 'Rounding', 'rounding', 1)))
        receipt = Receipt((ReceiptItem('dish', 'Shared meal', 3001, 3001),), 3001, 3365, adjustments)
        result = self.finalize_receipt(credentials, receipt, (('A', 'dish', 1501), ('B', 'dish', 1500)))
        self.assertEqual(tuple(p.sen for p in result.calculation.consumption), (1683, 1682))
        self.assertEqual(tuple((a.source_id, tuple(s.sen for s in a.shares)) for a in result.calculation.adjustments),
                         (('discount', (-51, -50)), ('round', (1, 0)), ('service', (145, 145)), ('sst', (87, 87))))

    def test_included_tax_is_informational_and_full_discount_keeps_zero_totals(self):
        for case, receipt, claims, expected in (
            ('included', Receipt((ReceiptItem('dish', 'Gross meal', 1, 600),), 600, 600, included_tax_sen=34),
             (('A', 'dish', 1),), (600, 0)),
            ('discount', Receipt((ReceiptItem('tiny', 'Tiny', 2, 1),), 1, 0,
                (ReceiptAdjustment('free', 'Discount', 'discount', -1, ('tiny',), 'Printed discount'),)),
             (('A', 'tiny', 1), ('B', 'tiny', 1)), (0, 0)),
        ):
            with self.subTest(case=case):
                self.authority.close()
                self.authority = Authority(Path(self.temp.name) / (case + '.sqlite'), clock=lambda: 1000)
                result = self.finalize_receipt(self.bootstrap(), receipt, claims)
                self.assertEqual(tuple(p.sen for p in result.calculation.consumption), expected)

    def test_overlapping_discounts_rejected_by_real_calculator_without_acceptance(self):
        credentials = self.bootstrap()
        receipt = Receipt((ReceiptItem('a', 'Small', 1, 1), ReceiptItem('b', 'Large', 1, 100)), 101, 99,
            tuple(ReceiptAdjustment(id_, 'Printed discount', 'discount', -1, ('a',), 'Separate printed line') for id_ in ('d1', 'd2')))
        with self.assertRaises(AuthorityError) as rejected:
            self.finalize_receipt(credentials, receipt, (('A', 'a', 1), ('B', 'b', 1)))
        self.assertEqual(rejected.exception.code, 'calculation_rejected')
        snapshot = self.authority.snapshot(credentials['A'], 'meal')
        self.assertEqual(snapshot.revision, 4)
        self.assertFalse(snapshot.finalized)
        self.assertIsNone(snapshot.calculation)

    def test_revocation_checks_current_authority_before_old_claim_replay(self):
        for kind in (RevokeSession, RevokeMembership):
            with self.subTest(kind=kind.__name__):
                self.authority.close()
                self.authority = Authority(Path(self.temp.name) / (kind.__name__ + '.sqlite'), clock=lambda: 1000)
                credentials = self.bootstrap()
                receipt = Receipt((ReceiptItem('dish', 'Rice', 1, 100),), 100, 100)
                self.authority.apply(credentials['A'], 'meal', ReplaceReceipt('entry', 0, 0, receipt))
                claim = SetOwnQuantity('claim', 'dish', 1, 1, 1)
                self.authority.apply(credentials['B'], 'meal', claim)
                revoke = kind('revoke', 2, 'B')
                result = self.authority.apply(credentials['A'], 'meal', revoke)
                self.assertEqual(result.revision, 3)
                self.assertEqual(self.authority.apply(credentials['A'], 'meal', revoke), result)
                for operation in (lambda: self.authority.snapshot(credentials['B'], 'meal'),
                                  lambda: self.authority.apply(credentials['B'], 'meal', claim)):
                    with self.assertRaises(AuthorityError) as rejected:
                        operation()
                    self.assertEqual(rejected.exception.code, 'invalid_session')
                snapshot = self.authority.snapshot(credentials['A'], 'meal')
                self.assertEqual(snapshot.claims[0].participant_id, 'B')
                self.assertEqual(tuple(p.id for p in snapshot.participants), ('A', 'B'))
                with self.assertRaises(AuthorityError) as noop:
                    self.authority.apply(credentials['A'], 'meal', kind('again', 3, 'B'))
                self.assertEqual(noop.exception.code, 'already_revoked')
                with self.assertRaises(AuthorityError) as self_revoke:
                    self.authority.apply(credentials['A'], 'meal', kind('self', 3, 'A'))
                self.assertEqual(self_revoke.exception.code, 'forbidden')


if __name__ == '__main__':
    unittest.main()
