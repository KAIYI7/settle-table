# Independent Phase 1 gate challenge

Reviewed 2026-10-16 by a delegated reviewer. **Recommendation to the orchestrator:** conditional progression into targeted feasibility closure and a bounded manual-first financial core is supported. This reviewer does not authorize phase transitions. Whole-product implementation readiness and public release readiness are different gates; neither is established by Phase 1.

The user's orchestrator-governance authorization supersedes historical requests for numbered-phase approval. It does not waive privacy, financial correctness, licensing or genuine product-policy decisions.

## Actual artifacts inspected

- [Requirements](../phase-1/requirements.md), [domain findings](../phase-1/domain-model.md), [architecture assessment](../phase-1/architecture-decision.md), [Phase 1 recommendation](../phase-1/phase-1-recommendation.md), [coordinator verification](../phase-1/verification.md).
- Full source of [financial experiment](../phase-1/experiments/domain/validate_domain.py), [concurrency experiment](../phase-1/experiments/collaboration/simulate.py), and [Notion fake-remote journal](../phase-1/experiments/notion/retry_simulation.py).
- [OCR findings](../phase-1/ocr-validation.md), first real-field metrics in [machine evidence](../phase-1/experiments/ocr/results/metrics.json), [Notion observations](../phase-1/notion-validation.md).

This challenge independently inspects code and persisted evidence; it does not rerun the OCR workload, contact Notion, audit the live scratch ACLs or establish new device/API facts. Reading a report of live activity is weaker than repeating that activity. No public receipt image was redistributed and no hosted image call was made.

## Material exit gates

These gates assess whether Phase 1 has supplied enough evidence for the **next bounded work**, not whether it already built a secure MVP.

| Gate | Assessment | Evidence and consequence |
|---|---|---|
| Requirements preserve the user's objective and authority choices | PASS | Live private-link diners, organizer-controlled amounts/finalization, diners' own claims, integer sen, required human review and local/self-hosted OCR are explicit. Product-policy alternatives are surfaced rather than represented as user decisions. |
| A coherent conserved arithmetic model exists | CONDITIONAL PASS | Financial source uses exact integers/Fraction, explicit included-tax basis, separate consumption/funding/transfers and no accounting effect for suggested/pending transfers. Randomized assertion counts are experimental, not independent proof. Practical money/quantity bounds and production persistence remain unspecified. |
| Settlement identity/history is safe to transplant | FAIL | New adversarial probe below exposes reused suggestion IDs across recommendation batches. Experiment remains useful evidence; it must not be copied unchanged into a production settlement module. |
| Simultaneous editing is feasible enough to investigate | CONDITIONAL PASS | Lock/revision simulation rejects stale writes, overclaims and revoked replay. Actual identity, durable atomic acceptance, two browsers, reconnect and hostile clients remain untested. This blocks claims of live-feature completion, not building the validation slice. |
| OCR can run locally | PASS for workstation feasibility | Three installed configurations produced timed local results. This is not phone/offline proof or a production engine selection. |
| OCR can establish financial truth without human review | FAIL | Persisted gate results include clean-but-wrong candidates; correct totals do not establish correct quantities/names. Mandatory review is required by user and evidence. |
| Modern Malaysian receipt quality is validated | FAIL | Six historical GST scans, four synthetic stresses, no positive real discounts or modern SST coverage, no independent human gold/held-out sample. Blocking for automation-quality promises; nonblocking for manual-first calculations with nonauthoritative OCR proposals. |
| Notion is suitable as optional asynchronous reporting | CONDITIONAL PASS | Synthetic six-entity connector round-trip and fake-remote recovery support the proposed shape. NUMBER accepts fractional values, so integer/reconciliation enforcement belongs in the canonical application model. |
| Production Notion REST/auth/media is validated | FAIL | Connector success does not prove raw REST credentials, OAuth, limits, real retry or formula behavior. Blocking for claiming a working production integration; nonblocking for an optional-export contract or the financial core. |
| Architecture alternatives were evaluated without circular framework selection | PASS | Next.js default was withdrawn; browser/native and Python/Node alternatives have explicit trade-offs. No framework is selected by popularity or by OCR wrapper examples. |
| Public-release security, operations and cost are established | FAIL | No deployed authentication, TLS, backups, abuse limits, retention implementation, real concurrency capacity or price commitment was verified. Public/production deployment requires human authority independently of numbered phases. |

## New financial challenge: repeated suggestion batches collide

Source references: `suggestions()` generates `suggestion-` plus an index starting at zero every call; `simulate_confirmation()` preserves that identity; `balances()` rejects two differing records with the same transfer ID. This is internally consistent immutable-identity enforcement, but the sample suggestion identity is unsuitable as a durable payment identity.

Executed locally against the existing source using an import with bytecode writing disabled, without changing its runner/results:

1. A owes 0 sen, B owes 100 sen; A paid the restaurant 100 sen.
2. First recommendation is `suggestion-0`, B→A, 100 sen.
3. Record a real partial 40-sen payment using that recommendation identity.
4. Recompute remaining recommendations: again `suggestion-0`, B→A, now 60 sen.
5. Confirming both batches produces `conflicting_transfer_id`.

Exact observed records:

```json
{
  "confirmed_partial": ["suggestion-0", "B", "A", 40, "confirmed"],
  "recomputed_confirmed_batch": [["suggestion-0", "B", "A", 60, "confirmed"]],
  "result": "conflicting_transfer_id"
}
```

**Production acceptance requirement:** recommendation identity/revision and real-transfer identity must be distinct. Recording an actual transfer creates a stable unique command/transfer identity; exact command replay counts once, differing payload reuse conflicts, and later recommendation batches cannot alias prior transfers. This can be decided as engineering identity design; it does not settle who may confirm or dispute a payment.

Additional spot probes returned quantity allocation 1001 sen at 1:2 → A334/B667, and a −1-sen scoped discount on A1/B1 → A0/B−1. Those outputs preserve their declared invariants. They do not independently prove all randomized cases.

## Important limits and contradictions to preserve

- The proposed concurrency module initializes `reviewed=True` and checks full quantity claims at finalization; it does **not** carry the domain runner's authoritative receipt-total reconciliation gate. Combining the two requires a real shared finalization contract, not assuming one simulation inherits the other's guarantees.
- The concurrency actor is a trusted in-process string, not authenticated diner identity. Membership checking on duplicate replay is good, but does not establish invitation security. Possessing a shared meal URL must not by itself grant organizer actions or the ability to impersonate another diner.
- The Notion journal uses one SQLite file as both journal and fake remote. It tests useful uncertainty states, but its exact/immediate lookup and single worker do not validate remote visibility or competing export workers. Zero-match uncertainty deliberately stays unresolved: a real adapter needs bounded/operator-visible recovery rather than falsely reporting success or blindly recreating rows.
- Largest remainder is conserved and deterministic for stable inputs but not monotonic per person. The preserved counterexample is correct; acceptance must avoid a promise that every individual amount always rises when total rises.
- `2^53−1` in the Notion adapter is a proposed transport guard, not a proven Notion maximum or sensible per-meal amount limit. Amount, quantity, participant-count and input-length bounds are needed before accepting untrusted payloads.
- An image sent to a self-hosted controlled server is no longer device-only. No third-party hosted vision is authorized. Optional Notion image archiving remains a separate external-sharing/retention choice.

## Blocking versus nonblocking next work

**Blocking before the relevant production feature is complete:** atomic durable acceptance with financial reconciliation; authenticated revocable role-bound identity; hostile payload bounds; unique real-transfer identity and ledger transitions; clear settlement confirmation/correction policies; raw REST/auth validation before claiming Notion integration; human review and no hosted image fallback.

**Nonblocking for bounded local/manual-first core work:** missing modern corpus, real phone OCR latency, native OCR comparison, account-specific Notion plan and raw credentials, public hosting choice. Keep OCR and Notion disabled/noncritical where their gates are unmet. Do not remove these product capabilities from the agreed objective; stage them and continue targeted validation.

**Genuine user-preference frontier:** who confirms/disputes settlements, voucher ownership/gifting where interpretation changes who owes money, settled-correction consent, and whether private receipt images may be retained/exported. These should be escalated when their feature depends on the choice. Ordinary engineering choices such as stable command IDs, safe integer bounds, revision checks and test strategy belong to the orchestrator.

## Suggested bounded next step

The orchestrator can record a CONDITIONAL PASS into feasible closure, build a disposable real transport/two-browser acceptance probe, select the smallest justified stack and define a manual-first vertical-slice specification. A calculation core can be developed/tested before OCR/mobile/Notion credentials are available; a complete collaborative MVP must still pass durable authorization/reconciliation tests. Treat no image upload, no automatic financial acceptance, no production exposure and no account action as accidental consequences of progressing a numbered phase.

The orchestrator should review this artifact and resolve the transfer-ID and composed-finalization gaps in the next specification/tests. This document supplies independent challenge evidence, not an authorization decision.
