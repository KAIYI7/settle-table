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
7. **Finding 7 (Security reserve math):** Bounded max security commands to $\le 6,534$ rows for $N \le 100$ and $G = 64$.
8. **Finding 8 (Input validation):** Strict 43-character base64url validation for invitation tokens raises `invalid_invitation` before hashing or database work.
