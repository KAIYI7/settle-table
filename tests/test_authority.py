import tempfile
import unittest
from pathlib import Path

from tabwise.authority import Authority, AuthorityError, Participant


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


if __name__ == '__main__':
    unittest.main()
