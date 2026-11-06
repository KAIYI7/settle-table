"""Independent security probes; all sessions/databases are ephemeral local data."""
from contextlib import closing, redirect_stderr, redirect_stdout
import hashlib
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from settletable import authority as auth


class AuthoritySecurityTests(unittest.TestCase):
    def setUp(self):
        scratch = Path('.local/tests')
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.path = Path(self.temp.name) / 'security.sqlite'
        self.authority = auth.Authority(self.path, clock=lambda: 1000)
        bootstrap = self.authority.bootstrap('meal', (
            auth.Participant('A', 'Organizer', True), auth.Participant('B', 'Diner')))
        self.credentials = {grant.participant_id: grant.credential for grant in bootstrap.sessions}
        self.assertFalse(self.credentials['A'] in repr(bootstrap), 'session material leaked')
        self.assertFalse(self.credentials['B'] in repr(bootstrap.sessions), 'session material leaked')

    def tearDown(self):
        self.authority.close()
        self.temp.cleanup()

    def test_credentials_reject_before_hashing_or_database_work(self):
        class StringSubclass(str):
            pass
        invalid = (None, True, 1, b'x' * 43, ['x'], StringSubclass('x' * 43),
                   '', 'x' * 42, 'x' * 44, 'x' * 1_048_577, '\u00e9' * 43,
                   'x' * 42 + '/', 'x' * 42 + '\x00', 'x' * 42 + '\ud800')
        # A closed connection would return storage_error for valid credentials.
        # Every invalid input must reject before reaching that dependency/hash.
        self.authority.close()
        output = io.StringIO()
        with patch.object(auth.hashlib, 'sha256', side_effect=AssertionError('hash reached')):
            with redirect_stdout(output), redirect_stderr(output):
                for value in invalid:
                    with self.subTest(type=type(value).__name__, length=len(value) if hasattr(value, '__len__') else None):
                        for operation in (lambda: self.authority.snapshot(value, 'meal'),
                                          lambda: self.authority.apply(value, 'meal', None)):
                            with self.assertRaises(auth.AuthorityError) as rejected:
                                operation()
                            self.assertEqual(rejected.exception.code, 'invalid_session')
                            self.assertEqual(str(rejected.exception), 'invalid_session')
        self.assertFalse(output.getvalue(), 'unexpected diagnostic output')

    def test_storage_contains_only_domain_separated_verifiers(self):
        snapshot = self.authority.snapshot(self.credentials['A'], 'meal')
        for credential in self.credentials.values():
            self.assertFalse(credential in repr(snapshot), 'session material leaked')
        with closing(sqlite3.connect(self.path)) as database:
            verifiers = tuple(row[0] for row in database.execute('SELECT verifier FROM sessions'))
            dump = '\n'.join(database.iterdump())
        for credential in self.credentials.values():
            expected = hashlib.sha256(b'settletable-local-session-v1\0' + credential.encode('ascii')).digest()
            self.assertTrue(expected in verifiers, 'expected session verifier missing')
            self.assertFalse(credential in dump, 'session material leaked')
            self.assertFalse(credential.encode('ascii') in self.path.read_bytes(), 'session material leaked')
        self.assertEqual(len(set(verifiers)), 2)

    def test_permission_is_checked_before_replay_lookup(self):
        command = auth.ReplaceReceipt('known-organizer-command', 0, 0, auth.Receipt())
        accepted = self.authority.apply(self.credentials['A'], 'meal', command)
        queries = []
        self.authority._db.set_trace_callback(queries.append)
        with self.assertRaises(auth.AuthorityError) as denied:
            self.authority.apply(self.credentials['B'], 'meal', command)
        self.authority._db.set_trace_callback(None)
        self.assertEqual(denied.exception.code, 'forbidden')
        self.assertFalse(any('SELECT body,digest,result' in query for query in queries))
        # Trace capture is private transient test state, never a persisted report.
        for credential in self.credentials.values():
            self.assertFalse(any(credential in query for query in queries))
        self.assertEqual(self.authority.snapshot(self.credentials['A'], 'meal').revision, accepted.revision)

    def test_diner_cannot_issue_any_organizer_command_or_inject_actor_role(self):
        commands = (auth.ReplaceReceipt('replace-denied', 0, 0, auth.Receipt()),
                    auth.ReviewReceipt('review-denied', 0, 0, '0' * 64),
                    auth.Finalize('finalize-denied', 0, 0),
                    auth.RevokeSession('session-denied', 0, 'A'),
                    auth.RevokeMembership('member-denied', 0, 'A'))
        for command in commands:
            with self.subTest(kind=type(command).__name__):
                with self.assertRaises(auth.AuthorityError) as rejected:
                    self.authority.apply(self.credentials['B'], 'meal', command)
                self.assertEqual(rejected.exception.code, 'forbidden')
        injected = {'command_id': 'injected', 'kind': 'Finalize', 'actor': 'A',
                    'role': 'organizer', 'reviewed': True, 'expected_revision': 0,
                    'expected_financial_revision': 0}
        with self.assertRaises(auth.AuthorityError) as rejected:
            self.authority.apply(self.credentials['B'], 'meal', injected)
        self.assertEqual(rejected.exception.code, 'invalid_input')
        self.assertEqual(self.authority.snapshot(self.credentials['A'], 'meal').revision, 0)
        with closing(sqlite3.connect(self.path)) as database:
            self.assertEqual(database.execute('SELECT COUNT(*) FROM commands').fetchone()[0], 0)

    def test_bootstrap_entropy_failure_is_safe_and_creates_no_meal(self):
        with patch.object(auth.secrets, 'token_urlsafe', side_effect=OSError('sensitive-entropy-diagnostic')):
            with self.assertRaises(auth.AuthorityError) as rejected:
                self.authority.bootstrap('entropy-failure', (auth.Participant('A', 'A', True),))
        self.assertEqual(str(rejected.exception), 'storage_error')
        self.assertIsNone(rejected.exception.__cause__)
        self.assertTrue(rejected.exception.__suppress_context__)
        with closing(sqlite3.connect(self.path)) as database:
            self.assertIsNone(database.execute('SELECT id FROM meals WHERE id=?', ('entropy-failure',)).fetchone())

    def test_finalized_results_snapshots_and_logs_exclude_session_material(self):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            receipt = auth.Receipt((auth.ReceiptItem('dish', 'Dish', 3, 1001),), 1001, 1001)
            results = [self.authority.apply(self.credentials['A'], 'meal', auth.ReplaceReceipt('receipt', 0, 0, receipt))]
            results.append(self.authority.apply(self.credentials['A'], 'meal', auth.SetOwnQuantity('claim-a', 'dish', 1, 1, 1)))
            results.append(self.authority.apply(self.credentials['B'], 'meal', auth.SetOwnQuantity('claim-b', 'dish', 2, 2, 1)))
            snapshot = self.authority.snapshot(self.credentials['A'], 'meal')
            results.append(self.authority.apply(self.credentials['A'], 'meal', auth.ReviewReceipt('review', 3, 1, snapshot.receipt_digest)))
            finalize_command = auth.Finalize('finalize', 4, 1)
            final = self.authority.apply(self.credentials['A'], 'meal', finalize_command)
            results.append(final)
            self.authority.close()
            self.authority = auth.Authority(self.path, clock=lambda: 1000)
            replay = self.authority.apply(self.credentials['A'], 'meal', finalize_command)
            self.assertEqual(replay.canonical_bytes, final.canonical_bytes)
            self.assertEqual(tuple(p.sen for p in final.calculation.consumption), (334, 667))
            snapshot = self.authority.snapshot(self.credentials['B'], 'meal')
        self.assertFalse(output.getvalue(), 'unexpected diagnostic output')
        for credential in self.credentials.values():
            verifier = hashlib.sha256(b'settletable-local-session-v1\0' + credential.encode('ascii')).digest()
            for ordinary_result in (*results, replay, snapshot):
                self.assertFalse(credential in repr(ordinary_result), 'session material leaked')
                self.assertFalse(verifier.hex() in repr(ordinary_result), 'session material leaked')
            for result in (*results, replay):
                self.assertFalse(credential.encode('ascii') in result.canonical_bytes, 'session material leaked')
                self.assertFalse(verifier.hex().encode('ascii') in result.canonical_bytes, 'session material leaked')
            for path in Path(self.temp.name).iterdir():
                if path.is_file():
                    self.assertFalse(credential.encode('ascii') in path.read_bytes(), 'session material leaked')

    def test_failed_rollback_and_close_discard_connection_without_leaking(self):
        class BrokenCleanup:
            def __init__(self, connection):
                self.connection = connection

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def execute(self, sql, *parameters):
                if sql == 'ROLLBACK':
                    raise sqlite3.OperationalError('sensitive-storage-diagnostic')
                return self.connection.execute(sql, *parameters)

            def close(self):
                # Close the real handle, then simulate another cleanup failure.
                self.connection.close()
                raise sqlite3.OperationalError('sensitive-close-diagnostic')

        def fail_after_mutation(stage):
            if stage == 'after_state':
                raise RuntimeError('sensitive-hook-diagnostic')

        self.authority._failure_hook = fail_after_mutation
        self.authority._db = BrokenCleanup(self.authority._db)
        command = auth.ReplaceReceipt('replace', 0, 0, auth.Receipt((auth.ReceiptItem('dish', 'Dish', 1, 100),), 100, 100))
        with self.assertRaises(auth.AuthorityError) as rejected:
            self.authority.apply(self.credentials['A'], 'meal', command)
        self.assertEqual(str(rejected.exception), 'storage_error')
        self.assertIsNone(rejected.exception.__cause__)
        self.assertTrue(rejected.exception.__suppress_context__)
        self.assertIsNone(self.authority._db)
        self.authority = auth.Authority(self.path, clock=lambda: 1000)
        self.assertEqual(self.authority.snapshot(self.credentials['A'], 'meal').revision, 0)
        with closing(sqlite3.connect(self.path)) as database:
            self.assertEqual(database.execute('SELECT COUNT(*) FROM commands').fetchone()[0], 0)

    def test_real_financial_history_exhaustion_preserves_revocation_reserve(self):
        receipt = auth.Receipt((auth.ReceiptItem('dish', 'Dish', 1, 100),), 100, 100)
        self.authority.apply(self.credentials['A'], 'meal', auth.ReplaceReceipt('receipt', 0, 0, receipt))
        # Exercise the real 10,000 limit through accepted public commands. No
        # direct fixture insertion, quota monkeypatch or weakened durability.
        previous_command = None
        for number in range(9_999):
            previous_command = auth.SetOwnQuantity(f'claim-{number}', 'dish', 1, number + 1, 1)
            result = self.authority.apply(self.credentials['B'], 'meal', previous_command)
        self.assertEqual(result.revision, 10_000)
        before = self.authority.snapshot(self.credentials['A'], 'meal')
        with self.assertRaises(auth.AuthorityError) as exhausted:
            self.authority.apply(self.credentials['B'], 'meal', auth.SetOwnQuantity('overflow', 'dish', 1, 10_000, 1))
        self.assertEqual(exhausted.exception.code, 'resource_limit')
        self.assertEqual(self.authority.snapshot(self.credentials['A'], 'meal'), before)
        session_command = auth.RevokeSession('revoke-session', 10_000, 'B')
        session_result = self.authority.apply(self.credentials['A'], 'meal', session_command)
        self.assertEqual(session_result.revision, 10_001)
        with self.assertRaises(auth.AuthorityError) as revoked_replay:
            self.authority.apply(self.credentials['B'], 'meal', previous_command)
        self.assertEqual(revoked_replay.exception.code, 'invalid_session')
        membership_command = auth.RevokeMembership('revoke-membership', 10_001, 'B')
        membership_result = self.authority.apply(self.credentials['A'], 'meal', membership_command)
        self.assertEqual(membership_result.revision, 10_002)
        for command in (auth.RevokeSession('repeat-session', 10_002, 'B'),
                        auth.RevokeMembership('repeat-membership', 10_002, 'B')):
            with self.assertRaises(auth.AuthorityError):
                self.authority.apply(self.credentials['A'], 'meal', command)
        self.assertEqual(self.authority.apply(self.credentials['A'], 'meal', session_command).canonical_bytes,
                         session_result.canonical_bytes)
        self.assertEqual(self.authority.apply(self.credentials['A'], 'meal', membership_command).canonical_bytes,
                         membership_result.canonical_bytes)
        after = self.authority.snapshot(self.credentials['A'], 'meal')
        self.assertEqual(after.revision, 10_002)
        self.assertEqual(after.claims, before.claims)
        self.assertEqual(after.participants, before.participants)
        self.assertIn('B', after.inactive_participant_ids)
        with closing(sqlite3.connect(self.path)) as database:
            self.assertEqual(database.execute('SELECT security,COUNT(*) FROM commands GROUP BY security ORDER BY security').fetchall(),
                             [(0, 10_000), (1, 2)])
            persisted = '\n'.join(database.iterdump())
        for credential in self.credentials.values():
            self.assertFalse(credential in persisted, 'session material leaked')
            self.assertFalse(credential.encode('ascii') in self.path.read_bytes(), 'session material leaked')

    def test_organizer_claims_lifecycle_and_security(self):
        # 1. Bootstrap automatically issues initial OrganizerClaimGrant
        boot = self.authority.bootstrap('claim-meal', (
            auth.Participant('O', 'Org', True), auth.Participant('D', 'Diner', False)))
        self.assertIsNotNone(boot.organizer_claim)
        initial_claim = boot.organizer_claim
        self.assertEqual(initial_claim.meal_id, 'claim-meal')
        self.assertFalse(initial_claim.token in repr(boot), 'token material leaked')

        # Raw claim token is never persisted in SQLite plaintext
        with closing(sqlite3.connect(self.path)) as database:
            dump = '\n'.join(database.iterdump())
            self.assertFalse(initial_claim.token in dump, 'raw claim token leaked into SQLite')

        # 2. Inspection of unconsumed claim
        insp = self.authority.inspect_organizer_claim(initial_claim.token)
        self.assertTrue(insp.valid)
        self.assertEqual(insp.meal_id, 'claim-meal')
        self.assertEqual(insp.organizer_id, 'O')
        self.assertEqual(insp.organizer_name, 'Org')

        # 3. Single-use redemption succeeds
        sess = self.authority.claim_organizer_session(initial_claim.token, 'claim-meal')
        self.assertEqual(sess.participant_id, 'O')
        # Session credential is valid
        auth_part, is_org = self.authority.authenticate(sess.credential, 'claim-meal')
        self.assertEqual(auth_part, 'O')
        self.assertTrue(is_org)

        # 4. Replay of consumed claim fails
        insp_consumed = self.authority.inspect_organizer_claim(initial_claim.token)
        self.assertFalse(insp_consumed.valid)
        self.assertEqual(insp_consumed.reason, 'consumed')
        with self.assertRaises(auth.AuthorityError) as replayed:
            self.authority.claim_organizer_session(initial_claim.token, 'claim-meal')
        self.assertEqual(replayed.exception.code, 'organizer_claim_consumed')

        # 5. Organizer generates recovery link
        recovery = self.authority.issue_organizer_recovery(sess.credential, 'claim-meal')
        self.assertIsNotNone(recovery.token)

        # Non-organizer cannot generate recovery link
        diner_cred = next(s.credential for s in boot.sessions if s.participant_id == 'D')
        with self.assertRaises(auth.AuthorityError) as denied:
            self.authority.issue_organizer_recovery(diner_cred, 'claim-meal')
        self.assertEqual(denied.exception.code, 'forbidden')

        # Generating another recovery link revokes previous unconsumed link
        newer_recovery = self.authority.issue_organizer_recovery(sess.credential, 'claim-meal')
        insp_older = self.authority.inspect_organizer_claim(recovery.token)
        self.assertFalse(insp_older.valid)
        self.assertEqual(insp_older.reason, 'revoked')
        with self.assertRaises(auth.AuthorityError) as revoked_redemption:
            self.authority.claim_organizer_session(recovery.token, 'claim-meal')
        self.assertEqual(revoked_redemption.exception.code, 'organizer_claim_revoked')

        # 6. Newer recovery link redeems successfully
        newer_sess = self.authority.claim_organizer_session(newer_recovery.token, 'claim-meal')
        self.assertEqual(newer_sess.participant_id, 'O')

        # 7. Wrong meal rejection
        host_claim = self.authority.issue_organizer_claim('claim-meal')
        with self.assertRaises(auth.AuthorityError) as wrong_meal:
            self.authority.claim_organizer_session(host_claim.token, 'other-meal')
        self.assertEqual(wrong_meal.exception.code, 'invalid_organizer_claim')

        # 8. Expired claim rejection
        current_time = 1000
        time_authority = auth.Authority(Path(self.temp.name) / 'expiry.sqlite', clock=lambda: current_time)
        try:
            exp_boot = time_authority.bootstrap('exp-meal', (auth.Participant('O', 'Org', True),), session_ttl=10)
            exp_token = exp_boot.organizer_claim.token
            current_time = 2000  # Advance past 10s TTL
            exp_insp = time_authority.inspect_organizer_claim(exp_token)
            self.assertFalse(exp_insp.valid)
            self.assertEqual(exp_insp.reason, 'expired')
            with self.assertRaises(auth.AuthorityError) as expired:
                time_authority.claim_organizer_session(exp_token, 'exp-meal')
            self.assertEqual(expired.exception.code, 'organizer_claim_expired')
        finally:
            time_authority.close()


if __name__ == '__main__':
    unittest.main()
