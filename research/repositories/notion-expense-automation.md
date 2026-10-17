# Notion Expense Automation source inspection

Status: source inspection complete; runtime verification limited as below. Accessed 2026-10-16. Research only; upstream code was not copied into the product.

## Reproducible evidence

- Official upstream: https://github.com/stefan-esquivel/notion_expense_automation_project
- Inspected HEAD: `0b22160559264ee34619fb8b660e5c8f577c8dd6`, authored 2026-09-24 (merge of architecture redesign).
- Temporary checkout: an ephemeral local checkout (path withheld); shallow clone. This path is an inspection cache, not a product dependency.
- Source permalinks below use this exact revision. GitHub metadata: default `main`, not archived, pushed 2026-09-29; HEAD commit dated 2026-09-24. This is recent activity, not proof of sustained maintenance. API tags response was empty. `CHANGELOG.md` calls version 2.0.0 **Unreleased**, with tag/publication pending.

## Verified facts

- Python CLI, not a mobile receipt-sharing application. `requirements.txt` pins pdfplumber, Pydantic, LangGraph, OpenAI and notion-client 2.2.1; comments explicitly retain the old Notion database API contract.
- `src/services/pdf_extractor.py` reads PDF text with pdfplumber, uses merchant/total/date rules, and optionally sends text to an LLM for line items. This is **not image OCR**: scanned photos need a separate OCR stage.
- `src/domain/models/receipt_item.py` intentionally omits quantity; name/float price/category only. `expense.py` has CAD float amount, one payer and percentage split records. It has no dining tax/service-charge/allocation schema.
- `src/workflows/langgraph/graph.py` routes ingest → extract → scan → optional augment → enrich → validate → review → revalidate → commit. Even high-confidence receipts pass human review.
- An extensive `test/unit`, `test/integration` and `test/e2e` tree exists. Test presence is not verified coverage or a passing run.

## Inspection matrix

| Dimension | Source-backed observation |
|---|---|
| License / reuse | No explicit license in README or LICENSE/COPYING/NOTICE file found in `git ls-tree -r HEAD`; GitHub repository metadata `license` is null. **Reference-only; do not copy source.** |
| Architecture | Typed domain models, services/LLM adapters and LangGraph nodes. `build_graph()` calls `compile()` without a persistent graph checkpointer; submission durability is provided separately by the journal. |
| Receipt input/image flow | Local folder/CLI PDF paths; PDF text extraction, filesystem receipt archiving and optional PDF upload. No camera, crop workflow or bitmap OCR engine in the inspected dependencies/services. Automated Gmail/folder triggers remain deferred according to changelog. |
| OCR / vision | LLM client defaults to `gpt-4o-mini`, sends text via chat completions, parses JSON responses; it is not image vision OCR. Active extract node always requests LLM item extraction when configured, rather than confidence-gating that call. |
| Structured schema | `Receipt`: misspelled `recipt_id`, vendor, transaction type, date string, optional float total, `ReceiptItem[]`; item = name, float price, optional category. Negative credits accepted, quantity deliberately excluded. `ExpenseSummary`: CAD amount, single payer, optional percentage `SplitDetail[]`. No per-field OCR evidence geometry. |
| Error / confidence | Required-field, positive amount, future date, unknown merchant and item-total checks. Composite score multiplies hand-chosen factors and LLM enrichment confidence: it is **not calibrated OCR probability**. Item mismatch is only advisory when beyond max(15% of total, $0.10). |
| Human correction | Terminal UI edits merchant/description/total/date, selects payer and one partner's percentage, previews Notion writes; review/revalidation loop. RED issues can be explicitly overridden: `ValidationResult.is_green()` accepts acknowledged keys of either severity. Thus comments saying all RED errors block are incomplete. No visual per-item assignment/correction canvas. |
| Participants/groups | Config maps exactly `YOUR_NAME` and `PARTNER_NAME` to Notion user IDs; one balance page. No reusable arbitrary group/member model. |
| Item assignment | No item-to-person allocation entity. Line items feed descriptions/categories; final split is an expense percentage owed by the other person. |
| Tax/service/discount | Final amount may include tax; no explicit SST/service/tax-base fields or proportional charge allocator. Negative extracted credits are preserved as items, but not modeled as scoped discounts. |
| Money / rounding | Binary float amounts/percentages and two-decimal display, without integer-minor-unit ledger or explicit remainder distribution. Notion rollups/formulas supply reporting balances rather than a verified settlement engine. |
| Settlement/debt | Two-person percentage expense reporting; no transfer ledger, multi-payer model or debt-minimization algorithm found in the inspected source. |
| Persistence | Notion Expense/Split Details pages and relations plus local PDF archive; local SQLite `SubmissionJournal` stores approved payload, receipt SHA-256/scope uniqueness and named operation status/result. Unix `fcntl.flock` lock serializes local submissions; not distributed uniqueness. |
| Notion integration | Direct File Upload API uses explicit `2025-09-03`; page calls use pinned notion-client 2.2.1 old database-ID contract. Per-operation journal distinguishes uncertain creates and reconciliation. Related pages are read/merged/updated, without concurrent-writer transaction or relation pagination. File upload errors are caught and return `None`, allowing expense creation without attachment; file size is read but not enforced, polling can finish without confirmed uploaded status. |
| Tests | Unit/integration/e2e source covers routing, extraction, input scenarios, retries and partial commit recovery. Upstream release notes report 452 pass, 11 skipped, 80.08% line coverage on macOS; this was not reproduced and conflicts with HEAD source as detailed below. No receipt image/Malaysian accuracy benchmark. |
| Mobile/responsive | CLI with Rich/Inquirer. No responsive web/mobile frontend; no UX validation performed. |
| Services/cost | Optional OpenAI text extraction/enrichment calls, Notion access/workspace plan and local machine/storage. No paid OCR service required, but text-free scanned PDFs are not supported by this path. No unit economics or token telemetry found. |

## Reusable ideas and exclusions (inferences)

Independently implement the **patterns** of reviewed immutable submission payloads, content-hash duplicate checks scoped to target workspace, operation journals, uncertain-write reconciliation and post-edit revalidation. Keep extraction separate from approved financial state. The next product does not need LangGraph just to implement this finite workflow; justify that dependency separately.

Do not reuse source without a license grant. Do not inherit the two-person/CAD/float model, uncalibrated confidence, 15% reconciliation tolerance, text-PDF assumptions, hard-coded Notion people mapping, raw whole-relation replacement, silent attachment failure or Unix-only locking. The future sync adapter needs current data-source APIs and workspace-aware file-size handling.

## Conflicting evidence and limitations

- **Coverage conflict:** `docs/RELEASE_VERIFICATION.md` states cleanup removed legacy `grocery.py` and reports passing tests. At inspected HEAD, `test/unit/test_receipt_item.py:5` still imports `src.domain.models.grocery`, which `git ls-tree` confirms absent. This implies collection failure absent an untracked compatibility module; do not treat the self-reported passing count as verified for this revision. No dependencies were installed or tests executed here, so this is a source-level contradiction, not an observed pytest result.
- **Blocking validation conflict:** model docstring says RED requires correction, while `is_green()` and `review_node.py` permit explicit RED override. The executable branch is the stronger evidence. A dining financial ledger should allow explicit documented adjustments but require conserved totals before finalization.
- **Platform limitation:** `submission_journal.py` imports `fcntl`, unavailable on native Windows. Upstream release verification exercised macOS, not this workspace's OS. This further limits direct adoption.
- **API version nuance:** the file upload constant is not evidence all page calls use that version. Dependency notes and constructor show separate old SDK/default contract; use current official Notion guides for the new integration.
- Clone was shallow; historical commit cadence and all issue discussions were not exhaustively reviewed. No credentials, live Notion writes, OpenAI calls, fixture execution or deployment audit were performed.

## Source references

- [Dependency pins](https://github.com/stefan-esquivel/notion_expense_automation_project/blob/0b22160559264ee34619fb8b660e5c8f577c8dd6/requirements.txt)
- [PDF extraction](https://github.com/stefan-esquivel/notion_expense_automation_project/blob/0b22160559264ee34619fb8b660e5c8f577c8dd6/src/services/pdf_extractor.py)
- [Workflow](https://github.com/stefan-esquivel/notion_expense_automation_project/blob/0b22160559264ee34619fb8b660e5c8f577c8dd6/src/workflows/langgraph/graph.py)
- [Domain](https://github.com/stefan-esquivel/notion_expense_automation_project/tree/0b22160559264ee34619fb8b660e5c8f577c8dd6/src/domain/models)
- [Notion writes/uploads](https://github.com/stefan-esquivel/notion_expense_automation_project/blob/0b22160559264ee34619fb8b660e5c8f577c8dd6/src/services/notion_api.py)
- [Submission journal](https://github.com/stefan-esquivel/notion_expense_automation_project/blob/0b22160559264ee34619fb8b660e5c8f577c8dd6/src/services/submission_journal.py), [retry policy](https://github.com/stefan-esquivel/notion_expense_automation_project/blob/0b22160559264ee34619fb8b660e5c8f577c8dd6/src/services/notion_retry.py)
- [Validation thresholds](https://github.com/stefan-esquivel/notion_expense_automation_project/blob/0b22160559264ee34619fb8b660e5c8f577c8dd6/src/workflows/langgraph/nodes/validate_node.py), [human overrides](https://github.com/stefan-esquivel/notion_expense_automation_project/blob/0b22160559264ee34619fb8b660e5c8f577c8dd6/src/workflows/langgraph/nodes/review_node.py)
- [Claimed verification](https://github.com/stefan-esquivel/notion_expense_automation_project/blob/0b22160559264ee34619fb8b660e5c8f577c8dd6/docs/RELEASE_VERIFICATION.md), [conflicting test import](https://github.com/stefan-esquivel/notion_expense_automation_project/blob/0b22160559264ee34619fb8b660e5c8f577c8dd6/test/unit/test_receipt_item.py), [tracked model tree](https://github.com/stefan-esquivel/notion_expense_automation_project/tree/0b22160559264ee34619fb8b660e5c8f577c8dd6/src/domain/models)
- [GitHub metadata](https://api.github.com/repos/stefan-esquivel/notion_expense_automation_project), [changelog](https://github.com/stefan-esquivel/notion_expense_automation_project/blob/0b22160559264ee34619fb8b660e5c8f577c8dd6/CHANGELOG.md)
