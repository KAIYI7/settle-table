# Kirtiraj01/Ai-bill-splitter — source inspection

Status: inspected; access date **2026-10-16**. Exact revision [8a89dd97a079fc3c5ce024985d500f9d052bc955](https://github.com/Kirtiraj01/Ai-bill-splitter/commit/8a89dd97a079fc3c5ce024985d500f9d052bc955). Full history has one commit, 2026-09-08; no tags returned. Temporary checkout only; no app source copied into TabWise, dependencies not installed and application not executed.

## Decision

**Inference:** useful reference for a proportional fee breakdown and visual correction affordances, but too inconsistent to fork. Several static source defects undermine its “production-grade” header. Reuse is **blocked pending license clarification**: README labels MIT but repository contains no complete MIT grant/copyright notice or LICENSE file. Preserve this ambiguity rather than describing it as definitively MIT-licensed or ignoring the README claim.

## Verified facts and evidence

| Dimension | Source finding |
|---|---|
| License | [README.md](https://github.com/Kirtiraj01/Ai-bill-splitter/blob/8a89dd97a079fc3c5ce024985d500f9d052bc955/README.md) ends “MIT License. Built with …”; no tracked LICENSE/COPYING/NOTICE. This is an explicit license label but incomplete grant evidence. Conservative policy: conceptual reference only until upstream supplies full terms; no source copying in this phase. |
| Activity / version | Single repository commit; backend API/header version 3.0.0 while frontend package version 1.0.0; no release tags. Version labels do not establish three maintained releases. |
| Stack / architecture | `backend/main.py` monolithic Python FastAPI/Pydantic; `requirements.txt` includes google-genai; React 18/Vite 5/Tailwind 3 frontend, Context state, three screens (upload/review/assign). Stateless API; no database. Repository dependency versions recorded as facts, not proposed choices. |
| Schema | [backend/main.py](https://github.com/Kirtiraj01/Ai-bill-splitter/blob/8a89dd97a079fc3c5ce024985d500f9d052bc955/backend/main.py): item UUID/name/quantity/price/unified confidence/name confidence/price confidence/category; bill restaurant/date/currency/items/subtotal/tax/service/discount/printed total; members ID/name; assignments map item index or ID → member IDs. Split outputs per-person item/fee breakdown, audit trail, tip suggestions and shareable text. No payer/settlement entities. |
| Receipt flow | Client accepts up to 2 photos, but `frontend/src/lib/api.js` sends **only first file** to `/api/extract`; backend separate `/api/extract-multi` supports up to 5 images and prompt-based overlap deduplication. 10 MiB/file backend limit, MIME `image/*` check; no magic bytes, image decode verification or empty-file rejection found. Images forwarded in memory, no server storage. |
| OCR / vision | `_extract_via_gemini`: direct Google Gemini 2.5 Flash structured schema or OpenRouter JSON vision calls, based on key prefix. OpenRouter attempts Gemini 2.5 Flash, Gemini Flash 1.5 then GPT-4o-mini. No local OCR. `requests` imported by OpenRouter branch but absent from requirements. Blocking calls inside async function. |
| Confidence / errors | Prompt asks model to self-rate field confidences; item defaults 0.95. Quality score 70% mean+30% minimum; warnings for <0.7, duplicate name, zero price and total mismatch. These are heuristic/self-reported scores, not calibrated probabilities. Provider exceptions yield 502 with exception text; no key (or no returned usable result) falls through to **plausible sample bill**, rather than explicit extraction failure. |
| Correction UI | `ReviewScreen.jsx` edits restaurant/item name/qty/price/charges/printed total; removes items; highlights low name/price confidence; displays computed-vs-printed mismatch. No item-add flow found. Continue requires ≥2 members/items but does not require reconciliation. |
| Participant model | UI 2–7 members, case-insensitive duplicate name check; Context generates IDs and cleans assignments when member removed. Backend requires only nonempty member list. No shared group history/authentication/invitation. |
| Assignment | `AssignScreen.jsx`: chips/checks per item and Everyone shortcut; nonempty assignment needed by UI. Backend allows index or item-ID keys, silently defaults missing/invalid assignments to all members; no duplicate assignee/member-ID validation found. |
| Tax/service/discount | Backend allocates these by raw consumed-value ratio; extra tip percentage is based on printed total. Equal sharing of each item's computed line cost. No item-specific taxable basis, fee dependency/order or coupon eligibility; fee sign/range constraints absent. |
| Precision / rounding | Python floats and JS Number. Round line cost to cents, raw shared fractions retained then individual totals rounded; no residual redistribution. Optional ceil/nearest whole-unit rounding. Reconciliation accepts ≤0.05 difference, so a missing cent can still claim success. Item-breakdown rounded sums can disagree with displayed subtotal/total. |
| Settlement | Per-person “owes” is consumption liability only: no payer credits, multi-meal netting, settlement transaction or paid status. No debt optimizer. |
| Persistence / Notion | React in-memory state only; no localStorage/backend DB, auth or Notion integration found. Refresh loses work; receipt image not durable. |
| Tests | No tracked automated test files, test script or CI workflow found. README features and production-grade label are not validation. Static source traced; no runtime pass claimed. |
| Mobile UX | Tailwind `px-4`, max widths, wrapped member chips; fee grid responsive (`grid-cols-2 sm:grid-cols-4`). Receipt row 12-column compact inputs, no rendered device/accessibility check. Currency formatting always `$`, despite backend currency field. |
| Services / costs | Requires web frontend+Python backend and Google/OpenRouter vision inference; provider billing/free quotas not verified by this source review. No zero-cost extraction fallback: demo data is not OCR. OpenRouter fallback can create multiple provider attempts; no budget/rate controls. |

## Critical source contradictions

1. **Line-total versus unit-price bug:** `_PROMPT_BASE` explicitly defines price as total line cost, not unit price; `_build_extract_response`, `/api/validate`, `/api/split` and frontend `billMath.js` multiply `price * quantity` again. Example: quantity 2, line total RM20 becomes RM40. This is directly established by source; exact runtime outcome depends on provider output conforming to prompt.
2. **Lost item identities:** `api.js` maps each extracted item to `{name, quantity, price, confidence}` and discards `id`, `name_confidence`, `price_confidence`, date/currency and other response metadata. `BillContext`/review/assignment use `li.id`, so all items are undefined-ID in that client path. **Inference:** editing/removing an undefined-ID item can affect all items, and assignment key `undefined` cannot map to backend regenerated UUIDs/indexes; backend can silently split everyone. No normalization restoring IDs found.
3. **Confidence highlighting bypass:** API keeps only unified confidence while review checks per-field scores with helper that requires a numeric value. Hence amber field warnings can disappear. Restaurant confidence checked by UI is not an extracted field.
4. **Multi-image promise mismatch:** upload UI accepts 2 images, API intentionally only uploads first; backend multi endpoint unused.
5. **Result contract mismatch:** backend returns `raw_subtotal`, summary UI reads `subtotal_share`, formatted helper converts undefined to zero; plausible but incorrect displayed subtotal.
6. **Missing-key behavior:** convincing sample bill returned in ordinary extraction route; consumers cannot distinguish genuine extraction. Do not replicate this fallback in a real financial workflow.

## Reusable ideas / avoid

Independently implement: explicit printed/computed totals, editable uncertain fields, separate service/discount amounts, proportional fee breakdown, transparent arithmetic audit and Everyone shortcut. Reject direct math/UI module reuse: license uncertainty, money/quantity errors, identity loss, inconsistent contracts, uncalibrated confidence, USD defaults, sample data fallthrough and silent assignment fallback.

## Unresolved / limits

No Malaysian receipt benchmark, provider availability/price or live frontend behavior verified. Confidence claims are prompt outputs and not experimentally calibrated. Runtime tests could refine defect severity but are unnecessary to rule out forking at this phase. Full source inspection is sufficient to reject copying this arithmetic engine.
