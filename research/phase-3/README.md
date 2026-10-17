# Phase 3 — small implementation slices

Started by the orchestrator on 2026-10-16 under the [recorded conditional transition](../../docs/agents/phase-transitions.md). [Project status](../../PROJECT_STATUS.md) owns current objectives and risks. This phase is implementation, following a bounded specification, not a claim that the complete collaborative MVP is ready.

The dedicated foundation refactor changes current imports to `settletable` while preserving both production module files byte-for-byte. Earlier reports/hash-manifest keys retain the original `tabwise` paths and test hashes; reproduce their exact old tree at [`authority-v1-accepted`](https://github.com/KAIYI7/settle-table/tree/authority-v1-accepted). [Refactor evidence](../foundation/package-refactor.md) maps those paths and validates old SQLite replay with the new package. Historical evidence is not a claim that current import-edited test files retain their old hashes.

## First slice

Implement a pure mathematical financial calculation module and exact decimal-money parser. Accepted [contract and limits](../phase-2/mvp-specification.md), [architecture](../phase-2/architecture-decision.md), [independent specification review](../phase-2/specification-review.md). The orchestrator resolved C1–C4 before authorizing code. Test interfaces: supplied immutable meal facts → calculated shares or rejection; decimal text → exact integer sen or rejection. These interfaces are technical decisions under delegated authority.

The calculator cannot establish human review, identity, current revision or permission to finalize. No UI, server, session/invite authority, database, extraction pipeline, image handling or Notion adapter belongs to this slice. Funding/settlements remain distinct later work. No reference-app source copied.

**Outcome: first slice accepted by the orchestrator.** Phase 3 as a whole remains in progress; [next-slice work and blocking gates](../../PROJECT_STATUS.md) are current. The [acceptance ledger](../../docs/agents/phase-transitions.md) records criteria and reviewed evidence.

| Evidence | Result |
|---|---|
| [Production module](https://github.com/KAIYI7/settle-table/blob/af7ba147642b8b8e9a5aee973a95c59d46c38b9a/tabwise/calculation.py), [interface](../../docs/calculation-interface.md) | Independently implemented standard-library Python calculator/parser |
| [Tests](../../tests/test_calculation.py), [implementation/red-green log](implementation-log.md), [implementer run](calculation-verification.json) |15 methods pass on recorded Python3.14/3.12 runtimes |
| [Main verification](coordinator-verification.json), [fixed baseline](review-baseline.json) | Main read actual source/tests/interface and independently ran15 methods successfully |
| [Independent specification review](spec-review.md), [prepared literal cases](adversarial-cases.md), [probe source](independent_probes.py), [results](independent-probes.json) |66 targeted checks PASS; zero blocking findings |
| [Engineering review](engineering-review.md), [probe source](engineering_probes.py), [results](engineering-probes.json) |11 targeted groups PASS; zero material findings |

The original pre-review log/result snapshots retain their historical pending-review wording; the acceptance ledger and current project status supersede that status. No phase or skill workflow overrides human escalation for spend, deployment, credentials, private information or product-policy preferences.

## Next slice — local authoritative draft

2026-10-17: after the GitHub checkpoint was remotely verified, the orchestrator resumed the [bounded specification](../../.scratch/authoritative-draft/SPEC.md). Its [independent challenge](authority-spec-review.md) resolved five clarifications before implementation readiness was recorded. That specification checkpoint contained no additional production implementation.

**Subsequent outcome: local authority internally accepted on `feature/authoritative-draft`.** [Interface](../../docs/authority-interface.md), [incremental implementation evidence](authority-implementation-log.md), [acceptance and limits](authority-acceptance.md), [coordinator run/hashes](authority-verification.json), [source/spec/concurrency review and20-case mapping](authority-adversarial-review.md), [security review](authority-security-review.md). All60 tests pass, including15 unchanged-calculator tests and actual10,000-command exhaustion. Final diagnostic-only test hardening received targeted reruns. Original material findings remain recorded with verified fixes. This local scope excludes network/UI/invitation delivery and future policy-dependent features; Phase 3 and the complete product remain unfinished. See [status](../../PROJECT_STATUS.md) for PR work.
