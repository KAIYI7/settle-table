# Technology options

> Historical authorization context: this report predates the user's orchestrator delegation on 2026-10-16. Requirements for user approval of numbered phases in this snapshot are superseded by [current governance](../docs/agents/governance.md) and the [transition ledger](../docs/agents/phase-transitions.md). Evidence and capability limitations remain valid to the extent stated; private-data, spending and product-policy consent are still separate.

Accessed 2026-10-16. **Status: recommendations only; no stack selected in code, dependency installation or app scaffold.** Repository stack evidence is in the individual reports. Context7 resolved and queried `/reactjs/react.dev`, `/vercel/next.js`, `/vitejs/vite` before this recommendation.

## Candidate stacks and trade-offs

| Candidate | Evidence-backed fit | Trade-off / decision |
|---|---|---|
| React + TypeScript + Next.js, relational ledger (PostgreSQL), optional OCR worker | Three maintained/reference apps use React/Next; their forms/chips/domain boundaries are relevant. Next can keep Notion credentials and API routes in the same server deployment while interactive receipt work remains client-side. Relational records match meals/items/shares/payments/settlements. | **Provisional preferred product stack** if browser access, durable groups and sharing are required. SSR is not a reason alone; secrets, authoritative writes and shared ledger are. Node server/DB operations required; CPU OCR may add a Python worker. Do not inherit an entire tRPC/Prisma/auth stack merely because examples use it. ORM/auth/UI library/version selection remains open. |
| React + TypeScript + Vite SPA, separate API | Vite's default build is statically hostable. A one-editor or local-first workflow can keep drafts/images in browser and benchmark Tesseract.js without a server OCR upload. | **Preferred alternative for a personal, mostly offline tool.** Notion synchronization and shared durable balances still need a secret-holding service; collaboration, routing/data loading and API boundaries must be chosen. Two deployable pieces once backend integration is real. |
| Python API + React/Vite frontend | Several receipt references separate a Python OCR API; local RapidOCR/Paddle runtime and parsing fit this process. | Strong if OCR dominates deployment constraints. More network/deployment boundaries, API contracts and two ecosystems from day one. Do not require it until the OCR benchmark demonstrates need over browser OCR. A later worker can be added to the preferred stack. |
| Native mobile shell + on-device OCR + sync API | ML Kit/Apple Vision offer device OCR; receipts can remain on device until explicit integration. | Best offline/native camera experience candidate; greater iOS/Android build/release/QA cost and native portability work. No evidence yet that it outweighs a mobile browser product. |
| Fork BillSplit / Spliit / SplitPro | Licensed existing UI or broad group ledger. | Each lacks essential dining entities or has mismatched allocation/storage/access semantics. Fork only if requirements pivot toward its existing primary product. See final path comparison. |
| Notion-only / Notion-first UI | Avoids owning some reporting UI. | Does not solve camera extraction/item assignment/exact ledger and inherits plan/API/write constraints. Reject as general product foundation. |

## Primary-document facts

**Verified:** React's official guidance recommends frameworks for many new apps and describes build-tool-only apps as taking responsibility for routing/data loading and other framework concerns. It also explicitly permits starting with Vite when constraints warrant it. This is context, not proof that Next is mandatory. [React creating an app](https://react.dev/learn/creating-a-react-app), [scratch trade-offs](https://react.dev/learn/build-a-react-app-from-scratch).

**Verified:** Next static export does not provide a runtime server; request-dependent handlers and server actions cannot supply a secret-backed Notion adapter there. Static GET output is possible, which is different from live synchronization. A deployed Node/server runtime or separate service is necessary. [Static exports](https://nextjs.org/docs/app/guides/static-exports), [backend-for-frontend guide](https://nextjs.org/docs/app/guides/backend-for-frontend).

**Verified:** Vite builds a static-hostable bundle by default; `VITE_` variables ship to client code. Never place Notion or model credentials in them. [Build](https://vite.dev/guide/build), [environment variables](https://vite.dev/guide/env-and-mode).

**Inference:** keep the monetary core independent of UI/framework, OCR provider and Notion adapter. Start with MYR and one reviewed receipt per meal; postpone FX, bank sync, receipt-driven autonomous settlement and elaborate agent frameworks. PostgreSQL is a proposal based on transactional/domain needs, not a configured production decision. SQLite remains viable for a single-server personal deployment, subject to backups/concurrency requirements; no SQLite package/API choice is made here.

## Vercel skills evaluation (not installed)

Official upstream https://github.com/vercel-labs/agent-skills inspected at `063bee94c3f4df8453406c830b0a7df0f2860278` (HEAD 2026-08-28).

- [`skills/react-best-practices/SKILL.md`](https://github.com/vercel-labs/agent-skills/blob/063bee94c3f4df8453406c830b0a7df0f2860278/skills/react-best-practices/SKILL.md): name is **vercel-react-best-practices**, metadata version 1.0.0 and MIT license declared. React/Next performance and data-loading guidance. README says 40+ rules, skill body says 70; do not treat either count as an independent quality metric. **Recommendation:** install only this scoped performance skill after React stack approval. It complements Impeccable's design role; server-specific rules apply only if that server model is used.
- [`skills/web-design-guidelines/SKILL.md`](https://github.com/vercel-labs/agent-skills/blob/063bee94c3f4df8453406c830b0a7df0f2860278/skills/web-design-guidelines/SKILL.md): metadata 1.0.0; fetches current external web-interface rules each review rather than bundling a fully pinned rule set. Overlaps Impeccable audit/a11y/responsive scope. **Recommendation:** do not install initially; evaluate later only for a specific audit gap, record fetched rule revision/license if vendoring.
- No deployment/Vercel-specific skill installed. React adoption does not require Vercel hosting. Repository root LICENSE was not found in this inspected checkout; do not generalize the React skill's MIT declaration to every other skill or remotely fetched guidelines.

## Remaining choice gates

Confirm personal versus shared groups, offline requirement, one editor versus simultaneous collaboration, receipt language mix, target phones, expected volume and hosting preference. Benchmark OCR before choosing a Python runtime dependency. Pin supported package versions/security baselines during the explicitly approved next phase, rather than treating old repository manifests or a docs index as current dependency recommendations.
