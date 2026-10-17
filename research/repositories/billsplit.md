# Nutlope/billsplit — source inspection

Status: inspected; access date **2026-10-16**. Verified facts below come from the tracked source at [65f3b1c966a88aa6c7c8cd4edb49dd9af6eb1cc6](https://github.com/Nutlope/billsplit/commit/65f3b1c966a88aa6c7c8cd4edb49dd9af6eb1cc6). Full history fetched to temporary research checkout; 85 commits reachable from HEAD, no tags returned. No application code copied to TabWise and no upstream application executed.

## Decision

**Inference:** strong reference for a small receipt-review and item-assignment wizard, and a possible source of selected MIT components. It is not a ready group-expense ledger or a correct Malaysian fee-allocation engine. A wholesale fork would inherit substantial missing domain behavior.

## Verified facts and evidence

| Dimension | Source finding |
|---|---|
| License / reuse | Root [LICENSE](https://github.com/Nutlope/billsplit/blob/65f3b1c966a88aa6c7c8cd4edb49dd9af6eb1cc6/LICENSE) is MIT, copyright 2025 Riccardo Giorato. Source reuse permitted subject to retaining notice/license; separately audit dependencies, images and fixture rights. |
| Maintenance | Latest commit 2026-07-30 migrates model, modernizes dependencies and hardens uploads; earlier commits 2026-07-01, 2026-02-23, 2026-01-27 update links/models. Source activity exists, but commits alone do not establish support SLA or maintainer capacity. |
| Stack | [package.json](https://github.com/Nutlope/billsplit/blob/65f3b1c966a88aa6c7c8cd4edb49dd9af6eb1cc6/package.json): app version 0.1.0; TypeScript, Next 16.2.11, React 19, Tailwind 4, React Hook Form, Zod, Decimal.js, Together SDK, AWS S3, optional Braintrust tracing, Plausible. Versions are repository facts, not endorsed new-project choices. |
| Architecture | Client wizard at `src/app/app/page.tsx`: intro → editable items → people/assignment → summary. Next route handlers sign S3 uploads and call vision provider. No relational domain backend. |
| Domain model | [types.ts](https://github.com/Nutlope/billsplit/blob/65f3b1c966a88aa6c7c8cd4edb49dd9af6eb1cc6/src/app/app/types.ts): bill business/date/items/subtotal/tax/tip/people/equal-split flag. Item has ID, name, Decimal price, assigned person IDs. Person is ID/name only. No persistent group, payer, payment, settlement, currency, quantity or adjustment entities. `subTotal` is declared but total calculation sums items. |
| Image flow | `UploadOrManualBill.tsx` → `client-receipt-upload.ts` → `/api/s3-upload` → direct presigned S3 POST → signed download URL → `/api/vision` → Together vision. `image-upload.ts`: 15 MiB, PNG/JPEG, extension/MIME/size checks, UUID object keys, upload expiry 5 min/download 10 min. S3 policy bounds length and headers. `api/vision/route.ts` finally removes matching receipt object on success/failure. Delete failure falls back to overwriting zero bytes in `s3-receipt-storage.ts`. |
| OCR / extraction | [scrapeBill.ts](https://github.com/Nutlope/billsplit/blob/65f3b1c966a88aa6c7c8cd4edb49dd9af6eb1cc6/src/lib/scrapeBill.ts): direct hosted vision, no local OCR. Default in `vision-model-config.ts` is `Qwen/Qwen3.5-9B`. JSON-schema response, temperature 0, 1000 output-token cap; parse JSON and validate Zod. |
| Extraction schema | Business name/date nullable; array `{name, price:number}`; tax/tip nullable numeric amounts. No receipt total/subtotal in extraction schema, service charge/discount/quantity/currency/bounding boxes/confidence. Prompt strips quantity prefixes. Tip prompt says use middle suggested tip if multiple shown: a dangerous policy to carry into actual liability. |
| Error / confidence | Schema failures and provider failures throw; privacy-aware trace redaction and phase timings exist. No calibrated confidence, arithmetic reconciliation or escalation gate. Client uploader checks HTTP status; `UploadOrManualBill.tsx:65` reads vision response JSON without checking `response.ok`, catches mainly to console, with commented-out toast. `/api/vision` does not validate or restrict image URL before calling provider; matching host/key check governs cleanup only. |
| Human correction | `subpages/ReceiptItems.tsx`: edit/add/delete item names/prices and tax/tip; manual entry of business/date supported. User reviews all items before assignment. No side-by-side bounding-box correction or explicit approval audit trail. |
| Participants / assignment | `PeopleAndSplit.tsx`: add/remove people, name buttons per item, equal split toggle. Continue disabled with no people/blank names or unassigned items. Shared item split equally among selected IDs. Removing person does not visibly clean their IDs from every item; validity checks only array length. |
| Fees / discounts | [SplitSummary.tsx](https://github.com/Nutlope/billsplit/blob/65f3b1c966a88aa6c7c8cd4edb49dd9af6eb1cc6/src/app/app/subpages/SplitSummary.tsx): tax+tip divided **evenly by headcount**, not proportionally to consumed value. No discount or distinct service charge model. |
| Precision / rounding | Decimal.js arithmetic for totals and shares; each equal/item share rounds to 2 decimals; residual, possibly negative after rounding up, assigned to first person. This conserves totals for valid complete assignments but is order-biased rather than largest remainder. API extraction passes JS numbers before conversion. |
| Settlement | Summary reports each person's liability and clipboard text. No payer credits, balances over meals, debt optimization, settlement records, or paid status. |
| Persistence | `page.tsx:34-48` stores single `billFormData` JSON in browser localStorage. No database/auth/multi-user sync. JSON parse sets raw values back without rehydrating Decimal/Date; item prices later call `.dividedBy()` and tax `.plus()`. **Inference:** reload can break non-even split unless corrected values are reconstructed. Receipt image deliberately ephemeral in S3. |
| Notion | No Notion integration found in tracked source/dependencies. |
| Tests | Six tracked `*.test.ts` files cover upload signing/validation, vision cleanup, client upload, schema/provider calls and privacy tracing; Evalite receipt fixtures/scorer under `evals/`. No split arithmetic, Decimal persistence hydration or end-to-end UI tests found. `test` is Evalite watch; `test:unit` Vitest. No coverage percentage inferred and tests not run in this source-only inspection. |
| Mobile UX | `app/app/layout.tsx`: narrow `max-w-[350px]`/`md:max-w-[388px]`, full-width buttons, wrapped name chips and upload preview. Source supports a phone-oriented wizard; no live accessibility or device check performed. Native share still TODO; dollar glyph hard-coded. |
| Services / costs | Hosted Together vision per extraction; S3 requests/storage/transfer; web hosting; optional Braintrust/Plausible. `vision-model-config.ts` embeds $0.17 input/$0.25 output per million tokens, which is **code's estimate, not independently verified current provider pricing**. No paid API call made. |

## Reuse / avoid

- Reuse ideas: short guided workflow, manual entry escape route, editable extraction before assignments, visible shared-item participant chips, private short-lived receipt uploads, trace redaction and cleanup tests.
- Candidate MIT code reuse only after targeted review: upload validation/policy helpers or isolated UI, with notices retained. Copying their stack wholesale is unnecessary.
- Avoid: equal distribution of fees as universal policy; suggested tip guessing; discarding quantity; lack of receipt-total reconciliation; implicit USD; raw localStorage object restore; trusting any nonempty assignment list; console-only user errors; unauthenticated provider endpoint without abuse controls.

## Unresolved / limits

No Malaysian receipt benchmark, accuracy claims or inference latency independently measured. Eval fixtures use remote S3 images and are not proof of Malaysian suitability. Retention lifecycle after abandoned uploads, abuse/rate controls and deployment configuration require review before reuse. Local source inspection does not establish live app behavior or production reliability.
