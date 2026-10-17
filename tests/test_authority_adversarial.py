"""Independent public-interface challenges of the local authority contract."""
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from settletable import authority as authority_module

from settletable.authority import (
    Authority, AuthorityError, Participant, Receipt, ReceiptItem, ReplaceReceipt,
    SetOwnQuantity, ReviewReceipt, Finalize, RevokeSession, RevokeMembership,
)


class AuthorityAdversarialTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(".local/tests")
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "authority.sqlite"
        self.clock = lambda: 1000
        self.authority = Authority(self.path, clock=self.clock)
        self.addCleanup(self.authority.close)
        grants = self.authority.bootstrap("meal", (
            Participant("O", "Organizer", organizer=True),
            Participant("A", "Alice"), Participant("B", "Bob"),
        )).sessions
        self.credentials = {grant.participant_id: grant.credential for grant in grants}

    def snapshot(self, person="O", authority=None):
        return (authority or self.authority).snapshot(self.credentials[person], "meal")

    def apply(self, person, command, authority=None):
        return (authority or self.authority).apply(self.credentials[person], "meal", command)

    def assertRejected(self, action):
        with self.assertRaises(AuthorityError) as caught:
            action()
        return caught.exception.code

    @staticmethod
    def receipt():
        return Receipt((ReceiptItem("dish", "Shared rice", 3, 1001),), 1001, 1001)

    def item_revision(self, item="dish"):
        return next(row.item_revision for row in self.snapshot().items if row.item_id == item)

    def race(self, operations):
        barrier = threading.Barrier(len(operations) + 1)
        def worker(person, command):
            connection = Authority(self.path, clock=self.clock)
            try:
                barrier.wait(timeout=10)
                try:
                    return person, self.apply(person, command, connection), None
                except AuthorityError as error:
                    return person, None, error.code
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=len(operations)) as executor:
            futures = [executor.submit(worker, person, command) for person, command in operations]
            barrier.wait(timeout=10)
            return [future.result(timeout=10) for future in futures]

    def prepare_reviewed(self):
        self.apply("O", ReplaceReceipt("entry", 0, 0, self.receipt()))
        self.apply("A", SetOwnQuantity("claim", "dish", 1, 1, 1))
        self.apply("B", SetOwnQuantity("claim", "dish", 2, 2, 1))
        snapshot = self.snapshot()
        self.apply("O", ReviewReceipt("review", snapshot.revision, 1, snapshot.receipt_digest))
        return self.snapshot()

    def ordered_pair(self, first, second):
        ready = threading.Barrier(3)
        held = threading.Event()
        second_started = threading.Event()
        def first_hook(stage):
            if stage == "after_state":
                held.set()
                if not second_started.wait(5):
                    raise RuntimeError("second operation did not start")
        def worker(operation, is_first):
            person, command = operation
            connection = Authority(self.path, clock=self.clock,
                                   failure_hook=first_hook if is_first else None)
            try:
                ready.wait(timeout=10)
                if not is_first:
                    if not held.wait(5):
                        raise RuntimeError("first transaction did not reach held state")
                    second_started.set()
                try:
                    return self.apply(person, command, connection), None
                except AuthorityError as error:
                    return None, error.code
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(worker, first, True)
            second_future = executor.submit(worker, second, False)
            ready.wait(timeout=10)
            return first_future.result(timeout=10), second_future.result(timeout=10)

    def test_bootstrap_isolation_and_credential_boundary(self):
        before = self.snapshot()
        self.assertEqual(before.revision, 0)
        self.assertIsNone(before.calculation)
        self.assertFalse(before.finalized)
        self.assertRejected(lambda: self.authority.bootstrap("meal", (
            Participant("attacker", "Attacker", organizer=True),
        )))
        for credential in (None, True, 43, b"A" * 43, "", "A" * 42,
                           "A" * 44, "!" * 43, "é" * 43, "A" * 1_100_000):
            with self.subTest(kind=type(credential).__name__, size=(len(credential)
                              if hasattr(credential, "__len__") else None)):
                self.assertRejected(lambda: self.authority.snapshot(credential, "meal"))
        self.assertRejected(lambda: self.authority.snapshot(self.credentials["A"], "other"))
        self.assertEqual(self.snapshot(), before)
        rendered = repr(before)
        for credential in self.credentials.values():
            self.assertFalse(credential in rendered, "session material leaked")

    def test_expiry_at_boundary_and_wrong_meal_isolation(self):
        grant = self.authority.bootstrap("other", (
            Participant("A", "Different Alice", organizer=True),
        ), session_ttl=1).sessions[0]
        expired = Authority(self.path, clock=lambda: 1001)
        self.addCleanup(expired.close)
        self.assertRejected(lambda: expired.snapshot(grant.credential, "other"))
        self.assertRejected(lambda: self.authority.snapshot(grant.credential, "meal"))
        self.assertEqual(self.snapshot("A").revision, 0)
        self.assertEqual(self.authority.snapshot(grant.credential, "other").revision, 0)

    def test_bootstrap_failure_does_not_leave_unrecoverable_meal(self):
        path = Path(self.temp.name) / "bootstrap-failure.sqlite"
        def fail(stage):
            if stage == "after_state":
                raise RuntimeError("injected")
        failed = Authority(path, clock=self.clock, failure_hook=fail)
        try:
            self.assertRejected(lambda: failed.bootstrap("fresh", (
                Participant("O", "Organizer", organizer=True),
            )))
        finally:
            failed.close()
        recovered = Authority(path, clock=self.clock)
        self.addCleanup(recovered.close)
        grant = recovered.bootstrap("fresh", (
            Participant("O", "Organizer", organizer=True),
        )).sessions[0]
        self.assertEqual(recovered.snapshot(grant.credential, "fresh").revision, 0)

    def test_receipt_command_rolls_back_state_and_response_at_each_precommit_seam(self):
        command = ReplaceReceipt("entry", 0, 0, self.receipt())
        original = self.snapshot()
        for stage in ("after_state", "after_result", "before_commit"):
            with self.subTest(stage=stage):
                def fail(actual):
                    if actual == stage:
                        raise RuntimeError("injected")
                connection = Authority(self.path, clock=self.clock, failure_hook=fail)
                try:
                    self.assertEqual(self.assertRejected(lambda: self.apply("O", command, connection)),
                                     "storage_error")
                    self.assertEqual(self.snapshot(), original)
                    self.assertEqual(self.snapshot(authority=connection), original)
                finally:
                    connection.close()
        accepted = self.apply("O", command)
        self.assertEqual(accepted.revision, 1)
        self.assertEqual(self.apply("O", command).canonical_bytes, accepted.canonical_bytes)

    def test_uncertain_response_retry_survives_fresh_process_without_duplicate(self):
        command = ReplaceReceipt("entry", 0, 0, self.receipt())
        def fail(stage):
            if stage == "after_commit":
                raise RuntimeError("response lost")
        uncertain = Authority(self.path, clock=self.clock, failure_hook=fail)
        try:
            self.assertEqual(self.assertRejected(lambda: self.apply("O", command, uncertain)),
                             "commit_uncertain")
        finally:
            uncertain.close()
        saved = self.apply("O", command)
        self.assertEqual((saved.revision, self.snapshot().revision), (1, 1))
        source = """
import json, sys
from settletable.authority import Authority, Receipt, ReceiptItem, ReplaceReceipt
payload = json.load(sys.stdin)
authority = Authority(payload['path'], clock=lambda: 1000)
try:
    command = ReplaceReceipt('entry', 0, 0, Receipt((ReceiptItem('dish', 'Shared rice', 3, 1001),), 1001, 1001))
    result = authority.apply(payload['credential'], 'meal', command)
    snapshot = authority.snapshot(payload['credential'], 'meal')
    print(json.dumps({'result': result.canonical_bytes.hex(), 'revision': snapshot.revision}))
finally:
    authority.close()
"""
        process = subprocess.run([sys.executable, "-c", source], input=json.dumps({
            "path": str(self.path.resolve()), "credential": self.credentials["O"],
        }), text=True, capture_output=True, timeout=10)
        for credential in self.credentials.values():
            self.assertFalse(credential in process.stdout + process.stderr, "session material leaked")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout), {
            "result": saved.canonical_bytes.hex(), "revision": 1,
        })
        self.assertEqual(self.snapshot().revision, 1)

    def test_postcommit_public_error_still_reports_uncertain_not_rejection(self):
        def fail(stage):
            if stage == "after_commit":
                raise AuthorityError("injected")
        connection = Authority(self.path, clock=self.clock, failure_hook=fail)
        try:
            self.assertEqual(self.assertRejected(lambda: self.apply("O",
                ReplaceReceipt("entry", 0, 0, self.receipt()), connection)), "commit_uncertain")
        finally:
            connection.close()
        self.assertEqual(self.snapshot().revision, 1)
        self.assertEqual(self.apply("O", ReplaceReceipt("entry", 0, 0, self.receipt())).revision, 1)

    def test_bootstrap_postcommit_loss_is_not_rollback_or_reissuance(self):
        path = Path(self.temp.name) / "bootstrap-uncertain.sqlite"
        def fail(stage):
            if stage == "after_commit":
                raise AuthorityError("injected")
        connection = Authority(path, clock=self.clock, failure_hook=fail)
        people = (Participant("O", "Organizer", organizer=True),)
        try:
            self.assertEqual(self.assertRejected(lambda: connection.bootstrap("lost", people)),
                             "commit_uncertain")
        finally:
            connection.close()
        reopened = Authority(path, clock=self.clock)
        self.addCleanup(reopened.close)
        self.assertEqual(self.assertRejected(lambda: reopened.bootstrap("lost", people)), "meal_exists")

    def test_same_item_race_has_one_stale_loser_and_no_capacity_overwrite(self):
        self.apply("O", ReplaceReceipt("entry", 0, 0, self.receipt()))
        results = self.race([(person, SetOwnQuantity("claim", "dish", 2, 1, 1))
                             for person in ("A", "B")])
        accepted = [person for person, result, error in results if result is not None]
        rejected = [(person, error) for person, result, error in results if error is not None]
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(rejected), 1)
        loser, error = rejected[0]
        self.assertEqual(error, "item_revision_conflict")
        before = self.snapshot()
        self.assertEqual([(claim.participant_id, claim.quantity) for claim in before.claims],
                         [(accepted[0], Fraction(2))])
        self.assertEqual(self.assertRejected(lambda: self.apply(loser,
            SetOwnQuantity("retry-too-large", "dish", 2, self.item_revision(), 1))), "quantity_capacity")
        self.assertEqual(self.snapshot(), before)
        self.apply(loser, SetOwnQuantity("available", "dish", 1, self.item_revision(), 1))
        self.assertEqual(sum(claim.quantity for claim in self.snapshot().claims), 3)
        self.assertEqual(self.snapshot().revision, 3)

    def test_distinct_item_race_preserves_both_claims_without_global_revision(self):
        receipt = Receipt((ReceiptItem("rice", "Rice", 1, 600),
                           ReceiptItem("tea", "Tea", 1, 400)), 1000, 1000)
        self.apply("O", ReplaceReceipt("entry", 0, 0, receipt))
        results = self.race([
            ("A", SetOwnQuantity("claim", "rice", 1, 1, 1)),
            ("B", SetOwnQuantity("claim", "tea", 1, 1, 1)),
        ])
        self.assertEqual([error for person, result, error in results], [None, None])
        self.assertEqual({(claim.item_id, claim.participant_id) for claim in self.snapshot().claims},
                         {("rice", "A"), ("tea", "B")})
        self.assertEqual(self.snapshot().revision, 3)

    def test_pending_owner_cannot_displace_current_claim_and_can_release(self):
        self.apply("O", ReplaceReceipt("entry", 0, 0, self.receipt()))
        old_claim = SetOwnQuantity("claim", "dish", 3, 1, 1)
        old_result = self.apply("A", old_claim)
        self.apply("O", ReplaceReceipt("correct", 2, 1,
            Receipt((ReceiptItem("dish", "Shared rice", 1, 600),), 600, 600)))
        self.assertEqual(self.snapshot().claims[0].status, "pending")
        corrected = self.snapshot()
        self.assertEqual(self.assertRejected(lambda: self.apply("A",
            SetOwnQuantity("old-basis", "dish", 1, self.item_revision(), 1))),
                         "financial_revision_conflict")
        self.apply("O", ReviewReceipt("new-review", corrected.revision, 2, corrected.receipt_digest))
        self.apply("B", SetOwnQuantity("current", "dish", 1, self.item_revision(), 2))
        before = self.snapshot()
        self.assertEqual(self.assertRejected(lambda: self.apply("O",
            Finalize("pending-final", before.revision, 2))), "pending_claim")
        self.assertEqual(self.assertRejected(lambda: self.apply("A",
            SetOwnQuantity("reconfirm", "dish", 1, self.item_revision(), 2))), "quantity_capacity")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.apply("A", old_claim).canonical_bytes, old_result.canonical_bytes)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.assertRejected(lambda: self.apply("O",
            ReplaceReceipt("delete", before.revision, 2, Receipt()))), "claimed_item_deletion")
        self.apply("A", SetOwnQuantity("release", "dish", None, self.item_revision(), 2))
        self.assertEqual([(claim.participant_id, claim.quantity, claim.status)
                          for claim in self.snapshot().claims], [("B", Fraction(1), "confirmed")])
        self.assertNotIn("pending_claim", self.snapshot().issues)

    def test_finalize_racing_claim_has_one_coherent_serialized_basis(self):
        reviewed = self.prepare_reviewed()
        final = Finalize("final", reviewed.revision, 1)
        results = self.race([
            ("O", final),
            ("A", SetOwnQuantity("edit", "dish", 1, self.item_revision(), 1)),
        ])
        self.assertEqual(sum(result is not None for person, result, error in results), 1)
        snapshot = self.snapshot()
        errors = [error for person, result, error in results if error is not None]
        if snapshot.finalized:
            self.assertEqual(errors, ["finalized"])
        else:
            self.assertEqual(errors, ["revision_conflict"])
            self.assertEqual(snapshot.review, reviewed.review)
            self.apply("O", Finalize("fresh-final", snapshot.revision, 1))
        result = self.snapshot().calculation
        self.assertEqual({row.participant_id: row.sen for row in result.consumption},
                         {"A": 334, "B": 667, "O": 0})

    def test_finalize_racing_receipt_edit_never_mixes_review_and_claim_basis(self):
        reviewed = self.prepare_reviewed()
        correction = Receipt((ReceiptItem("dish", "Shared rice", 3, 1200),), 1200, 1200)
        results = self.race([
            ("O", Finalize("final", reviewed.revision, 1)),
            ("O", ReplaceReceipt("correct", reviewed.revision, 1, correction)),
        ])
        self.assertEqual(sum(result is not None for person, result, error in results), 1)
        snapshot = self.snapshot()
        if snapshot.finalized:
            self.assertEqual(snapshot.financial_revision, 1)
            self.assertEqual(snapshot.receipt.total_sen, 1001)
            self.assertEqual({row.participant_id: row.sen for row in snapshot.calculation.consumption},
                             {"A": 334, "B": 667, "O": 0})
        else:
            self.assertEqual(snapshot.financial_revision, 2)
            self.assertIsNone(snapshot.review)
            self.assertIsNone(snapshot.calculation)
            self.assertEqual({claim.status for claim in snapshot.claims}, {"pending"})

    def test_finalization_failure_restores_reviewed_draft_and_durable_response(self):
        reviewed = self.prepare_reviewed()
        command = Finalize("final", reviewed.revision, 1)
        for stage in ("after_state", "after_result", "before_commit"):
            with self.subTest(stage=stage):
                def fail(actual):
                    if actual == stage:
                        raise RuntimeError("injected")
                connection = Authority(self.path, clock=self.clock, failure_hook=fail)
                try:
                    self.assertEqual(self.assertRejected(lambda: self.apply("O", command, connection)),
                                     "storage_error")
                    self.assertEqual(self.snapshot(), reviewed)
                finally:
                    connection.close()
        saved = self.apply("O", command)
        reopened = Authority(self.path, clock=self.clock)
        self.addCleanup(reopened.close)
        self.assertEqual(self.snapshot(authority=reopened).calculation, saved.calculation)
        self.assertEqual(self.apply("O", command, reopened).canonical_bytes, saved.canonical_bytes)
        self.assertEqual({row.participant_id: row.sen for row in saved.calculation.consumption},
                         {"A": 334, "B": 667, "O": 0})

    def test_real_response_size_bound_failure_after_state_rolls_back(self):
        # Explicit trusted serialization fault, not a naturally maximal receipt.
        # It preserves the real 1MiB bound and exercises rollback at its failure.
        original_wire = authority_module._wire
        original_snapshot = self.snapshot()
        command = ReplaceReceipt("entry", 0, 0, self.receipt())
        activated = []
        def oversized_result(value):
            if type(value) is dict and "changed_claims" in value and "command_id" in value:
                return original_wire({**value, "injected_padding": "x" * 1_048_576})
            return original_wire(value)
        def fail(stage):
            if stage == "after_state":
                replacement = patch.object(authority_module, "_wire", oversized_result)
                replacement.start()
                activated.append(replacement)
        connection = Authority(self.path, clock=self.clock, failure_hook=fail)
        try:
            self.assertEqual(self.assertRejected(lambda: self.apply("O", command, connection)),
                             "resource_limit")
        finally:
            for replacement in reversed(activated):
                replacement.stop()
            connection.close()
        self.assertTrue(activated)
        self.assertEqual(self.snapshot(), original_snapshot)
        self.assertEqual(self.apply("O", command).revision, 1)

    def test_both_revocation_kinds_deny_old_replay_and_preserve_financial_facts(self):
        reviewed = self.prepare_reviewed()
        original_claims = reviewed.claims
        old_a = SetOwnQuantity("claim", "dish", 1, 1, 1)
        old_b = SetOwnQuantity("claim", "dish", 2, 2, 1)
        self.apply("O", RevokeSession("revoke-a", reviewed.revision, "A"))
        self.assertEqual(self.assertRejected(lambda: self.apply("A", old_a)), "invalid_session")
        self.assertEqual(self.assertRejected(lambda: self.snapshot("A")), "invalid_session")
        self.apply("O", RevokeMembership("revoke-b", self.snapshot().revision, "B"))
        self.assertEqual(self.assertRejected(lambda: self.apply("B", old_b)), "invalid_session")
        self.assertEqual(self.assertRejected(lambda: self.snapshot("B")), "invalid_session")
        snapshot = self.snapshot()
        self.assertEqual(snapshot.claims, original_claims)
        self.assertEqual({person.id for person in snapshot.participants}, {"O", "A", "B"})
        self.assertEqual(snapshot.inactive_participant_ids, ("B",))
        self.apply("O", Finalize("final", snapshot.revision, 1))
        self.assertEqual({row.participant_id: row.sen for row in self.snapshot().calculation.consumption},
                         {"A": 334, "B": 667, "O": 0})

    def test_revocation_first_denies_racing_claim_before_replay_lookup(self):
        self.apply("O", ReplaceReceipt("entry", 0, 0, self.receipt()))
        result, denied = self.ordered_pair(
            ("O", RevokeMembership("revoke", 1, "A")),
            ("A", SetOwnQuantity("claim", "dish", 1, 1, 1)))
        self.assertIsNone(result[1])
        self.assertEqual(denied, (None, "invalid_session"))
        self.assertEqual(self.snapshot().claims, ())
        self.assertEqual(self.snapshot().revision, 2)

    def test_claim_first_commits_then_stale_revoke_conflicts_before_fresh_revoke(self):
        self.apply("O", ReplaceReceipt("entry", 0, 0, self.receipt()))
        command = SetOwnQuantity("claim", "dish", 1, 1, 1)
        result, stale = self.ordered_pair(
            ("A", command), ("O", RevokeMembership("revoke", 1, "A")))
        self.assertIsNone(result[1])
        self.assertEqual(stale, (None, "revision_conflict"))
        self.assertEqual(self.apply("A", command).canonical_bytes, result[0].canonical_bytes)
        self.apply("O", RevokeMembership("fresh-revoke", self.snapshot().revision, "A"))
        self.assertEqual(self.assertRejected(lambda: self.apply("A", command)), "invalid_session")
        self.assertEqual([(claim.participant_id, claim.quantity) for claim in self.snapshot().claims],
                         [("A", Fraction(1))])

    def test_snapshot_during_uncommitted_revocation_reads_one_old_committed_basis(self):
        self.apply("O", ReplaceReceipt("entry", 0, 0, self.receipt()))
        ready = threading.Barrier(3)
        mutated = threading.Event()
        read_done = threading.Event()
        def held_revoke(stage):
            if stage == "after_state":
                mutated.set()
                if not read_done.wait(5):
                    raise RuntimeError("snapshot did not finish")
        def writer():
            connection = Authority(self.path, clock=self.clock, failure_hook=held_revoke)
            try:
                ready.wait(10)
                return self.apply("O", RevokeMembership("revoke", 1, "A"), connection)
            finally:
                connection.close()
        def reader():
            connection = Authority(self.path, clock=self.clock)
            try:
                ready.wait(10)
                if not mutated.wait(5):
                    raise RuntimeError("revocation did not reach mutation")
                try:
                    return self.snapshot("A", connection)
                finally:
                    read_done.set()
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as executor:
            write_future = executor.submit(writer)
            read_future = executor.submit(reader)
            ready.wait(10)
            snapshot = read_future.result(10)
            result = write_future.result(10)
        self.assertEqual((snapshot.revision, snapshot.financial_revision), (1, 1))
        self.assertEqual(snapshot.inactive_participant_ids, ())
        self.assertEqual(result.revision, 2)
        self.assertEqual(self.assertRejected(lambda: self.snapshot("A")), "invalid_session")

    def test_unknown_money_is_not_zero_and_unassigned_quantity_cannot_finalize(self):
        unknown = Receipt((ReceiptItem("dish", "Rice", 1, None),), None, None)
        self.apply("O", ReplaceReceipt("unknown", 0, 0, unknown))
        snapshot = self.snapshot()
        self.assertIsNone(snapshot.receipt.items[0].line_sen)
        self.assertIn("missing_amount", snapshot.issues)
        self.assertEqual(self.assertRejected(lambda: self.apply("O",
            ReviewReceipt("missing", 1, 1, snapshot.receipt_digest))), "missing_amount")
        zero = Receipt((ReceiptItem("dish", "Complimentary rice", 1, 0),), 0, 0)
        self.apply("O", ReplaceReceipt("zero", 1, 1, zero))
        snapshot = self.snapshot()
        self.apply("O", ReviewReceipt("review", 2, 2, snapshot.receipt_digest))
        self.assertEqual(self.assertRejected(lambda: self.apply("O", Finalize("unassigned", 3, 2))),
                         "incomplete_quantity")
        self.apply("A", SetOwnQuantity("assign-zero", "dish", 1, self.item_revision(), 2))
        result = self.apply("O", Finalize("zero-final", 4, 2))
        self.assertEqual({row.sen for row in result.calculation.consumption}, {0})

    def test_changed_payload_collision_cannot_rewrite_an_accepted_claim(self):
        self.apply("O", ReplaceReceipt("entry", 0, 0, self.receipt()))
        command = SetOwnQuantity("claim", "dish", 1, 1, 1)
        saved = self.apply("A", command)
        self.apply("B", SetOwnQuantity("other", "dish", 1, 2, 1))
        current = self.snapshot()
        self.assertEqual(self.assertRejected(lambda: self.apply("A",
            SetOwnQuantity("claim", "dish", 2, 1, 1))), "command_conflict")
        self.assertEqual(self.assertRejected(lambda: self.apply("A",
            SetOwnQuantity("claim", "dish", 1, 3, 1))), "command_conflict")
        self.assertEqual(self.snapshot(), current)
        replay = self.apply("A", command)
        self.assertEqual(replay.canonical_bytes, saved.canonical_bytes)
        self.assertEqual((replay.revision, self.snapshot().revision), (2, 3))


if __name__ == "__main__":
    unittest.main()
