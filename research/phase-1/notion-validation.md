# Phase 1: disposable Notion validation

Status: Phase 1 bounded validation complete, with raw REST and scale limitations explicitly open. Access date: 2026-10-16 (Asia/Kuala_Lumpur). Scope: synthetic, disposable validation only; no production schema, real receipt, personal diner data, credentials or existing workspace content modified.

## Evidence baseline

Read [research index](../README.md), [prior Notion assessment](../notion-architecture.md), project `AGENTS.md` current Phase 1 authorization and `.agents/skills/research/SKILL.md`. The index still contained pre-Phase-1 status at start; the coordinator owns that update. Current task authorization and AGENTS current phase explicitly permit this experiment.

Context7 resolution selected `/websites/developers_notion_reference`; official docs identify current REST `Notion-Version: 2026-03-11`, database containers plus data-source schemas/row parents. Connector SQL DDL and flattened SQLite-like values are adapter conventions, **not raw REST API syntax**.

## Connected capability inspection (observed, redacted)

- `get_self`: a connected workspace and authenticated person returned successfully. Account name/email and workspace/user IDs deliberately omitted from persisted research.
- `get_tool_access`: create/fetch/update pages, create database, update data source, file upload/attachment tools available. Single-data-source query available with limits; multiple-data-source query requires fuller plan. AI search is plan-required. These results do not identify the exact billing plan or establish raw REST permissions/rates.
- Target policy: connector `creation_mode: draft` is documented as server-enforced workspace-level **private** creation. Create one fresh parent titled `TabWise Phase 1 DISPOSABLE validation`; all experiment databases/rows remain under that parent. No sharing/moving into existing pages.

## Validation plan

1. Create private synthetic parent, six related data sources (Meals, People, Receipt Items, Item Allocations, Payers, Settlements).
2. Create one synthetic MYR meal using integer sen, two fictional people, shared item allocations, multiple payer records, tax/service/discount/rounding totals and status fields.
3. Fetch schemas/rows, verify relations, update settlement status and report totals via allowed single-source queries/client-side joins. Record connector limits separately from REST.
4. Exercise retry/uncertain-outcome scenarios locally with a deterministic fake remote and persisted journal; never provoke real rate limits, duplicate remote writes or API errors.
5. Preserve scratch page as evidence and provide exact cleanup location; do not delete unless requested.

## Live observations (verified through connector only)

- Created fresh private draft [TabWise Phase 1 DISPOSABLE validation](https://example.invalid/notion/synthetic-notion-id-013) using server-enforced `creation_mode: draft`; six child databases were created there. No existing content was fetched or edited beyond account capability inspection. Fetch does not independently expose ACLs; privacy proof is the draft tool contract, not an ACL audit.
- Created two fictional People, one meal, one shared line item (Unicode label retained), two allocations, two payers and one settlement. Readbacks preserve relation target page URLs and small integer-sen values.
- Meal subtotal 3001 − discount 101 + SST 174 + service 290 + rounding 1 = total 3365. A owes 1683 and paid 2000; B owes 1682 and paid 1365; B→A settlement 317 clears both balances. These are fabricated amounts, not statutory rates or a receipt parser result.
- Added a `Sync State` select and a `Reconciles` formula to the scratch Meals schema. Updated settlement Proposed→Confirmed and meal Open→Settled. Final revision is 4, including a restored constraint probe described below. The connector schema exposes number properties as SQLite `FLOAT`; small integers round-trip, but this does not prove arbitrary-precision integer storage or monetary arithmetic guarantees.
- Uploaded a 597-byte synthetic SVG with connector `create_attachment`, then attached it to Meals. A bare **file upload ID** in `Receipt` was rejected as “File ... not found” (400); this was an incidental validation mismatch, not an intentionally induced service failure. Corrected to the supported `{type: file_upload, file_upload: {id}}` object in `update_page`, which succeeded. **File-upload IDs are not interchangeable with existing file IDs** despite the connector's shorthand documentation. No blind retry of the same invalid request.

### Number constraint probe and restored final state

The only deliberately invalid raw value was a temporary `Paid Sen = 2000.5` on Synthetic A's scratch payer record. It was written while `Sync State = Pending`, read back as 2000.5 and immediately restored to **2000** before reporting/calculation. No domain model or financial calculation accepted that invalid input. This demonstrates that a Notion NUMBER property does **not enforce integer sen**. The local adapter experiment rejects a fractional value, boolean and value above `2^53−1` before arithmetic. A safe transport bound is a proposed adapter guard, not a proven Notion number maximum; stricter practical receipt bounds remain a requirements decision.

Final query after restoration returned total paid **3365**, meal revision **4**, `Sync State = Complete`, `Review = Approved`, `Settlement = Settled`. All valid fixture arithmetic uses integers. Funding and settlement are different: two payments fund 3365; the later 317 transfer reimburses between diners and must not be added to merchant funding or meal total. The live completion marker is manually exercised adapter state, not an automatic Notion consistency guarantee.

### Reporting and formula limitation

Single-source SQL over Allocations returned base=3001, discount=101, SST=174, service=290, rounding=1, owed=3365; Payers SUM=3365. A corrected Meals query calculated 3365 from its numeric components and returned status/sync fields. Client-side relation matching connects these reports without a gated multi-source connector query.

The new formula is present in the data-source schema, but `fetch`/rows return a `formulaResult://...` reference. I attempted a SQL select of it and received a connector validation error explaining formula columns cannot be queried. The fetched SQLite definition did not list it, so that query should have excluded it initially; the corrected query uses only listed numeric columns. **Formula evaluation is not verified through this connector.** REST docs instead define typed formula results, e.g. `{type: boolean, boolean: true}`; that is documentation evidence, not this live result. [REST page property values](https://developers.notion.com/reference/page-property-values).

## Created structures and evidence

All tables are beneath the same private experiment root. Values are fictional; no real person records or Notion `people` membership were created.

| Entity | Data-source ID | Rows | Demonstrated |
|---|---|---:|---|
| People | `synthetic-notion-id-003` | 2 | App ID/revision and arbitrary diner identity without workspace membership |
| Meals | `synthetic-notion-id-016` | 1 | Participants, integer components, receipt FILES, review/settlement/sync states, schema update |
| Receipt Items | `synthetic-notion-id-017` | 1 | Meal relation, quantity, line sen, Unicode label |
| Item Allocations | `synthetic-notion-id-021` | 2 | Item/meal/person relations, weights, per-component shares, SQL aggregate |
| Payers | `synthetic-notion-id-002` | 2 | Independent multiple payments, fractional-input weakness and restoration |
| Settlements | `synthetic-notion-id-001` | 1 | Directed person relations, amount, Proposed→Confirmed update |

Evidence files: [initial schema snapshot](experiments/notion/connector-evidence.json), [redacted requests/results and final IDs](experiments/notion/connector-roundtrip.json), [synthetic receipt SVG](experiments/notion/synthetic-receipt.svg), [experiment/cleanup guide](experiments/notion/README.md). Account name/email, workspace identity and internal attachment references are omitted or redacted in persisted research. Synthetic page/data-source/upload IDs are retained to reproduce this inspection.

## Retry and uncertainty experiment (local fake remote only)

Executed [retry_simulation.py](experiments/notion/retry_simulation.py) using Python 3.14.6, standard library only; no network, framework, Notion token or SDK. [Results](experiments/notion/simulation-results.json): **12 checks passed, zero failed**. SQLite `simulation.sqlite` preserves the local journal/fake remote for inspection. Re-running clears only the experiment's own journal/fake-remote tables and recreates deterministic synthetic cases.

- Adapter rejects fractional, boolean and unsafe-size minor units before calculating.
- Simulated 429/529 obey fake Retry-After=17 seconds without sleeping; confirmed repeat runs create one remote row. Retry budget stops after four attempts. A simulated plan 403 is blocked rather than retried indefinitely.
- Simulated create-commit-then-503 persists uncertainty, closes/reopens SQLite, reconciles an existing matching row and confirms without creating a second row.
- Zero matches after uncertainty remains manual/uncertain; multiple matches block recreation. A same-revision payload mutation is rejected. A corrected revision is distinct; its completion marker waits until every simulated child operation confirms.

This demonstrates local failure-state mechanics only. Fake lookup is exact/immediate; real query visibility may be stale. No distributed lock, authentication, real REST idempotency, atomic multi-page write or automatic cross-table financial enforcement is proven. Official guidance says a write can commit despite 503, so blind retries are inappropriate; inspect `retry_guidance`/committed IDs and reconcile. [Request limits and ambiguous writes](https://developers.notion.com/reference/request-limits).

## Connector versus raw REST / Free-plan limits

| Capability | What is demonstrated | What remains documentation-only or unverified |
|---|---|---|
| Schema and records | Connector DDL → six live data sources, create/read/update relation values and small integers | Raw REST `initial_data_source`, typed property payloads, pinned headers, service credentials and transaction behavior were not exercised |
| Files | 597-byte synthetic SVG upload + FILES attachment/readback | Raster camera receipt path, mobile rendering, 5 MiB threshold, bot byte limit, multipart, signed URL expiry/refresh not boundary-tested |
| Reports | Limited single-source connector queries work; client-side relation joins feasible | Multi-source SQL is tool-plan gated; **this does not mean REST cannot query each data source separately**. Formula results not resolved by connector |
| Retry | Deterministic local fake remote cases and durable restart | No live rate pressure or failures were induced; the two incidental validation errors above were fixed requests, not rate/retry tests |
| Plan/privacy | Connected tool capabilities and private-draft contract | Exact subscription, workspace member count, ACL audit, internal integration permissions and public OAuth installation not inspected |

Current primary documentation (accessed 2026-10-16) retains Free single-member unlimited blocks, multi-member 1,000 lifetime blocks with connection-type exceptions, 5 MiB per file, and 180 requests per 60-second Free/Plus connection window plus a separate shared-workspace budget. These are **documentation facts, not limits measured in this account**. Deletion does not reclaim lifetime blocks; never test quota exhaustion deliberately. [Block policy](https://developers.notion.com/reference/workspace-block-limits), [file limits](https://developers.notion.com/guides/data-apis/working-with-files-and-media), [request limits](https://developers.notion.com/reference/request-limits). Connector AI search and multi-source-query upsell are separate from the public REST service and do not force an app integration to buy Notion AI.

## Decision implications and open work

**Inference:** validation supports six entities, independent payers and optional one-way Notion reporting. The integer-money boundary, revision tracking, copy completeness and retry/reconciliation belong in the app adapter/canonical ledger. Notion select states alone cannot establish conservation, settled balances or completed synchronization. The result still favors an optional report/archive copy over primary interactive financial storage; it does not select a production stack.

**Unresolved:** owner selection of Notion optional integration versus other reporting requirements; personal versus multi-member workspace; full-row versus compact export; image retention/privacy; authorized internal token or OAuth model; raw REST end-to-end authentication/schema/media contract; native formula/rollup readback; scale/large relation pagination; change conflicts/webhooks; realistic receipt volume. No raw REST credentials were supplied to or used by this experiment. No assumption of connector access substituting for production OAuth is made.

**Cleanup:** scratch [root page](https://example.invalid/notion/synthetic-notion-id-013) and all six child databases/9 rows remain private evidence under the connector draft contract. They have not been trashed. Owner may delete that exact labeled root and descendants later; no cleanup should target existing workspace pages. Preserve local artifacts regardless.

## Primary sources

- [Create database](https://developers.notion.com/reference/create-database), [property schemas](https://developers.notion.com/reference/property-object), [2025 data-source migration](https://developers.notion.com/guides/get-started/upgrade-guide-2025-09-03).
- [2026 migration](https://developers.notion.com/guides/get-started/upgrade-guide-2026-03-11), [request limits](https://developers.notion.com/reference/request-limits), [files](https://developers.notion.com/guides/data-apis/working-with-files-and-media), [Free block policy](https://developers.notion.com/reference/workspace-block-limits).

All online sources accessed 2026-10-16; Notion docs are live/versioned API documentation, not a cloned source snapshot. Experiment files are confined to `research/phase-1/experiments/notion/`.


## Phase 1 disposition after live-collaboration decision

| Role | Disposition | Evidence and limits |
|---|---|---|
| A. Primary operational database | Reject for the specified multi-diner live financial editing workflow | NUMBER did not enforce integer-sen values; revision-complete labels were manually managed; no atomic multi-page financial transaction or app role/revision enforcement demonstrated. These cannot be supplied by simply making a Notion view editable. |
| B. Synchronized reporting/storage layer | Supported as a reviewed, asynchronous copy | Six entities, multiple payers, file/relations and small integer values round-tripped. Copy completeness/retry state needs an independent authority/adapter. |
| C. Optional export/integration | Recommended delivery contract for B | User's dining/settlement workflow must remain usable when Notion is disconnected, restricted or delayed. Exact account plan and raw REST contracts still need verification before a production adapter. |

Live collaboration should operate against the shared canonical meal authority; Notion remains downstream. Local-only OCR does not prohibit an optional Notion archive copy, but exporting receipt images is a separate explicit reporting/retention choice. No real receipt was uploaded in this experiment.
