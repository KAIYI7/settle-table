# SettleTable research index

Access date **2026-10-16** (Asia/Kuala_Lumpur). **Current governance: orchestrator-managed phase transitions**, explicitly delegated by the user on 2026-10-16. Start with [project status](../PROJECT_STATUS.md) and [governance](../docs/agents/governance.md).

Publication preparation2026-10-17: see [safe checkpoint and reproducibility notes](publishing/README.md). Some raw inputs remain local for rights/privacy; historical hashes describe their original bytes. Current project name/import namespace: SettleTable / `settletable`. Older synthetic labels and `tabwise` import paths remain historical evidence; the deterministic `tabwise-apportion-v1` contract remains active and unchanged. See the [dedicated naming assessment](foundation/package-naming.md) and [refactor evidence](foundation/package-refactor.md).

**Current work:** [Phase 3](phase-3/README.md): calculator and [bounded local authority](phase-3/authority-acceptance.md) accepted; [PR #1](https://github.com/KAIYI7/settle-table/pull/1) merged with verified annotated `authority-v1-accepted` checkpoint. Repository foundation precedes transport/identity/invitation planning; [status](../PROJECT_STATUS.md) owns current gates. The [initial checkpoint](publishing/checkpoint.json) remains fixed. See [revised Phase 2](phase-2/README.md) and [transition decisions](../docs/agents/phase-transitions.md). Phase 1 results remain at [its index](phase-1/README.md) and [recommendation](phase-1/phase-1-recommendation.md). Live multi-diner editing, private internet invitations, organizer financial controls and device/self-hosted-only OCR remain confirmed; the whole application is unfinished. Earlier phase-approval wording is historical, subordinate to current governance.

**Foundation complete; next planning:** [separate CI and namespace evidence](foundation/README.md), [independent identity/security challenge](phase-3/transport-identity-challenge.md) and [orchestrator next-slice plan](phase-3/next-slice-plan.md). Exact lifecycle contracts/limits need specification and challenge before implementation. No HTTP/OCR/Notion/UI capability was added by foundation work.

## Evidence conventions

12 November 2026. The owner accepted the [bounded SettleTable–KaiPay synthetic integration](../docs/agents/phase-transitions.md#2026-11-12--settletable-kaipay-integration-06). The acceptance record summarizes the verified organizer flow and financial invariants. The exact execution evidence is retained locally.

29 October 2026: [two focused independent-UAT UI corrections](phase-3/uat-ui-corrections.md), including real receipt DOM regressions, allocation affordance checks and independent reviews. The original incomplete UAT scenarios remain open for separate independent retest.

- **Verified / Fact:** inspected source at an exact revision or current primary documentation.
- **Inference / Proposal:** conclusion, architecture recommendation, cost assumption or future acceptance criterion.
- **Unresolved / Open:** unmeasured, incomplete, conflicting or requiring user choice.

## Phase 0 workstream records (historical)

| Workstream | Status | Artifact |
|---|---|---|
| Official upstream skill inspection/install | Complete: published Matt manifest + Impeccable; globals preserved | [Skills record](agent-skills.md), [discovery](skill-discovery.json), [file hashes](skill-installation-manifest.json), [excluded experiments](skill-excluded-inventory.txt) |
| Tracker/label/domain skill configuration | Complete: user approved draft; project guidance and local conventions applied | [Approved draft](skill-configuration-draft.md), [project guidance](../AGENTS.md), [tracker](../docs/agents/issue-tracker.md), [labels](../docs/agents/triage-labels.md), [domain conventions](../docs/agents/domain.md) |
| Six requested repositories + Malaysian supplement | Complete source inspection; runtime not exercised | [Comparison matrix](repository-comparison.md), reports below |
| Additional GitHub candidate search | Complete focused relevance search | [Search/selection record](additional-candidates.md) |
| Licensing / reuse | Complete assessment with unresolved grants clearly marked | [Licensing](licensing-and-reuse.md) |
| OCR comparison | Historical document/source evaluation; local benchmark subsequently completed in Phase 1 | [OCR](ocr-evaluation.md) |
| Dining logic/rounding/settlements | Complete proposal, worked examples and invariants | [Domain model](domain-model.md) |
| Notion schema/synchronization/Free limits | Complete current-document assessment; no live account test | [Notion](notion-architecture.md) |
| Stack options and official Vercel skills evaluation | Complete; no framework skill installed | [Technology](technology-options.md) |
| Recurring dependencies/risks/open questions | Complete planning assessment; hosting not quoted | [Costs and risks](costs-and-risks.md) |
| Coordinator review / evidence reconciliation | Complete source/doc review and skill integrity checks | [Verification](verification.md) |
| Consolidated decision and next phase | Historical recommendation; Phase 1 completed and later governance supersedes approval wording | [Final recommendation](final-recommendation.md) |

## Reproducible application snapshots

All sources are official requested upstreams or the identified Malaysian author repository. Each report links exact source files, records access/revision/activity and distinguishes absent features from unverified behavior.

| Report / upstream | Exact inspected commit |
|---|---|
| [Nutlope/billsplit](repositories/billsplit.md) | `65f3b1c966a88aa6c7c8cd4edb49dd9af6eb1cc6` |
| [spliit-app/spliit](repositories/spliit.md) | `5dac4119f0441cb945756f8c92911de6f312a1a3` |
| [oss-apps/split-pro](repositories/split-pro.md) | `3583568319807e193fbe57085ea9560a2e872b93` |
| [stefan-esquivel/notion_expense_automation_project](repositories/notion-expense-automation.md) | `0b22160559264ee34619fb8b660e5c8f577c8dd6` |
| [NikunjModgill/ReceiptIQ](repositories/receiptiq.md) | `86d72cf6e9f85f7ff87ac5dc92207f3625fd4b7d` |
| [Kirtiraj01/Ai-bill-splitter](repositories/ai-bill-splitter.md) | `8a89dd97a079fc3c5ce024985d500f9d052bc955` |
| [lester-liam/receipt-splitter](repositories/malaysian-receipt-splitter.md) | `766b2c9201007f589cb128f60936a0d2946d9fe0` |

Skills: Matt `49dd158d1076134a641b33efb035946536778336` / v1.3.1; Impeccable `5bf0a069dc857e1b5f4b090e004d9d5b231416ca` / v4.6.0; Vercel inspected-only `063bee94c3f4df8453406c830b0a7df0f2860278`. OCR engine snapshots/licenses are in OCR evaluation.

## Important resolved contradictions

- Current Spliit already conserves integer splits with largest remainder; precision is not unique to SplitPro. JS intermediate bounds still matter.
- BillSplit tax/tip allocation is equal, not proportional. Neither general expense app supplies dining items/charges/multiple payers.
- ReceiptIQ and the local Paddle sample invoke configured LLM parsing every receipt; neither proves confidence-triggered fallback.
- Notion automation's claimed passing coverage conflicts with a test importing a missing module; passing status is unverified.
- ReceiptIQ/Notion automation have no license grant; Ai-bill-splitter has an incomplete README MIT statement. All three remain reference-only under this project's reuse policy.
- Current Notion documentation refines historical 3/s guidance into request windows and documents Free block enforcement with connection-type exceptions. Preserve the nuance in the integration design.

## Current resume points

1. Read [project status](../PROJECT_STATUS.md), [governance](../docs/agents/governance.md) and the [transition ledger](../docs/agents/phase-transitions.md). The main agent owns transitions; subagent outputs require artifact review. Context7 and pinned skill invocation rules remain effective.
2. Resume from project status and [Phase 3](phase-3/README.md), using [Phase 2 evidence](phase-2/README.md) without repeating completed research. Path C and a Python calculation core are selected; Next.js default preference was withdrawn. Evaluate readiness per capability; the orchestrator authorizes implementation against documented gates.
3. Live collaboration, invitation/role model and local-only OCR are confirmed in Phase 1 requirements. Remaining decisions: target devices, receipt languages/volume, financial edge policies, settlement confirmation, image retention and Notion workspace/connection type.
4. Exploratory OCR/domain/Notion work is followed by actual localhost two-browser and SQLite probes in Phase 2 and an accepted pure calculator in Phase 3. Modern representative accuracy, correction time, phone behavior, production identity/durable live integration, raw REST and production cost remain unverified. Feasibility probes do not clear those feature gates.

## Phase 0 verification limits and preserved work (historical)

Workspace started empty and without Git. Only research and necessary skill files were created. No production scaffold, dependencies, external issues, app commits, deployment or Notion writes. Temporary upstream checkouts support inspection; exact SHAs make the findings reproducible without those caches. No upstream apps/tests/OCR models were executed; no coverage, mobile runtime, service reliability or Malaysian accuracy claim is made. Antigravity runtime is unavailable; shared format compatibility is documented, not live-tested.

Resume future sessions from this index and linked artifacts. Preserve existing findings and conflicting evidence; update the relevant document before closing a workstream.
