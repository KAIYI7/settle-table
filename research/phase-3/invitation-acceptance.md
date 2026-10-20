# Bounded invitation and session lifecycle implementation acceptance

Started 2026-10-20 on `feature/invitation-lifecycle`, from main `7253cf9e2888802d00fb037f2a1fbcd517868e73`.  
**Orchestrator decision: PASS / accepted for the bounded invitation and session lifecycle slice.**  
Internal acceptance on the feature branch pending PR publication and review.

## Scope and Test Seams

Implement the [reviewed specification](../../.scratch/invitation-lifecycle/SPEC.md), without broadening it.
The public test seams are:
- `Authority.issue_invitation(organizer_credential, meal_id, participant_id, *, invite_ttl=86400, issue_id=None)`
- `Authority.redeem_invitation(invitation_token, meal_id, *, session_ttl=3600)`
- `Authority.rotate_session(credential, meal_id, *, session_ttl=3600)`
- `Authority.apply(organizer_credential, meal_id, RevokeInvitation(command_id, expected_revision, participant_id))`
- Cascading revocation in `RevokeSession` and `RevokeMembership`
- Deterministic, secret-free metadata in `DraftSnapshot.invitations`
- Additive SQLite schema: `invitations` and `participant_lifecycle`

The accepted calculator module remains byte-identical to baseline SHA-256 `4e448475892293ec9f252e1c769ef8b4699c7874c7eeefe8d73d9e16e1ccab3a`. All 15 calculation tests continue to pass. All 60 original tests continue to pass. No HTTP, UI, unauthenticated participant creation, organizer handover, settlements, OCR, or Notion belongs to this slice.

## Material Gates

| Gate | Disposition / Verified Evidence |
|---|---|
| Single authority transaction owner | PASS — All issuance, redemption, session rotation, and revocations execute inside `settletable.authority.Authority` under `BEGIN IMMEDIATE` on the single SQLite connection. |
| Zero credential persistence & domain separation | PASS — CSPRNG 32-byte tokens (`token_urlsafe(32)`) with `repr=False` in dataclasses. SQL dumps, raw database bytes, snapshots, results, and logs contain no raw bearer material. Strict SHA-256 domain separation: `settletable-invitation-v1\0` and `settletable-local-session-v1\0`. |
| Single-use, expiry, and atomic rotation | PASS — Redemption marks invitation consumed once, invalidates prior session atomically, and binds new session to the intended member. Trusted clock exclusive upper bound checked. Retries of consumed tokens reject with `invalid_invitation`. |
| Concurrency correctness | PASS — Two connections racing the same redemption: exactly one commits, other receives `invalid_invitation` (or lock wait `busy`); no duplicate sessions or split state. Redemption racing revocation in both orders yields consistent serialized state. |
| Cascading revocation | PASS — `RevokeSession` and `RevokeMembership` invalidate outstanding active invitations for that participant. Revoking an inactive session with an active invitation still cascades to the invitation and does not raise `already_revoked`. |
| Resource limits and security reserve | PASS — 64 lifecycle generations per participant enforced (`resource_limit`). Security revocations remain strictly available even when ordinary 10,000 quota or lifecycle quota is exhausted. |
| Safe acknowledgment & retry | PASS — Lost grant commits are explicitly uncertain (`commit_uncertain`). Reissuance is authorized by organizer without resetting financial facts or reviving inactive members. |
| Additive backward compatibility | PASS — Reopening existing v1 SQLite databases creates new tables via `CREATE TABLE IF NOT EXISTS` without modifying existing rows. Historical snapshots and commands replay byte-identically. |

## Resolved Findings from Independent Review

1. **Finding 1 (Revision conflict on rotation):** `rotate_session` does not increment `meals.revision`, preventing false concurrency conflicts on financial drafts and eliminating 900 KB write amplification.
2. **Finding 2 (Cascading revocation race):** `RevokeSession` revokes both sessions and active invitations; requires `session_updated + invite_updated > 0` before raising `already_revoked`.
3. **Finding 3 (Active invitation definition):** Standardized across issuance, revocation, and redemption as `revoked == 0 AND consumed == 0 AND expires > now`.
4. **Finding 4 (Schema unique constraint):** Added `UNIQUE(meal_id, issue_id)` to `invitations` table.
5. **Finding 5 (Snapshot ordering):** Specified and verified `ORDER BY participant_id, created_at, issue_id` for deterministic comparisons.
6. **Finding 6 (Hooks & uncertainty):** Added `self._hook('before_commit')` and `self._hook('after_commit')`, catching commit exceptions and raising `commit_uncertain` on committed transactions.
7. **Finding 7 (Security reserve math):** Rigorously proved max security commands $\le 12,771$ rows for $N \le 100$ and $G = 64$ ($99 \text{ diners} \times (64 \text{ RevokeInvitation} + 64 \text{ RevokeSession} + 1 \text{ RevokeMembership})$); enforced via defensive code check `< 15,000` for `security = 1` commands.
8. **Finding 8 (Input validation):** Strict 43-character base64url validation for invitation tokens raises `invalid_invitation` before hashing or database work.

## Post-Implementation Review Findings & Final Resolutions (PR #4)

1. **Credential-generation failures escaping before protected error handling**:
   - *Evidence / Root Cause*: In `issue_invitation`, `redeem_invitation`, and `rotate_session`, token and credential generation calls (`secrets.token_urlsafe`) and hashing occurred outside the `try:` block. If CSPRNG entropy failed or OS errors arose, unhandled exceptions escaped instead of mapping to `AuthorityError('storage_error')` with rollback.
   - *Resolution*: Moved all token/credential generation and verifier computation inside the `try:` block across all three methods. Verified with fault-injection unit tests using `patch('secrets.token_urlsafe')`.

2. **Insufficiently justified security-command reserve bound**:
   - *Evidence / Root Cause*: The initial combinatorial bound assumed at most 1 `RevokeSession` per diner. However, across up to $G = 64$ generations, a diner could have multiple sessions/invitations revoked upon reissuance.
   - *Resolution*: Proved the exact theoretical combinatorial bound: each diner can have at most 64 `RevokeInvitation`, 64 `RevokeSession`, and 1 `RevokeMembership` ($64 + 64 + 1 = 129$); organizer cannot be targeted ($0$). For 99 diners, $99 \times 129 = 12,771$ commands maximum. Enforced in `settletable.authority.Authority.apply()` with defensive limit `SELECT COUNT(*) FROM commands WHERE meal_id=? AND security=1 < 15_000`, raising `resource_limit` if exceeded. Verified via adversarial test `test_security_commands_upper_bound_enforced`.

3. **Duplicate invitation `issue_id` behavior and safe rejection**:
   - *Evidence / Root Cause*: The schema enforced `UNIQUE(meal_id, issue_id)`. Reusing an `issue_id` caused SQLite constraint failure (`sqlite3.IntegrityError`), escaping through `_storage_failure` as internal `storage_error` rather than a domain error.
   - *Resolution*: Added pre-check in `issue_invitation`: `SELECT 1 FROM invitations WHERE meal_id=? AND issue_id=?`, cleanly raising `AuthorityError('command_conflict')` before attempting insert. Verified via unit test `test_duplicate_issue_id_rejects_with_command_conflict`.

4. **Missing evidence of an independent post-implementation source/security review**:
   - *Evidence / Root Cause*: PR #4 lacked a dedicated independent post-implementation review artifact evaluating the final reviewed source code against security and lifecycle gates.
   - *Resolution*: Executed an independent source and security review covering the full implementation, adversarial tests, schema, and error handling, recorded in `research/phase-3/invitation-security-review.md`.

5. **Organizer credential loss after uncertain session rotation**:
   - *Evidence / Root Cause*: `rotate_session` allowed any caller, including the organizer. If an organizer rotated their session and the commit succeeded but `after_commit` failed, the organizer received `commit_uncertain` while the previous credential was destroyed. Because organizers cannot be re-invited or re-bootstrapped, the meal was permanently locked.
   - *Resolution*: Explicitly restricted `rotate_session` to non-organizers via `_require(not organizer, 'forbidden')`. Organizer credentials remain fixed at bootstrap. Verified via unit test `test_organizer_cannot_rotate_session`.
