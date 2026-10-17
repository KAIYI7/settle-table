# Spliit source inspection

Status: complete source review; runtime and hosted UX not exercised. Accessed **2026-10-16**. Labels: **Fact** = inspected source/history; **Inference** = conclusion from that evidence; **Open** = unverified.

## Snapshot and reuse

- **Fact:** official upstream https://github.com/spliit-app/spliit ; inspected `5dac4119f0441cb945756f8c92911de6f312a1a3` (HEAD commit 2026-10-13, locale additions). Read-only temporary checkout: `%TEMP%/tabwise-domain-research/spliit`; no dependencies installed or application launched.
- **Fact:** [MIT license](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/LICENSE), copyright 2023 Sebastien Castiel. Copying/modifying/distributing is permitted subject to preserving copyright/permission notices in copies or substantial portions. This repository-level finding does not clear third-party assets/dependencies separately.
- **Fact:** `git log -8` shows substantive recurrence, document preservation and recent-group fixes plus dependency/translation work on Oct 10–13. `git ls-remote --tags` exposes `1.30.0` at `28d360d2372b51782d8be92de03d73e220b19dc6`; inspected HEAD is newer. `package.json` says `0.1.0`, so that is not a trustworthy product-release indicator. No claim is made about GitHub issue responsiveness or CI success.
- **Inference:** strong maintained general expense-domain reference and potentially reusable MIT accounting helpers; not an existing receipt-item splitter ready to fork unchanged.

## Verified architecture and model

| Dimension | Source findings |
|---|---|
| Language/framework | TypeScript; Next.js `^16.3.8`, React `^19.3.0`, Tailwind, tRPC, React Query, Prisma `^7.10.0`, PostgreSQL; package engine Node >=24/npm >=11. These are manifest ranges, not independently installed/resolved versions. [Manifest](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/package.json). |
| Layers | App Router UI → tRPC procedures → `src/lib/api.ts` → Prisma/Postgres. Separate server action invokes vision extraction. `src/lib/shares.ts` centralizes shared allocation used by balances/exports/previews. |
| Group/participants | `Group` owns `Participant` rows; participants are group-local identities rather than registered accounts. One group currency plus optional original-currency/rate on an expense. |
| Expense | One `paidBy` participant, total integer `amount`, category, date, `paidFor` rows with integer `shares`, split mode, notes, documents, recurrence and reimbursement flag. No `ReceiptItem`, item-owner allocation, tax/service/discount fields, multi-payer payment table or Notion entity in inspected schema. |
| Persistence/audit | PostgreSQL normalized relations, migrations, `Activity` records, optional scheduled group deletion/restoration, document URLs/dimensions; recent groups/default split preferences live in browser storage. |
| Access model | tRPC context is empty and procedures use `baseProcedure`; knowledge of a group ID is effectively the access mechanism. Group-local identity is not authenticated attribution. Membership checks on expense participants prevent foreign group IDs, but do not provide account authorization. |

Sources: [schema](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/prisma/schema.prisma), [API/persistence](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/src/lib/api.ts), [tRPC context](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/src/trpc/init.ts), [create procedure](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/src/trpc/routers/groups/expenses/create.procedure.ts).

## Receipt flow, extraction and correction

**Fact:** optional receipt UI selects JPEG/PNG with a 5 MiB client limit → presigned S3-compatible upload → image URL sent by server action to configured OpenAI-compatible endpoint → summary preview → editable expense creation form. Receipt itself can be retained as an expense document. Narrow screens use a drawer, wider screens a dialog.

**Fact:** extraction schema is exactly `{amount:number, categoryId:string, date:string, title:string}`. It extracts the total and guesses category/date/title, **not line items**. Strict JSON schema is sent to the model and the response is parsed again with Zod. Runtime feature gating and allowed-upload-URL validation occur server-side. Model defaults to `gpt-5-nano`, with configurable model/base URL/API key. No local OCR, OCR boxes, per-field confidence, calibrated accuracy measure, deterministic receipt parser or reconciliation against item subtotals was found.

**Fact:** malformed/missing model content returns nullable fields; upload/extraction exceptions show a retry toast; unknown fields get visible placeholders and the next page permits correction. Inspection found a null-conversion edge: after parse failure, `Number(parsed?.amount)` is `NaN` and returns `null`; when a model explicitly returns a schema-valid numeric zero the preview treats it as unknown via truthiness. Errors from model API calls propagate to the UI catch.

Sources: [receipt server action/schema](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/src/app/groups/%5BgroupId%5D/expenses/create-from-receipt-button-actions.ts), [receipt UI](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/src/app/groups/%5BgroupId%5D/expenses/create-from-receipt-button.tsx), [environment/defaults](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/src/lib/env.ts), [editable expense form](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/src/app/groups/%5BgroupId%5D/expenses/expense-form.tsx).

## Splits, precision and settlements

- **Fact:** split modes EVENLY, BY_SHARES, BY_PERCENTAGE, BY_AMOUNT. Write validation requires amount shares to sum to amount and percentage basis points to total 10000; selected participant shares must be positive. Amount is persisted as Prisma `Int` (32-bit database type), not floating currency units.
- **Fact:** current `getExpenseShares` uses floor + **largest remainder** apportionment, stable participant-ID sorting, and expense-ID seeded rotation for ties; handles negative amounts. Allocation sums to the expense even if legacy amount/percentage weights are inconsistent, because it normalizes weights. Zero-total legacy weights return all zero (explicit exception to conservation; requires validation/repair).
- **Fact:** balances are `paid − paidFor`; reimbursement expenses move balances using the same accounting. Suggested repayments pair positive and negative balances using stable ID ordering so paying one suggestion does not arbitrarily reshuffle the remainder. This is a heuristic for valid payments, not proof of a globally minimum transaction count.
- **Fact:** no first-class proportional tax/service/discount allocation or item assignment exists. Single-payer expense limits direct reuse for meals paid by multiple people.
- **Inference:** the hypothesis that SplitPro is required to fix Spliit's rounding is **rejected for this revision**. Spliit already demonstrates conserving integer allocations; its central pure helper is a better pattern than independent rounding of each person's total. For a new domain, reject inconsistent legacy data visibly rather than silently normalizing exact amounts.

Sources: [allocation algorithm](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/src/lib/shares.ts), [schemas](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/src/lib/schemas.ts), [balances/repayments](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/src/lib/balances.ts).

## Tests, mobile, services and limitations

- **Fact:** inspected Jest tests cover uneven/negative splits, all split modes, deterministic ordering, rounding residue, randomized balance conservation and full settlement. Receipt-action tests cover malformed output, missing content, strict-schema/model configuration and invalid upload URLs; the server feature gate was inspected in source, but a disabled-feature receipt test was not found in that test file. Playwright scenarios include split modes, reimbursement, recurrence, currencies, PWA and group management; CI has unit, E2E and performance workflows.
- **Fact:** Playwright config runs **desktop Chromium at 1280×900**, explicitly avoiding mobile dialog/drawer branching. Responsive source/PWA manifest exist; this is not verified mobile browser quality or offline write support.
- **Fact:** required ongoing infrastructure is Node hosting + PostgreSQL; receipt documents add S3-compatible storage/traffic and vision extraction adds model usage. Optional analytics and scheduled cleanup add deployment work. AI/documents default off. No Notion integration found in `src`/Prisma inspection.
- **Open:** hosted uptime, model accuracy on Malaysian receipts, exact recurring vendor prices, dependency/asset license inventory, measured test coverage percentage and current CI pass status were not verified. Tests were **read, not executed**; dependencies were intentionally not installed.

Sources: [share tests](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/src/lib/shares.test.ts), [balance tests](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/src/lib/balances.test.ts), [receipt tests](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/src/app/groups/%5BgroupId%5D/expenses/create-from-receipt-button-actions.test.ts), [Playwright](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/playwright.config.ts), [PWA](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/src/app/manifest.ts), [CI](https://github.com/spliit-app/spliit/tree/5dac4119f0441cb945756f8c92911de6f312a1a3/.github/workflows).

## Reuse decision

**Inference:** borrow group-local guest identities, editable receipt confirmation, normalized expense/domain boundaries, deterministic apportionment and conservation-oriented tests. Consider carefully attributed MIT helper adaptation only after stack selection. Do not inherit unauthenticated group-link permissions for private receipt/Notion data, AI-only total extraction as a line-item OCR solution, singleton payer schema, blind normalization of inconsistent exact allocations, or a whole fork's recurrence/stats complexity merely to obtain a few domain functions.
