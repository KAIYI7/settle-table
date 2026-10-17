# Costs, risks and open decisions

> Historical authorization context: this report predates the user's orchestrator delegation on 2026-10-16. Requirements for user approval of numbered phases in this snapshot are superseded by [current governance](../docs/agents/governance.md) and the [transition ledger](../docs/agents/phase-transitions.md). Evidence and capability limitations remain valid to the extent stated; private-data, spending and product-policy consent are still separate.

Accessed 2026-10-16. **Verified prices** are explicitly sourced. **Planning envelopes** and **worked assumptions** are not vendor quotations or measured usage. No paid service was purchased or called.

## Recurring dependencies

| Component | Cost basis | Assessment |
|---|---|---|
| Browser/native local OCR | No required per-receipt OCR API charge; device CPU/battery and model/asset delivery remain | Existing hardware can mean $0 incremental vendor usage. Native release/QA or browser model caching adds development effort. |
| Server RapidOCR/Paddle | CPU seconds, peak RAM, cold starts/concurrency, model storage and operations | Not free merely because models are open. Benchmark first; a permanently running OCR worker can exceed cheap hosted vision spend at low volume. |
| Optional vision fallback | Input/image/output/thinking tokens × fallback fraction × retries | Budget/cap explicitly; paid mode may offer better data terms than free. Do not select provider/model from a repo's hard-coded default. |
| Canonical ledger/API | Server hosting, DB, backups and network | Local single-user deployment can use existing hardware; shared durable product needs operations. No specific provider selected. |
| Receipt originals | Retention days × receipt volume × size plus backup/downloads | At assumed 1,000 receipts/month × 2 MB × 12 months, originals alone grow ~24 GB/year before derived images/backups. Retention choice matters more than storing JSON. |
| Notion | Free if workspace limits fit; otherwise optional workspace upgrade | Verified Free upload cap 5 MiB; team block limit can prevent creates. No paid Notion AI/automation needed. See [Notion](notion-architecture.md). |
| Auth/email/domain | Optional SMTP/OAuth, abuse controls, domain renewal | Guests should not require paid accounts. Price depends on chosen product/auth strategy; do not import banking/FX/SMS services by default. |
| Agent skills | Downloaded skills have no mandatory recurring API fee | Agent/model subscription usage, Impeccable browser tools or future cloud capabilities are separate. No paid plugin setup performed. |

**Planning envelope/inference:** a small shared pilot might budget USD 10–60/month for modest server/DB/storage/backups, before unusual OCR load, paid workspace seats or labor. This is an engineering reserve, **not an inspected hosting quote** and not a claim of sufficiency; existing hardware/free allowances could lower cash spend, while always-on ML or managed production guarantees could raise it. Choose a host only after measured memory/latency and retention/availability requirements. No MYR exchange conversion is assumed.

**Verified illustrative rate:** Gemini 2.5 Flash-Lite Standard lists $0.10/million text/image input and $0.40/million output tokens at [official pricing](https://ai.google.dev/gemini-api/docs/pricing), accessed this date. This is an illustration, not an endorsed model or measured receipt bill. For assumed 3,000 input and 1,000 output tokens, a call costs $0.0007; 1,000 all-AI receipts cost $0.70 or 20% escalation $0.14, before retries/taxes/hosting. Actual image tokenization/output and fallback fraction are unmeasured. Formula and privacy terms: [OCR evaluation](ocr-evaluation.md).

**Inference:** at small volume, reducing API spend by cents may not justify weeks of parser engineering. Hybrid is favored for privacy/offline/control and testability, conditional on benchmark results; direct schema-validated vision plus human review remains a legitimate alternative if it wins total cost and consent requirements. Zero paid API usage remains possible by allowing manual correction.

## Risk register

| Risk / evidence | Impact | Proposed response; verification still needed |
|---|---|---|
| Unit versus line-price ambiguity causes quantity errors in two inspected samples | Incorrect diner liabilities | Explicit schema semantics, preserve both values, reconcile to printed line/receipt totals; invariant tests |
| Independent rounding and unsupported fee eligibility | Lost cents/unfair charges | Integer minor units, largest remainder per component, explicit bases/discount scope and reviewed rounding |
| OCR confidence is uncalibrated or discarded | False certainty | Retain evidence, evaluate field-level precision and reconciliation, human review; no confidence-as-probability claim |
| Mixed English/Malay/Chinese/Tamil, thermal fade and skew | Missing/garbled line items | Representative consented corpus and per-script/error-stratum reporting; do not strip Unicode |
| Receipt contains personal/payment data; some sample code logs full content | Privacy/retention exposure | Local default, deliberate cloud consent, redacted telemetry, private access/retention/deletion design |
| Public URL/weak file authorization in references | Cross-group receipt access or API abuse | Resource membership checks, safe decode/size bounds, private object access, rate/spend caps |
| Notion multi-page writes, timeouts, quota and user schema edits | Duplicate/partial reports | Outbox/operation mapping, reconciliation before retry, revision-complete marker, compact exports |
| No license or ambiguous grant in three references | Inappropriate source copying | Concept reference only; seek grant if adoption becomes necessary |
| Existing global skill names duplicate local collections | Wrong skill copy invoked / catalogue bloat | Report paths/revisions; preserve global files; explicit local paths and invocation policy; host discovery verification |
| Upstream tests present but unexecuted; Notion example has conflicting coverage claim | False production confidence | Record limits; reproduce only relevant checks after explicit experimental approval; no success claim here |

## Material unanswered questions

1. Personal one-editor tool, recurring group ledger or simultaneous collaborative product? How many editors/groups/receipts per month?
2. Does offline mean device-only, local network, or a self-hosted service? Which phones/scripts must work?
3. Can images leave the device/service, and which consent/retention/deletion rules apply? Are private originals retained or only redacted reporting copies?
4. Is target Notion workspace single-member Free, multi-member Free, or paid; which integration type and export detail do users need?
5. Is Notion read/report-only or should edits initiate app review? Who may change finalized/settled meals?
6. Which fee/discount/gift/quantity/refund policies are required? Is cross-meal netting needed initially?
7. What acceptable manual correction time, mobile p95 latency and escalation rate justify automation complexity?

These questions constrain a next-phase spec; they do not change this phase's completed source/document findings. No production uptime, OCR accuracy, tax compliance, dependency security audit or legal clearance is claimed.
