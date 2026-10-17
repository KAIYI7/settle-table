# Notion integration decision

Status: recommendation drafted; current API constraints verified 2026-10-16 through official documentation and Context7 (`/websites/developers_notion_reference`). No Notion workspace was created or modified.

## Decision (inference)

Use Notion as an **optional, asynchronously synchronized reporting and receipt archive layer**. Keep the authoritative allocation/settlement ledger in the application database and complete interactive review there. This supports the user's durable storage hypothesis with a qualification: Notion is a durable *copy/report*, not the sole recovery source.

| Role | Assessment |
|---|---|
| Primary database | Reject for the general product: multi-record writes, interactive assignment latency, external availability and workspace limits complicate correctness. A personal single-user prototype could accept these constraints, but that is a narrower product. |
| Synchronized reporting/storage | Recommend: meal history, people balances, receipt attachment and final item shares are useful Notion views. Queue synchronization outside the save path. |
| Optional integration | Recommend packaging the sync layer this way: diners need no Notion account; a disconnected workspace must not prevent splitting or settlement recording. |

The evidence is the documented request/plan constraints below and the sample repository's substantial local submission journal. Notion API documentation reviewed here does not establish a transaction spanning pages, unique constraints on application IDs, or compare-and-swap writes; treat these capabilities as unavailable unless verified later, rather than silently assuming database semantics.

## Proposed reporting schema (design inference, not implemented)

Use six related data sources; choose database containers/views separately. Every exported row includes immutable `App ID`, `App revision`, `Synced at`, `Schema version`; keep the app-to-Notion page mapping in the application database.

| Data source | Key fields and relationships |
|---|---|
| Meals | Title/merchant, meal date/time and timezone, currency, participants relation, subtotal, tax/SST, service charge, discount magnitude, rounding adjustment, final total, receipt files, review status, settlement status, app link, receipt hash, allocation policy/version. Export integer minor-unit values as authoritative numbers; decimal currency values are presentation fields. |
| People | App person ID, display name, optional contact reference. A separate relation avoids forcing diners to become Notion workspace users. Optional Notion `people` property only for an actual mapped member. |
| Receipt Items | Meal relation, line index, raw label, corrected label, quantity and unit price when known, line amount, category, extraction/review provenance. Preserve uncertainty rather than inventing missing unit prices. |
| Item Allocations | Item relation, meal relation, person relation, exact weight or quantity share, allocated base minor units, allocated discount/tax/service/rounding components and final owed amount. One row per item/person; many diners may share one item. |
| Payers | Meal relation, person relation, amount paid minor units, payment time/method optional. Multiple rows allow multiple payers; payment is separate from consumption. |
| Settlements | From person, to person, amount minor units, currency, timestamp, status, related meal/group scope, app settlement ID. Distinguish proposed transfers from confirmed transfers. |

Store the printed totals separately from computed totals and reconciliation differences. Never infer an SST rate or whether service is taxable from an OCR guess. Formula/rollup views are useful displays, while the application's deterministic cent allocation remains authoritative. A compact export mode can write one meal page plus an attached item/allocation CSV or JSON instead of hundreds of row pages; it trades Notion filtering for lower write/block volume. Preserve the six-entity model in the source ledger regardless.

## Verified current constraints

- **API model:** since `2025-09-03`, a database is a container; rows/schema/query/relations address a specific data source. Persist both IDs and pin an explicit supported `Notion-Version`. `2026-03-11` is also documented; review its migration changes when selecting the SDK. Do not carry forward the inspected sample's legacy database-parent calls. [2025 migration](https://developers.notion.com/guides/get-started/upgrade-guide-2025-09-03), [2026 migration](https://developers.notion.com/guides/get-started/upgrade-guide-2026-03-11).
- **Free workspace:** one-member workspaces have unlimited blocks; multiple members/owners trigger 1,000 lifetime blocks and deletion does not restore quota. API creation enforcement (effective September 8, 2026) applies to internal/restricted-workspace OAuth connections after a three-day grace period; docs explicitly exempt personal access tokens and OAuth installable in any workspace. Guests are not members. Do not generalize internal-integration enforcement to every connection, or base product capacity on an exemption continuing indefinitely. [Block usage](https://www.notion.com/help/understanding-block-usage), [API enforcement](https://developers.notion.com/reference/workspace-block-limits).
- **Free features:** $0, 10 external guests, seven-day page history, one chart, basic button automations. Public API/webhooks are listed; paid database automations and Notion AI are unnecessary for our integration. [Pricing](https://www.notion.com/pricing).
- **Files:** Free upload maximum is **5 MiB per file** in API documentation (pricing says 5 MB). Query the connection bot's workspace limit in bytes; compress a legible receipt below that limit. Direct upload can attach a file to a page `files` property or image block; the 20 MiB single-part threshold does not override a Free workspace's lower allowance. [Files API guide](https://developers.notion.com/guides/data-apis/working-with-files-and-media).
- **Rate/payload:** Free/Plus connection budget is 180 requests per 60-second window; a separate workspace budget can also throttle. Handle 429/529 and `Retry-After`; ambiguous failed writes need reconciliation before retry. Requests have 500 KB/1,000-block bounds; a relation write is limited to 100 related pages in one request, not 100 lifetime relations. Paginate large properties. [Request limits](https://developers.notion.com/reference/request-limits).

## Synchronization design (inference)

1. Commit an approved meal revision and an outbox entry atomically in the application database. Preserve the receipt original in controlled storage and a checksum; upload a compressed reporting copy when enabled.
2. A worker validates permissions/schema and upserts mapped pages, creating People/Meal/Items before dependent rows. Track each operation and revision, errors and uncertain outcomes. Notion app IDs are application deduplication keys, not assumed unique constraints.
3. Serialize per-meal exports and publish a `Complete revision` marker only after all rows are linked. Readers can distinguish pending, complete and failed exports; retain retry/reconcile controls.
4. Queue and bound retries, honor server timing, pause on permission/schema/plan failures and reconcile timeouts before creating duplicate pages. Deletion/disconnection does not delete the canonical ledger.
5. Initially one-way app → Notion. Notion-owned notes/tags remain editable; application-owned amounts/allocations are regenerated. Bidirectional amount edits require a later explicit conflict/version design and should enter review, never silently change balances.

Store integration secrets server-side, restrict shared pages/data sources, avoid public receipt URLs for convenience, and document retention/deletion expectations. These are concrete requirements of the proposed optional integration, not features already implemented.

Notion-hosted download URLs expire (documented as one hour); persist file/page identity and retrieve fresh URLs, not a signed URL as permanent evidence. File-list updates replace the list, so preserve existing files explicitly. [File object](https://developers.notion.com/reference/file-object), [page property values](https://developers.notion.com/reference/page-property-values). If bidirectional notes are later needed, webhook events are change signals rather than complete changed content; retrieve current state and deduplicate/reconcile events. [Webhook delivery](https://developers.notion.com/reference/webhooks-events-delivery).

Capacity illustration (assumption): a meal with 20 items, 40 allocation rows, two payer rows and one meal row creates at least 63 row pages before settlements/new People/attachment blocks. Full-detail export can therefore exhaust a nearly empty 1,000-block multi-member Free workspace in roughly 15 such meals; actual quota use depends on existing content and representation. This motivates compact export and makes the personal-versus-team workspace question material.

## Conflicting evidence and limitations

- Historical guidance of “3 requests/second” is less precise than current windowed budgets. Use the accessed current documentation, not hard-coded historical assumptions.
- Pricing uses MB; developer docs use MiB and expose byte limits. Use the bot-reported byte maximum.
- The inspected automation intentionally pins notion-client 2.2.1 for its old contract, while current docs recommend data-source IDs. Its recovery pattern is useful; its API shape is not the new baseline. See [source inspection](repositories/notion-expense-automation.md).
- No live Notion API calls, account-plan inspection, database creation, webhook tests or round-trip file tests were performed. Confirm workspace membership, shared resources, expected diners/receipt volume, consent and desired Notion edit direction before implementation.
