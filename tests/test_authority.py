import tempfile
import unittest
from pathlib import Path

from tabwise.authority import (Authority, AuthorityError, Participant, Receipt, ReceiptItem,
                               ReplaceReceipt)


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


if __name__ == '__main__':
    unittest.main()
