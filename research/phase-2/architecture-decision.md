# Phase 2 architecture decision

2026-10-16. **Orchestrator engineering decision:** retain Path C and stage a manual-first collaborative product. Choose Python for the first financial calculation slice, independently of the eventual frontend framework. This is a reversible local implementation choice, not deployment approval.

## Evidence and trade-offs

- [Phase 1 arithmetic](../phase-1/domain-model.md) exercises the needed exact integer/rational behavior; Python's standard library supplies integers, Fraction, immutable data structures and executable tests without a paid service or framework. The reference-model mismatch favors explicit dining concepts rather than importing Spliit/SplitPro wholesale.
- [Independent challenge](gate-challenge.md) found suggestion identity and composed-finalization gaps. Keep a pure reviewed calculation interface separate from accepted commands and actual transfer facts. Do not copy the disposable runner as production code.
- [Local OCR evidence](../phase-1/ocr-validation.md) establishes Python workstation inference feasibility, while native/device latency is unmeasured. A Python core avoids requiring a second production language/runtime for the measured OCR route. This does not choose server upload over device OCR or authorize retaining images.
- Private internet invitations and simultaneous edits need a shared authority regardless of frontend framework. [Phase 1 comparison](../phase-1/architecture-decision.md) established no SSR requirement and no inherent React/Next camera/OCR advantage. Continue browser-first; native remains a later evidence-driven option if actual capture/privacy needs require it.
- [Notion review](notion-contract-review.md) supports optional downstream reporting. No credentials or Notion availability are needed for pure calculation. Do not choose a Node server solely because reference apps use it.

## Selected now versus deferred

| Decision | Disposition and rationale |
|---|---|
| First slice runtime | Python standard-library financial core; exact integer sen/Fraction, immutable reviewed inputs, no ORM/framework or external service needed. Use the existing isolated compatible runtime for validation; pin supported versions before packaging. |
| Financial truth | Reviewed source amounts plus explicit allocations/components. Separate consumption, restaurant funding, actual transfers and reporting. Human review remains mandatory. |
| Persistence candidate | Single-host SQLite with transactional accepted commands is the smallest candidate for a bounded initial deployment; [actual two-connection/rollback/reopen validation](transaction-validation.md) passed20 narrow fixture checks. This is feasibility, not an implemented production authority. No network-filesystem/multi-host write assumption. Revisit PostgreSQL when measured deployment/concurrency requires it. |
| HTTP host candidate | FastAPI is a supported Python option with validation/testing/static support, but it supplies neither financial transactions nor identity/CSRF policy automatically. Defer installation until the transport slice needs it. |
| Browser UI | Defer framework installation until interactive slice. Start from the bounded screens/state requirements; static TypeScript with Vite is a viable minimal candidate. React/Vite is available if component/state complexity warrants it; SvelteKit/Next add server runtimes/conventions without demonstrated need now. No unique framework benchmark winner is claimed. |
| Updates | Versioned snapshots with polling are sufficient to test live acceptance initially; SSE/WebSocket can replace delivery later if measured UX/load warrants it. Never replace database acceptance with broadcasts. |
| OCR | Local/self-hosted proposal only; manual entry required. No third-party hosted image fallback. Modern corpus/device gates remain open. |
| Notion | Optional asynchronous copy, independent of financial truth; real REST/privacy/plan gates before enabling. |
| Hosting | Unselected; localhost development only. No cost commitment or public deployment. |

**Why not require a complete production stack before the first module:** a pure calculator has no camera, HTTP, database or UI dependency. Selecting a web framework solely to create that module adds no evidence or useful behavior. Later slice decisions require their own testable acceptance gates. No framework-specific skill is necessary for this first slice.

## Current documentation check

Context7 resolved `/websites/fastapi_tiangolo` and `/websites/sqlite_docs`, then queried on 2026-10-16. Official [FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/) and [cookie parameters](https://fastapi.tiangolo.com/reference/parameters/) establish request/test capabilities, not application security completeness. [SQLite WAL](https://www.sqlite.org/wal.html) permits concurrent readers with one writer and requires same-host shared memory; [online backup](https://www.sqlite.org/backup.html) provides a consistent backup route. These documentation facts are distinct from the [executed Phase 2 transaction probe](transaction-validation.md), whose20 checks establish only the recorded fixture behavior. Earlier [architecture evidence](../phase-1/architecture-evidence.md) remains the source for browser/framework comparisons and CPU-worker cautions.
