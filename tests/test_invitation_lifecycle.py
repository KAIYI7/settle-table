"""Functional and integration tests for invitation and session lifecycle."""
from contextlib import closing
from dataclasses import replace
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from settletable.authority import (
    Authority, AuthorityError, Participant, SessionGrant,
    InvitationGrant, InvitationRecord, RevokeInvitation,
    RevokeSession, RevokeMembership,
)


class InvitationLifecycleTests(unittest.TestCase):
    def setUp(self):
        scratch = Path('.local/tests')
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'lifecycle.sqlite'
        self.current_time = 1000.0
        self.authority = Authority(self.path, clock=lambda: self.current_time)
        self.addCleanup(self.authority.close)
        self.participants = (
            Participant('A', 'Alice', organizer=True),
            Participant('B', 'Bob', organizer=False),
            Participant('C', 'Charlie', organizer=False),
        )
        self.bootstrap = self.authority.bootstrap('meal-1', self.participants)
        self.organizer_cred = self.bootstrap.sessions[0].credential
        self.bob_cred = self.bootstrap.sessions[1].credential

    def test_additive_schema_and_initial_snapshot(self):
        snapshot = self.authority.snapshot(self.organizer_cred, 'meal-1')
        self.assertEqual(snapshot.meal_id, 'meal-1')
        self.assertEqual(snapshot.invitations, ())
        with closing(sqlite3.connect(self.path)) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn('invitations', tables)
            self.assertIn('participant_lifecycle', tables)

    def test_issue_invitation_success(self):
        grant = self.authority.issue_invitation(
            self.organizer_cred, 'meal-1', 'B', invite_ttl=3600, issue_id='inv-bob-1'
        )
        self.assertIsInstance(grant, InvitationGrant)
        self.assertEqual(grant.meal_id, 'meal-1')
        self.assertEqual(grant.participant_id, 'B')
        self.assertEqual(len(grant.token), 43)
        self.assertEqual(grant.expires, self.current_time + 3600)
        self.assertFalse(grant.token in repr(grant), 'token leaked in repr')

        # Snapshot shows public InvitationRecord
        snapshot = self.authority.snapshot(self.organizer_cred, 'meal-1')
        self.assertEqual(len(snapshot.invitations), 1)
        record = snapshot.invitations[0]
        self.assertEqual(record.participant_id, 'B')
        self.assertEqual(record.created_at, self.current_time)
        self.assertEqual(record.expires, self.current_time + 3600)
        self.assertFalse(record.consumed)
        self.assertFalse(record.revoked)
        self.assertEqual(record.issue_id, 'inv-bob-1')
        self.assertFalse(grant.token in repr(snapshot), 'token leaked in snapshot repr')

        # Verify storage contains domain-separated verifier and no raw token
        verifier = hashlib.sha256(b'settletable-invitation-v1\0' + grant.token.encode('ascii')).digest()
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute('SELECT verifier, consumed, revoked FROM invitations WHERE meal_id=?', ('meal-1',)).fetchone()
            self.assertEqual(row[0], verifier)
            self.assertEqual(row[1], 0)
            self.assertEqual(row[2], 0)
            dump = '\n'.join(db.iterdump())
            self.assertNotIn(grant.token, dump)

    def test_issue_invitation_permission_and_target_validation(self):
        # Diner cannot issue invitation
        with self.assertRaises(AuthorityError) as err:
            self.authority.issue_invitation(self.bob_cred, 'meal-1', 'C')
        self.assertEqual(err.exception.code, 'forbidden')

        # Cannot invite organizer
        with self.assertRaises(AuthorityError) as err:
            self.authority.issue_invitation(self.organizer_cred, 'meal-1', 'A')
        self.assertEqual(err.exception.code, 'forbidden')

        # Cannot invite unknown participant
        with self.assertRaises(AuthorityError) as err:
            self.authority.issue_invitation(self.organizer_cred, 'meal-1', 'D')
        self.assertEqual(err.exception.code, 'forbidden')

    def test_only_one_active_invitation_per_target(self):
        self.authority.issue_invitation(self.organizer_cred, 'meal-1', 'B', issue_id='inv-1')
        with self.assertRaises(AuthorityError) as err:
            self.authority.issue_invitation(self.organizer_cred, 'meal-1', 'B', issue_id='inv-2')
        self.assertEqual(err.exception.code, 'active_invitation_exists')

        # Different diner can be invited
        grant_c = self.authority.issue_invitation(self.organizer_cred, 'meal-1', 'C', issue_id='inv-c-1')
        self.assertEqual(grant_c.participant_id, 'C')

    def test_redeem_invitation_success(self):
        grant = self.authority.issue_invitation(self.organizer_cred, 'meal-1', 'B', invite_ttl=3600)
        bob_session = self.authority.redeem_invitation(grant.token, 'meal-1', session_ttl=1800)
        self.assertIsInstance(bob_session, SessionGrant)
        self.assertEqual(bob_session.participant_id, 'B')
        self.assertEqual(len(bob_session.credential), 43)
        self.assertNotEqual(bob_session.credential, self.bob_cred)
        self.assertFalse(bob_session.credential in repr(bob_session))

        # Bob can use the new credential to read snapshot
        snapshot = self.authority.snapshot(bob_session.credential, 'meal-1')
        self.assertEqual(snapshot.meal_id, 'meal-1')
        self.assertTrue(snapshot.invitations[0].consumed)

        # Bob's old bootstrap session is invalidated atomically
        with self.assertRaises(AuthorityError) as err:
            self.authority.snapshot(self.bob_cred, 'meal-1')
        self.assertEqual(err.exception.code, 'invalid_session')

        # Retrying to redeem the consumed token fails (single-use)
        with self.assertRaises(AuthorityError) as err:
            self.authority.redeem_invitation(grant.token, 'meal-1')
        self.assertEqual(err.exception.code, 'invalid_invitation')

    def test_redeem_invitation_rejections(self):
        # Malformed token
        for bad_token in ('', 'too-short', 'a' * 42, 'a' * 44, '!' * 43, None, 123):
            with self.subTest(bad_token=bad_token):
                with self.assertRaises(AuthorityError) as err:
                    self.authority.redeem_invitation(bad_token, 'meal-1')
                self.assertEqual(err.exception.code, 'invalid_invitation')

        # Expired token
        grant = self.authority.issue_invitation(self.organizer_cred, 'meal-1', 'B', invite_ttl=100)
        self.current_time += 101.0
        with self.assertRaises(AuthorityError) as err:
            self.authority.redeem_invitation(grant.token, 'meal-1')
        self.assertEqual(err.exception.code, 'invalid_invitation')

        # Wrong meal
        self.current_time = 1000.0
        grant2 = self.authority.issue_invitation(self.organizer_cred, 'meal-1', 'C', invite_ttl=100)
        with self.assertRaises(AuthorityError) as err:
            self.authority.redeem_invitation(grant2.token, 'other-meal')
        self.assertEqual(err.exception.code, 'invalid_invitation')

    def test_rotate_session_success(self):
        rev_before = self.authority.snapshot(self.bob_cred, 'meal-1').revision
        rotated = self.authority.rotate_session(self.bob_cred, 'meal-1', session_ttl=1200)
        self.assertIsInstance(rotated, SessionGrant)
        self.assertEqual(rotated.participant_id, 'B')
        self.assertNotEqual(rotated.credential, self.bob_cred)
        self.assertFalse(rotated.credential in repr(rotated))

        # Snapshot using new credential succeeds
        snapshot = self.authority.snapshot(rotated.credential, 'meal-1')
        self.assertEqual(snapshot.meal_id, 'meal-1')
        # Revision did NOT advance on private session rotation (Finding 1)
        self.assertEqual(snapshot.revision, rev_before)

        # Old credential is dead
        with self.assertRaises(AuthorityError) as err:
            self.authority.snapshot(self.bob_cred, 'meal-1')
        self.assertEqual(err.exception.code, 'invalid_session')

    def test_revoke_invitation_command(self):
        grant = self.authority.issue_invitation(self.organizer_cred, 'meal-1', 'B', invite_ttl=3600)
        rev = self.authority.snapshot(self.organizer_cred, 'meal-1').revision
        cmd = RevokeInvitation('rev-inv-1', rev, 'B')
        accepted = self.authority.apply(self.organizer_cred, 'meal-1', cmd)
        self.assertEqual(accepted.kind, 'RevokeInvitation')
        self.assertEqual(accepted.revision, rev + 1)

        # Snapshot shows revoked invitation
        snapshot = self.authority.snapshot(self.organizer_cred, 'meal-1')
        self.assertTrue(snapshot.invitations[0].revoked)

        # Redemption of revoked invitation fails
        with self.assertRaises(AuthorityError) as err:
            self.authority.redeem_invitation(grant.token, 'meal-1')
        self.assertEqual(err.exception.code, 'invalid_invitation')

        # Repeat revoke with fresh command ID fails with already_revoked
        with self.assertRaises(AuthorityError) as err:
            self.authority.apply(self.organizer_cred, 'meal-1', RevokeInvitation('rev-inv-2', rev + 1, 'B'))
        self.assertEqual(err.exception.code, 'already_revoked')

    def test_cascading_revocation_on_session_and_membership_revoke(self):
        # Case 1: Active session + active invitation -> RevokeSession revokes both
        grant_b = self.authority.issue_invitation(self.organizer_cred, 'meal-1', 'B', invite_ttl=3600)
        rev = self.authority.snapshot(self.organizer_cred, 'meal-1').revision
        self.authority.apply(self.organizer_cred, 'meal-1', RevokeSession('rev-sess-b', rev, 'B'))
        with self.assertRaises(AuthorityError) as err:
            self.authority.redeem_invitation(grant_b.token, 'meal-1')
        self.assertEqual(err.exception.code, 'invalid_invitation')
        with self.assertRaises(AuthorityError) as err:
            self.authority.snapshot(self.bob_cred, 'meal-1')
        self.assertEqual(err.exception.code, 'invalid_session')

        # Case 2: Inactive session (already revoked) + fresh invitation -> RevokeSession still revokes invitation (Finding 2)
        grant_b2 = self.authority.issue_invitation(self.organizer_cred, 'meal-1', 'B', invite_ttl=3600)
        rev = self.authority.snapshot(self.organizer_cred, 'meal-1').revision
        # This RevokeSession must succeed because the active invitation exists, cascading to it!
        self.authority.apply(self.organizer_cred, 'meal-1', RevokeSession('rev-sess-b2', rev, 'B'))
        with self.assertRaises(AuthorityError) as err:
            self.authority.redeem_invitation(grant_b2.token, 'meal-1')
        self.assertEqual(err.exception.code, 'invalid_invitation')

        # Case 3: Membership revocation cascades to invitations and deactivates participant
        grant_c = self.authority.issue_invitation(self.organizer_cred, 'meal-1', 'C', invite_ttl=3600)
        rev = self.authority.snapshot(self.organizer_cred, 'meal-1').revision
        self.authority.apply(self.organizer_cred, 'meal-1', RevokeMembership('rev-mem-c', rev, 'C'))
        with self.assertRaises(AuthorityError) as err:
            self.authority.redeem_invitation(grant_c.token, 'meal-1')
        self.assertEqual(err.exception.code, 'invalid_invitation')
        # Organizer cannot re-invite deactivated participant C
        with self.assertRaises(AuthorityError) as err:
            self.authority.issue_invitation(self.organizer_cred, 'meal-1', 'C')
        self.assertEqual(err.exception.code, 'forbidden')

    def test_duplicate_issue_id_rejects_with_command_conflict(self):
        grant = self.authority.issue_invitation(
            self.organizer_cred, 'meal-1', 'B', invite_ttl=3600, issue_id='custom-issue-1'
        )
        self.assertEqual(grant.participant_id, 'B')
        # Reissuing or issuing another invitation with the same issue_id raises command_conflict
        with self.assertRaises(AuthorityError) as err:
            self.authority.issue_invitation(
                self.organizer_cred, 'meal-1', 'C', invite_ttl=3600, issue_id='custom-issue-1'
            )
        self.assertEqual(err.exception.code, 'command_conflict')

    def test_organizer_cannot_rotate_session(self):
        # Organizer session rotation is forbidden to protect against self-lockout/credential loss
        with self.assertRaises(AuthorityError) as err:
            self.authority.rotate_session(self.organizer_cred, 'meal-1', session_ttl=3600)
        self.assertEqual(err.exception.code, 'forbidden')


if __name__ == '__main__':
    unittest.main()
