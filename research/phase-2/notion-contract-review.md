# Independent Notion contract review

2026-10-16, Asia/Kuala_Lumpur. Reviewer: delegated Notion workstream. **Advisory evidence for the main orchestrator; this review does not authorize a phase transition.** No Notion write, account action, private-data export, credential access or paid service was performed.

## Disposition

**Conclusion:** raw Notion integration can be deferred while a manual-first collaborative core proceeds. Keep Notion in the product objective as an optional asynchronous reporting adapter, with a separate acceptance gate before claiming that adapter works. A disconnected export must not block allocation, finalization or settlement. This is sequencing of the agreed objective, not cancellation of Notion integration.

The evidence supports B (a downstream copy), delivered as C (an optional integration). It does not support A (the primary financial database). The main orchestrator must combine this finding with the domain, collaboration and security reviews; this document establishes no readiness for public deployment.

## Actual artifacts reviewed

- [Phase 1 validation](../phase-1/notion-validation.md), [architecture](../phase-1/architecture-decision.md), [requirements](../phase-1/requirements.md).
- [Retry experiment source](../phase-1/experiments/notion/retry_simulation.py), SHA-256 `22aca725a826064a4e9b89bfa5ac8d7c6dd22c23a698b54331fca646c1f13791`; [recorded results](../phase-1/experiments/notion/simulation-results.json).
- [Connector schemas](../phase-1/experiments/notion/connector-evidence.json) and [redacted roundtrip traces](../phase-1/experiments/notion/connector-roundtrip.json), including number/formula/attachment observations.

**Local recheck:** the unchanged retry script's `main()` was executed with `ROOT` redirected to a temporary directory inside `research/phase-2/`: 12 checks passed, zero failed. Original Phase 1 results and SQLite file were preserved. An initial OS temporary-directory attempt failed with sandbox file-access errors; rerunning inside the workspace succeeded. This environment limitation is unrelated to Notion API behavior.

**Experimental boundary:** the retry script imports no HTTP client/Notion SDK and uses a SQLite fake remote. Its twelve checks cannot prove authenticated REST behavior, network concurrency, eventual visibility, distributed locking or idempotency. Connector DDL/SQL is also not a raw REST contract. Phase 1 states these limitations explicitly; no material contradiction was found in those claims.

## Current verified documentation facts

Context7 was resolved afresh to `/websites/developers_notion_reference` (official reference, High reputation). Three scoped queries covered limits/retries, schema/number values and files. The linked official pages were accessed on 2026-10-16; these are live documentation, not a repository revision.

| Fact | Consequence |
|---|---|
| JSON number values are the Number property representation. The inspected schema exposes formatting, not an integer-sen constraint. | Integer validation and all financial arithmetic belong in the canonical application. [Number properties](https://developers.notion.com/reference/page-property-values). |
| Data sources have their own schemas and paginated queries; the API version header is required. The current file reference lists `2026-03-11`. | Separate database/container IDs from data-source IDs, pin a tested API version, and fully paginate reconciliation. [Create data source](https://developers.notion.com/reference/create-a-data-source), [query](https://developers.notion.com/reference/query-a-data-source), [file upload](https://developers.notion.com/reference/upload-file). |
| Free/Plus connections have 180 requests per 60-second window; a separate workspace budget also applies. Notion can save a write that returns 503. Responses may identify committed resources/children and give retry guidance. | Queue writes, respect the actual Retry-After, bound retries and reconcile uncertain outcomes before recreation. A successful local operation ID is not a Notion uniqueness guarantee. [Request limits](https://developers.notion.com/reference/request-limits). |
| Multi-member Free workspaces have 1,000 lifetime blocks for internal/restricted-workspace OAuth connections; single-member Free is unlimited. Guests are excluded from member counts. PAT and broadly installable OAuth exceptions exist; MCP enforcement differs. Deletion does not restore capacity. | Inspect the actual authorization model/plan before estimating capacity. A page is a block; “unlimited meals on Free” is not established. Plan blocks are actionable failures, not retry loops. [Block limits](https://developers.notion.com/reference/workspace-block-limits). |
| Free files are limited to 5 MiB. Indirect import needs a publicly accessible URL. | Do not expose a private receipt URL to make an import work. Check the workspace byte limit before any authorized upload. [Files and media](https://developers.notion.com/guides/data-apis/working-with-files-and-media). |
| Uploaded files attach using a completed `file_upload` object; readback uses `file`. Hosted download URLs expire and should be refreshed. Updating a Files property replaces its list. | Preserve intended existing attachments, never treat signed download URLs as permanent identifiers, and redact them in logs. [File objects](https://developers.notion.com/reference/file-object), [page properties](https://developers.notion.com/reference/page-property-values). |

**Live evidence inherited, not repeated:** Phase 1's synthetic connector probe accepted `Paid Sen = 2000.5` and restored it to 2000 before calculation. Small integer roundtrip and six related entities were observed, but arbitrary precision and REST authorization were not. Formula creation did not prove evaluation: connector SQL rejected that formula column. No new account inspection was needed to reverify the documentation claims above.

## Minimal export contract to preserve now

This is a proposed adapter boundary, not a final Notion schema or implemented integration.

1. Export an immutable, reviewed meal revision with stable app/entity IDs, currency, source revision, contract version, content digest and an explicit completeness manifest. Refer to actual payment/transfer facts independently from suggested settlements. Keep dining, funding, settlement and export states separate.
2. Include integer-sen subtotal, signed/explicit tax inclusion, service charge, discounts, rounding and authoritative total; receipt items, allocations, people, restaurant payers and confirmed settlements remain distinct. Quantities/weights use exact numerator/denominator pairs. Validate missing/null values and every monetary leaf before serialization; reject booleans/fractions and unsafe transport magnitudes. No authoritative Notion formula calculation.
3. Export states: queued → sending → complete, or uncertain/blocked/failed. Mark a revision complete only when every required entity/relation operation is confirmed. Failures never alter the canonical balances. Corrected revisions retain real payments and produce a new projection revision.
4. Persist immutable operation identities/digests and destination mapping. Resolve uncertain writes using committed IDs when supplied; otherwise inspect fully paginated matching identities and content. Zero matches after an ambiguous write do not establish non-commit; duplicates require reconciliation. Serialize workers per destination/operation. Do not describe this as guaranteed exactly-once delivery.
5. Start with one-way canonical-to-Notion financial fields; external edits cannot silently change liability. Put optional Notion-owned notes in an explicitly separate field. Validate schema drift and report stale/partial copies rather than overwriting arbitrary user fields.
6. Default to metadata/amounts only until the owner explicitly chooses what personal details and receipt images may leave the controlled system. Local OCR consent is not Notion image-sharing consent. Do not embed private invitation URLs, participant session tokens or signed image URLs in exports/logs. Preserve source IDs without exposing access capabilities.

**Financial boundary caution:** the experiment validates top-level keys ending `_sen` in a narrowly fixed fixture. It does not recursively validate arbitrary nested export entities, missing required fields, row-level quantities or a full immutable snapshot. Its retry model uses a fake 17-second delay, not a production queue with jitter, complete error classification or worker leases. Those are implementation requirements, not reasons to reuse the throwaway script unchanged.

## Gate assessment for orchestrator review

| Gate | Finding | Blocking for what? |
|---|---|---|
| Notion role and independence | **PASS:** downstream optional copy follows the source evidence and agreed live-edit objective. | No Notion blocker for a local manual-first core. |
| Integers and accounting boundary | **CONDITIONAL PASS:** app-owned integer arithmetic is required; connector demonstrably does not enforce it. | Block any adapter that trusts Notion values or formulas as authoritative. |
| Projection recovery concept | **CONDITIONAL PASS:** local synthetic failure tests are reproducible; real API semantics remain untested. | Block a production-sync reliability claim; not independent core work. |
| Raw REST auth/schema/media | **FAIL / not executed:** no application credential or OAuth end-to-end test. | Block enabling/accepting the real adapter. Defer until authorized account participation is necessary. |
| Plan, volume, image consent | **OPEN:** actual workspace and user choices not verified. | Block personal/receipt export and capacity promises; not core manual meal validation. |

Before adapter acceptance: use an explicitly authorized disposable destination and proper account flow; pin the API version; test real create/read/update of all supported types, pagination, schema drift, permissions/disconnect, safe retry/uncertain recovery and redacted diagnostics. Test raster/media only after separate image-copy consent; do not deliberately exhaust quotas or claim a live failure model from mocks. Assess the actual Free-plan and expected row/file volume before enabling automatic history exports.

No paid service or account change is required to close the other project workstreams now. Escalation for credentials/privacy remains appropriate just before a real integration needs it. The orchestrator alone records the resulting project transition.
