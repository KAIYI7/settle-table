# Integrated invitation and session lifecycle — bounded specification

Status: **Specification accepted; independent review findings incorporated.**
Location: `.scratch/invitation-lifecycle/SPEC.md`
Context: [Next slice plan](../../research/phase-3/next-slice-plan.md), [Transport identity challenge](../../research/phase-3/transport-identity-challenge.md), [Accepted authority interface](../../docs/authority-interface.md), [Governance](../../docs/agents/governance.md).

## 1. Problem and Objective

The accepted `settletable.authority` (v1) provides atomic command replay, participant-attributed claims, organizer review, and deterministic finalization for a fixed group of participants provisioned locally during bootstrap. However, in an actual dining scenario:
1. Diners are not physically present on the organizer's terminal at bootstrap to receive credentials; they must be invited over a private link.
2. Diners need single-use, expiring capabilities (invitations) bound to their declared meal membership.
3. Once redeemed, diners require secure session issuance and atomic session rotation without losing their participant-attributed claims or financial history.
4. If a session or membership is revoked, or if an invitation is revoked, outstanding invitations must not allow unauthorized re-entry or capability resurrection.
5. Lost network responses during issue, redemption, or rotation must not mint duplicate sessions, leak credentials into durable logs/history, or leave state in an undefined limbo.

This increment delivers an integrated invitation and session lifecycle within the existing SQLite authority transaction owner, preserving all financial invariants, deterministic calculations, versioned hash domains, and backward compatibility.

## 2. Explicit Inclusions and Exclusions

### In Scope
- Organizer-authorized invitation issuance for existing active diner participants.
- Single-use, expiring invitation tokens with domain-separated verifiers.
- At most one active invitation per target participant.
- Atomic invitation redemption within the authority's SQLite transaction, binding a fresh session to the intended participant and invalidating any prior session.
- Secure participant-initiated session rotation without false meal revision conflicts.
- Organizer revocation of invitations (`RevokeInvitation` command in `apply`).
- Cascading revocation: revoking a session or membership automatically invalidates outstanding invitations for that participant.
- Finite lifecycle quota: maximum 64 lifecycle generations per participant; ordinary and lifecycle exhaustion preserves the security revocation reserve.
- Lost response and retry safety: no plaintext or recoverably encrypted credentials stored; non-recoverable one-time grants are explicitly uncertain upon lost response; idempotency checks reject duplicate issuance or re-redemption.
- Public status visibility: `DraftSnapshot` includes public, secret-free invitation status metadata deterministically ordered.
- Backward compatibility: opening an existing v1 SQLite database is additive, non-destructive, and preserves historical replay and calculation byte-identically.

### Excluded
- HTTP endpoints, network listeners, WebSockets, reverse proxy adapters (deferred to the next separate increment).
- HTML/browser UI, styling, client-side JavaScript.
- Anonymous self-enrollment or dynamic creation of new participants after bootstrap.
- Organizer handover or transfer of the organizer role.
- Account recovery, federated identity, passwords, OAuth, email sending.
- OCR, receipt image capture/storage, Notion integration.
- Public deployment or cloud hosting.

## 3. Architecture and Trust Model

1. **Single Transaction Owner**: All invitation issuance, redemption, session rotation, revocation, and audit records belong strictly inside `settletable.authority.Authority`. No external store, sidecar DB, or check-then-apply framework is permitted.
2. **Possession vs Identity**: Possession of an invitation token proves control of that capability, not real-world biometric identity. The token is cryptographically bound to a specific pre-declared diner `participant_id` in a specific `meal_id`.
3. **No Credential Persistence**:
   - Plaintext invitation tokens and session credentials exist only in transient memory during generation and are returned once to the caller in frozen slotted dataclasses (`InvitationGrant`, `SessionGrant`).
   - Their string representation (`repr`) suppresses the secret field (`repr=False`).
   - SQLite stores only domain-separated SHA-256 verifiers.
   - Commands, snapshots, accepted results, canonical wire JSON, exceptions, and test diagnostics NEVER contain raw tokens or credentials.
4. **Domain Separation**:
   - Existing session verifier: `SHA-256(b'settletable-local-session-v1\0' + credential.encode('ascii'))` (preserved exactly).
   - New invitation verifier: `SHA-256(b'settletable-invitation-v1\0' + token.encode('ascii'))`.
   - Existing command digest: `SHA-256(b'settletable-command-digest-v1\0' + body)` (preserved exactly).
   - Existing receipt digest: `SHA-256(b'settletable-receipt-v1\0' + wire)` (preserved exactly).

## 4. Database Schema and Compatibility

Existing tables (`meals`, `participants`, `sessions`, `commands`) remain unchanged.

Additive tables created via `CREATE TABLE IF NOT EXISTS`:
```sql
CREATE TABLE IF NOT EXISTS invitations (
    verifier BLOB PRIMARY KEY,
    meal_id TEXT NOT NULL,
    participant_id TEXT NOT NULL,
    issuer_id TEXT NOT NULL,
    issue_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires REAL NOT NULL,
    consumed INTEGER NOT NULL DEFAULT 0,
    revoked INTEGER NOT NULL DEFAULT 0,
    generation INTEGER NOT NULL,
    UNIQUE(meal_id, issue_id),
    FOREIGN KEY(meal_id, participant_id) REFERENCES participants(meal_id, id),
    FOREIGN KEY(meal_id, issuer_id) REFERENCES participants(meal_id, id)
);

CREATE TABLE IF NOT EXISTS participant_lifecycle (
    meal_id TEXT NOT NULL,
    participant_id TEXT NOT NULL,
    generation INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY(meal_id, participant_id),
    FOREIGN KEY(meal_id, participant_id) REFERENCES participants(meal_id, id)
);
```

### Compatibility Invariant:
When an existing v1 SQLite database is opened by `Authority(path)`, the `CREATE TABLE IF NOT EXISTS` statements ensure the new tables are created without modifying existing rows. Existing participants default to lifecycle generation 1 when queried if not present in `participant_lifecycle`.

## 5. Public Types and Interfaces

```python
@dataclass(frozen=True, slots=True)
class InvitationGrant:
    meal_id: str
    participant_id: str
    token: str = field(repr=False)
    expires: float | int

@dataclass(frozen=True, slots=True)
class InvitationRecord:
    participant_id: str
    created_at: float | int
    expires: float | int
    consumed: bool
    revoked: bool
    issue_id: str

@dataclass(frozen=True, slots=True)
class RevokeInvitation:
    command_id: str
    expected_revision: int
    participant_id: str
```

### Methods on `Authority`:
1. `issue_invitation(organizer_credential: str, meal_id: str, participant_id: str, *, invite_ttl: int = 86400, issue_id: str | None = None) -> InvitationGrant`
2. `redeem_invitation(invitation_token: str, meal_id: str, *, session_ttl: int = 3600) -> SessionGrant`
3. `rotate_session(credential: str, meal_id: str, *, session_ttl: int = 3600) -> SessionGrant`
4. `apply(credential: str, meal_id: str, command: ...)`:
   Supports new command `RevokeInvitation(command_id, expected_revision, participant_id)`.
5. `snapshot(credential: str, meal_id: str) -> DraftSnapshot`:
   Updated `DraftSnapshot` includes `invitations: tuple[InvitationRecord, ...] = ()`.

## 6. Detailed Operation Rules

### 6.1 `issue_invitation`
- **Validation**:
  - `organizer_credential` valid 43-char base64url string.
  - `meal_id` and `participant_id` pass `_id`.
  - `invite_ttl` integer, `1 <= invite_ttl <= 604800` (up to 7 days).
  - `issue_id`: if provided, passes `_id`; if omitted, generated via `_id` grammar.
- **Authorization & State**:
  - `BEGIN IMMEDIATE`
  - Token and `issue_id` generation occur inside protected error handling. CSPRNG entropy failure raises `AuthorityError('storage_error')`.
  - Caller must be the active organizer (`organizer == 1`, `active == 1`).
  - Target `participant_id` must be an active diner (`organizer == 0`, `active == 1`).
  - Idempotency & Conflict Check: `SELECT 1 FROM invitations WHERE meal_id=? AND issue_id=?`. If found, raises `AuthorityError('command_conflict')`.
  - Target's lifecycle generation must be `< 64`.
  - Active invitation check: an invitation is active if and only if `revoked == 0 AND consumed == 0 AND expires > now`. If one exists for `(meal_id, participant_id)`, raise `AuthorityError('active_invitation_exists')`.
- **Action**:
  - Generate 32 bytes random base64url token (43 chars).
  - Compute verifier with `settletable-invitation-v1`.
  - Increment participant generation in `participant_lifecycle`.
  - Insert row into `invitations`.
  - Monotonically increment `meals.revision` (updating public snapshot).
  - Call `self._hook('before_commit')`.
  - Commit transaction.
  - Call `self._hook('after_commit')`.
  - Catch commit exceptions/uncertainty and raise `AuthorityError('commit_uncertain')` if committed.
  - Return `InvitationGrant(meal_id, participant_id, token, expires)`.

### 6.2 `redeem_invitation`
- **Validation**:
  - `invitation_token` valid 43-char base64url string. If invalid type, length, or alphabet, raise `AuthorityError('invalid_invitation')` before hashing or database work.
  - `meal_id` passes `_id`.
  - `session_ttl` integer, `1 <= session_ttl <= 86400`.
- **Authorization & State**:
  - `BEGIN IMMEDIATE`
  - Credential generation occurs inside protected error handling. CSPRNG entropy failure raises `AuthorityError('storage_error')`.
  - Compute verifier with `settletable-invitation-v1`.
  - Lookup invitation by `verifier` and `meal_id`.
  - If not found, expired (`expires <= now`), consumed (`consumed == 1`), or revoked (`revoked == 1`): raise `AuthorityError('invalid_invitation')`.
  - Check target participant: must be `active == 1` and `organizer == 0`.
  - Target's lifecycle generation must be `< 64`.
- **Action**:
  - Mark invitation `consumed = 1`.
  - Increment participant generation in `participant_lifecycle`.
  - Generate fresh session credential (43 chars base64url).
  - Compute session verifier `settletable-local-session-v1`.
  - Update or insert in `sessions`: set new verifier, new `expires = now + session_ttl`, `revoked = 0`.
  - Monotonically increment `meals.revision` (updating public snapshot).
  - Call `self._hook('before_commit')`.
  - Commit transaction.
  - Call `self._hook('after_commit')`.
  - Catch commit exceptions/uncertainty and raise `AuthorityError('commit_uncertain')` if committed.
  - Return `SessionGrant(participant_id, credential)`.

### 6.3 `rotate_session`
- **Validation**:
  - `credential` valid 43-char base64url string (`_verifier` check).
  - `session_ttl` integer, `1 <= session_ttl <= 86400`.
- **Authorization & State**:
  - `BEGIN IMMEDIATE`
  - Credential generation occurs inside protected error handling. CSPRNG entropy failure raises `AuthorityError('storage_error')`.
  - Authenticate caller via `_authenticate(verifier, meal_id)` (checks active, unrevoked, unexpired).
  - Caller must be an active diner (`organizer == 0`). Calling with organizer credential raises `AuthorityError('forbidden')`, eliminating irreversible organizer credential loss/lockout on uncertain rotation.
  - Participant lifecycle generation must be `< 64`.
- **Action**:
  - Increment participant generation in `participant_lifecycle`.
  - Generate fresh session credential.
  - Compute session verifier `settletable-local-session-v1`.
  - Update `sessions` row for `(meal_id, participant_id)` with new verifier, new `expires = now + session_ttl`. The previous verifier is atomically destroyed.
  - **No `meals.revision` increment**: Session rotation is private to the participant and does not change the meal draft or public snapshot. This avoids false concurrency conflicts on financial drafts and unnecessary 900 KB write amplification.
  - Call `self._hook('before_commit')`.
  - Commit transaction.
  - Call `self._hook('after_commit')`.
  - Catch commit exceptions/uncertainty and raise `AuthorityError('commit_uncertain')` if committed.
  - Return `SessionGrant(participant_id, credential)`.

### 6.4 Revocation and Cascading
1. `RevokeInvitation(command_id, expected_revision, participant_id)`:
   - Organizer only.
   - Security command (`security = 1` in `commands`).
   - Requires active invitation (`revoked == 0 AND consumed == 0 AND expires > now`).
   - Sets `invitations.revoked = 1`.
   - If no active invitation exists: raises `AuthorityError('already_revoked')` without inserting a command record.
2. `RevokeSession(command_id, expected_revision, participant_id)`:
   - Organizer only.
   - Security command (`security = 1` in `commands`).
   - Updates `sessions SET revoked=1 WHERE meal_id=? AND participant_id=? AND revoked=0`.
   - **Cascades**: Also updates `invitations SET revoked=1 WHERE meal_id=? AND participant_id=? AND revoked=0 AND consumed=0 AND expires > now`.
   - Requires `session_updated + invite_updated > 0`; if both are 0, raises `AuthorityError('already_revoked')` without inserting a command record. This ensures a revoked session cannot be bypassed by an unrevoked active invitation.
3. `RevokeMembership(command_id, expected_revision, participant_id)`:
   - Organizer only.
   - Security command (`security = 1` in `commands`).
   - Sets `participants.active = 0` and `sessions.revoked = 1`.
   - **Cascades**: Sets `invitations.revoked = 1` for all unconsumed, unrevoked active invitations for that participant.
   - If participant was already inactive: raises `AuthorityError('already_revoked')` without inserting a command record.

### 6.5 Resource Limits and Security Reserve
- Quota: Participant lifecycle operations (`issue_invitation`, `redeem_invitation`, `rotate_session`) are capped at generation `64`. Attempting to advance past 64 raises `AuthorityError('resource_limit')`.
- Headroom: Ordinary financial commands are capped at 10,000 (`security == 0`).
- Security commands (`RevokeSession`, `RevokeMembership`, `RevokeInvitation`) remain executable even if ordinary 10,000 quota or lifecycle quota is exhausted.
- **Rigorously Justified Mathematical Bound on Security Commands**:
  - Meal participant limit: $N \le 100$ (1 organizer and up to 99 diners).
  - Lifecycle generation ceiling: $G \le 64$ per participant.
  - Per diner:
    - At most $64$ `RevokeInvitation` calls: each requires an active unconsumed invitation (`revoked == 0 AND consumed == 0 AND expires > now`), which required an `issue_invitation` advancing generation. Repeat revocations find `revoked == 1` and reject with `already_revoked`.
    - At most $64$ `RevokeSession` calls: each requires an unrevoked active session or active invitation (`sess_up + inv_up > 0`), which required a lifecycle advancement (issuance, redemption, or rotation). Repeat revocations with no active session or invitation reject with `already_revoked`.
    - At most $1$ `RevokeMembership` call: sets `participants.active = 0`. An inactive participant can never be re-activated, invited, or redeemed. Repeat revocations find `active == 0` and reject with `already_revoked`.
    - Maximum security commands per diner: $64 + 64 + 1 = 129$.
  - Organizer:
    - Calling `RevokeSession`, `RevokeMembership`, or `RevokeInvitation` targeting the organizer is strictly forbidden (`_permission` requires `not target[0] and data['participant_id'] != actor`).
    - Organizer session rotation is forbidden (`_require(not organizer, 'forbidden')`).
    - Organizer security commands targeting self: 0.
  - Theoretical maximum security commands across full meal lifecycle:
    $$\text{Max Security Commands} \le 99 \times (64 + 64 + 1) = 99 \times 129 = 12,771 \text{ rows}$$
  - Defensive code enforcement: `apply()` enforces `SELECT COUNT(*) FROM commands WHERE meal_id=? AND security=1 < 15_000`, providing ample headroom above 12,771 while definitively preventing unbounded growth.
  - Because security commands store tiny JSON bodies and results ($\approx 150$ bytes each) and do not mutate claims or receipt items, the total storage remains strictly within SQLite limits and preserves the 148,576-byte headroom between the 900,000-byte ordinary state ceiling and 1,048,576-byte maximum.
- Repeat fresh-ID revocations for an already revoked resource reject with `already_revoked` without inserting rows, preventing unbounded growth of security history.

### 6.6 Lost Response and Idempotency
- Raw secrets are never saved in `commands`, `invitations`, or logs.
- If an `issue_invitation`, `redeem_invitation`, or `rotate_session` transaction commits but the client loses the response:
  - The commit is explicitly uncertain.
  - Retrying with the same token/credential does NOT return the previous secret.
  - Retrying redemption of a consumed token raises `AuthorityError('invalid_invitation')`.
  - Retrying session rotation with an invalidated credential raises `AuthorityError('invalid_session')`.
  - The organizer inspects public status via `snapshot` and can safely revoke and reissue an invitation.

### 6.7 Public Status in `DraftSnapshot`
- `DraftSnapshot` includes `invitations: tuple[InvitationRecord, ...] = ()`.
- Each `InvitationRecord` contains `participant_id`, `created_at`, `expires`, `consumed`, `revoked`, `issue_id`.
- Sorted deterministically: `ORDER BY participant_id, created_at, issue_id`.
- Contains zero tokens or verifiers.
