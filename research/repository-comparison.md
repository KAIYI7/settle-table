# Repository comparison matrix

Access date **2026-10-16**. All seven rows are source-inspected candidates, not README-only assessments. Exact full revisions, file evidence, detailed domain/UX/error/test/cost observations and limits are in the linked reports. Tests/applications were not executed. “Recent” reflects commits, not support quality.

| Candidate / snapshot | License / activity | Receipt and correction | Domain / fees / money | Main reuse decision |
|---|---|---|---|---|
| [BillSplit](repositories/billsplit.md), `65f3b1c` Jul 30 | MIT; ongoing updates, 85 reachable commits | Hosted vision → editable item wizard; manual entry; no confidence gate or full receipt reconciliation | Local people/item chips; tax+tip equal by headcount; Decimal but first-person residue; no payer/settlement ledger | Strong UX pattern; selected MIT pieces possible, do not fork arithmetic/persistence wholesale |
| [Spliit](repositories/spliit.md), `5dac411` Oct 13 | MIT; active recent domain/test work | Hosted vision total/title/date/category only; editable expense; no receipt items | Groups/weights; integer minor units + deterministic largest remainder; one payer; reimbursement/net balances; no charge entities | Best group/conservation reference; already addresses precision hypothesis |
| [SplitPro](repositories/split-pro.md), `3583568` Oct 15 | MIT; active recent commits/tests | Compressed attachments only, no OCR | Account/group model; BigInt; broader split modes and settlement events; signed net rows, single payer; no item/charge schema | Useful settlement/currency patterns; too broad and mismatched for first shell |
| [Notion automation](repositories/notion-expense-automation.md), `0b22160` Sep 24 | No explicit license; recent redesign | Text PDFs + text LLM, terminal review; no photo OCR | Two-person/CAD/float percentage expenses; local journal → Notion; no dining items/settlement ledger | Reference-only recovery/outbox pattern; old API/Windows incompatibility; claimed coverage conflicts with source |
| [ReceiptIQ](repositories/receiptiq.md), `86d72cf` Sep 22 | No license; two commits | RapidOCR + deterministic rules; optional configured LLM every receipt; inspect-only UI | SQLite extraction records/float; no groups/assignment/settlement; MYR/SST parser gaps | Reference-only extraction decomposition; independently implement/benchmark |
| [Ai-bill-splitter](repositories/ai-bill-splitter.md), `8a89dd9` Sep 8 | README MIT label without full grant; one commit | Hosted vision + editable review; self-rated scores, sample fallback; ID/contract defects | Proportional fees in concept, float arithmetic, quantity double-counting; no real payer/settlement model | Ambiguous-license reference-only; reject fork/math code |
| [Malaysian Receipt Splitter](repositories/malaysian-receipt-splitter.md), `766b2c9` Feb 1 | MIT; shallow latest snapshot | Paddle OCR + local/cloud LLM every receipt; corrections; Unicode stripping/mock fallback | MYR, proportional SST/service; float independent rounding, quantity undercount; no persistence/settlements | Valuable local/Malaysian counterexample; borrow patterns, reject present core |

## Cross-project findings (inferences)

- No candidate supplies a complete correct receipt → shared item allocations → explicit charges → multiple payers → confirmed settlements → resilient Notion pipeline.
- BillSplit's wizard, Spliit's normalized group behavior/conservation and SplitPro's settlements are complementary **ideas**. Their data models are not plug-compatible modules.
- ReceiptIQ supports a local OCR/parser decomposition, but none of the inspected implementations demonstrates the proposed calibrated confidence-gated cloud fallback.
- All apparent per-person “owes” summaries are not equivalent to a funded ledger. Separate consumption from restaurant payments and actual peer transfers.
- Declared licenses enable selective review, not automatic dependency/fixture/model clearance. See [licensing](licensing-and-reuse.md).
