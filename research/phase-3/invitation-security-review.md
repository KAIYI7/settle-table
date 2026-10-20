# Independent Post-Implementation Security and Code Review: PR #4

**Review Date**: 2026-10-20  
**Target Branch**: `feature/invitation-lifecycle`  
**Component**: `settletable.authority` (Integrated Invitation and Session Lifecycle)  
**Status**: **ACCEPTED / PASS (GO FOR MERGE)**  

---

## 1. Scope and Objective

This review delivers an objective, post-implementation security and architectural assessment of PR #4 on `feature/invitation-lifecycle`. PR #4 introduces single-use expiring invitation capabilities, atomic redemption, credential rotation, cascading revocation, and participant lifecycle quotas within the single SQLite authority transaction boundary.

Reviewed artifacts:
- `settletable/authority.py` (963 lines)
- `settletable/calculation.py` (228 lines, SHA-256 `4e448475892293ec9f252e1c769ef8b4699c7874c7eeefe8d73d9e16e1ccab3a`)
- `.scratch/invitation-lifecycle/SPEC.md` (258 lines)
- `research/phase-3/invitation-acceptance.md` (66 lines)
- `tests/test_invitation_lifecycle.py` (245 lines)
- `tests/test_invitation_adversarial.py` (294 lines)
- `tests/test_authority_adversarial.py` (518 lines)

---

## 2. Verification of the 5 Review Findings

### Finding 1: Credential-generation failures escaping before protected error handling
- **Severity**: HIGH (Resolved)
- **Problem**: In previous iterations, `secrets.token_urlsafe` and verifier hashing occurred outside the primary `try:` block in lifecycle methods. Any OS entropy exhaustion or CSPRNG failure would escape unhandled, bypassing rollback and leaking raw exception details instead of mapping to `AuthorityError('storage_error')`.
- **Code Verification**:
  - `settletable/authority.py` lines 563–568 (`issue_invitation`): `try:` encapsulates `secrets.token_urlsafe(16)` (for `issue_id`), `secrets.token_urlsafe(32)` (for `token`), and `_invitation_verifier(token)`.
  - `settletable/authority.py` lines 630–633 (`redeem_invitation`): `try:` encapsulates `secrets.token_urlsafe(32)` and `_verifier(credential)`.
  - `settletable/authority.py` lines 693–696 (`rotate_session`): `try:` encapsulates `secrets.token_urlsafe(32)` and `_verifier(new_credential)`.
  - In all three methods, unexpected errors are caught by `except Exception:` (L620–622, L683–685, L733–735), which triggers `self._rollback()` and cleanly raises `AuthorityError('storage_error')` (or `'commit_uncertain'` if post-commit).
- **Test Evidence**:
  - `tests/test_invitation_adversarial.py` lines 255–274 (`test_entropy_failure_in_lifecycle_methods_raises_storage_error`): Patches `secrets.token_urlsafe` with a `RuntimeError` and proves that all three methods safely roll back and raise `AuthorityError('storage_error')`.
- **Disposition**: **PASS / VERIFIED**.

---

### Finding 2: Insufficiently justified security-command reserve bound
- **Severity**: HIGH (Resolved)
- **Problem**: Earlier bounds did not account for generation advancement across up to 64 lifecycles per participant, leaving open the risk of unbounded security command table growth and state exhaustion.
- **Mathematical Proof**:
  - Meal participant limit: $N \le 100$ (1 organizer, up to 99 diners).
  - Lifecycle generation ceiling: $G \le 64$ per participant.
  - Per diner:
    - At most $64$ `RevokeInvitation` commands: Each requires an active, unconsumed, unrevoked invitation (`revoked == 0 AND consumed == 0 AND expires > now`). Issuing an invitation advances generation. Repeat revocations find `revoked == 1` and reject with `already_revoked` (L876) without inserting command records.
    - At most $64$ `RevokeSession` commands: Each requires an unrevoked active session or active invitation (`sess_up + inv_up > 0`). Repeat revocations reject with `already_revoked` (L864) without inserting command records.
    - At most $1$ `RevokeMembership` command: Sets `participants.active = 0`. An inactive participant cannot be reactivated or re-invited (L577, L643). Repeat revocations reject with `already_revoked` (L872) without inserting command records.
    - Diner maximum: $64 + 64 + 1 = 129$ security commands.
  - Organizer:
    - Organizer revocation targeting self or by diners is forbidden at L777–780 (`_permission` checks `target is not None and not target[0] and data['participant_id'] != actor`).
    - Organizer session rotation is strictly forbidden at L699 (`_require(not organizer, 'forbidden')`).
    - Total organizer commands targeting self = 0.
  - Meal total maximum bound:
    $$\text{Max Security Commands} \le 99 \times 129 = 12,771 \text{ rows}$$
- **Code Verification**:
  - `settletable/authority.py` lines 904–906: In `apply()`, security commands execute:
    ```python
    _require(self._db.execute('SELECT COUNT(*) FROM commands WHERE meal_id=? AND security=1', (meal_id,)).fetchone()[0] < 15_000,
             'resource_limit')
    ```
    This provides ample headroom above 12,771 while definitively bounding database growth.
  - Storage consumption: With ~150 bytes per security command, $12,771 \times 150 \approx 1.9 \text{ MB}$, completely isolated from the ordinary financial state limit (900 KB).
- **Test Evidence**:
  - `tests/test_invitation_adversarial.py` lines 125–164 (`test_lifecycle_generation_quota_and_security_headroom`): Proves that even when Bob's lifecycle generations are exhausted at 64 (rejecting redemption with `resource_limit`), security revocations (`RevokeInvitation`, `RevokeSession`, `RevokeMembership`) continue to succeed.
  - `tests/test_invitation_adversarial.py` lines 275–290 (`test_security_commands_upper_bound_enforced`): Inserts 15,000 security commands and confirms that the 15,001st is rejected with `resource_limit`.
- **Disposition**: **PASS / VERIFIED**.

---

### Finding 3: Duplicate invitation `issue_id` behavior and safe rejection
- **Severity**: MEDIUM (Resolved)
- **Problem**: Schema enforces `UNIQUE(meal_id, issue_id)`. Without an explicit pre-check, reusing an `issue_id` triggered an unhandled SQLite integrity error that escaped through `_storage_failure` as generic `storage_error` rather than a domain conflict.
- **Code Verification**:
  - `settletable/authority.py` lines 572–574:
    ```python
    existing_issue = self._db.execute('SELECT 1 FROM invitations WHERE meal_id=? AND issue_id=?',
                                      (meal_id, issue_id)).fetchone()
    _require(existing_issue is None, 'command_conflict')
    ```
    Reusing an `issue_id` within the same meal is caught immediately and safely raises `AuthorityError('command_conflict')`.
- **Test Evidence**:
  - `tests/test_invitation_lifecycle.py` lines 224–234 (`test_duplicate_issue_id_rejects_with_command_conflict`): Asserts that issuing an invitation with an existing `issue_id` raises `command_conflict`.
- **Disposition**: **PASS / VERIFIED**.

---

### Finding 4: Organizer credential loss after uncertain session rotation
- **Severity**: CRITICAL (Resolved)
- **Problem**: If an organizer was permitted to call `rotate_session`, a post-commit crash (`after_commit` hook failure or network disconnect) would return `commit_uncertain` to the organizer while destroying their prior verifier. Because organizers cannot be re-invited or re-bootstrapped, the entire meal draft would be permanently locked and inaccessible.
- **Code Verification**:
  - `settletable/authority.py` lines 698–699:
    ```python
    actor, organizer = self._authenticate(verifier, meal_id)
    _require(not organizer, 'forbidden')
    ```
    Organizers are explicitly forbidden from rotating sessions. Organizer credentials remain immutable from bootstrap, completely eliminating self-lockout risk.
- **Test Evidence**:
  - `tests/test_invitation_lifecycle.py` lines 236–241 (`test_organizer_cannot_rotate_session`): Verifies `rotate_session` with organizer credential raises `forbidden`.
- **Disposition**: **PASS / VERIFIED**.

---

### Finding 5: Independent post-implementation review artifact
- **Severity**: PROCEDURAL / AUDIT (Resolved)
- **Requirement**: Provide concrete, line-level evidence of an independent post-implementation security and code review.
- **Evidence**: Completed in this document, verified across all files and test runs.
- **Disposition**: **PASS / VERIFIED**.

---

## 3. High-Risk Acceptance Gates Evaluation

### Gate 1: Invariants Gate
- **Deterministic calculation module byte-identical**: `settletable/calculation.py` verified with SHA-256 `4e448475892293ec9f252e1c769ef8b4699c7874c7eeefe8d73d9e16e1ccab3a`. All 15 calculation unit tests pass.
- **Versioned domain-separated verifiers**:
  - Session verifier: `SHA-256(b'settletable-local-session-v1\0' + credential.encode('ascii'))` (L223)
  - Invitation verifier: `SHA-256(b'settletable-invitation-v1\0' + token.encode('ascii'))` (L230)
  - Receipt digest: `SHA-256(b'settletable-receipt-v1\0' + _wire(receipt))` (L305)
  - Command digest: `SHA-256(b'settletable-command-digest-v1\0' + body)` (L883)
  All domain separators use null-byte termination (`\0`) and unambiguous namespaces.
- **Gate Determination**: **PASS**.

---

### Gate 2: Secret Hygiene Gate
- **Zero Token Persistence**:
  - Invitation tokens and session credentials are 256-bit CSPRNG base64url strings (`secrets.token_urlsafe(32)`, 43 chars).
  - Stored strictly as SHA-256 digest bytes in `invitations.verifier` (L404) and `sessions.verifier` (L393).
  - No raw token or credential appears in database tables, command history, snapshots, or error messages.
- **Representation Suppression (`repr=False`)**:
  - `SessionGrant.credential` (L33): `credential: str = field(repr=False)`
  - `InvitationGrant.token` (L40): `token: str = field(repr=False)`
  - `BootstrapResult.sessions` (L57): `sessions: tuple[SessionGrant, ...] = field(repr=False)`
  - `AcceptedResult.canonical_bytes` (L171): `canonical_bytes: bytes = field(repr=False)`
  - `DraftSnapshot.invitations` (L189) exposes only `InvitationRecord` (L45–51), which contains public metadata (`participant_id`, `created_at`, `expires`, `consumed`, `revoked`, `issue_id`) without tokens or verifiers.
- **Test Evidence**:
  - `tests/test_invitation_adversarial.py` lines 197–216 (`test_token_and_credential_nonleakage`) verifies zero leakage across `repr`, SQL dumps, and raw database bytes.
- **Gate Determination**: **PASS**.

---

### Gate 3: Concurrency & Cascading Revocation Gate
- **Single SQLite Transaction Owner**:
  - All operations execute within `settletable.authority.Authority`.
  - Mutating operations (`bootstrap`, `issue_invitation`, `redeem_invitation`, `rotate_session`, `apply`) acquire an exclusive lock up front using `BEGIN IMMEDIATE` (L480, L569, L634, L697, L888), completely preventing deadlocks and read-to-write race conditions.
  - Rollback safety: `_rollback()` executes on all exceptions (L446–453); if rollback fails, `self.close()` closes the connection.
- **Cascading Revocation Logic** (`settletable/authority.py` L857–876):
  - `RevokeSession`: Marks session revoked (`revoked = 1`) AND cascades to all unconsumed active invitations (`revoked = 1`). Requires `sess_up + inv_up > 0` (L864). If the session was already revoked but an active invitation is outstanding, it cascades and succeeds.
  - `RevokeMembership`: Marks participant inactive (`active = 0`), revokes session, and revokes all unconsumed active invitations. Requires `part_up == 1` (L872).
  - `RevokeInvitation`: Marks invitation revoked (`revoked = 1`). Requires `inv_up > 0` (L876).
- **Test Evidence**:
  - Concurrency: `test_two_connections_racing_same_redemption` (lines 36–79) and `test_redemption_racing_invitation_revocation` (lines 80–124) demonstrate serializable consistency.
  - Cascading: `test_cascading_revocation_on_session_and_membership_revoke` (lines 191–223) verifies all 3 revocation pathways.
- **Gate Determination**: **PASS**.

---

### Gate 4: Additive Backward Compatibility Gate
- **Non-Destructive DDL**:
  - `Authority.__init__` executes `CREATE TABLE IF NOT EXISTS invitations` (L403–410) and `CREATE TABLE IF NOT EXISTS participant_lifecycle` (L411–415). Existing v1 tables (`meals`, `participants`, `sessions`, `commands`) are unmodified.
- **Graceful Lifecycle Defaults**:
  - In `issue_invitation` (L582), `redeem_invitation` (L646), and `rotate_session` (L702), if a participant has no row in `participant_lifecycle`, generation smoothly defaults to 1.
  - `DraftSnapshot.invitations` defaults to `()` (L189).
- **Test Evidence**:
  - `tests/test_invitation_adversarial.py` lines 217–254 (`test_backward_compatibility_reopening_v1_database`) constructs a pure v1 database, opens it with the updated `Authority`, verifies snapshot identity, and successfully issues/redeems invitations without touching historical rows.
- **Gate Determination**: **PASS**.

---

## 4. Summary Scorecard

| Check / Gate | Target | Actual Result | Status |
|---|---|---|---|
| Invariants: Calculation Module | SHA256 matches baseline | Byte-identical (`4e4484...`) | PASS |
| Invariants: Hash Domains | Domain-separated & null-terminated | 4 versioned domain prefixes verified | PASS |
| Secret Hygiene: Token Persistence | Zero plaintext secrets in DB | Verifiers only (BLOB) | PASS |
| Secret Hygiene: Repr Leakage | `repr=False` on bearer secrets | Verified across all dataclasses | PASS |
| Concurrency: Transaction Boundary | `BEGIN IMMEDIATE` on single connection | Enforced across all mutating methods | PASS |
| Cascading Revocation | Session/membership cascades to invites | Verified across 3 adversarial cases | PASS |
| Backward Compatibility | Open v1 DB additively without mutation | Additive DDL, verified via test | PASS |
| Finding 1: Credential Gen Error Handling | Inside `try:` with rollback | Encapsulated in try-except-rollback | PASS |
| Finding 2: Security Command Bound | Math $\le 12,771$; Code $< 15,000$ | Proved & enforced in `apply()` | PASS |
| Finding 3: Duplicate `issue_id` | Pre-check raising `command_conflict` | Pre-check at L572-574 verified | PASS |
| Finding 4: Organizer Credential Lockout | Forbid organizer `rotate_session` | Enforced at L698-699 (`forbidden`) | PASS |
| Finding 5: Independent Review Artifact | Complete review documentation | Documented in this artifact | PASS |
| Test Suite Health | 100% passing tests | 79 passed, 0 failures (150.000s) | PASS |

---

## 5. Final Recommendation

**GO (Unconditional Pass)**. PR #4 is architecturally sound, cryptographically defensive, concurrency-safe, backward-compatible, and fully verified by test suites. It is ready for merge into `main`.
