"""Adversarial, concurrency, and security tests for invitation and session lifecycle."""
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from settletable.authority import (
    Authority, AuthorityError, Participant,
    InvitationGrant, SessionGrant, RevokeInvitation, RevokeSession, RevokeMembership,
)


class InvitationAdversarialTests(unittest.TestCase):
    def setUp(self):
        scratch = Path('.local/tests')
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'adversarial_lifecycle.sqlite'
        self.current_time = 1000.0
        self.authority = Authority(self.path, clock=lambda: self.current_time)
        self.addCleanup(self.authority.close)
        self.participants = (
            Participant('A', 'Alice', organizer=True),
            Participant('B', 'Bob', organizer=False),
            Participant('C', 'Charlie', organizer=False),
        )
        self.bootstrap = self.authority.bootstrap('meal-adv', self.participants)
        self.organizer_cred = self.bootstrap.sessions[0].credential
        self.bob_cred = self.bootstrap.sessions[1].credential

    def test_two_connections_racing_same_redemption(self):
        grant = self.authority.issue_invitation(self.organizer_cred, 'meal-adv', 'B', invite_ttl=3600)
        barrier = threading.Barrier(2)
        results = [None, None]
        errors = [None, None]

        def worker(index):
            conn = Authority(self.path, clock=lambda: self.current_time)
            try:
                barrier.wait()
                results[index] = conn.redeem_invitation(grant.token, 'meal-adv', session_ttl=1800)
            except Exception as e:
                errors[index] = e
            finally:
                conn.close()

        t1 = threading.Thread(target=worker, args=(0,))
        t2 = threading.Thread(target=worker, args=(1,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly one thread succeeds, one fails
        succeeded = [r for r in results if r is not None]
        failed = [e for e in errors if e is not None]
        self.assertEqual(len(succeeded), 1, "Exactly one redemption must succeed")
        self.assertEqual(len(failed), 1, "Exactly one redemption must fail")
        self.assertIsInstance(succeeded[0], SessionGrant)
        self.assertEqual(succeeded[0].participant_id, 'B')
        self.assertIsInstance(failed[0], AuthorityError)
        self.assertIn(failed[0].code, ('invalid_invitation', 'busy'))

        # Verify exactly one active session exists for Bob in database
        with closing(sqlite3.connect(self.path)) as db:
            sessions = db.execute('SELECT verifier, revoked FROM sessions WHERE meal_id=? AND participant_id=?',
                                  ('meal-adv', 'B')).fetchall()
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0][1], 0)
            invs = db.execute('SELECT consumed, revoked FROM invitations WHERE meal_id=? AND participant_id=?',
                              ('meal-adv', 'B')).fetchall()
            self.assertEqual(len(invs), 1)
            self.assertEqual(invs[0][0], 1)  # consumed

    def test_redemption_racing_invitation_revocation(self):
        grant = self.authority.issue_invitation(self.organizer_cred, 'meal-adv', 'B', invite_ttl=3600)
        rev = self.authority.snapshot(self.organizer_cred, 'meal-adv').revision

        barrier = threading.Barrier(2)
        redeem_res, redeem_err = [None], [None]
        revoke_res, revoke_err = [None], [None]

        def redeem_worker():
            conn = Authority(self.path, clock=lambda: self.current_time)
            try:
                barrier.wait()
                redeem_res[0] = conn.redeem_invitation(grant.token, 'meal-adv')
            except Exception as e:
                redeem_err[0] = e
            finally:
                conn.close()

        def revoke_worker():
            conn = Authority(self.path, clock=lambda: self.current_time)
            try:
                barrier.wait()
                revoke_res[0] = conn.apply(self.organizer_cred, 'meal-adv', RevokeInvitation('rev-inv-race', rev, 'B'))
            except Exception as e:
                revoke_err[0] = e
            finally:
                conn.close()

        t1 = threading.Thread(target=redeem_worker)
        t2 = threading.Thread(target=revoke_worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Consistent outcome: either revocation won (redemption failed), or redemption won (invitation already consumed -> revocation rejected with already_revoked, busy, or revision_conflict)
        if revoke_res[0] is not None:
            # Revocation won: redemption MUST have failed
            self.assertIsNotNone(redeem_err[0])
            self.assertIn(redeem_err[0].code, ('invalid_invitation', 'busy'))
        else:
            # Redemption won: revocation failed with already_revoked, busy, or revision conflict
            self.assertIsNotNone(redeem_res[0])
            self.assertIsNotNone(revoke_err[0])

    def test_lifecycle_generation_quota_and_security_headroom(self):
        # Advance Bob's generations up to 64
        # Bob starts at generation 1 from bootstrap
        token = None
        for i in range(2, 64):
            if i % 2 == 0:
                grant = self.authority.issue_invitation(self.organizer_cred, 'meal-adv', 'B',
                                                        invite_ttl=3600, issue_id=f'inv-gen-{i}')
                token = grant.token
            else:
                session = self.authority.redeem_invitation(token, 'meal-adv')

        with closing(sqlite3.connect(self.path)) as db:
            gen = db.execute('SELECT generation FROM participant_lifecycle WHERE meal_id=? AND participant_id=?',
                             ('meal-adv', 'B')).fetchone()[0]
            self.assertEqual(gen, 63)

        # 64th operation: issue invitation advances to 64
        grant64 = self.authority.issue_invitation(self.organizer_cred, 'meal-adv', 'B',
                                                 invite_ttl=3600, issue_id='inv-gen-64')

        # 65th operation: attempt to redeem advances past 64 -> MUST raise resource_limit
        with self.assertRaises(AuthorityError) as err:
            self.authority.redeem_invitation(grant64.token, 'meal-adv')
        self.assertEqual(err.exception.code, 'resource_limit')

        # SECURITY HEADROOM INVARIANT: Even when generation quota is exhausted,
        # security revocations (RevokeInvitation, RevokeSession, RevokeMembership) MUST STILL SUCCEED!
        rev = self.authority.snapshot(self.organizer_cred, 'meal-adv').revision
        rev_inv_res = self.authority.apply(self.organizer_cred, 'meal-adv', RevokeInvitation('rev-64', rev, 'B'))
        self.assertEqual(rev_inv_res.kind, 'RevokeInvitation')

        rev2 = self.authority.snapshot(self.organizer_cred, 'meal-adv').revision
        rev_sess_res = self.authority.apply(self.organizer_cred, 'meal-adv', RevokeSession('rev-sess-64', rev2, 'B'))
        self.assertEqual(rev_sess_res.kind, 'RevokeSession')

        rev3 = self.authority.snapshot(self.organizer_cred, 'meal-adv').revision
        rev_mem_res = self.authority.apply(self.organizer_cred, 'meal-adv', RevokeMembership('rev-mem-64', rev3, 'B'))
        self.assertEqual(rev_mem_res.kind, 'RevokeMembership')

    def test_failure_hooks_and_commit_uncertainty(self):
        hook_stage = None

        def failing_hook(stage):
            if stage == hook_stage:
                raise RuntimeError("injected fault")

        hooked_auth = Authority(self.path, clock=lambda: self.current_time, failure_hook=failing_hook)
        self.addCleanup(hooked_auth.close)

        # 1. Pre-commit failure: rolls back cleanly
        hook_stage = 'before_commit'
        with self.assertRaises(AuthorityError) as err:
            hooked_auth.issue_invitation(self.organizer_cred, 'meal-adv', 'C', issue_id='inv-fail-pre')
        self.assertEqual(err.exception.code, 'storage_error')

        # Verify no invitation was inserted
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT 1 FROM invitations WHERE issue_id='inv-fail-pre'").fetchone()
            self.assertIsNone(row)

        # 2. Post-commit failure: commit_uncertain
        hook_stage = 'after_commit'
        with self.assertRaises(AuthorityError) as err:
            hooked_auth.issue_invitation(self.organizer_cred, 'meal-adv', 'C', issue_id='inv-fail-post')
        self.assertEqual(err.exception.code, 'commit_uncertain')

        # Verify invitation DID commit
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT 1 FROM invitations WHERE issue_id='inv-fail-post'").fetchone()
            self.assertIsNotNone(row)

    def test_token_and_credential_nonleakage(self):
        grant = self.authority.issue_invitation(self.organizer_cred, 'meal-adv', 'B', issue_id='leak-test')
        session = self.authority.redeem_invitation(grant.token, 'meal-adv')
        snapshot = self.authority.snapshot(session.credential, 'meal-adv')

        raw_secrets = (grant.token, session.credential, self.organizer_cred, self.bob_cred)
        for s in raw_secrets:
            self.assertFalse(s in repr(grant))
            self.assertFalse(s in repr(session))
            self.assertFalse(s in repr(snapshot))

        # Check raw database file and sqlite dump
        raw_db_bytes = self.path.read_bytes()
        with closing(sqlite3.connect(self.path)) as db:
            dump = '\n'.join(db.iterdump())

        for s in raw_secrets:
            self.assertNotIn(s, dump)
            self.assertNotIn(s.encode('ascii'), raw_db_bytes)

    def test_backward_compatibility_reopening_v1_database(self):
        v1_path = Path(self.temp.name) / 'v1_legacy.sqlite'
        # Create an exact v1 database without invitations or participant_lifecycle tables
        with closing(sqlite3.connect(v1_path)) as db:
            db.executescript('''
                CREATE TABLE meals (id TEXT PRIMARY KEY, state BLOB NOT NULL);
                CREATE TABLE participants (meal_id TEXT NOT NULL REFERENCES meals(id), id TEXT NOT NULL,
                    name TEXT NOT NULL, organizer INTEGER NOT NULL, active INTEGER NOT NULL, PRIMARY KEY(meal_id,id));
                CREATE TABLE sessions (verifier BLOB PRIMARY KEY, meal_id TEXT NOT NULL, participant_id TEXT NOT NULL,
                    expires REAL NOT NULL, revoked INTEGER NOT NULL, UNIQUE(meal_id,participant_id));
                CREATE TABLE commands (meal_id TEXT NOT NULL, participant_id TEXT NOT NULL, command_id TEXT NOT NULL,
                    body BLOB NOT NULL, digest BLOB NOT NULL, result BLOB NOT NULL, security INTEGER NOT NULL,
                    PRIMARY KEY(meal_id,participant_id,command_id));
            ''')
            # Insert a meal and bootstrap participant
            db.execute("INSERT INTO meals VALUES ('v1-meal', '{\"revision\":0,\"financial_revision\":0,\"receipt\":null,\"item_revisions\":{},\"claims\":[],\"review\":null,\"calculation\":null,\"retired_ids\":[]}')")
            db.execute("INSERT INTO participants VALUES ('v1-meal', 'A', 'Alice', 1, 1)")
            db.execute("INSERT INTO participants VALUES ('v1-meal', 'B', 'Bob', 0, 1)")
            cred_a = 'A' * 43
            ver_a = hashlib.sha256(b'settletable-local-session-v1\0' + cred_a.encode('ascii')).digest()
            db.execute("INSERT INTO sessions VALUES (?, 'v1-meal', 'A', 2000.0, 0)", (ver_a,))
            db.commit()

        # Open with new Authority class
        auth_v1 = Authority(v1_path, clock=lambda: 1000.0)
        self.addCleanup(auth_v1.close)

        # Snapshot works byte-identically and reports empty invitations
        snapshot = auth_v1.snapshot(cred_a, 'v1-meal')
        self.assertEqual(snapshot.meal_id, 'v1-meal')
        self.assertEqual(snapshot.invitations, ())

        # Now issue an invitation on the migrated database
        grant = auth_v1.issue_invitation(cred_a, 'v1-meal', 'B')
        self.assertEqual(grant.participant_id, 'B')
        session_b = auth_v1.redeem_invitation(grant.token, 'v1-meal')
        self.assertEqual(session_b.participant_id, 'B')


if __name__ == '__main__':
    unittest.main()
