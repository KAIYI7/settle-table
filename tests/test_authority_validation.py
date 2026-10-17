"""Coordinator checks of real encoded bounds and receipt attestation gates."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from settletable.authority import (
    Authority, AuthorityError, Participant, Receipt, ReceiptItem,
    ReceiptAdjustment, ReplaceReceipt, ReviewReceipt, Finalize,
)


class AuthorityValidationTests(unittest.TestCase):
    def setUp(self):
        scratch = Path('.local/tests')
        scratch.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temp.cleanup)
        self.authority = Authority(Path(temp.name) / 'validation.sqlite', clock=lambda: 1000)
        self.addCleanup(self.authority.close)
        self.credential = self.authority.bootstrap('meal', (
            Participant('A', 'Organizer', True),)).sessions[0].credential

    def snapshot(self):
        return self.authority.snapshot(self.credential, 'meal')

    def apply(self, command):
        return self.authority.apply(self.credential, 'meal', command)

    def reject(self, command, code):
        before = self.snapshot()
        with self.assertRaises(AuthorityError) as error:
            self.apply(command)
        self.assertEqual(error.exception.code, code)
        self.assertEqual(self.snapshot(), before)

    def test_valid_field_lengths_cannot_bypass_actual_encoded_command_bound(self):
        # All individual fields/counts are within the documented limits. ASCII
        # JSON escaping expands non-BMP characters; the real 1MiB bound applies.
        glyph = '\U00010400'
        receipt = Receipt(
            tuple(ReceiptItem(f'item{i}', glyph * 160, 1, 0) for i in range(500)),
            0, 0,
            tuple(ReceiptAdjustment(f'adj{i}', glyph * 160, 'rounding', 0,
                                    ('item0',), glyph * 500) for i in range(100)),
        )
        self.reject(ReplaceReceipt('oversize', 0, 0, receipt), 'resource_limit')
        accepted = self.apply(ReplaceReceipt('small', 0, 0,
            Receipt((ReceiptItem('dish', 'Rice', 1, 1001),), 1001, 1001)))
        self.assertEqual(accepted.revision, 1)

    def test_attestation_rejects_unknown_and_mismatched_facts_without_fake_assignments(self):
        incomplete = Receipt((ReceiptItem('dish', 'Rice', 1, None),), None, None)
        self.apply(ReplaceReceipt('incomplete', 0, 0, incomplete))
        current = self.snapshot()
        self.reject(ReviewReceipt('unknown', 1, 1, current.receipt_digest), 'missing_amount')
        known = Receipt((ReceiptItem('dish', 'Rice', 1, 1001),), 1001, 1002)
        self.apply(ReplaceReceipt('mismatch', 1, 1, known))
        self.reject(ReviewReceipt('total', 2, 2, self.snapshot().receipt_digest),
                    'receipt_total_mismatch')
        self.apply(ReplaceReceipt('correct', 2, 2, replace(known, total_sen=1001)))
        self.reject(ReviewReceipt('wrong-digest', 3, 3, '0' * 64), 'receipt_digest_conflict')
        self.reject(Finalize('no-review', 3, 3), 'review_required')
        self.apply(ReviewReceipt('human-review', 3, 3, self.snapshot().receipt_digest))
        self.assertEqual(self.snapshot().claims, ())
        self.reject(Finalize('no-assignment', 4, 3), 'incomplete_quantity')


if __name__ == '__main__':
    unittest.main()
