# Phase 1 — Requirements and Technical Validation

Historical Phase 1 snapshot, authorized on **2026-10-16**. Feasible findings are complete; production readiness was not established by this phase. Later user delegation supersedes numbered-phase approval restrictions: see [governance](../../docs/agents/governance.md), [current status](../../PROJECT_STATUS.md) and [Phase 2](../phase-2/README.md). Evidence and original-scope observations below are historical, not current authorization rules.

Start with [Phase1 recommendation](phase-1-recommendation.md), then the relevant evidence below. **Conclusion:** PathC remains favored; Next.js no longer the default; local OCR/human verification and live collaborative financial revisions require further targeted validation before production.

## User-confirmed decisions

- Several diners edit the same meal live, joining through private internet invitation links.
- Organizer controls receipt amounts/charges and finalization; diners edit their own assignments.
- OCR on device or self-hosted only, both in validation and product; no hosted vision calls or cloud fallback budget.
- No private receipt folder. Public historical scans and clearly synthetic fixtures only, with provenance limits recorded.

## Progress / required outputs

| Workstream | Status | Artifact |
|---|---|---|
| Authorization update | Complete; only AGENTS.md Current phase modified | [Project instructions](../../AGENTS.md) |
| Workflow/requirements/interview | Complete analysis; remaining policy choices explicitly surfaced | [Requirements](requirements.md) |
| Dining-domain/integer invariants |67 concrete scenarios +54,000 seeded assertion groups pass | [Domain](domain-model.md), [results](experiments/domain/results.json) |
| Live-edit consequences |17 domain checks pass; actual browser/transport trial remains open | [Simulation](experiments/collaboration/README.md) |
| Local OCR benchmark |3 engines ×6 historical dining scans +4 synthetic cases,2passes; representative accuracy remains open | [OCR validation](ocr-validation.md), [metrics](experiments/ocr/results/metrics.json) |
| Notion validation |6 live scratch DBs/9 synthetic rows;12 local recovery checks pass; raw REST/scale gates remain open | [Notion validation](notion-validation.md) |
| Stack/path re-evaluation | Complete nonbinding comparison; framework unselected | [Architecture](architecture-decision.md), [documentation evidence](architecture-evidence.md) |
| Go/no-go and next scope | Historical recommendation; subsequent orchestrator transition recorded separately | [Phase1 recommendation](phase-1-recommendation.md) |
| Coordinator/integrity checks | Complete within recorded limitations | [Verification](verification.md), [machine checks](verification.json) |

## Evidence labels

**Verified fact** = primary source/environment observation. **Experimental evidence** = executable observation with versions/inputs/results. **Conclusion/proposal** = interpretation, not production commitment. **Assumption** = scenario input, not user choice. **Unresolved** = missing decision/measurement/permission.

## Important findings and conflicts

- Totals6/6 for Rapid/Paddle did not mean item extraction correct. Each produced3/6 real clean-but-incorrect candidates under the frozen gate. No automatic acceptance or AI recovery validated.
- Real data is historical GST; modern SST, real vouchers and phone-photo distributions remain unmeasured. Synthetic transformations are not real acquisition evidence. Agent annotations are not independent human gold.
-600sen item sum can coexist with566sen printed tax-exclusive subtotal plus34included tax. Distinguish bases; do not double-add tax or multiply line totals by quantity again.
- Domain runner fixes closed noninteger-input and suggested/confirmed-transfer ambiguity before final re-execution. Current counts/hashes supersede interrupted early drafts.
- Notion accepts fractional NUMBER values; synthetic invalid probe was restored. Application validation is necessary. Connector success is not REST/OAuth or transactional proof.
- User requires live editing; the earlier one-editor recommendation is rejected. Framework choice follows this requirement and actual device/runtime evidence.

## Prototype and skill record

Read/invoked the explicitly requested grill-with-docs plus grilling/domain-modeling, research, prototype and codebase-design. Bounded background work persisted its findings. Two workers hit usage limits after saving partial artifacts; coordinator continued from files, corrected/reviewed claims and completed feasible runs. No findings depend solely on messages or memory.

User's minimum headless validation scope takes precedence over prototype skill suggestions to build UI variants, absorb code into production or commit a throwaway branch. No repository initialized and no production source created. GLOSSARY records durable concepts; no ADR warranted while architecture remains provisional.

AGENTS.md outside-section SHA256 preserved: `681a3445bfa0c0a5c86eadaa5359ab58c98edac9b16d0f8730e3687ae533b226`. No framework-specific skills installed. Existing global skills preserved.

## Scratch resources / reproducibility

- [Experiments guide](experiments/README.md): separate domain, collaboration, OCR and Notion subdirectories.
- [OCR guide](experiments/ocr/README.md): pinned environment, data/model hashes, commands, rights and frozen-parser limits. Image/model caches ignored and not cleared for product distribution.
- [Notion scratch guide](experiments/notion/README.md): [private disposable root](https://example.invalid/notion/synthetic-notion-id-013), retained synthetic structures and exact cleanup instructions. No real receipts uploaded or existing content changed.

## Outstanding gates / resume

The orchestrator evaluated the recommendation and started a revised bounded Phase 2; see [decision](../../docs/agents/phase-transitions.md). Unattended extraction remains no-go on current evidence. Phone/corpus/REST gaps remain capability-specific restrictions. Preserve raw counter-evidence and current hashes when continuing; current authority comes from governance rather than this snapshot.
