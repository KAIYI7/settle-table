# Next bounded MVP work: invitation identity, then transport

2026-10-17. Orchestrator planning decision derived from the [independent challenge](transport-identity-challenge.md), accepted authority evidence and confirmed [requirements](../phase-1/requirements.md). This is a plan, not new product implementation or public-release approval. Repository foundation must pass its recorded CI/refactor gates first.

## Direction and evidence

**Verified:** the current engine has fixed financial participants, current meal-role authorization, exact replay and atomic SQLite finalization. It lacks remote enrollment, session renewal and a browser transport. One session per participant and a two-revocation-per-person reserve were accepted together. A shared link or HTTP wrapper around trusted bootstrap cannot safely fill those gaps.

**Conclusion:** prioritize this missing access path before OCR, Notion or broader UI. Keep Python/SQLite and the accepted financial module. Do not select a frontend or HTTP framework by reference-project popularity. The next two independently reviewable increments are (1) integrated local invitation/session lifecycle for predeclared diners and (2) a same-origin transport adapter. Real public exposure remains a human gate.

## First increment: local invitation/session lifecycle

**Proposed scope:** an authenticated organizer issues/revokes a bounded expiring invitation bound to one existing active diner membership. Possession proves control of that capability, not the named person's real identity. Redemption consumes it once and binds a fresh high-entropy session to exactly that participant; rotation invalidates the previous verifier atomically. Initial organizer provisioning stays trusted/local. No anonymous remote bootstrap, participant insertion/removal, organizer handover, account recovery or membership reactivation.

All invite consumption, current organizer/member checks, session rotation and audit effects belong to the authority's existing SQLite transaction owner. A second credential database, a framework reaching into `_db`, or a check-then-call wrapper is rejected. Existing participant-scoped financial replay identities, all v1 canonical bytes and every existing versioned hash domain remain unchanged. New invitation contracts need their own explicit versioned domains; a package/brand rename is never a reason to change existing ones.

**Selected safe acknowledgment policy for the first specification:** one-time raw grants are not replayed from persisted accepted results. A commit whose grant response is lost is explicitly uncertain. The current organizer can revoke/reissue an invitation or authorize a fresh session grant for an active diner; this does not reset financial facts, revive an inactive membership or become account recovery. Do not persist plaintext or recoverably encrypted bearer material merely to make retry convenient. An identical issue/redemption retry must never mint another session or return an old revoked grant. A receipt/status protocol using only public identifiers/verifiers must be specified and challenged before code. Client-preselected credentials could avoid lost grants, but shift entropy/trust guarantees and are deferred rather than silently introduced.

**Engineering bounds to close in the concrete spec:** one active invite per target; finite lifetime issuance/session generations and audit rows; independent token type/length/alphabet bounds before hash/DB; explicit trusted-clock expiry. Use a proposed ceiling of64 lifecycle generations per participant as a starting point, not an accepted implementation constant. Recompute the security reserve for those generations plus final membership revocation. The original fixed two-per-person proof is invalid after rotation. Exhausting financial or invitation capacity must still permit revocation without deleting accepted financial history or growing security history indefinitely. Current session revocation must invalidate outstanding invitations; membership revocation must stop all old capabilities from restoring access. Fresh-ID revoked no-ops remain bounded/rejected.

## Required design/validation gates before lifecycle implementation

| Gate | Current disposition / exact closure work |
|---|---|
| Same authority transaction owner | PASS as direction; specify a small public lifecycle interface and internal transaction seam, not a second store. |
| One-time issue/redemption/uncertain acknowledgment | CONDITIONAL PASS — the safe failure policy above is selected; write exact operation IDs, stored metadata, replay/status behavior and reissue transitions, then independently challenge them. No claim of seamless credential recovery. |
| Rotation/revocation/resource accounting | CONDITIONAL PASS — define generations, active/past capability state and reserved security capacity; test exhaustion and both serialization orders. |
| Existing SQLite compatibility | PENDING — additive/versioned local schema plan, disposable old-v1 database reopening and byte-identical historical finance/replay. No irreversible production migration. |
| Readiness to implement | PENDING concrete bounded spec and adversarial review. These engineering gaps are targeted next work, not a request for routine user phase approval. |

Acceptance tests must cover two independent connections racing one invite, redemption versus session/member/invite revocation in both orders, changed identity/replay attempts, expired/unknown/wrong-meal capabilities, lost grant response, all pre/postcommit failures, reopen and exact prior financial replay. Scan SQLite/sidecars/dumps/results/logs/test diagnostics for raw tokens. Exhaust real configured lifecycle limits and verify finite security reserve. Preserve current full-suite CI; no weakening the actual10,000-command test.

## Following increment: same-origin transport

After the lifecycle seam is proven, select the smallest maintained Python HTTP adapter against explicit requirements: strict bounded wire decoder before allocation, no caller actor/role authority, same-origin mutation checks and CSRF defense, host-only HttpOnly/Secure cookie semantics, trusted Host/proxy policy, safe errors/logging and explicit retry versus current snapshot. Polling is sufficient initially; no WebSocket requirement is established.

Invitation landing GET must not consume a token. No third-party assets/analytics or token-bearing access logs; use no-referrer/no-store and an explicitly reviewed link/redemption representation. Test actual isolated browser contexts, hostile/missing/null origins, forged Host/forwarded headers, duplicate JSON keys, bool/float/rational mistakes, oversized bodies/headers and real concurrent command behavior. An in-process HTTP test is insufficient proof of cookie/browser behavior. Local-only fixtures and public HTTPS deployment have separate gates.

Public readiness still requires TLS/ingress, bounded abuse protection, backup/restore, operational session/recovery decisions and deployment authorization. The user has not authorized paid identity providers, receipt sharing, public services or recovery/handover policy. None is needed to write/review the next local lifecycle specification. This plan does not reactivate deferred settlement, voucher, image-retention, OCR or Notion decisions.
