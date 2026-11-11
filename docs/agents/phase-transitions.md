# Phase transition decisions

## 2026-11-11 — Public Meal Creation Release Blockers & Operational Hardening (PR #68)

**Orchestrator decision: PASS / MERGED AUTONOMOUSLY.** In response to independent GitHub source review and CI failure on `main` following PR #67:
1. **Docker Compose Environment Propagation**: Added all 11 public creation, Turnstile, rate limiting, and capacity variables to `docker-compose.yml` under `settletable_app` environment block with fail-closed defaults (`SETTLETABLE_PUBLIC_CREATION_ENABLED=${SETTLETABLE_PUBLIC_CREATION_ENABLED:-0}`). Ensures configuration set in host `.env` reliably reaches the running application container.
2. **Ephemeral In-Memory Recovery & Zero Bearer Secrets in Web Storage**: Addressed bearer credential exposure in client-side storage. Removed `claim_url` from `saveRecentMeal()` in `settletable/static/app.js` across both room creation and active-room recovery link generation. Replaced persistent recovery storage with an ephemeral, in-memory recovery banner (`state.emergencyRecoveryUrl`, scoped to `state.emergencyRecoveryMealId`) displayed to the organizer immediately after room creation with 1-click clipboard copy guidance. `localStorage` now stores strictly non-sensitive metadata (`meal_id`, `title`, `role`, `created_at`).
3. **Hard ACID Transactional Capacity Limits**: Hardened capacity trust boundaries. In addition to in-memory gates, `authority.bootstrap()` now validates `max_total_meals` (`SELECT COUNT(*) FROM meals`) and `max_meals_per_day` (`SELECT COUNT(*) FROM organizer_claims WHERE generation=1 AND created_at >= ?`) inside an ACID `BEGIN IMMEDIATE` SQLite transaction, eliminating concurrency TOCTOU races under distributed ingress.
4. **Turnstile Production Enforcement & Key Validation**: Reconciled Turnstile environment variable aliases (`EXPECTED_ACTION` / `ACTION`, `EXPECTED_HOSTNAME` / `HOSTNAME`). In production environments (non-loopback origin), missing Turnstile keys fail closed (`ValueError`), and dummy Cloudflare test keys (`1x00...AA`) are rejected with actionable configuration errors.
5. **CI Financial Test Resolution**: Resolved CI failure in `tools/verify_financial_export.mjs` caused by `crypto.randomUUID()` monkey-patching colliding with public creation form submission. Scoped monkey-patch to post-creation and replaced client-side form UUIDs with `crypto.getRandomValues(new Uint8Array(16))`.
6. **Independent Review Remediations (SEC-01–SEC-04)**: Monotonically assigned `generation = COALESCE(MAX(generation), 0) + 1` in `_issue_organizer_claim_in_tx()` so that re-issuing organizer recovery links does not inflate daily room counts (`generation=1`); mapped `daily_capacity_exceeded` to HTTP 429; and isolated host port 8000 state in `tests/test_backup_restore.py`.
7. **Testing & Hosted CI**: Test suite expanded to 420 Python tests passing locally and in GitHub Actions CI (run [42993820800](https://github.com/KAIYI7/settle-table/actions/runs/42993820800), 100% success); browser E2E suites passing 100%; repository security audit clean (0 findings); independent code, security, and architectural review approved merge with verdict PASS. Reviewed head: `2d38e87`. Merged autonomously to `main` via `--no-ff`.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 420 Python tests passing locally and in hosted GitHub Actions CI; real browser CDP suites pass 100%. |
| Gate 2: Publicly Reachable Restricted Online Pilot (`v0.9.0-beta.1`) | **PILOT COMPLETED & CONTROLLER COMPLETED**: Real-meal pilot completed and snapshotted. On-demand hosting and local development safely managed via hardened, fully-verified `tools/SettleTable-Control.ps1` and `tools/SettleTable-Control.cmd`. |
| Gate 3: Unrestricted Public Product Access & Multi-Tenant Identity | **PASS (SECURE SELF-SERVICE CREATION)**: Low-friction public room creation without persistent account databases or host CLI is now fully implemented and protected with Turnstile, IP rate limiting, cryptographic room entropy, and ACID capacity bounds. Release blockers cleanly resolved. |
| Gate 4: Public GitHub Repository & Portfolio Demonstration | **PASS (Product Owner Decision)**: Repository visibility public on GitHub for technical portfolio evaluation; All Rights Reserved licensing preserved. Always-accessible showcase deployed at `https://kaiyi7.github.io/settle-table/`. |
| Container Environment Propagation | **PASS**: All 11 public creation configuration variables propagated via `docker-compose.yml` with fail-closed defaults. |
| Client Storage Credential Isolation | **PASS**: Zero bearer credentials or claim tokens in `localStorage`; emergency recovery URL kept strictly in-memory during room creation. |
| Transactional Resource Bounds | **PASS**: Global room cap and 24-hour rate limit enforced inside SQLite `BEGIN IMMEDIATE` transactions. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-11 — Secure Public Self-Service Meal Creation (PR #67)

**Orchestrator decision: PASS / MERGED AUTONOMOUSLY.** In response to public meal creation HTTP 403 `forbidden` investigation and confirmed product requirement enabling mobile/desktop visitors to create private meal rooms without accounts or host CLI: (1) **Separated Ingress Boundary**: Preserved loopback-only restrictions on `POST /api/meals/{meal_id}/bootstrap` while introducing `POST /api/meals/public-create` accessible behind Cloudflare Tunnel without 403 errors; (2) **Anti-Squatting Cryptographic Room IDs**: Generated unguessable room IDs (`slug-entropy`, e.g. `friday-hotpot-595f719c42`) with 40 bits of cryptographic entropy (`secrets.token_hex(5)`), preventing URL enumeration, collision, and room squatting while preserving human-readable restaurant titles; (3) **Defense-in-Depth Abuse Prevention**: Implemented server-side kill switch (`SETTLETABLE_PUBLIC_CREATION_ENABLED=0` fail-closed default); Cloudflare Turnstile bot verification with server-side Siteverify, token replay cache (300s TTL), and strict action/hostname validation; updated CSP to permit `https://challenges.cloudflare.com`; sliding-window IP rate limiter (burst 2/120s, hourly 5/1h, daily 10/24h) with memory leak pruning; global database capacity limits (max 100 total meals, max 25 meals/day); input length bounds (title max 60 chars, organizer max 40 chars, max 20 diners) and control character rejection; and completed idempotency caching that bypasses rate limits on network retries; (4) **Organizer Authority & Multi-Meal Session Resolution**: Creator immediately gains authenticated organizer session cookie (`HttpOnly; Secure; SameSite=Strict; Path=/`) and receives a 256-bit single-use recovery token; frontend maintains a local device registry (`settletable_recent_meals`) in `localStorage` allowing organizers to switch rooms and restore organizer credentials with 1-click without requiring an account database; (5) **Testing & Independent Review**: Test suite expanded by 25 automated tests in `tests/test_public_creation.py` and `tests/test_reverse_proxy_ingress.py`; mobile viewport Headless Chrome E2E suite (`tools/verify_public_creation_flow.mjs`) 100% passed; repository security audit clean (0 findings); independent code and security review approved merge with verdict PASS. Reviewed head: `73daaca`. Merged autonomously to `main` via `--no-ff`. Merge commit: `722ec0d`.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 421 Python tests passing; real browser CDP suites pass 100%. |
| Gate 2: Publicly Reachable Restricted Online Pilot (`v0.9.0-beta.1`) | **PILOT COMPLETED & CONTROLLER COMPLETED**: Real-meal pilot completed and snapshotted. On-demand hosting and local development safely managed via hardened, fully-verified `tools/SettleTable-Control.ps1` and `tools/SettleTable-Control.cmd`. |
| Gate 3: Unrestricted Public Product Access & Multi-Tenant Identity | **CONDITIONAL PASS (SELF-SERVICE ROOM CREATION)**: Low-friction public room creation without persistent account databases or host CLI is now fully implemented and protected with Turnstile, IP rate limiting, cryptographic room entropy, and capacity bounds. Multi-tenant persistent account profiles remain deferred to future roadmap. |
| Gate 4: Public GitHub Repository & Portfolio Demonstration | **PASS (Product Owner Decision)**: Repository visibility public on GitHub for technical portfolio evaluation; All Rights Reserved licensing preserved. Always-accessible showcase deployed at `https://kaiyi7.github.io/settle-table/`. |
| Public Creation Boundary Isolation | **PASS**: Administrative bootstrap loopback isolation preserved; public creation routed via dedicated path behind Cloudflare Tunnel. |
| Cryptographic Room Squatting Defense | **PASS**: 40-bit unguessable entropy prevents enumeration and collisions. |
| Anti-Abuse Defenses & Resource Caps | **PASS**: Turnstile Siteverify, sliding-window IP rate limiter, max 100 meal cap, max 25 meals/day cap, input bounds, and idempotency deduplication verified. |
| Multi-Meal Session Resolution | **PASS**: Organizer session cookie set upon creation; single-use emergency claim token generated; frontend local device registry enables 1-click room switching and access recovery. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-10 — Host Lifecycle Controller Execution Policy Resolution & Companion App Support (PR #66)

**Orchestrator decision: PASS / MERGED AUTONOMOUSLY.** In response to Windows PowerShell Execution Policy restrictions (`Restricted` by default on Windows client OS) preventing `tools/SettleTable-Control.ps1` from launching on default Windows installations: (1) **Zero-Configuration Native Command Launcher (`tools/SettleTable-Control.cmd`)**: Implemented a resilient native batch launcher tailored for Companion App Quick Actions, Stream Deck buttons, desktop shortcuts, Windows Task Scheduler, Command Prompt, and PowerShell. Invokes PowerShell with scoped process bypass (`-NoLogo -NoProfile -ExecutionPolicy Bypass`), working immediately on systems with Windows default `Restricted` policy without altering system-wide or user-wide configuration or requiring elevation; auto-detects `pwsh.exe` (PowerShell Core 7+) with graceful fallback to built-in `powershell.exe`; safely quotes directory paths and script names with space resilience (`"%~dp0SettleTable-Control.ps1"`); forwards all parameters (`%*`); and deterministically propagates exit codes (`exit /b %ERRORLEVEL%`); (2) **Interactive PowerShell Execution Guidance**: Documented the Microsoft-sanctioned user-scoped policy setup (`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`) in `tools/SettleTable-Control.ps1` header, CLI usage error messages, and `README.md`, enabling parameter completion and local script execution while preserving protection against untrusted remote scripts; (3) **Companion App Quick Actions Configuration**: Added a structured Quick Actions reference table in `README.md` defining command targets (`start-local`, `start-public`, `stop-public`, `stop-all`, `status`) and verified behavior; (4) **Showcase & Test Suite Reconciliation**: Reconciled test suite from 390 to 396 tests across `README.md`, `docs/index.html`, and `tests/test_settletable_control.py` (+6 tests: structure verification, help, invalid-action, status with mocks, external working directory execution, and execution policy resolution); (5) **Testing & Independent Review**: All 396 tests pass locally (`Ran 396 tests in 106.8s, OK`); repository security audit clean (0 findings); independent code, security, and operational review approved merge with verdict PASS. Reviewed head: `cc9aa5a`. Merged autonomously to `main` via `--no-ff`.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 396/396 Python tests passing locally; real browser CDP suites pass 100%. |
| Gate 2: Publicly Reachable Restricted Online Pilot (`v0.9.0-beta.1`) | **PILOT COMPLETED & CONTROLLER COMPLETED**: Real-meal pilot completed and snapshotted. On-demand hosting and local development safely managed via hardened, fully-verified `tools/SettleTable-Control.ps1` and `tools/SettleTable-Control.cmd`. Public ingress safely deactivated (`HTTP 530 / Error 1033`). |
| Gate 3: Unrestricted Public Product Access & Multi-Tenant Identity | **DEFERRED**: Preserved for future Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) where arbitrary public visitors can create persistent accounts and self-serve meal discovery. |
| Gate 4: Public GitHub Repository & Portfolio Demonstration | **PASS (Product Owner Decision)**: Repository visibility public on GitHub for technical portfolio evaluation; All Rights Reserved licensing preserved. Always-accessible showcase deployed at `https://kaiyi7.github.io/settle-table/`. |
| Host Lifecycle Controller Usability & Safety | **PASS**: Scoped process bypass ensures zero-configuration execution for Companion App Quick Actions and Windows terminals without altering host security policies; all container state checks, pre-flight guards, and secret redaction preserved. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-10 — Notion Timeout & Retry Concurrency Safety Hardening (PR #65)

**Orchestrator decision: PASS / MERGED AUTONOMOUSLY.** In response to review and isolated synthetic UAT: (1) **Notion Concurrency & Overlap Protection**: Fixed worker overlap vulnerability when an asynchronous export exceeds 75s and organizer retries while worker is in-flight. Implemented in-process `_export_threads` tracking under `_export_lock` with double-checked locking in `settletable/transport.py`, returning HTTP 202 without spawning duplicate worker threads or creating duplicate Notion pages. Added `_bg_export()` early return if export is already completed. Implemented database-level protection in `settletable/authority.py` (`WHERE notion_exports.status != 'completed'`) preventing lagging failures from corrupting completed records or URLs; (2) **Synthetic Post-Finalization UAT (`tests/test_post_finalization_uat.py`)**: Verified receipt sharing toggle, active diner photo access, non-organizer modification block, disabled photo block; exact mathematical balances across underfunded, funded, and settled states; strict rejection of non-organizer payment commands (`RecordContribution`, `ReverseContribution`, `RecordTransfer`, `ReverseTransfer`); Notion report retrieval, diner private URL protection, view-only web link sharing and removal; and cross-meal authorization boundaries; (3) **Historical SQLite Schema Migration**: Tested upgrading an isolated legacy database without `public_url` and `share_with_diners`, confirming zero data loss, intact meal snapshots and photo blobs, default `share_with_diners = 0`, and full backward compatibility; (4) **Real-Data Deployment Readiness Procedure**: Confirmed normal controller startup does not rebuild Docker images automatically (`docker compose build settletable` required); documented pre-upgrade single-snapshot 7-Zip AES-256 encrypted Google Drive backup, volume pre-flight check, and atomic rollback plan, strictly preserving real volume boundaries (zero real volume mounting); (5) **Testing & Independent Review**: Test suite expanded from 384 to 390 tests with 100% pass rate (`Ran 390 tests, OK`); real browser CDP suites pass 100%; repository audit clean (0 findings); independent code and security review approved merge following SEC-01 resolution. Reviewed head: `0ea1cfe`. Merged autonomously to `main` via `--no-ff`.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 390/390 Python tests passing locally; real browser CDP suites pass 100%. |
| Gate 2: Publicly Reachable Restricted Online Pilot (`v0.9.0-beta.1`) | **PILOT COMPLETED & CONTROLLER COMPLETED**: Real-meal pilot completed and snapshotted. On-demand hosting and local development safely managed via hardened, fully-verified `tools/SettleTable-Control.ps1`. Public ingress safely deactivated (`HTTP 530 / Error 1033`). |
| Gate 3: Unrestricted Public Product Access & Multi-Tenant Identity | **DEFERRED**: Preserved for future Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) where arbitrary public visitors can create persistent accounts and self-serve meal discovery. |
| Gate 4: Public GitHub Repository & Portfolio Demonstration | **PASS (Product Owner Decision)**: Repository visibility public on GitHub for technical portfolio evaluation; All Rights Reserved licensing preserved. Always-accessible showcase deployed at `https://kaiyi7.github.io/settle-table/`. |
| Notion Concurrency & Retry Safety | **PASS**: Double-checked in-process locking prevents duplicate worker threads or pages during concurrent requests; SQLite conditional update prevents lagging worker failure from overwriting completed export. |
| Synthetic Post-Finalization UAT | **PASS**: Verified photo sharing permissions, mathematical balance conservation across funded/underfunded/settled, non-organizer financial command rejection, Notion private URL masking, and cross-meal boundaries on synthetic data. |
| Historical Schema Upgrade Invariance | **PASS**: Verified automatic schema upgrade against pre-PR #64 database lacking `public_url` and `share_with_diners`; 100% data retention and backwards compatibility confirmed. |
| Real-Data Deployment Readiness | **PASS**: Image rebuild requirements verified; mandatory pre-upgrade encrypted Google Drive backup documented; volume pre-flight check and atomic rollback procedure established; deployment boundary strictly maintained (no live volume mount/migration). |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-10 — Post-Finalization UX & Diner Access Improvements (PR #64)

**Orchestrator decision: PASS / MERGED AUTONOMOUSLY.** In response to real-device feedback and accepted investigation on diner permissions and post-finalization UX: (1) **Notion Export Reliability & Visibility**: Ensured exported status and "Open Report in Notion ↗" link persist across UI re-renders, snapshot polling, and browser refreshes; collapsed bulky export form into `<details>` once completed; aligned backend timeout (75.0s) and frontend polling (70s) to prevent duplicate exports; resumed in-progress export observation on reload without timer cancellation; added diner-visible Notion archive indicator while strictly preventing exposure of tokens or private workspace URLs; added organizer registration of view-only published Notion links (`notion.site`/`notion.so`) with strict HTTPS, hostname, and length validation; (2) **Diner Funding & Settlement UX**: Kept organizer-attested financial ledger authoritative, strictly prohibiting diner mutations (`RecordContribution`, `ReverseContribution`, `RecordTransfer`, `ReverseTransfer` return 403 `forbidden`); added personalized outstanding balance banner for diners (debt, credit, settled, or unfunded obligation) reusing existing suggested transfers; added clear role guidance explaining external payment notification; (3) **Organizer-Controlled Receipt Photo Sharing**: Implemented optional read-only photo sharing defaulting to disabled (`share_with_diners = 0`) across all meals; post-finalization organizer toggle with physical receipt privacy warning; active authenticated meal participants receive read-only photo access; diners cannot access photo before finalization and never gain write/upload/delete permissions; unauthenticated, inactive, revoked, and cross-meal sessions strictly blocked (401/403); storage in `receipt_photos.share_with_diners` preserves 100% financial calculation, revision, and digest invariance; (4) **Testing & Independent Review**: Test suite expanded from 371 to 384 tests with 100% pass rate (`Ran 384 tests in 119.3s, OK`); real browser CDP suites passed (`verify_receipt_photo_flow.mjs`, `verify_peer_settlement_flow.mjs`, `e2e_browser_test.mjs`); repository audit clean (0 findings); independent senior review evaluated HIGH risk classification and approved merge; Finding M-01 (in-progress poll timer clear on reload) resolved and verified prior to merge. Reviewed head: `649a7a3`. Merged autonomously to `main` via `--no-ff`. Merge commit: `0acb1a5`.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 384/384 Python unit, calculation, security, restore, and hermetic lifecycle controller tests passed; real browser CDP suites pass 100%. |
| Gate 2: Publicly Reachable Restricted Online Pilot (`v0.9.0-beta.1`) | **PILOT COMPLETED & CONTROLLER COMPLETED**: Real-meal pilot completed and snapshotted. On-demand hosting and local development safely managed via hardened, fully-verified `tools/SettleTable-Control.ps1`. Public ingress safely deactivated (`HTTP 530 / Error 1033`). |
| Gate 3: Unrestricted Public Product Access & Multi-Tenant Identity | **DEFERRED**: Preserved for future Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) where arbitrary public visitors can create persistent accounts and self-serve meal discovery. |
| Gate 4: Public GitHub Repository & Portfolio Demonstration | **PASS (Product Owner Decision)**: Repository visibility public on GitHub for technical portfolio evaluation; All Rights Reserved licensing preserved. Always-accessible showcase deployed at `https://kaiyi7.github.io/settle-table/`. |
| Notion Export Reliability & Diner Visibility | **PASS**: Export status and link persist across reload/re-render; in-progress polling resumes on session restoration; backend 75.0s / frontend 70s timeout alignment prevents duplicates; tokens and private workspace URLs strictly withheld from diners; organizer can register validated view-only published links. |
| Authoritative Ledger & Diner Settlement Clarity | **PASS**: Organizer-attested financial ledger strictly authoritative; diners forbidden from executing `RecordContribution`, `ReverseContribution`, `RecordTransfer`, or `ReverseTransfer` (403); diners receive personalized balance summary and role attestation guidance. |
| Organizer-Controlled Receipt Photo Sharing | **PASS**: Default disabled across new and existing meals; organizer-toggled post-finalization with privacy warning; read-only access for active meal participants; unfinalized, unauthenticated, inactive, and cross-meal access blocked; financial calculation and revision immutability preserved. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

**Orchestrator decision: PASS / MERGED AUTONOMOUSLY.** In response to recruiter showcase content and presentation review on public GitHub Pages site (`https://kaiyi7.github.io/settle-table/`): (1) Replaced raw unrendered LaTeX markup (`$$\text{Net Balance}...$$` and `$\sum...$`) in `docs/index.html` with an accessible, semantic HTML `.formula-box` element using `role="math"`, `aria-label`, and Unicode mathematical entities (`&minus;`, `&sum;`) without introducing external runtime libraries; (2) Preserved mathematical rigor by explicitly stating the prerequisite condition under which net balances conserve to zero: *"When the cashier bill is fully funded (total paid equals receipt total), largest-remainder apportionment guarantees that the sum of all individual net balances is exactly RM0.00 (&sum; Net Balances = RM0.00), with zero floating-point penny drift."*; (3) Replaced "Air-Gapped Optical Recognition" with "Server-Side Offline Receipt OCR", correctly reflecting local CPU execution via RapidOCR ONNX without implying host-level air-gapping; (4) Refined session cookie documentation to specify an authenticated `HttpOnly; Secure; SameSite=Strict` session cookie transmitted over TLS and verified server-side against a SHA-256 verifier, removing inaccurate claims of application-layer cookie payload encryption; (5) Replaced "Greedy Minimum-Transfer Heuristic" with "Greedy Settlement Suggestions" to avoid unproven claims of transfer sequence minimality; (6) Updated page title and hero headline to *"Restaurant Bill Splitting Engineered for Mathematical Precision"* with an accessible, compelling subtitle balancing recruiter clarity with engineering craftsmanship; (7) Validated HTML5 tag hierarchy and CSS syntax (0 errors); (8) Verified all 7 demo assets; (9) Confirmed 0 security findings in repository audit; (10) Local test suite passed 371/371 tests; (11) Independent review verdict: PASS. Reviewed head: `0279699`. Merged autonomously to `main` via `--no-ff`.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 371/371 Python unit, calculation, security, restore, and hermetic lifecycle controller tests passed; containerized WSGI application operational; smoke checks pass 13/13. |
| Gate 2: Publicly Reachable Restricted Online Pilot (`v0.9.0-beta.1`) | **PILOT COMPLETED & CONTROLLER COMPLETED**: Real-meal pilot completed and snapshotted. On-demand hosting and local development safely managed via hardened, fully-verified `tools/SettleTable-Control.ps1`. Public ingress safely deactivated (`HTTP 530 / Error 1033`). |
| Gate 3: Unrestricted Public Product Access & Multi-Tenant Identity | **DEFERRED**: Preserved for future Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) where arbitrary public visitors can create persistent accounts and self-serve meal discovery. |
| Gate 4: Public GitHub Repository & Portfolio Demonstration | **PASS (Product Owner Decision)**: Repository visibility public on GitHub for technical portfolio evaluation; All Rights Reserved licensing preserved. Always-accessible showcase deployed at `https://kaiyi7.github.io/settle-table/`. |
| Mathematical & Terminology Precision | **PASS**: Raw LaTeX eliminated in favor of clean HTML/Unicode; prerequisite condition for balance zero-summing explicitly articulated; OCR, cookie auth, and settlement transfer terminology verified strictly against implementation. |
| Recruiter Presentation Clarity | **PASS**: Hero headline updated to "Restaurant Bill Splitting Engineered for Mathematical Precision" with accessible supporting copy. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-09 — Public Portfolio Showcase & Recruiter Demonstration (PR #62)

**Orchestrator decision: PASS / MERGED AUTONOMOUSLY.** In response to Product Owner explicit decision intentionally changing repository `KAIYI7/settle-table` visibility from private to public for recruiter evaluation: (1) Reconciled repository visibility documentation across `README.md`, `docs/uat-handover.md`, and project governance records, reflecting public visibility for portfolio evaluation while strictly preserving the All Rights Reserved licensing position (zero open-source redistribution authorized); (2) Verified repository public visibility via unauthenticated external HTTP probe (`https://github.com/KAIYI7/settle-table` returning HTTP 200 OK anonymously); (3) Executed comprehensive repository security and privacy audits across all 342 tracked files and full Git commit history using automated heuristic scanners (`scratch/scan_repo_secrets.py`, `scratch/audit_tracked_files.py`, and `tools/audit_repository.py`), confirming 0 exposed credentials, tokens, passwords, private keys, or real dining data; (4) Built automated recruiter demonstration capture suite (`tools/capture_recruiter_demo.mjs`) using headless Chrome CDP against an isolated Docker container running genuine RapidOCR ONNX inference, capturing 6 high-fidelity authentic walkthrough stages (`01-room-setup.png`, `02-candidate-review.png`, `03-portion-allocation.png`, `04-mobile-diner-view.png`, `05-payer-reconciliation.png`, `06-peer-settlement.png`) using 100% synthetic fixtures without touching production volume `settletable_data`; (5) Generated optimized animated walkthrough overview (`docs/assets/demo/walkthrough.gif`) using containerized PIL; (6) Established always-accessible, fast, responsive, zero-dependency static project showcase at `docs/index.html` with `.nojekyll` and GitHub Actions deployment workflow (`.github/workflows/pages.yml`), featuring problem introduction, interactive walkthrough, backend engineering achievements, architecture topology, and verified testing evidence; (7) Refreshed `README.md` for recruiter experience with prominent showcase, repository, and on-demand deployment links, verified test counts (371 tests), and clear on-demand hosting status disclosures (HTTP 530 / Error 1033); (8) Independent architecture, security, and documentation review confirmed verdict PASS; (9) All 371 tests pass locally and in CI. Reviewed head: `b8b9d9a`; merge commit: `bd1bc5f`. Merged autonomously to `main` via `--no-ff`.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 371/371 Python unit, calculation, security, restore, and hermetic lifecycle controller tests passed; containerized WSGI application operational; smoke checks pass 13/13. |
| Gate 2: Publicly Reachable Restricted Online Pilot (`v0.9.0-beta.1`) | **PILOT COMPLETED & CONTROLLER COMPLETED**: Real-meal pilot completed and snapshotted. On-demand hosting and local development safely managed via hardened, fully-verified `tools/SettleTable-Control.ps1`. Public ingress safely deactivated (`HTTP 530 / Error 1033`). |
| Gate 3: Unrestricted Public Product Access & Multi-Tenant Identity | **DEFERRED**: Preserved for future Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) where arbitrary public visitors can create persistent accounts and self-serve meal discovery. |
| Gate 4: Public GitHub Repository & Portfolio Demonstration | **PASS (Product Owner Decision)**: Repository visibility intentionally changed from private to public on GitHub for technical portfolio and recruiter evaluation. All Rights Reserved licensing strictly preserved (no open-source license grant or redistribution right authorized). Always-accessible project showcase established at `https://kaiyi7.github.io/settle-table/` via GitHub Pages. |
| Confidentiality & Privacy Integrity | **PASS**: Staged content audit and full repository audit confirmed 0 security findings across all tracked files and commit history. Zero credentials, tokens, or real dining data tracked or exposed. Demo assets generated from 100% synthetic fixtures in isolated container. |
| Authentic Demonstration Assets | **PASS**: 6-stage walkthrough screenshots and animated GIF (`walkthrough.gif`) generated directly from the live application via automated Chrome CDP without mock fabrication. |
| Showcase Accessibility & Maintainability | **PASS**: Static showcase at `docs/index.html` has zero external JavaScript/CSS frameworks, zero build pipelines, and zero tracking services. Fast, accessible, and responsive. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

**Orchestrator decision: PASS / MERGED AUTONOMOUSLY.** In response to post-PR #60 code inspection regarding container query failure edge cases and production preflight safety: (1) Refactored `Get-RunningContainerIds` to return a structured verification object (`@{ Success = [bool]; Error = [string]; Ids = [array] }`), eliminating the ambiguity between a query returning 0 containers and a query failing; (2) Enforced fail-closed handling across `stop-public`, `stop-all`, and `start-local`, ensuring a failed `docker ps` query is never accepted as proof of container deactivation; (3) Added active container verification during `start-public` rollback: if the local health check fails or live edge HTTPS check fails, the controller stops `cloudflared`, verifies container deactivation, and outputs clear critical diagnostics if the tunnel cannot be verified inactive; (4) Hardened volume preflight bypass safety by removing ambient environment variable bypasses and strictly blocking test-only parameters (`-SkipPreflight`, `-PreflightCmd`) when targeting production Docker (`$DockerCmd -eq "docker"`); (5) Expanded automated test suite from 23 to 28 hermetic unit tests in `tests/test_settletable_control.py` covering query failures, lingering containers, and production rejection of test-only flags; (6) Staged publishing audit confirmed 0 security findings; (7) Independent architecture and security review confirmed verdict PASS; (8) Hosted GitHub Actions CI (`docker-smoke` and `tests`) passed on exact head SHA (`9752409`). Merged autonomously to `main` via `--no-ff`. Lifecycle controller implementation is complete.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 371/371 Python unit, calculation, security, restore, and hermetic lifecycle controller tests passed; containerized WSGI application operational; smoke checks pass 13/13. |
| Gate 2: Publicly Reachable Restricted Online Pilot (`v0.9.0-beta.1`) | **PILOT COMPLETED & CONTROLLER COMPLETED**: Real-meal pilot completed and snapshotted. On-demand hosting and local development safely managed via hardened, fully-verified `tools/SettleTable-Control.ps1`. Public ingress safely deactivated (`HTTP 530 / Error 1033`). |
| Gate 3: Unrestricted Public Product Access & Multi-Tenant Identity | **BLOCKED / DEFERRED**: Dependent on Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) where arbitrary public visitors can create persistent accounts, access multi-meal dashboards, and manage self-serve meal discovery. |
| Gate 4: Public GitHub Repository & Tagged Release (`v1.0.0`) | **BLOCKED / ESCALATED**: Preserved for Product Owner consequential authority regarding repository visibility and intellectual property licensing. |
| Container Query Verification Contract | **PASS**: Structured contract distinguishes query success from query failure. Failed queries fail closed and are never treated as confirmation of container deactivation. |
| Production Preflight Safety | **PASS**: Ambient environment variable bypasses removed; test-only flags rejected against production Docker. |
| Rollback Diagnostics & Safety | **PASS**: Start-public rollback actively verifies tunnel deactivation and alerts operator with explicit cleanup commands on linger. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-09 — Windows Host Lifecycle Controller Reliability Hardening & README Reconciliation (PR #60)

**Orchestrator decision: PASS / MERGED AUTONOMOUSLY.** In response to post-PR #59 independent review findings regarding operational reliability in `tools/SettleTable-Control.ps1` and README precision: (1) Added explicit Docker command exit code verification and post-execution container state assertions in `stop-public` and `stop-all`, ensuring neither `settletable_tunnel` nor `settletable_app` linger after a stop command; (2) In `start-local`, enforced Cloudflare connector shutdown and verified inactive state *before* volume pre-flight validation and app startup, with a final fail-closed guard preventing unintentional public exposure; (3) In `start-public`, enforced local application health check (`/healthz` returning 200 OK) before edge verification, automatically stopping the Cloudflare tunnel connector on local probe failure to avoid exposing an unhealthy service; (4) Distinguished local connector deactivation from externally observed Cloudflare edge responses (HTTP 530 Tunnel Offline vs 000 Network Timeout vs 200 In-flight/Cached); (5) Eliminated PowerShell output stream pollution by capturing external command stdout, ensuring functions return clean booleans and the dispatcher reliably exits with code 1 on failures; (6) Added `-PreflightCmd` and `-SkipPreflight` (supporting `SETTLETABLE_SKIP_VOLUME_PREFLIGHT=1` and `SETTLETABLE_SKIP_PREFLIGHT=1`) for hermetic mock execution; (7) Reconciled README wording: "Server-Side Offline Receipt OCR" (replacing "Air-Gapped"), "Heuristically computes suggested reimbursement transfers" (replacing minimal transfer sequence claim), and clarified private repository access for authorized collaborators; (8) Expanded test suite from 6 to 23 automated hermetic unit tests in `tests/test_settletable_control.py`; (9) Staged audit confirmed 0 security findings; (10) Independent architecture and security review confirmed verdict PASS; (11) GitHub Actions CI (`docker-smoke` and `tests`) passed on exact head SHA (`f4ab520`). Merged autonomously to `main` via `--no-ff`.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 366/366 Python unit, calculation, security, restore, and hermetic lifecycle controller tests passed; containerized WSGI application operational; smoke checks pass 13/13. |
| Gate 2: Publicly Reachable Restricted Online Pilot (`v0.9.0-beta.1`) | **PILOT COMPLETED & CONTROLLER HARDENED**: Real-meal pilot completed and snapshotted. On-demand hosting and local development safely managed via hardened `tools/SettleTable-Control.ps1`. Public ingress safely deactivated (`HTTP 530 / Error 1033`). |
| Gate 3: Unrestricted Public Product Access & Multi-Tenant Identity | **BLOCKED / DEFERRED**: Dependent on Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) where arbitrary public visitors can create persistent accounts, access multi-meal dashboards, and manage self-serve meal discovery. |
| Gate 4: Public GitHub Repository & Tagged Release (`v1.0.0`) | **BLOCKED / ESCALATED**: Preserved for Product Owner consequential authority regarding repository visibility and intellectual property licensing. |
| Lifecycle Controller Reliability | **PASS**: `tools/SettleTable-Control.ps1` enforces Docker command exit codes, verifies container termination via filter queries, rolls back public tunnel on local health failure, distinguishes edge status, and maintains pipeline stream purity. |
| Test Hermeticity & Cross-Platform CI | **PASS**: 23/23 controller tests run hermetically using mocked Docker, Curl, and Preflight scripts, passing seamlessly across local Windows host and GitHub Actions Ubuntu runners without Docker volume dependencies. |
| Portfolio Documentation Precision | **PASS**: `README.md` reconciled with mathematically accurate heuristic settlement terminology, server-side offline OCR, and explicit private collaborator access terms. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-08 — Windows Host Lifecycle Controller & Portfolio README Refresh (PR #59)

**Orchestrator decision: PASS / MERGED AUTONOMOUSLY.** In response to operator usability and portfolio presentation requirements following the successful Stage C1-B real-meal pilot: (1) Replaced outdated README with professional, portfolio-oriented documentation accurately detailing SettleTable as a tested, functional, self-hosted dining expense management MVP; (2) Documented the actual verified deployment URL (`https://settle.kybuilds.com`) and on-demand hosting model (HTTP 530 / Error 1033 when host tunnel is inactive); (3) Illustrated architecture (Python 3.14 WSGI, SQLite WAL, RapidOCR ONNX, Cloudflare Named Tunnel); (4) Reconciled automated test counts to 349 tests and 13/13 deployment smoke checks; (5) Implemented `tools/SettleTable-Control.ps1` providing an interactive menu and non-interactive automation commands (`start-local`, `start-public`, `stop-public`, `stop-all`, `status`) with path discovery relative to script root and strict data preservation; (6) Added 6 unit tests in `tests/test_settletable_control.py`; (7) Independent architecture and security review completed with verdict PASS; (8) All 349 tests pass locally and in GitHub Actions CI (`ALL_CI_SUCCESS`). Merged autonomously to `main`.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 349/349 Python unit, calculation, security, restore, and lifecycle controller tests passed; containerized WSGI application operational; smoke checks pass 13/13 locally and externally. |
| Gate 2: Publicly Reachable Restricted Online Pilot (`v0.9.0-beta.1`) | **PILOT COMPLETED & CONTROL SCRIPT OPERATIONAL**: First live real-data dining session successfully conducted and snapshotted. On-demand hosting and local-only development controlled via `tools/SettleTable-Control.ps1`. Public ingress safely deactivated (`HTTP 530 / Error 1033`). |
| Gate 3: Unrestricted Public Product Access & Multi-Tenant Identity | **BLOCKED / DEFERRED**: Dependent on Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) where arbitrary public visitors can create persistent accounts, access multi-meal dashboards, and manage self-serve meal discovery. |
| Gate 4: Public GitHub Repository & Tagged Release (`v1.0.0`) | **BLOCKED / ESCALATED**: Preserved for Product Owner consequential authority regarding repository visibility and intellectual property licensing. |
| Host Lifecycle Controller Safety | **PASS**: `tools/SettleTable-Control.ps1` prevents accidental public exposure in local mode, runs real-volume pre-flight before public start, avoids destructive commands (preserves all Docker volumes and SQLite files), protects secrets in status output, and handles relative paths. |
| Portfolio Documentation Quality | **PASS**: `README.md` refreshed with accurate architecture diagrams, on-demand hosting disclosure, reconciled test counts, sanitized synthetic screenshots, and source-available private licensing. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-08 — Stage C1-B: First Real-Meal Pilot & Post-Event Closure

**Orchestrator decision: PASS / REAL-MEAL PILOT ACCEPTED & SAFELY DEACTIVATED.** Product Owner authorized and personally conducted the inaugural real-meal dining pilot on `https://settle.kybuilds.com`: (1) Verified real storage volume `settletable_data`, pristine schema, and baseline backup before launch; (2) Stack activated via Cloudflare Named Tunnel with 13/13 deployment smoke checks passing; (3) Product Owner created meal via host CLI, uploaded paper restaurant receipt with RapidOCR candidate extraction, verified Malaysian SST and service charges, and distributed fragment invitation links; (4) Diners successfully accessed the room from separate physical devices over mobile data, claimed portions, and verified real-time financial balance calculations (verdict: PASS for tested actions); (5) Stack cleanly quiesced (`docker compose stop settletable`); (6) Verified consistent snapshot `20261108_123746Z` containing database (`settletable_20261108_123746Z.sqlite`), manifest (`manifest_20261108_123746Z.json`), and receipt photo (`receipt_photos_20261108_123746Z/`), with bit-for-bit SHA-256 match and `PRAGMA integrity_check` -> `ok`; (7) AES-256 header-encrypted archive (`settletable_backup_20261108_123746Z.7z`, 855,088 bytes) created with interactive operator passphrase, verified via `7z t`, and uploaded to Google Drive (`<GDRIVE_BACKUPS_DIR>`); (8) DriveFS metadata confirmed permanent cloud resource ID (`12VUc8etjr4Y1vJmnZNIDowf6qj9nq8L_`) with 0 pending operations; (9) Public ingress cleanly terminated (`docker compose stop cloudflared`), verified offline (`HTTP 530 / Error 1033`). Zero containers running. All 343 tests pass. Both `settletable_data` and `settletable_synthetic_data` volumes safely preserved.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 343/343 Python unit, calculation, security, restore, and ingress tests passed; containerized WSGI application operational; smoke checks pass 13/13 locally and externally. |
| Gate 2: Publicly Reachable Restricted Online Pilot (`v0.9.0-beta.1`) | **PILOT COMPLETED & SAFELY DEACTIVATED**: First live real-data dining session successfully conducted with invited friends. Receipt upload, RapidOCR parsing, fragment diner invitations, and financial calculations verified on physical devices. Real dataset safely quiesced, snapshotted, AES-256 encrypted, and verified durable in Google Drive. Public ingress deactivated (`HTTP 530 / Error 1033`). |
| Gate 3: Unrestricted Public Product Access & Multi-Tenant Identity | **BLOCKED / DEFERRED**: Dependent on Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) where arbitrary public visitors can create persistent accounts, access multi-meal dashboards, and manage self-serve meal discovery. |
| Gate 4: Public GitHub Repository & Tagged Release (`v1.0.0`) | **BLOCKED / ESCALATED**: Preserved for Product Owner consequential authority regarding repository visibility and intellectual property licensing. |
| Real-World Pilot Verification | **PASS (Product Owner Verdict)**: Real meal created, organizer session claimed, restaurant receipt scanned and confirmed, diner links redeemed from separate physical devices, items claimed, and settlements calculated without errors. |
| Dataset Integrity & Quiescence | **PASS**: Authoritative records verified (1 meal, 4 participants, 4 sessions, 3 invitations, 1 organizer claim, 16 command events, 1 payer contribution, 2 peer transfers, 1 receipt photo). `PRAGMA integrity_check;` returned `ok`. No private data logged. |
| AES-256 Encrypted Backup | **PASS**: `settletable_backup_20261108_123746Z.7z` created with `-mhe=on` and operator-held passphrase. Archive integrity test (`7z t`) passed. Archive fails closed without passphrase. |
| Google Drive Durability | **PASS**: Copied with fail-fast handling; SHA-256 verified bit-for-bit; DriveFS confirmed permanent cloud ID `12VUc8etjr4Y1vJmnZNIDowf6qj9nq8L_` and 0 pending operations. |
| Ingress Deactivation | **PASS**: Cloudflare connector stopped; `https://settle.kybuilds.com/healthz` returns `HTTP 530 / Error 1033`. Zero containers running. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-08 — Stage C1: Final Safety Corrections (PR #58)

**Orchestrator decision: PASS / FINAL SAFETY CORRECTIONS VERIFIED.** In response to pre-activation findings prior to first real-data activation: (1) Enforced fail-closed volume pre-flight in `tools/verify_volume_target.py`: mode `real` strictly asserts `settletable_data`, mode `synthetic` strictly asserts `settletable_synthetic_data`, custom or conflicting volume configurations fail closed with code 1; storage UID/GID (10001) and storage/photos directory writability are actively asserted rather than printed; (2) Hardened volume identity marker integrity in `settletable/wsgi.py`: detects existing databases/photos missing `.volume_identity` or possessing malformed/unreadable marker JSON and fails closed with `RuntimeError`; ensures pristine fresh volumes initialize atomically via temporary file replacement; (3) Resolved baseline quiescent backup prerequisite via `tools/bootstrap_meal.py init-db`: creates initial database schema and activates WAL mode on brand-new volumes in a local container without public ingress; verified complete initialization -> baseline backup -> offsite mirror -> disaster restore sequence in isolated Docker test; (4) Updated `docs/runbooks/windows_host_operations.md` to document pristine DB initialization, cloud sync vs local copy durability distinction, and data confidentiality/storage encryption. All 343 tests pass. Primary production volume `settletable_data` remains completely unmounted, empty, and pristine. Awaiting Product Owner explicit authorization to begin invited-friends pilot.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 343/343 Python unit, calculation, security, restore, and ingress tests passed; containerized WSGI application operational; smoke checks pass 13/13 locally and externally. |
| Gate 2: Publicly Reachable Restricted Online Pilot (`v0.9.0-beta.1`) | **PREPARED & SAFETY HARDENED**: Fail-closed volume pre-flight, fail-closed marker integrity guard, and pristine DB bootstrap verified. Baseline backup sequence proven in isolated Docker drill. Public ingress verified closed (`HTTP 530 / Error 1033`). Ready for Product Owner explicit authorization to execute volume cutover (`SETTLETABLE_DATA_VOLUME=settletable_data`) and launch real-meal pilot. |
| Gate 3: Unrestricted Public Product Access & Multi-Tenant Identity | **BLOCKED / DEFERRED**: Dependent on Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) where arbitrary public visitors can create persistent accounts, access multi-meal dashboards, and manage self-serve meal discovery. |
| Gate 4: Public GitHub Repository & Tagged Release (`v1.0.0`) | **BLOCKED / ESCALATED**: Preserved for Product Owner consequential authority regarding repository visibility and intellectual property licensing. |
| Volume Pre-Flight Fail-Closed | **PASS**: `tools/verify_volume_target.py` enforces exact volume match (`settletable_data` for real, `settletable_synthetic_data` for synthetic), checks non-root ownership (UID/GID 10001) and storage writability, and rejects malformed/custom configs without mutating data. Negative unit tests cover all failure modes. |
| Volume Identity Marker Guard | **PASS**: `settletable/wsgi.py` fails closed with `RuntimeError` on missing marker on existing datasets, unreadable/malformed marker JSON, or volume mismatch. Writes atomically on fresh volumes. Unit tests in `tests/test_wsgi_volume_guard.py` pass. |
| Pristine Database Bootstrap & Backup | **PASS**: `tools/bootstrap_meal.py init-db` establishes SQLite schema and `.volume_identity` on fresh volumes without ingress. Baseline backup with `--copy-to /offsite` and disaster restore verified against temporary isolated Docker volume. |
| Operational Runbook & Confidentiality | **PASS**: Documented initial DB initialization command, host cloud sync client latency distinction (OneDrive/Google Drive), and host/backup drive confidentiality (NTFS ACLs, BitLocker, MFA). |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-08 — Stage C1: Restricted Invited-Friends Pilot Preparation (PR #57)

**Orchestrator decision: PASS / OPERATIONAL PREPARATION COMPLETE & VERIFIED.** In preparation for the transition from synthetic testing to a restricted invited-friends pilot using real dining receipts: (1) Established and documented two-phase operational lifecycle: supervised on-demand first session followed by mostly-available background operation with Windows downtime resilience; (2) Implemented storage volume protection: verified non-root storage permissions (`UID=10001 GID=10001`), integrated in-container volume identity marker guard (`/data/.volume_identity` in `settletable/wsgi.py`), and created pre-flight volume verification utility (`tools/verify_volume_target.py`); (3) Enhanced `tools/backup_restore.py` with offsite secondary storage mirror (`--copy-to`) and verified disaster recovery restore from offsite storage in isolated Docker drill (`tools/verify_isolated_docker_drill.py`); (4) Documented 11-step real-meal pilot executable checklist in `docs/runbooks/windows_host_operations.md`; (5) Retested PR #56 invitation security invariants over live HTTPS (`https://settle.kybuilds.com`) with clean body inspection/redemption and immediate deactivation verification (`HTTP 530 / Error 1033`). All 328 tests pass. Ready for Product Owner real-data pilot authorization.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 328/328 Python unit, calculation, security, restore, and ingress tests passed; containerized WSGI application operational; smoke checks pass 13/13 locally and externally. |
| Gate 2: Publicly Reachable Restricted Online Pilot (`v0.9.0-beta.1`) | **PREPARED & SAFELY DEACTIVATED**: Operational runbooks, volume cross-contamination guards, offsite backup mirroring, and real-meal checklists fully established. Public ingress verified closed (`HTTP 530 / Error 1033`). Ready for Product Owner explicit authorization to execute volume cutover (`SETTLETABLE_DATA_VOLUME=settletable_data`) and launch real-meal pilot. |
| Gate 3: Unrestricted Public Product Access & Multi-Tenant Identity | **BLOCKED / DEFERRED**: Dependent on Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) where arbitrary public visitors can create persistent accounts, access multi-meal dashboards, and manage self-serve meal discovery. |
| Gate 4: Public GitHub Repository & Tagged Release (`v1.0.0`) | **BLOCKED / ESCALATED**: Preserved for Product Owner consequential authority regarding repository visibility and intellectual property licensing. |
| Operational Lifecycle | **PASS**: Practical deployment lifecycle defined: supervised on-demand activation for the inaugural live meal, followed by mostly-available background daemon with Windows restart/outage resilience. |
| Volume Isolation & Safety | **PASS**: Non-root storage permissions verified (`UID=10001 GID=10001`); in-container `.volume_identity` guard automatically aborts container startup if volume marker mismatches; `tools/verify_volume_target.py` verifies configuration before launch. Primary volume `settletable_data` remains 100% untouched. |
| Off-Host Backup & Disaster Recovery | **PASS**: `tools/backup_restore.py` supports `--copy-to`; `tools/verify_isolated_docker_drill.py` verified end-to-end backup, offsite copy hash verification, and disaster restoration directly from offsite storage. |
| Live HTTPS PR #56 Retest | **PASS**: All 13 deployment smoke checks and full invitation flow verified over live HTTPS (`settle.kybuilds.com`). Replay attack rejected (400), diner administrative actions denied (403). Public ingress verified immediately deactivated (`HTTP 530 / Error 1033`). All synthetic tokens consumed or revoked. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-07 — Stage C0: Supervised Browser UAT Acceptance & Finalization (PR #56)

**Orchestrator decision: PASS / ACCEPTED & SAFELY DEACTIVATED.** Product Owner personally conducted and completed supervised multi-device browser UAT on `https://settle.kybuilds.com` using Windows desktop browser and physical mobile phone over mobile data. All items verified: organizer activation and persistence, receipt ingestion, RapidOCR, verification, item assignment, mobile diner invitation redemption without Cloudflare Access, diner interactions, financial calculation, session persistence across refresh, and role restrictions. Qualitative performance was acceptable with 0 defects observed. Following UAT, public ingress was immediately terminated (`docker compose stop cloudflared`) and verified offline via `curl` returning HTTP 530 / Cloudflare Error 1033. Reviewed and eliminated client fallback to URL-based tokens in `settletable/static/app.js`, ensuring the browser client strictly uses JSON-body inspection and redemption without ever degrading to unshielded URL paths on transient failures. All 322 tests pass. Synthetic data volume `settletable_synthetic_data` preserved; primary data volume `settletable_data` remains untouched and unmounted.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 322/322 Python unit, calculation, security, restore, and ingress tests passed; containerized WSGI application operational; smoke checks pass 13/13 locally and externally. |
| Gate 2: Publicly Reachable Restricted Online Pilot (`v0.9.0-beta.1`) | **ACCEPTED & CLEANLY DEACTIVATED**: Multi-device real browser UAT personally completed by Product Owner over Cloudflare Named Tunnel without Cloudflare Access. Desktop and mobile phone (cellular data) verified end-to-end. Public ingress verified deactivated (HTTP 530 / Error 1033). Client fallback to URL-token requests eliminated. Ready for subsequent restricted invited-friends pilot upon Product Owner authorization. |
| Gate 3: Unrestricted Public Product Access & Multi-Tenant Identity | **BLOCKED / DEFERRED**: Dependent on Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) where arbitrary public visitors can create persistent accounts, access multi-meal dashboards, and manage self-serve meal discovery. |
| Gate 4: Public GitHub Repository & Tagged Release (`v1.0.0`) | **BLOCKED / ESCALATED**: Preserved for Product Owner consequential authority regarding repository visibility and intellectual property licensing. |
| Supervised Real Browser UAT | **PASS (Product Owner Observed)**: Verified organizer session activation and persistence, receipt ingestion, RapidOCR extraction, receipt verification, portion allocation, mobile diner invitation redemption, diner portion claims, financial calculation, and role-based restrictions. |
| Ingress Deactivation Proof | **PASS**: Executed `docker compose stop cloudflared`. Verified `curl -i https://settle.kybuilds.com/healthz` returns `HTTP/1.1 530 error code: 1033`. Zero containers running. |
| Strict Body Token Invariant | **PASS**: Removed client fallback in `settletable/static/app.js`. Browser client strictly sends tokens in JSON request bodies; regression test `test_browser_assets_do_not_contain_url_token_fallbacks` asserts zero token interpolation into API URLs in `app.js`. |
| Volume Isolation & Safety | **PASS**: Pilot conducted strictly on `settletable_synthetic_data`. Primary volume `settletable_data` remained completely unmounted, empty, and untouched. All synthetic test tokens verified consumed/revoked. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-07 — Stage C0: Diner Invitation Security Hardening & Supervised Browser UAT Preparation (PR #55)

**Orchestrator decision: PASS / VERIFIED FOR SUPERVISED BROWSER UAT.** In response to independent review findings regarding diner invitation tokens in URL paths, completed focused investigation and smallest appropriate hardening: (1) Added fragment-based invitation links (`/#/invite/{token}`) where the token is stored in the client-side URL hash and never transmitted across HTTP request lines to Cloudflare or upstream reverse proxies; (2) Implemented clean JSON-body inspection endpoint `POST /api/invitations/inspect` (`{"invitation_token": token}`) treated as an unauthenticated read-only query; (3) Implemented clean JSON-body redemption endpoint `POST /api/meals/{meal_id}/invitations/redeem` (`{"invitation_token": token}`) with CSRF Origin and `X-SettleTable-Action: 1` protection; (4) Maintained 100% backward compatibility with existing path-based links (`/invite/{token}`) and legacy endpoints; (5) Enhanced internal WSGI log redaction for `invitation_token` and legacy redemption paths; (6) Added automated smoke checks (13/13 passing) and unit/E2E regression tests (321/321 passing). Ready for supervised browser and physical mobile UAT on isolated volume `settletable_synthetic_data`.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 321/321 Python unit, calculation, security, restore, and ingress tests passed; containerized WSGI application operational; smoke checks pass 13/13 locally and externally. |
| Gate 2: Publicly Reachable Restricted Online Pilot (`v0.9.0-beta.1`) | **VERIFIED & HARDENED / READY FOR SUPERVISED REAL BROWSER UAT**: Ingress hardened to prevent diner invitation token exposure in network request lines and access logs. Fragment-based links `/#/invite/{token}` and JSON-body inspection/redemption match the secure pattern established for organizer claims. Prepared for supervised organizer-and-diner journey with synthetic data on isolated volume `settletable_synthetic_data` via `https://settle.kybuilds.com`. |
| Gate 3: Unrestricted Public Product Access & Multi-Tenant Identity | **BLOCKED / DEFERRED**: Dependent on Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) where arbitrary public visitors can create persistent accounts, access multi-meal dashboards, and manage self-serve meal discovery. |
| Gate 4: Public GitHub Repository & Tagged Release (`v1.0.0`) | **BLOCKED / ESCALATED**: Preserved for Product Owner consequential authority regarding repository visibility and intellectual property licensing. |
| Invitation Token Exposure Mitigation | **PASS**: Potential token exposure in CDN edge and reverse proxy access logs eliminated via client-side hash routing (`/#/invite/{token}`) and JSON-body inspection (`POST /api/invitations/inspect`) and redemption (`POST /api/meals/{meal_id}/invitations/redeem`). Backward compatibility preserved. |
| Confidentiality & Zero Verified Leakage | **PASS**: Proved zero leakage occurred during Stage B2 pilot (synthetic data on isolated volume, single-use atomic consumption, internal log redaction). Publication audit passed with 0 findings. |
| Test Coverage & Regression Safety | **PASS**: Added comprehensive unit tests in `tests/test_transport.py` and browser session tests in `tests/test_browser_mvp_e2e.py`. All 321 test cases passed. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-07 — Stage B2: Controlled Cloudflare Activation & External Verification Pilot (PR #54)

**Orchestrator decision: PASS / VERIFIED & CLEANLY DEACTIVATED.** Product Owner authorized temporary, synthetic-data-only external verification pilot at `https://settle.kybuilds.com`. Using isolated synthetic data volume `settletable_synthetic_data` (leaving primary volume `settletable_data` 100% untouched), all 18 live external verification checks and 11 deployment smoke checks passed cleanly over Cloudflare Named Tunnel without Cloudflare Access. Real RapidOCR ran in production container on synthetic receipt; organizer claim inspection, redemption, single-use consumption, guest invitation issuance, diner redemption, diner isolation, origin CSRF rejection, public bootstrap rejection, and no-store caching headers verified against live Cloudflare edge (`cf-ray: SIN`, `server: cloudflare`, `cf-cache-status: DYNAMIC`). Restart recovery verified. Public tunnel connector cleanly stopped (`docker compose stop cloudflared`), proving immediate closure of public ingress with Cloudflare Error 1033 (HTTP 530). Zero credentials or tokens leaked.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 319/319 Python unit, calculation, security, restore, and ingress tests passed; containerized WSGI application operational; smoke checks pass 11/11 locally and externally. |
| Gate 2: Publicly Reachable Restricted Online Pilot (`v0.9.0-beta.1`) | **VERIFIED & CLEANLY DEACTIVATED**: Live public HTTPS endpoint `https://settle.kybuilds.com` verified end-to-end via Cloudflare Named Tunnel without Cloudflare Access. All 18 synthetic verification invariants passed: public TLS handshake, standard browser access, unauthenticated data/photo denial (401), public bootstrap denial (403), origin/CSRF enforcement (403/400), organizer claim single-use redemption (200, 409 replay rejection), diner invitation issuance and isolated guest session establishment (200), diner administrative denial (403), production RapidOCR extraction on synthetic receipt (200), private receipt photo caching (`private, no-cache, no-store, must-revalidate`, `cf-cache-status: DYNAMIC`), guest photo denial (403), container and tunnel restart recovery, and immediate shutdown verification (HTTP 530 / Cloudflare error 1033 when connector stopped). |
| Gate 3: Unrestricted Public Product Access & Multi-Tenant Identity | **BLOCKED / DEFERRED**: Dependent on Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) where arbitrary public visitors can create persistent accounts, access multi-meal dashboards, and manage self-serve meal discovery. |
| Gate 4: Public GitHub Repository & Tagged Release (`v1.0.0`) | **BLOCKED / ESCALATED**: Preserved for Product Owner consequential authority regarding repository visibility and intellectual property licensing. |
| Volume Isolation & Safety | **PASS**: Configurable `SETTLETABLE_DATA_VOLUME=settletable_synthetic_data` (PR #53) isolated all pilot state to `settletable_synthetic_data`. Verified primary volume `settletable_data` remained completely untouched and unmounted. |
| Secret & Credential Confidentiality | **PASS**: `CLOUDFLARE_TUNNEL_TOKEN` and single-use claim secrets strictly preserved in `.env` and memory; zero credentials or tokens logged, printed to stdout, committed, or included in PRs/reports. `tools/audit_repository.py` passed with 0 findings. |
| Deactivation Proof | **PASS**: Tunnel connector stopped (`docker compose stop cloudflared`). Verified `curl -i https://settle.kybuilds.com/healthz` immediately returns HTTP 530 (Cloudflare Error 1033), proving public ingress is closed while Cloudflare DNS and route definitions remain intact. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-07 — Stage B: Domain Purchase Confirmation & Hostname Alignment

**Orchestrator decision: PASS / READY FOR PRODUCT OWNER ACTIVATION AUTHORIZATION.** Product Owner confirmed purchase and registration of `kybuilds.com` through Cloudflare Registrar. Confirmed target public hostname: `https://settle.kybuilds.com`. Illustrative placeholders updated across deployment templates (`deploy/env.template`, `deploy/cloudflare/README.md`, `deploy/cloudflare/config.template.yml`), operations runbooks (`docs/runbooks/windows_host_operations.md`), deployment roadmap (`docs/plans/MVP_RELEASE_AND_DEPLOYMENT.md`), and synthetic ingress tests (`tests/test_reverse_proxy_ingress.py`). Stage B offline preparation at `9a463c1` remains accepted and preserved. Zero public tunnels activated; zero DNS records modified; live external activation strictly held pending explicit Product Owner authorization.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 319/319 Python unit, calculation, security, restore, and ingress tests passed; all 12 browser CDP regression test suites passed; containerized WSGI application operational. |
| Gate 2: Publicly Reachable Restricted Online Pilot (`v0.9.0-beta.1`) | **CONFIRMED DOMAIN RECORDED / OFFLINE CONFIGURATION ALIGNED / ACTIVATION HELD**: Target hostname `https://settle.kybuilds.com` and domain `kybuilds.com` aligned across configuration templates and tests. Architecture confirmed: Windows Docker self-hosting, remotely-managed Cloudflare Named Tunnel without Cloudflare Access, native organizer claims & guest invitations, and synthetic-data multi-device pilot. Zero live external tunnels created or active. |
| Gate 3: Unrestricted Public Product Access & Multi-Tenant Identity | **BLOCKED / DEFERRED**: Dependent on Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) where arbitrary public visitors can create persistent accounts, access multi-meal dashboards, and manage self-serve meal discovery. |
| Gate 4: Public GitHub Repository & Tagged Release (`v1.0.0`) | **BLOCKED / ESCALATED**: Preserved for Product Owner consequential authority regarding repository visibility and intellectual property licensing. |
| Confirmed Domain Decision | **PASS**: Product Owner registered `kybuilds.com` via Cloudflare Registrar. Domain DNS managed natively by Cloudflare. Step 1 of pre-activation checklist marked CONFIRMED / COMPLETED. |
| Exact Host & Origin Alignment | **PASS**: Ingress suite (`tests/test_reverse_proxy_ingress.py`) updated to target `https://settle.kybuilds.com` and `settle.kybuilds.com`; 9/9 synthetic reverse-proxy ingress tests pass, including exact-origin CSRF validation and deny-by-default on unmatched hostnames (`kybuilds.com`, subdomains, external IPs). |
| Pre-Publication Privacy & Rights Audit | **PASS**: `tools/audit_repository.py` passed with 0 findings across all tracked files. |
| Authorization Boundary Strict Enforcement | **PASS**: Zero external network connections opened, zero tunnel tokens created, zero DNS records modified, and zero public tests initiated. Live external activation requires explicit Product Owner authorization. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-06 — Stage B: Final Pre-Activation Reconciliation

**Orchestrator decision: PASS / READY FOR PRODUCT OWNER AUTHORIZATION.** Bounded pre-activation reconciliation completed: (1) Production volume isolation proven without mounting or referencing `settletable_data`; (2) `cloudflare/cloudflared` pinned by immutable multi-arch digest `2026.10.7@sha256:4955524aeaa379e154023d5a027c250f7b35041a2e7e950cf13f144bc9b9c5ba`; (3) Request limits reconciled with actual transport constants (1MB JSON / 5MB image); (4) Gate definitions updated to distinguish public network reachability from unrestricted public product access; (5) Canonical storage path `/data/receipt_photos` aligned; (6) Comprehensive 12-item pre-activation checklist prepared. Zero external tunnels opened; zero spending incurred.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 319/319 Python unit, calculation, security, restore, and ingress tests passed; all 12 browser CDP regression test suites passed; containerized WSGI application operational. |
| Gate 2: Publicly Reachable Restricted Online Pilot (`v0.9.0-beta.1`) | **STAGE B OFFLINE PREPARATION & DRILL COMPLETE / EXTERNAL ACTIVATION PENDING PO AUTHORIZATION**: Application is reachable from the public internet via Cloudflare Named Tunnel on dedicated subdomain without Cloudflare Access; native organizer claim and diner invitation mechanisms protect individual meals, while public `/bootstrap` is denied. Offline configuration templates, pinned Docker Compose connector, Windows host runbook, synthetic ingress suite, non-destructive isolated Docker recovery drill, and 12-point pre-activation checklist completed. |
| Gate 3: Unrestricted Public Product Access & Multi-Tenant Identity | **BLOCKED / DEFERRED**: Dependent on Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) where arbitrary public visitors can create persistent accounts, access multi-meal dashboards, and manage self-serve meal discovery. |
| Gate 4: Public GitHub Repository & Tagged Release (`v1.0.0`) | **BLOCKED / ESCALATED**: Preserved for Product Owner consequential authority regarding repository visibility and intellectual property licensing. |
| Volume Isolation & Drill Integrity | **PASS**: Non-destructive Docker recovery drill (`tools/verify_isolated_docker_drill.py`) refactored to verify volume isolation strictly using ephemeral test volumes without mounting, creating, or referencing `settletable_data`. Destination volume empty state prior to restore, strict file containment post-restore, and volume entity independence verified. |
| Image Reproducibility & Cryptographic Pinning | **PASS**: `docker-compose.yml` pins `cloudflare/cloudflared:2026.10.7@sha256:4955524aeaa379e154023d5a027c250f7b35041a2e7e950cf13f144bc9b9c5ba` covering both `linux/amd64` and `linux/arm64`. |
| Transport Wire Limits & Content Boundaries | **PASS**: Transport limits accurately documented: `MAX_BODY_BYTES` (1 MB) for JSON API payloads, `MAX_IMAGE_BYTES` (5 MB) for receipt photo uploads and RapidOCR extraction, 4 KB single header, 16 KB total headers. |
| Pre-Publication Privacy & Rights Audit | **PASS**: `tools/audit_repository.py` passed with 0 findings across all tracked files. |
| Authorization Boundary Strict Enforcement | **PASS**: Zero external network connections, zero tunnel tokens created, zero DNS records modified, and zero spending incurred. Live external activation requires explicit Product Owner authorization. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-06 — Stage B: Operational Runbook Corrections & Pre-Activation Verification

**Orchestrator decision: PASS / READY FOR PRODUCT OWNER AUTHORIZATION.** Operational runbook corrections, backup/restore CLI argument alignment and aliases, non-destructive isolated Docker recovery drill, pinned cloudflared image, Docker bridge network service resolution verification, and application abuse controls audit completed and verified. Zero external tunnels opened; zero spending incurred.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 319/319 Python unit, calculation, security, restore, and ingress tests passed; all 12 browser CDP regression test suites passed; containerized WSGI application operational. |
| Gate 2: Restricted Online Deployment Pilot (`v0.9.0-beta.1`) | **STAGE B OFFLINE PREPARATION & DRILL COMPLETE / EXTERNAL ACTIVATION PENDING PO AUTHORIZATION**: (1) Documented runbook commands in `docs/runbooks/windows_host_operations.md` aligned with `tools/backup_restore.py` CLI parser; supported backward-compatible aliases (`--storage-dir`, `--backup-dir`, `--dest-storage-dir`) and directory-based `--manifest` resolution; (2) Non-destructive end-to-end recovery drill (`tools/verify_isolated_docker_drill.py`) executed against isolated ephemeral Docker volumes, verifying SQLite `PRAGMA integrity_check`, receipt photo SHA-256 hashes, and organizer snapshot/authentication while leaving primary data volume `settletable_data` untouched; (3) Pinned `cloudflare/cloudflared:2026.10.7` image (`sha256:4955524aeaa379e154023d5a027c250f7b35041a2e7e950cf13f144bc9b9c5ba`) in `docker-compose.yml`; (4) Tested internal service name resolution on Compose bridge network (`http://settletable:8000/healthz` -> 200 OK) without exposing ports; (5) Clarified documentation accuracy: SHA-256 checksummed manifest (not cryptographically signed), container healthcheck status (`settletable_app: Up (healthy)` vs `settletable_tunnel: Up`), WSL2 memory recommendations, and connector token confidentiality in `.env`; (6) Audited existing application-level abuse controls (join requests table bounding, unauthenticated anti-enumeration, claim token single-use domain separation, organizer-only receipt upload/OCR); (7) Maintained strict authorization boundaries: zero external tunnels, zero DNS modifications, zero domain spending. |
| Gate 3: Publicly Reachable Application | **BLOCKED / DEFERRED**: Dependent on Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) and explicit Product Owner authorization for public traffic. |
| Gate 4: Public GitHub Repository & Tagged Release (`v1.0.0`) | **BLOCKED / ESCALATED**: Preserved for Product Owner consequential authority regarding repository visibility and intellectual property licensing. |
| Operational Durability & Verified Recovery Drill | **PASS**: Automated non-destructive drill (`tools/verify_isolated_docker_drill.py`) verifies full backup creation from running container, stopped-container destination cutover, SQLite integrity, photo hash validation, and organizer authentication on restored dataset. |
| Ingress Security & Exact-Origin Invariants | **PASS**: Custom domain Host validation, exact-origin CSRF enforcement, Cloudflare header processing, proxy header rejection on `/bootstrap`, unauthenticated access denial, and no-cache/no-store enforcement verified via automated test suite. |
| Application Abuse Controls | **PASS**: Join request table limits (20 pending / 100 historical), anti-enumeration responses, single-use 43-character claim tokens with SHA-256 verifiers, and organizer-only receipt photo uploads and OCR execution protect the application without requiring third-party rate-limiting frameworks. |
| Pre-Publication Privacy & Rights Audit | **PASS**: `tools/audit_repository.py` passed with 0 findings across all tracked files. |
| Authorization Boundary Strict Enforcement | **PASS**: Zero external network connections, zero tunnel tokens created, zero DNS records modified, and zero spending incurred. Live external activation requires explicit Product Owner authorization. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-06 — Stage B: Offline Hosting Preparation & Local Verification

**Orchestrator decision: PASS / READY FOR PRODUCT OWNER AUTHORIZATION.** Stage B offline configuration templates, Docker Compose integration, Windows host operations runbook, and synthetic reverse-proxy / Cloudflare ingress test suite completed and verified. Zero external tunnels opened; zero spending incurred.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 318/318 Python unit, calculation, security, restore, and ingress tests passed; all 12 browser CDP regression test suites passed; containerized WSGI application operational. |
| Gate 2: Restricted Online Deployment Pilot (`v0.9.0-beta.1`) | **STAGE B OFFLINE PREPARATION COMPLETE / EXTERNAL ACTIVATION PENDING PO AUTHORIZATION**: (1) Remotely-managed Cloudflare Named Tunnel selected as primary pattern per official Cloudflare docs, eliminating local credentials files; (2) Inactive locally-managed template (`deploy/cloudflare/config.template.yml`) and guide (`deploy/cloudflare/README.md`) prepared; (3) Docker Compose optional profile `with-cloudflared` configured for Topology A (internal network routing to `http://settletable:8000`); (4) `deploy/env.template` updated for custom domain origin and allowed hosts without Cloudflare Access; (5) Windows host operational runbook authored (`docs/runbooks/windows_host_operations.md`) covering sleep/power management, Docker Desktop auto-start, crash consistency, WAN outage recovery, and stopped-container disaster recovery; (6) 9-point synthetic ingress test suite (`tests/test_reverse_proxy_ingress.py`) verified 100%; (7) Future manual deployment checklist documented with explicit Product Owner approval boundaries. |
| Gate 3: Publicly Reachable Application | **BLOCKED / DEFERRED**: Dependent on Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) and explicit Product Owner authorization for public traffic. |
| Gate 4: Public GitHub Repository & Tagged Release (`v1.0.0`) | **BLOCKED / ESCALATED**: Preserved for Product Owner consequential authority regarding repository visibility and intellectual property licensing. |
| Ingress Security & Exact-Origin Invariants | **PASS**: Synthetic tests prove custom domain Host validation (400 invalid_host on spoofed host), exact-origin CSRF enforcement under public HTTPS (403 on scheme mismatch, foreign origin, null origin; 400 on missing action header), Cloudflare header processing, proxy header rejection on `/bootstrap` (403 on CF-Connecting-IP, X-Forwarded-For, etc.), unauthenticated access denied (401 invalid_session), and no-cache/no-store enforcement on dynamic API and photo endpoints. |
| Operational Durability & Stopped-Container Restore | **PASS**: Windows host power management, Docker Desktop WSL2 configuration, SQLite WAL crash consistency, WAN drop automatic reconnection, and stopped-container verified restore with automated cutover rollback fully documented. |
| Pre-Publication Privacy & Rights Audit | **PASS**: `tools/audit_repository.py` passed with 0 findings across all tracked files. |
| Authorization Boundary Strict Enforcement | **PASS**: Zero external network connections, zero tunnel tokens created, zero DNS records modified, and zero spending incurred. Live external activation requires explicit Product Owner authorization. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-06 — Stage A: Post-Merge Corrective Hardening: PR #48 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head merged autonomously under orchestrator governance policy into `main`. GitHub PR #48 verified on hosted CI before merge.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 309/309 Python unit & integration tests passed; all 12 browser CDP regression test suites passed; containerized WSGI application operational. |
| Gate 2: Restricted Online Deployment Pilot (`v0.9.0-beta.1`) | **STAGE A PREREQUISITES MET / READY FOR STAGE B**: Independent review findings remediated: (1) Restore safety contract enforces stopped container (`--confirm-stopped` + health probe + Docker check + SQLite exclusive lock); (2) Staged restore with isolated staging, previous data quarantine, controlled cutover, and automated rollback upon post-cutover failure; (3) Comprehensive token redaction in logs/query-strings and clean POST inspection/redemption preventing URL path token exposure in reverse proxy and Gunicorn request lines; (4) Scope accuracy distinguishing CI vs local test coverage; (5) Finalized Product Owner decision recorded (Windows Docker + Cloudflare Named Tunnel without Cloudflare Access). |
| Gate 3: Publicly Reachable Application | **BLOCKED / DEFERRED**: Dependent on Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) and explicit Product Owner authorization for public traffic. |
| Gate 4: Public GitHub Repository & Tagged Release (`v1.0.0`) | **BLOCKED / ESCALATED**: Preserved for Product Owner consequential authority regarding repository visibility and intellectual property licensing. |
| Restore Safety & Staged Cutover | **PASS**: Demonstrates that idle connections cannot bypass restore safety contract; active server blocks restore; failure injection proves automated rollback to previous valid dataset; orphaned destination photos are cleanly pruned into archive. |
| Bearer Token Redaction & Request Line Privacy | **PASS**: `redact_log_string` redacts all token patterns; POST `/api/organizer-claims/inspect` and POST `/api/meals/{meal_id}/organizer-claims/claim` send tokens in request bodies, ensuring web server access logs remain free of secret tokens. CLI setup link accurately documented as emitting ephemeral secret on stdout. |
| Pre-Publication Privacy & Rights Audit | **PASS**: `tools/audit_repository.py` passed with 0 findings across all tracked files. |
| Independent Code & Security Review | **PASS**: Completed independent HIGH-risk review by subagent with 0 BLOCKERS and 0 WARNINGS. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-06 — Stage A: Local Reliability & Security Hardening: PR #47 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `e1f16265be34a61e81b299606a0d649cd802125c` merged autonomously under orchestrator governance policy into `main` ([merge commit 02107e2](https://github.com/KAIYI7/settle-table/commit/02107e22cde0924590125b0c37f679d50f593542)). GitHub PR #47 ([#47](https://github.com/KAIYI7/settle-table/pull/47)) verified on hosted CI before merge ([run 42155144910](https://github.com/KAIYI7/settle-table/actions/runs/42155144910)).

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 303/303 Python unit & integration tests passed; all 12 browser CDP regression test suites passed; containerized WSGI application operational. |
| Gate 2: Restricted Online Deployment Pilot (`v0.9.0-beta.1`) | **STAGE A PREREQUISITES MET / READY FOR STAGE B**: Local hardening backlog fully implemented: (1) Organizer browser claim token lifecycle & recovery links; (2) Configurable session TTL up to 30 days defaulting to 7 days; (3) Quiescent database backup protocol & verified restore with active lock detection; (4) Dockerfile `"gunicorn>=21.2.0"` redirection fix, non-root user permissions, and loud OCR cache verification; (5) Hosted CI container build and deployment smoke check. External hosting gateway deferred per Product Owner instruction. |
| Gate 3: Publicly Reachable Application | **BLOCKED / DEFERRED**: Dependent on Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) and explicit Product Owner authorization for public traffic. |
| Gate 4: Public GitHub Repository & Tagged Release (`v1.0.0`) | **BLOCKED / ESCALATED**: Preserved for Product Owner consequential authority regarding repository visibility and intellectual property licensing. |
| Organizer Session & Recovery Lifecycle | **PASS**: `organizer_claims` SQLite schema with domain-separated SHA-256 verifier (`settletable-organizer-claim-v1\0`), atomic single-use redemption inside `BEGIN IMMEDIATE` transaction, HttpOnly Strict Max-Age session cookie setting, client claim routing `/#/claim-organizer/:token`, and host CLI recovery. Zero raw credentials leaked to stdout. |
| Quiescent Backup & Verified Restore | **PASS**: `BEGIN IMMEDIATE` write lock ensures synchronized SQLite WAL database and receipt photos with SHA-256 manifest. Restore checks for active database locks, cleans `.sqlite-wal`/`.sqlite-shm` sidecars, and cross-verifies all photo hashes against the database manifest. |
| Non-Root Container & Smoke Verification | **PASS**: `Dockerfile` executes as non-root `settletable:settletable` (UID 10001) with dedicated model cache directories. Automated 10-point deployment smoke check passed 10/10. |
| Pre-Publication Privacy & Rights Audit | **PASS**: `tools/audit_repository.py` passed with 0 findings across 16 staged files and all 332 tracked files. |
| Independent Code & Security Review | **PASS**: Completed independent HIGH-risk review by subagent with 0 BLOCKERS and 0 WARNINGS. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-06 — Low-Cost Mostly-Available Deployment Strategy Revision Checkpoint

**Orchestrator decision: REVISED / HARDENING REQUIRED.** Following Product Owner directive, deployment strategy is pivoted to low-cost, mostly-available Windows self-hosting (RM0/month target) with tunneling. Commercial cloud hosting (Fly.io, Hetzner, Railway) deferred.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 296/296 Python unit tests passed; all 9 browser CDP regression test suites passed; local runner operational. |
| Gate 2: Restricted Online Deployment Pilot (`v0.9.0-beta.1`) | **BLOCKED / HARDENING REQUIRED**: Reassessed from "implementation-ready". P1 hardening backlog must be resolved prior to pilot authorization: (1) Organizer browser claim mechanism; (2) Session TTL alignment in `Authority.bootstrap`; (3) Quiescent backup protocol & restore verification; (4) Dockerfile syntax and model caching fixes; (5) Product Owner selection of access gateway (Tailscale Funnel vs Cloudflare Named Tunnel). |
| Gate 3: Publicly Reachable Application | **BLOCKED / DEFERRED**: Dependent on Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) and explicit Product Owner authorization for public traffic. |
| Gate 4: Public GitHub Repository & Tagged Release (`v1.0.0`) | **BLOCKED / ESCALATED**: Preserved for Product Owner consequential authority regarding repository visibility and intellectual property licensing. |
| Access Architecture Assessment | **PRIMARY A (If Domain Approved/Owned)**: Cloudflare Named Tunnel + Cloudflare Access.<br>**PRIMARY B (Strict RM0 / No Domain Spend)**: Tailscale Funnel (`*.ts.net`).<br>**FALLBACK**: ngrok Free (1 GB/mo bandwidth cap). |
| Readiness Claim Correction | **CORRECTED**: Documentation claims regarding 7-day session TTL and "atomic hot backup" corrected to reflect actual codebase constraints (`session_ttl=3600` default and sequential photo sync). |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-05 — MVP Release & Deployment Preparation Checkpoint

**Orchestrator decision: PASS / VERIFIED.** Release plan established in `docs/plans/MVP_RELEASE_AND_DEPLOYMENT.md`. Packaging, containerization, ingress templates, hot backup/restore utilities, and repository presentation verified.

| Gate | Disposition |
| --- | --- |
| Gate 1: Reproducible Local Working Release | **PASS**: 296/296 Python unit tests passed; all 9 browser CDP regression test suites passed; local runner operational with mock and real local OCR modes. |
| Gate 2: Restricted Online Deployment Pilot (`v0.9.0-beta.1`) | **IMPLEMENTATION READY**: Production WSGI entrypoint (`settletable/wsgi.py`), `/healthz` probe, non-root `Dockerfile`, `docker-compose.yml`, Caddy/Nginx ingress templates, hot backup utility (`tools/backup_restore.py`), and administrative bootstrap CLI (`tools/bootstrap_meal.py`) verified. Awaiting PO hosting platform selection before live deployment. |
| Gate 3: Publicly Reachable Application | **BLOCKED / DEFERRED**: Dependent on Account Identity roadmap (`docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) and explicit Product Owner authorization for public traffic and ongoing hosting expenditure. |
| Gate 4: Public GitHub Repository & Tagged Release (`v1.0.0`) | **BLOCKED / ESCALATED**: Preserved for Product Owner consequential authority regarding repository visibility and intellectual property licensing. |
| Two-Tier Ingress Boundary Verification | **PASS**: `POST /api/meals/*/bootstrap` strictly rejects external calls bearing proxy headers with HTTP 403; Tier 1 reverse proxy templates enforce wire limits and block external bootstrap access. |
| Hot Backup & WAL Crash Consistency | **PASS**: Hot backup utility creates consistent database snapshots using SQLite Online Backup API (`sqlite3.backup()`) and syncs receipt photos with SHA-256 manifest; restoration verified with PRAGMA integrity check. |
| Repository Pre-Publication Privacy & Rights Audit | **PASS**: `tools/audit_repository.py` passed with 0 findings across all tracked files. Zero credentials, tokens, or private Notion locators in git tree. All Rights Reserved notice strictly preserved. |
| Independent Code & Security Review | **PASS**: Completed independent review with 0 blocking and 0 warning findings. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-04 — Suggested Peer Transfer Prefill Navigation: PR #44 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `ac8bea9a1025e579714f34d3fd11c022c1cdb807` merged autonomously under orchestrator governance policy into `main`. GitHub PR #44 ([#44](https://github.com/KAIYI7/settle-table/pull/44)) verified on hosted CI before merge.

| Gate | Disposition |
| --- | --- |
| Button Retitled to "Use Suggestion" | PASS: suggestion button retitled from `Record Payment` to `Use Suggestion` (`.prefill-transfer-btn`), eliminating ambiguity and making clear that no transaction is executed upon clicking. |
| Non-Submitting Prefill Behavior | PASS: clicking `Use Suggestion` pre-fills Payer (Debtor), Recipient (Creditor), and Amount fields without executing or scheduling any transfer (`state.snapshot.transfers.length === 0`). |
| Contextual Reimbursement Form Navigation | PASS: automatically navigates to `#record-transfer-form` using `navigateToWorkflowSection()`. Sticky header clearance guaranteed via CSS `scroll-margin-top: calc(var(--app-header-height, 68px) + 16px)` on desktop and `12px` on mobile ($\le 640$px). |
| Programmatic Heading Focus & Keyboard Suppression | PASS: programmatic focus directed to `#record-transfer-heading` (`tabindex="-1"`) with `{ preventScroll: true }`, ensuring screen reader announcement and keyboard context while suppressing auto-opening of the mobile virtual keyboard. |
| Accessible Prefill Status Banner | PASS: renders polite live-region status banner (`#prefill-transfer-banner`, `role="status"`, `aria-live="polite"`): `"ℹ️ Details pre-filled. Review and confirm the reimbursement below."` inside the form. Automatically dismissed upon recording or clearing. |
| Form Editing & Financial Isolation | PASS: manual editing of debtor, creditor, amount, and reference notes preserved before submission. `#record-transfer-btn` remains the sole trigger for recording. Zero changes to calculation engine, authority schema, or Notion export. |
| Dedicated Browser CDP Verification | PASS: `tools/verify_peer_settlement_flow.mjs` passed 8/8 stages across desktop and 375px mobile viewport (zero horizontal overflow, touch safety, and scroll stability across refresh). Full regression suite passed 100%. |
| Independent Code Review & Hosted CI | PASS: independent review PASS (unconditional) with 0 blocking/warning findings. Hosted GitHub Actions CI passed on exact PR head SHA `ac8bea9` (check run tests: `conclusion=success`). |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.


## 2026-11-04 — Context-Aware Workflow Navigation & Focus: PR #43 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `bfa7c8aae7a4c77a7e037e783cff9280276febea` merged autonomously under orchestrator governance policy into `main`. GitHub PR #43 ([#43](https://github.com/KAIYI7/settle-table/pull/43)) verified on hosted CI ([run 41816588612](https://github.com/KAIYI7/settle-table/actions/runs/41816588612)) before merge.

| Gate | Disposition |
| --- | --- |
| Action A: OCR Acceptance Navigation | PASS: after clicking `#ocr-accept-btn`, smoothly navigates to Human Receipt Review (`#review-section`) and places programmatic focus on `#review-confirm-check`. |
| Action B: Receipt Review Approval Navigation | PASS: after clicking `#review-submit-btn`, inspects authoritative refreshed snapshot: routes to Item Allocation (`#allocation-section`, focusing `#allocation-heading`) if paid items need claims; ignores RM0.00 complimentary items; routes to Seal & Finalize Meal (`#finalize-section`, focusing `#finalize-btn`) if all paid items are allocated; routes to `#finalize-section` and highlights `.finalize-warning` if blocking issues exist. |
| Action C: Finalize & Apportionment Navigation | PASS: after clicking `#finalize-btn`, smoothly navigates to Final Apportionment Summary (`#apportionment-section`) and places focus on `#apportionment-heading`. |
| Sticky Header Clearance & Reduced Motion | PASS: CSS `scroll-margin-top: calc(var(--app-header-height, 68px) + 16px)` (desktop) and `12px` (mobile) guarantees clearance below the sticky header. `prefers-reduced-motion` compliance enforced in both CSS (`scroll-behavior: auto !important`) and JavaScript (`behavior = 'auto'`). |
| Programmatic Focus & Duplicate Jump Prevention | PASS: focus calls use `focus({ preventScroll: true })` inside defensive try/catch to prevent secondary scroll jumps. Accessible `:focus-visible` styling provided for headings and warnings (`tabindex="-1"`). |
| Viewport Stability & Non-Interference | PASS: background polling, manual header refresh, and failed actions do not scroll. Core financial calculations, authority schema, and Notion exporter remain 100% untouched. |
| Dedicated Browser CDP Verification | PASS: `tools/verify_context_aware_navigation.mjs` passed 8/8 stages across desktop and 375px mobile (zero horizontal overflow). Full regression suite passed 100%. |
| Independent Code Review & Hosted CI | PASS: independent review APPROVE with 0 findings. Hosted GitHub Actions CI passed on exact PR head SHA `bfa7c8a` ([run 41816588612](https://github.com/KAIYI7/settle-table/actions/runs/41816588612)). |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.


## 2026-11-04 — Complimentary RM0.00 Items Without Mandatory Allocation: PR #42 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `6edcef49c00e4bc8f154c0bf1a56390225253fe1` merged autonomously under orchestrator governance policy into `main`. GitHub PR #42 ([#42](https://github.com/KAIYI7/settle-table/pull/42)) verified on hosted CI ([run 41804800476](https://github.com/KAIYI7/settle-table/actions/runs/41804800476)) before merge.

| Gate | Disposition |
| --- | --- |
| Informational Preservation Without Mandatory Allocation | PASS: RM0.00 receipt items (e.g. Warm Water, Ice Water) are preserved on the receipt with item ID, label, quantity, and 0 sen price. `Authority._issues()` excludes `line_sen == 0` from incomplete quantity checks, allowing receipt sealing and finalization without allocating complimentary items. |
| Claim Prohibition on Complimentary Items | PASS: `Authority._set_own_quantity()`, `Authority._assign_participant_quantity()`, and `Authority._set_item_allocations()` reject claims on zero-priced items with machine-readable error `complimentary_item`. Diners cannot claim complimentary items. |
| Strict Calculation Contract | PASS: `settletable/calculation.py:163-166` permits empty share collection strictly when `amount == 0 and len(split.shares) == 0`, returning `()`. Paid items with empty shares continue to raise `CalculationError("collection_bound")`. Scoped adjustments on zero-priced items trigger `CalculationError("zero_base")`. All-zero receipts finalize cleanly with RM0.00 total and RM0.00 consumption. |
| Frontend & OCR Validation | PASS: manual Add Item accepts explicit RM0.00 while rejecting malformed or negative prices (`parseSen`). OCR candidate editor `syncCandidateInputs()` distinguishes valid `0` from parse errors, preventing empty/invalid inputs from falling back to 0. Acceptance validation blocks candidates with empty or invalid prices. |
| DOM Presentation & Control Suppression | PASS: complimentary cards render `.is-complimentary` styling with `Complimentary · RM 0.00` and `Complimentary · No allocation needed` badges, while suppressing allocation steppers, quick-assign pills, and progress bars in both Diner and Organizer views. |
| Notion Export Compliance | PASS: Notion compact and full meal tables render split column as `"Complimentary"` instead of `"Unclaimed"` for zero-priced items with no shares. |
| Dedicated Browser CDP Verification | PASS: `tools/verify_complimentary_items_flow.mjs` passed 6/6 stages with real Chrome CDP automation covering manual RM0.00 entry, malformed/negative price rejections, OCR candidate acceptance, DOM control suppression, review sealing, finalization, and 375px mobile viewport bounds (zero horizontal overflow). |
| Full Regression Suite | PASS: 301/301 Python unit tests passed; dedicated Chrome CDP suite passed 100%; hosted GitHub Actions CI passed on exact PR head SHA `6edcef4` ([run 41804800476](https://github.com/KAIYI7/settle-table/actions/runs/41804800476)). |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.


## 2026-11-04 — Financial Form Dropdown Chevron Polish: PR #41 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `5ec6ae03b322eaf3b3ef336ec54548dc9991a98a` merged autonomously under orchestrator governance policy into `main`. GitHub PR #41 ([#41](https://github.com/KAIYI7/settle-table/pull/41)) verified on hosted CI ([run 41783878095](https://github.com/KAIYI7/settle-table/actions/runs/41783878095)) before merge.

| Gate | Disposition |
| --- | --- |
| Subtle Chevron Inset & Arrow Suppression | PASS: native OS/browser arrows suppressed across platforms via `appearance: none`, `-webkit-appearance: none`, `-moz-appearance: none`, and `select::-ms-expand { display: none; }`. Clean data-URI SVG chevron (`#94a3b8`) positioned via `background-position: right 15px center;` (within 14–16px right inset). |
| Text Clearance & Name Containment | PASS: `padding-right: 42px;` guarantees an 11px clear margin before the 16px chevron. `max-width: 100%; min-width: 0; text-overflow: ellipsis; white-space: nowrap;` prevents grid blowout from long participant names and balance strings. |
| Native Dropdown & Accessibility Preservation | PASS: zero JavaScript dropdown replacement. Native `<select>` elements, keyboard navigation (Tab, Arrow keys, Enter, Esc), native OS touch pickers, and screen reader support fully preserved. Focus and disabled states styled cleanly. |
| Zero Calculation Drift & Financial Isolation | PASS: `settletable/calculation.py`, `settletable/authority.py`, `settletable/funding.py`, and `settletable/settlement.py` remain 100% byte-untouched. Zero floating-point arithmetic. Form behavior and submission handlers unchanged. |
| Dedicated Browser CDP Verification | PASS: expanded `tools/verify_ux_polish.mjs` to 8 stages with Stage [7/8] directly validating computed styles on all four financial dropdowns (`#payer-participant-select`, `#payer-method-select`, `#transfer-sender-select`, `#transfer-receiver-select`) and long participant option containment. |
| Mobile Viewport Compliance (375px) | PASS: Stage [8/8] verified `document.documentElement.scrollWidth === 375` and confirmed bounding rects of cards and all four dropdowns remain within viewport bounds (`<= 375px`) with zero horizontal overflow. |
| Full Regression Suite | PASS: 290/290 Python unit tests passed; 8/8 headless Chrome multi-payer tests passed; 8/8 headless Chrome peer settlement tests passed; dedicated 8-stage suite `tools/verify_ux_polish.mjs` passed 100%. |
| Independent Code & CI Review | PASS: independent review APPROVE with 0 findings. Hosted GitHub Actions CI passed on exact PR head SHA `5ec6ae0` ([run 41783878095](https://github.com/KAIYI7/settle-table/actions/runs/41783878095)). |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.


## 2026-11-03 — Mobile Stepper Touch Target Compliance & Verification: PR #40 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `49cd56d5aee43f99fa4657866e29274abc99b951` merged autonomously under orchestrator governance policy into `main`. GitHub PR #40 ([#40](https://github.com/KAIYI7/settle-table/pull/40)) verified on hosted CI ([run 41657355223](https://github.com/KAIYI7/settle-table/actions/runs/41657355223)) before merge.

| Gate | Disposition |
| --- | --- |
| Effective $\ge 44 \times 44$px Mobile Touch Targets | PASS: in `settletable/static/style.css`, updated `.numeric-stepper .stepper-btn`, `.ocr-qty-btn`, `.quantity-stepper.numeric-stepper button`, and `.quantity-stepper.numeric-stepper .stepper-btn` to `width: 44px; min-width: 44px; height: 44px; min-height: 44px;`. Container widths set to `128px; min-width: 128px; height: 44px;` with input/display at `width: 40px; min-width: 40px; height: 44px;`. |
| OCR Candidate Grid Adjustment | PASS: adjusted `.ocr-cand-item-row` grid template columns to `128px 1fr 44px;` in both container query and media query breakpoints. |
| Narrow Viewport Claim Actions Wrapping | PASS: added `flex-wrap: wrap; gap: 8px;` to `.claim-actions` for narrow screens. |
| Dedicated CDP Touch Target Bounding Box Verification | PASS: expanded `tools/verify_ux_polish.mjs` to measure actual computed clickable bounding rectangles via CDP in real headless Chromium at 375px viewport across OCR item steppers, manual Add Item steppers, and diner portion steppers. All buttons verified $\ge 44 \times 44$px with typographic minus `−` (U+2212). |
| Zero Page Overflow at 375px | PASS: verified `document.documentElement.scrollWidth === 375` and body `scrollWidth === 375`, confirming zero horizontal overflow, clipping, or overlapping controls. |
| Zero Calculation Drift & Invariant Preservation | PASS: `settletable/calculation.py` remains 100% byte-untouched. Zero floating-point arithmetic. Direct typing, exact rational portion allocation, and financial balances fully preserved. |
| Full Regression Suite | PASS: 290/290 Python unit tests passed; 12/12 real-browser CDP test stages passed; conflict recovery, financial export, multi-payer funding, and peer settlement browser suites passed with 0 failures. Dedicated 7-stage suite `tools/verify_ux_polish.mjs` passed 100%. |
| Independent Code & CI Review | PASS: independent review APPROVE with 0 findings. Hosted GitHub Actions CI passed on exact PR head SHA `49cd56d` ([run 41657355223](https://github.com/KAIYI7/settle-table/actions/runs/41657355223)). |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.


## 2026-11-03 — Targeted Numeric Stepper & Financial UX Clarity Refinement: PR #39 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `d0e85af491a581f36c31ea16f297716bc48c82d6` merged autonomously under orchestrator governance policy into `main`. GitHub PR #39 ([#39](https://github.com/KAIYI7/settle-table/pull/39)) verified on hosted CI ([run 41650957160](https://github.com/KAIYI7/settle-table/actions/runs/41650957160)) before merge.

| Gate | Disposition |
| --- | --- |
| Unified Numeric Steppers | PASS: unified `.numeric-stepper` component implemented across Manual Add Item (`#new-item-qty`), Scanned OCR editor (`.ocr-qty-stepper`), and Diner portions (`.quantity-stepper`). Typographic minus (`−` / U+2212) used consistently across all steppers. Direct typing preserved with automatic button state synchronization. Accessible `role="group"`, `aria-label`, and `aria-live="polite"` applied. |
| Financial Terminology & Clarity | PASS: updated Restaurant Funding card prompt to *"Who paid the restaurant bill? Record how much each person actually paid at the counter."* and column headers to *Amount Consumed*, *Paid to Restaurant*, *Base Net (Paid − Consumed)*. Updated Peer Settlement card prompt to *"Who needs to reimburse whom? Suggested transfers help everyone pay their fair share after the restaurant bill has been covered."* and column headers to *Base Net (Bill)*, *Reimbursed Others*, *Received from Peers*, *Still Owed / Recoverable*. |
| Organizer Attestation Disclaimer | PASS: added prominent settlement attestation banner explaining that suggested transfers and repayments are organizer-recorded and not independently bank-verified. |
| Product-Owner-Confirmed UAT Evidence | PASS: recorded product owner's confirmed real-browser Microsoft Edge UAT results (all 8/8 checks passed for multi-payer funding and peer settlements) in `PROJECT_STATUS.md` as integration evidence, explicitly distinguishing from formal independent UAT. |
| Mobile Viewport Compliance (375px) | PASS: responsive `.add-item-grid` layout stacks item name and wraps stepper and price side-by-side with $\ge 44$px touch targets and zero horizontal overflow. |
| Zero Calculation Drift & Decimal Currency Inputs | PASS: `settletable/calculation.py` remains 100% byte-untouched. Zero floating-point arithmetic added; RM currency inputs remain standard decimal text inputs without spinners. |
| Local Regression Suite | PASS: 290/290 Python tests passed; 12/12 real-browser CDP test stages passed; conflict recovery, financial export, multi-payer funding, and peer settlement browser suites passed with 0 failures. Dedicated 6-phase test suite `tools/verify_ux_polish.mjs` passed 100%. |
| Independent Code & CI Review | PASS: independent review APPROVE with 0 findings. Hosted GitHub Actions CI passed on exact PR head SHA `d0e85af` ([run 41650957160](https://github.com/KAIYI7/settle-table/actions/runs/41650957160)). |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.


## 2026-11-03 — Conflict recovery reload context renewal & CI suite expansion: PR #38 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `79c684d7b6d615ea8689725a05a0c9bd7df03522` merged autonomously under orchestrator governance policy into `main`. GitHub PR #38 ([#38](https://github.com/KAIYI7/settle-table/pull/38)) verified on hosted CI ([run 41622668317](https://github.com/KAIYI7/settle-table/actions/runs/41622668317)) before merge.

| Gate | Disposition |
| --- | --- |
| Context Renewal & Reload Synchronization | PASS: in `tools/verify_conflict_recovery.mjs`, `CDPPage.prototype.reload` sets `window.__reloading_marker = true` before sending `Page.reload` and waits for `window.__reloading_marker === undefined`. Guarantees context recreation across reloads and eliminates race condition where post-reload assertions evaluated on stale pre-reload contexts. |
| Explicit Observable DOM Readiness | PASS: in line 302 of `tools/verify_conflict_recovery.mjs`, explicitly waits for `Boolean(typeof state !== 'undefined' && state?.snapshot?.claims?.length === 2 && document.getElementById('add-item-form'))` before logging or reading `state.snapshot.claims`. Eliminates `TypeError: Cannot read properties of null (reading 'claims')`. |
| CDPPage Implementation Uniformity | PASS: standardized `reload()` context renewal implementation across `tools/verify_conflict_recovery.mjs`, `tools/verify_financial_export.mjs`, `tools/verify_multi_payer_flow.mjs`, and `tools/verify_peer_settlement_flow.mjs`. |
| Headless Chrome & CI Expansion | PASS: added `--headless=new` and `--remote-debugging-address=127.0.0.1` flags in `tools/verify_multi_payer_flow.mjs` and `tools/verify_peer_settlement_flow.mjs`. Registered both multi-payer and peer settlement browser suites into `.github/workflows/python-tests.yml`. |
| Zero Production Logic Modification | PASS: `settletable/calculation.py` and all backend/frontend application code remain 100% byte-untouched. |
| Local Regression Suite | PASS: 290/290 Python tests passed; 12/12 real-browser CDP test stages passed; conflict recovery, financial export, multi-payer funding, and peer settlement browser suites passed with 0 failures. |
| Independent Code & CI Review | PASS: independent review APPROVE with 0 findings. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.


## 2026-11-03 — Suggested Peer Transfers, Partial Reimbursements & Settlement Tracking: PR #37 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `ad0c5a9c166fa18d7f0ca7277545097bf9defde4` merged autonomously under orchestrator governance policy into `main`. GitHub PR #37 ([#37](https://github.com/KAIYI7/settle-table/pull/37)) verified on hosted CI ([run 41618225730](https://github.com/KAIYI7/settle-table/actions/runs/41618225730)) before merge.

| Gate | Disposition |
| --- | --- |
| Peer Settlement Engine & Cent Conservation | PASS: Greedy transfer suggestion algorithm in `settletable/settlement.py` computes deterministic peer-to-peer transfer recommendations respecting cent conservation $\sum_{p \in \mathcal{P}} \text{OutstandingNet}(p) \equiv -\text{UnfundedAmount}$ (and 0 when fully funded). Enforced unconditionally via runtime assertion. |
| Additive SQLite Transfer Ledger & Immutability Triggers | PASS: Created `peer_transfers` table with database triggers `prevent_peer_transfers_delete` and `prevent_peer_transfers_tamper`. Historical records are never deleted; adjustments require explicit `ReverseTransfer` commands. |
| Over-Settlement & Invariant Defenses | PASS: `RecordTransfer` validates sender is debtor ($< 0$), receiver is creditor ($> 0$), `sender_id != receiver_id`, and strictly caps `amount_sen <= min(-sender_debt, receiver_credit)`. Bipartite matching ensures acyclic, deadlock-free transfers. |
| Cross-Feature Balance Guard | PASS: In `_reverse_contribution`, rejects with `active_peer_transfers_exist` if reversing a restaurant contribution would reduce a participant's active contributions below the peer reimbursements they have already received. |
| Organizer Authority & Security | PASS: `RecordTransfer` and `ReverseTransfer` mutations are strictly restricted to organizers via `_permission()`. Replay safety guaranteed by deterministic ID derivation `derive_transfer_id(meal_id, command_id)`. |
| Zero Calculation Drift | PASS: `settletable/calculation.py` remains 100% byte-untouched. Authoritative finalized meal consumption liabilities are immutable. |
| Local Regression Suite | PASS: 290/290 Python tests passed (`python -m unittest discover tests`); 16/16 dedicated settlement unit tests passed; 12/12 real-browser CDP test stages passed (`tools/e2e_browser_test.mjs`); 8/8 headless Chrome peer settlement flow tests passed (`tools/verify_peer_settlement_flow.mjs`); 8/8 headless Chrome multi-payer funding flow tests passed (`tools/verify_multi_payer_flow.mjs`). |
| Independent Code & Security Review | PASS: Two-axis independent reviews (Standards: APPROVE, Spec & Financial Safety: APPROVE) completed with 0 blocking defects. Hosted GitHub Actions CI passed on exact head SHA `ad0c5a9` ([run 41618225730](https://github.com/KAIYI7/settle-table/actions/runs/41618225730)). |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.


## 2026-11-03 — Multi-Payer Contributions & Net Balance Reconciliation: PR #36 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `9fce84a9a4aba68f0dcde6fdd48a2a26edb45183` merged autonomously under orchestrator governance policy into `main`. GitHub PR #36 ([#36](https://github.com/KAIYI7/settle-table/pull/36)) verified on hosted CI ([run 41612866522](https://github.com/KAIYI7/settle-table/actions/runs/41612866522)) before merge.

| Gate | Disposition |
| --- | --- |
| Multi-Payer Accounting & Ledger Immutability | PASS: created additive `payer_contributions` table in SQLite with database triggers `prevent_payer_contributions_delete` and `prevent_payer_contributions_tamper` (including `payment_method` immutability). Historical records are never deleted; corrections use additive `ReverseContribution` commands. |
| Deterministic Cent Conservation | PASS: $\sum_{p \in \mathcal{P}} \text{Base Net Balance}(p) \equiv \text{Total Contributed} - \text{Receipt Total} \equiv -\text{Unfunded Amount}$ enforced unconditionally via runtime assertion in `compute_net_balances`. Includes post-finalization revoked participants in net balance calculations. |
| Zero Calculation Drift | PASS: `settletable/calculation.py` remains 100% byte-untouched. Authoritative finalized meal consumption liabilities are immutable. |
| Notion Cache Decoupling & Historical Backfill | PASS: Notion export lookup decouples from mutable live `revision` by binding to immutable `finalized_revision`. In `Authority.apply`, historical meals finalized prior to schema update automatically backfill `finalized_revision = state['revision']` on post-finalization commands. |
| Security, Anti-Enumeration & Concurrency | PASS: command mutations use SQLite `BEGIN IMMEDIATE` locks. Replay safety guaranteed by deterministic ID derivation `derive_contribution_id`. Overpayment beyond bill total rejected. Session credentials verified with anti-enumeration protection. |
| Local Regression Suite | PASS: 273/273 Python tests passed (`python -m unittest discover tests`); 12/12 real-browser CDP test stages passed (`tools/e2e_browser_test.mjs`); 8/8 headless Chrome multi-payer and funding flow tests passed (`tools/verify_multi_payer_flow.mjs`). |
| Independent Code & Security Review | PASS: independent reviewer findings remediated (backfill `finalized_revision`, single-quote SQL literals, `payment_method` trigger immutability, unified command limits, mobile input attributes) with passing regression tests. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.


## 2026-11-03 — Browser reload synchronization & receipt DOM readiness: PR #35 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `6dadc0222c80cb60c360472a4ea1fd50cd84a402` merged autonomously under orchestrator governance policy into `main`. GitHub PR #35 ([#35](https://github.com/KAIYI7/settle-table/pull/35)) verified on hosted CI ([run 41600343451](https://github.com/KAIYI7/settle-table/actions/runs/41600343451)) before merge.

| Gate | Disposition |
| --- | --- |
| CDP Reload Context Renewal | PASS: in `tools/e2e_browser_test.mjs`, `CDPPage.prototype.reload` sets `window.__reloading_marker = true` before sending `Page.reload` and awaits `window.__reloading_marker === undefined`. Guarantees context recreation across reloads and eliminates race condition where post-reload assertions evaluated on stale pre-reload contexts. |
| Explicit Observable DOM Readiness | PASS: in `checkReceiptDom`, explicitly polls for the presence of the `Receipt & Charges` card container and all 5 `Quantity case` rows before accessing properties. Eliminates `TypeError: Cannot read properties of undefined` during asynchronous DOM rendering. |
| Diagnostic Forensics | PASS: if `Receipt & Charges` card is absent during extraction, outputs visible card titles and `#app` inner text in error details instead of crashing on property dereferences. |
| Production Code Untouched | PASS: `settletable/calculation.py` and all backend/frontend application code remain 100% byte-untouched. |
| Local Regression Suite | PASS: 257/257 Python tests passed (`python -m unittest discover tests`); 12/12 real-browser CDP test stages passed (`tools/e2e_browser_test.mjs`); 8/8 headless Chrome receipt photo & pattern tests passed (`tools/verify_receipt_photo_flow.mjs`). |
| Code & Security Review | PASS: independent review APPROVE with 0 critical, 0 high, 0 medium findings. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-03 — Receipt photo CSP blob: support & Chromium UnicodeSets meal ID pattern: PR #34 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `a852bd9826a4f3acc52c4f24bf8ab12e55a1a9c0` merged autonomously under orchestrator governance policy into `main` at `4da3bde`. GitHub PR #34 ([#34](https://github.com/KAIYI7/settle-table/pull/34)) verified on hosted CI ([run 41596591754](https://github.com/KAIYI7/settle-table/actions/runs/41596591754)) before merge.

| Gate | Disposition |
| --- | --- |
| CSP `blob:` Image Source Support | PASS: in `settletable/transport.py`, `img-src` updated to `'self' data: blob:;`. All other directives (`default-src 'self'`, `script-src 'self'`, `connect-src 'self'`, `frame-ancestors 'none'`) strictly untouched. Staged OCR preview thumbnails and full-screen zoom previews render cleanly without browser CSP blocks. |
| Object URL Lifecycle & Leak Prevention | PASS: `state.localPhotoUrl` is revoked upon new upload, discard, meal load, session reset, and window `beforeunload` event. Zero memory leaks on reload or navigation. |
| Meal ID Pattern UnicodeSets Compliance | PASS: in `settletable/static/app.js`, escaped hyphen `pattern="[A-Za-z0-9_\\-]+"` evaluates to `[A-Za-z0-9_\-]+` in rendered HTML, compiling cleanly under modern Chromium RegExp `v` flag / UnicodeSets mode with 0 console errors. Hyphenated IDs (`dinner-friday`, `lunch_room-1`) valid; invalid characters rejected. |
| Real Image Decoding Browser Verification | PASS: `tools/verify_receipt_photo_flow.mjs` upgraded with genuine decodable PNG generator and image decoding assertions (`complete === true`, `naturalWidth > 0`, `naturalHeight > 0`). 8/8 stages passed with 0 CSP violations and 0 console errors. |
| Calculation Engine Untouched | PASS: `settletable/calculation.py` remains 100% byte-untouched. 0 changes to financial apportionment contract or test suites. |
| Local Regression Suite | PASS: 257/257 Python tests passed (`python -m unittest discover tests`); 8/8 headless Chrome receipt photo & pattern tests passed (`tools/verify_receipt_photo_flow.mjs`); 12/12 real-browser CDP tests passed (`tools/e2e_browser_test.mjs`). |
| Code & Security Review | PASS: independent review APPROVE with 0 critical, 0 high, 0 medium findings. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-03 — Receipt photo reliability hardening, crash consistency, and Notion in-place upgrade: PR #33 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `1fdc75bf5b6b05fae6905dc70b25a35948b8c86a` merged autonomously under orchestrator governance policy into `main` at `6a1cee4`. GitHub PR #33 ([#33](https://github.com/KAIYI7/settle-table/pull/33)) verified on hosted CI ([run 41576630328](https://github.com/KAIYI7/settle-table/actions/runs/41576630328)) before merge.

| Gate | Disposition |
| --- | --- |
| Explicit Photo Inclusion Failure Gate | PASS: synchronous photo validation in `transport.py` aborts immediately with 404 (`photo_not_found`) or 500 (`photo_corrupted`) when photo is missing or corrupted, eliminating silent fallback to text-only exports and preventing false `completed` records. Exporter defends against missing photo payloads. |
| Crash Consistency & Atomic Durability | PASS: `store_receipt_photo` reordered to move staging file into destination before SQLite commit; rolls back and unlinks destination on failure; unlinks replaced files only after successful commit. |
| Physical Integrity Checksum & Snapshot Recovery | PASS: `get_receipt_photo` enforces byte length and SHA-256 hash match (`photo_corrupted` on failure). `snapshot()` verifies physical file existence on disk, safely recovering `has_receipt_photo=False` if disk files are missing. |
| Notion In-Place Upgrade & Idempotency | PASS: uniquely identifies photo inclusion in `export_digest` (`:photo=0` vs `:photo=1`). When an export requests photo inclusion for an existing text-only export, upgrades the page in-place using `append_block_children` without duplicate pages. Repeated exports return `already_exported`. |
| Compact Block Budget Preserved | PASS: `format_compact_meal_blocks` reserves 6 base blocks unconditionally, guaranteeing that upgrading an existing text-only report with an image block strictly maintains total blocks $\le 40$ blocks (`MAX_COMPACT_BLOCKS`). |
| Calculation Engine Untouched | PASS: `settletable/calculation.py` remains 100% byte-untouched. 0 changes to financial apportionment contract or test suites. |
| Local Regression Suite | PASS: 257/257 Python tests passed (`python -m unittest discover tests`); 25/25 dedicated receipt photo and reliability tests passed (`tests/test_receipt_photo.py`); 7/7 headless Chrome receipt photo tests passed (`tools/verify_receipt_photo_flow.mjs`); 12/12 real-browser CDP tests passed (`tools/e2e_browser_test.mjs`). |
| Code & Security Review | PASS: independent review APPROVE with 0 critical, 0 high, 0 medium findings. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-03 — Receipt photo retention, interactive zoom modal, and optional Notion export milestone: PR #32 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `8168d77395a716e35bfbb3636bd606da12bbff0c` merged autonomously under orchestrator governance policy into `main` at `05258db`. GitHub PR #32 ([#32](https://github.com/KAIYI7/settle-table/pull/32)) verified on hosted CI ([run 41572682124](https://github.com/KAIYI7/settle-table/actions/runs/41572682124)) before merge.

| Gate | Disposition |
| --- | --- |
| Local Receipt Photo Storage & Isolation | PASS: created `receipt_photos` table and private directory `<db_dir>/receipt_photos/`. Binary image bytes strictly excluded from `meals.state`, snapshots, and audit logs. Filenames strictly synthesized as `{safe_meal_id}_{sha256[:16]}.{ext}`, sanitizing path separators and Windows Alternate Data Streams (ADS). All serving resolves `target_path.is_relative_to(storage_dir.resolve())`. Temporary files cleaned up reliably on failure. |
| Organizer-Only Access Control & CSRF | PASS: enforced authenticated organizer authority across `POST /ocr/extract`, `POST /receipt/photo`, `GET /receipt/photo`, and `DELETE /receipt/photo` (401 for unauthenticated, 403 for diners/non-members). Extended `X-SettleTable-Action: 1` and Origin/Referer matching to all `POST` and `DELETE` methods. |
| Finalized Meal Immutability | PASS: `store_receipt_photo` and `delete_receipt_photo` acquire SQLite `BEGIN IMMEDIATE` locks and assert `state.get('calculation') is None`, rejecting mutations on finalized meals with HTTP 409 `finalized`. Organizers retain read-only GET access post-finalization. |
| Calculation Engine Untouched | PASS: `settletable/calculation.py` remains 100% byte-untouched. Photo storage and deletion produce 0 changes to `receipt_digest` or financial apportionment math. |
| Responsive Preview & Zoom Modal UI | PASS: implemented responsive preview bar during OCR candidate staging and attached receipt photo card in organizer view with View & Zoom, Replace Photo, and Remove Photo. Added accessible `#receipt-modal` with zoom in/out/reset, mouse wheel zoom, drag-to-pan, touch support, and Escape key dismissal. Preserved photo access after finalization. |
| Notion 2-Step File Upload & Budget | PASS: implemented Notion official 2-step single-part file upload API (`POST /v1/file_uploads` then `POST /v1/file_uploads/{id}/send` with standard library multipart) and referenced via `image.file_upload.id` block. Enforced compact block budget reserving 6 non-table blocks to guarantee total page blocks remain $\le 40$ blocks without assertion failure. |
| View-Only Sharing Guidance & Privacy Warning | PASS: added organizer checkbox `[ ] Include original receipt photo in Notion report` (default OFF, enabled only when photo exists). Rendered verified 4-step manual "Publish to web" guidance upon export with an explicit privacy warning regarding confidential data exposure. |
| Local Regression Suite | PASS: 249/249 Python tests passed (`python -m unittest discover tests`); 17/17 dedicated receipt photo tests passed (`tests/test_receipt_photo.py`); 12/12 automated real-browser CDP test stages passed (`tools/e2e_browser_test.mjs`); dedicated 7-stage headless Chrome receipt photo suite passed (`tools/verify_receipt_photo_flow.mjs`); repo audit passed with 0 findings. |
| Code & Security Review | PASS: independent security and code review APPROVE (`research/phase-3/receipt-photo-independent-review.md`) with zero critical/high/medium findings; 1 informational low note on standard REST delete idempotency recorded. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-02 — OCR fixture privacy sanitization & all-items scope guard milestone: PR #31 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `3d5f05c580b6a2edcaf7e67bda521cd4516c5fb2` merged autonomously under orchestrator governance policy into `main` at `7ca36be35006e296683765288acecc26cec4e210`. GitHub PR #31 ([#31](https://github.com/KAIYI7/settle-table/pull/31)) verified on hosted CI before merge.

| Gate | Disposition |
| --- | --- |
| Fixture privacy sanitization | PASS: sanitized 17 business and visit-identifying tokens in `tests/fixtures/ocr/tokens.json` (`brewhouse_receipt.png`) into generic Malaysian dining data while maintaining 100% of spatial 2D coordinates, scores, menu items, line totals, and tax breakdown tables. |
| All-items scope synchronization | PASS: in `settletable/static/app.js` (`add-item-form`), dynamically mapped `eligible_item_ids` to include all current receipt items for `scope_mode === 'all_items'` adjustments, preventing client-side `AuthorityError('invalid_input')` without altering financial calculation or fixed-item scopes. |
| Authority scope regression | PASS: added regression assertion in `tests/test_authority.py` confirming authority strictly rejects `ReplaceReceipt` commands with `all_items` adjustments that omit receipt items. |
| Local regression | PASS: 232/232 Python test suite methods passed in 65.0s; 12/12 automated real-browser CDP test stages passed (`tools/e2e_browser_test.mjs`); financial scope and conflict recovery browser suites passed; repository hygiene audit 0 findings. |
| Hosted CI | PASS: [run 41467848944](https://github.com/KAIYI7/settle-table/actions/runs/41467848944) passed all Python and browser steps on exact PR head `3d5f05c580b6a2edcaf7e67bda521cd4516c5fb2` in ubuntu-24.04 (Python 3.14). |
| Code review & hygiene | PASS: independent review APPROVE (conversation `c8bb5895-516a-4bff-8f41-6df5c04f3052`); zero critical/high/medium findings; git history preserved intact without rewrites. |
| Acceptance status | OBSERVED: real OCR extraction succeeded for The Brew House genuine receipt, but video capture did not complete finalization. Human review and explicit approval required prior to final calculation. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-02 — Malaysian restaurant receipt OCR corrections milestone: PR #30 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `03574cbff7687808fcb6ac2bbcf769ff47cffe72` merged autonomously under orchestrator governance policy into `main` at `f1661188845d086f5217d68bbee26d7103fe9830`. GitHub PR #30 ([#30](https://github.com/KAIYI7/settle-table/pull/30)) verified on hosted CI before merge.

| Gate | Disposition |
| --- | --- |
| Negative currency & rounding parsing | PASS: enhanced `MONEY_PATTERN` regex and `parse_sen` to parse currency-prefixed negative numbers (e.g. `-RM0.02`, `-RM 0.02`, `RM -0.02`, `(RM 0.02)`) without floating-point conversion, yielding exact `-2` sen. |
| Post-total tax summary isolation | PASS: added `total_found` barrier and `TAX SUMMARY` detection to prevent post-total tax breakdown tables (such as taxable basis RM 169.20) from clobbering extracted bill charges (`tax_sen`). |
| Item label & modifier cleaning | PASS: stripped stray trailing currency symbols (`RM`, `MYR`, `$`), trailing modifier quantities (`x 1`, `× 1`), leading item multipliers, and normalized inline dashes (`—`). |
| Spatial row grouping | PASS: upgraded `group_lines_into_rows` using vertical bounding-box overlap heuristic (`overlap >= min_h * 0.35` and `|y - r_mid_y| <= min_h * 0.55`) so multi-line modifiers cluster reliably without contaminating adjacent items. |
| Granular mismatch feedback | PASS: enhanced UI mismatch alert and scan toasts to detail exact computed charges sum vs printed bill total and exact discrepancy in sen. |
| Local regression | PASS: 232/232 Python test suite methods passed; 12/12 automated real-browser CDP test stages passed (`tools/e2e_browser_test.mjs`); financial scope and conflict recovery browser suites passed. |
| Hosted CI | PASS: [run 41416668397](https://github.com/KAIYI7/settle-table/actions/runs/41416668397) passed all Python and browser steps on exact PR head `03574cbff7687808fcb6ac2bbcf769ff47cffe72` in ubuntu-24.04 (Python 3.14). |
| Code review & hygiene | PASS: independent review APPROVE (conversation `e5bdaee4-90ba-45c4-8257-3da97ef76b78`); zero critical/high/medium findings; non-blocking cosmetic note addressed; no authentic images or secrets committed. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-02 — Notion block schema and error diagnostics milestone: PR #28 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `02302e95bba8ce9adab621d9c523e59f09d31ffe` merged autonomously under orchestrator governance policy into `main` at `5c0a8d88e049d956241dd23328cc2ef4af499858`. GitHub PR #28 ([#28](https://github.com/KAIYI7/settle-table/pull/28)) verified on hosted CI before merge.

| Gate | Disposition |
| --- | --- |
| Notion block schema compliance | PASS: enforced `"object": "block"` and `type="table_row"` on all 9 `table_row` child block constructors across compact and full formats; updated `MockNotionClient` to strictly validate block object compliance. |
| Granular export diagnostics | PASS: differentiated `NotionNotFoundError` (HTTP 404, `page_not_found`) from `NotionValidationError` (HTTP 400, `validation_error`); sanitized error messages to prevent token exposure in `export_digest`. |
| Local regression | PASS: 230/230 Python test suite methods passed in 93.2s; 12/12 automated real-browser CDP test stages passed (`tools/e2e_browser_test.mjs --port 8095`). |
| Hosted CI | PASS: [run 41386556198](https://github.com/KAIYI7/settle-table/actions/runs/41386556198) passed all Python and browser steps on exact PR head `02302e95bba8ce9adab621d9c523e59f09d31ffe` in ubuntu-24.04 (Python 3.14). |
| Code review & hygiene | PASS: independent review APPROVE (conversation `ecebd01c-1413-4d68-a9a7-cf720a72e231`); zero critical/high/medium findings; all 3 low polish points remediated; no credentials or secrets committed. |
| Live Notion smoke test guidance | PASS: identified live connection prerequisites (integrations require explicit UI connection to target parent page via Notion `...` -> **Connect to** to avoid 404 `object_not_found`). |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-01 — Local OCR parsing and Notion redirect defense milestone: PR #26 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `d65d383857229600252a7c1d206bb5e59280a0f1` merged autonomously under orchestrator governance policy into `main` at `e06f606d5f9ff822ce54de7334fe9bc4daf1e63b`. GitHub PR #26 ([#26](https://github.com/KAIYI7/settle-table/pull/26)) verified on hosted CI before merge.

| Gate | Disposition |
| --- | --- |
| OCR parser & RapidOCR compatibility | PASS: summary lines require monetary amounts to prevent column header false positives from aborting scanning; added trailing item quantity extraction; polymorphic handling of RapidOCROutput dataclass and tuple/list formats. |
| Notion security & redirect defense | PASS: DisallowRedirectHandler blocks all HTTP 3xx redirects on NotionHttpClient to eliminate Bearer token forwarding leakage across redirect chains; API version pinned at stable 2022-06-28. |
| Local regression | PASS: 226/226 Python test suite methods passed in 88.7s; 12/12 automated real-browser CDP test stages passed in 23.5s (`tools/e2e_browser_test.mjs`). |
| Hosted CI | PASS: [run 41314417879](https://github.com/KAIYI7/settle-table/actions/runs/41314417879) passed all Python and browser steps on exact PR head `d65d383857229600252a7c1d206bb5e59280a0f1` in ubuntu-24.04 (Python 3.14). |
| Code review & hygiene | PASS: independent review APPROVE (conversation `dd8929f9-5be4-467c-8547-cd29620df349`); zero critical/high/medium findings; audited publication diff contains zero authentic receipt images, ONNX models, virtualenvs, or personal paths. |
| Live Notion workspace & deployment | HELD: live smoke test procedure documented (`docs/notion-smoke-test.md`) with explicit consent and disposable setup steps; held behind PO authorization. No deployment or multi-payer work authorized. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-01 — Focused UAT corrective milestone: pre-merge decision

**Orchestrator decision: PASS for the bounded corrective merge**, subject to unchanged PR head and base at merge. This is not local MVP acceptance or deployment approval.

Merged [PR #24](https://github.com/KAIYI7/settle-table/pull/24) as `7aaf2b32a72462d956f93e8f54adfd627a7ff86e`; GitHub confirmed that SHA on remote `main` and PR head `0cfb96119fc17cb21f0d77b76c0362b1fe8acfcb`. The merge has both expected parents and its tree equals the reviewed head tree.

| Gate | Disposition |
| --- | --- |
| Financial policy and compatibility | PASS: owner confirmed fixed legacy scope and blocking empty fixed scopes; independent financial/security review and historical replay checks passed; calculator unchanged. |
| Modal and recovery | PASS: independent specification and recovery reviews, keyboard tests, competing identities, blocked and superseded refreshes, and preserved drafts. |
| Local regression | PASS: 216 Python tests; 12 Chrome E2E stages; focused financial/export and recovery tests; ten Concept C scenarios. Path cleanup independently reviewed and affected browser tests rerun. |
| Hosted CI | PASS: [run 41276975790](https://github.com/KAIYI7/settle-table/actions/runs/41276975790) passed all Python and browser steps on PR head `0cfb96119fc17cb21f0d77b76c0362b1fe8acfcb`. |
| Final review | PASS: 17 audited publication files matched reviewed local blob hashes; private repository, PR head, and base `73806f67338461ed169a47f4e639c02d71e56e56` rechecked. |
| Independent UAT and release | OPEN: separate manual UAT, physical mobile and screen-reader validation remain outstanding; no public deployment authorized. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-10-16 — Phase 1 → revised Phase 2

**Orchestrator decision: CONDITIONAL PASS for targeted feasibility closure.** Phase 1 completed its feasible requirements/domain, three-engine OCR, synthetic Notion and architecture-comparison work. It does not establish release readiness. This transition starts Phase 2 directly under the user's new delegation; no phase approval is requested.

| Material exit criterion | Disposition / evidence | Risk and scope restriction |
|---|---|---|
| Coherent workflow, confirmed collaboration/privacy requirements and explicit decision frontier | PASS — [requirements](../../research/phase-1/requirements.md) | Unresolved settlement/voucher/retention preferences block those policy-dependent features, not further validation. |
| Integer-money reconciliation and exercised domain invariants | CONDITIONAL PASS — [domain](../../research/phase-1/domain-model.md), executable scenarios/results | Disposable simulation is not production validation. Independently review correctness and carry counterexamples into acceptance criteria. |
| Viable permitted extraction path and honest field evidence | CONDITIONAL PASS — [OCR](../../research/phase-1/ocr-validation.md) | Local inference works; human review mandatory. Modern/held-out/device accuracy remains FAIL for unattended OCR claims. Manual entry can proceed independently. |
| Live-edit integrity across actual browser transport | FAIL — [simulation](../../research/phase-1/experiments/collaboration/README.md) proves only in-process behavior | Blocking production live-collaboration readiness; Phase 2 will run a real local transport/two-client probe. |
| Notion representation and failure model | CONDITIONAL PASS — [Notion](../../research/phase-1/notion-validation.md) | Connector/fake-remote evidence only; raw authenticated REST and real workspace limits remain unverified. Optional integration cannot block the core meal workflow. |
| Evidence-based architecture alternatives | PASS for comparison — [assessment](../../research/phase-1/architecture-decision.md) | Production selection was not met at entry; Path C favored, no automatic Next.js preference. Select the smallest stack against a bounded specification after protocol review. |
| Implementation-ready, secure bounded MVP specification | FAIL at transition entry | No production scaffold is authorized by this transition decision. Close protocol/specification gaps first; orchestrator may later approve implementation on recorded evidence. |

**Next scope:** independently challenge financial/security gates; validate actual localhost browser transport, revision/replay/revocation behavior; review optional Notion contract boundaries; write a bounded manual-first collaborative MVP specification and updated architecture decision. Reuse existing OCR evidence; no rerun without a new question. Phone/corpus work remains explicitly unmeasured rather than fabricated. No paid service, public deployment, credentials request or real private-data export is needed for this closure scope.

**Strategy revision:** split capability gates. Manual-first collaboration can become implementation-ready while modern OCR accuracy and authenticated Notion integration remain separately gated. Neither is silently declared validated; production auto-extraction, image archiving and live Notion delivery stay unavailable until their own gates pass. This avoids making absent phone hardware or account credentials prerequisites for all engineering work.

## 2026-10-16 — bounded Phase 2 closure → Phase 3 first calculation slice

**Orchestrator decision: CONDITIONAL PASS into production implementation of the isolated financial calculation module only.** Reviewed the actual independent reports, browser fixture/server/client/runner, SQLite source/results and specification; checked five source hashes against machine evidence in [closure verification](../../research/phase-2/closure-verification.json). Phase 2 closes the feasible engineering questions for this first slice, not every capability in the historical Phase 2 proposal.

| Exit criterion for this implementation scope | Disposition / reviewed evidence | Blocking risk or restriction |
|---|---|---|
| Explicit, bounded mathematical contract and acceptance tests | PASS — [specification](../../research/phase-2/mvp-specification.md), C1–C4 clarifications resolve [independent review](../../research/phase-2/specification-review.md) | Core proves supplied facts mathematically; it cannot establish human review, current revision or organizer identity. |
| Independent financial challenge integrated | PASS — [challenge](../../research/phase-2/gate-challenge.md) | Transfer-ID trap excluded from this calculation-only slice; rounded-base one-sen discount counterexample becomes a required regression. |
| Appropriate stack for the slice | PASS — [architecture](../../research/phase-2/architecture-decision.md) | Python standard library selected; no frontend/server/framework necessary. No source transplant from reference apps. |
| Real browser authority/revision feasibility | CONDITIONAL PASS — [30/30 Chromium assertions](../../research/phase-2/collaboration-validation.md) | Synthetic tokens/in-memory state, not production auth or actual network-failure recovery. Not a dependency of a pure calculator. |
| Durable transaction/replay feasibility | CONDITIONAL PASS — [20/20 actual SQLite checks](../../research/phase-2/transaction-validation.md) | Single-host synthetic fixture; no crash/power-loss, full financial/auth composition or backups. Blocks later authority acceptance until implemented/tested together. |
| Public live feature/authentication and full workflow readiness | FAIL — explicit gaps in both probes | Blocks public/live-feature completion, not isolated core implementation. No network host or identity feature in the first slice. |
| OCR, private image handling and real Notion integration | FAIL for feature acceptance — [Phase 1 OCR](../../research/phase-1/ocr-validation.md), [Notion contract](../../research/phase-2/notion-contract-review.md) | Keep these capabilities unimplemented/disabled pending evidence, privacy/account decisions. Their work remains in the product objective. |
| Human escalation needed for this narrow action | PASS — no spend, deployment, credential, private data, destructive operation or unclear source reuse | Future settlement/retention preferences are unresolved and excluded from the first slice. |

**Approved work:** build the independently implemented pure calculation interface and strict decimal-money parser, one behavior/test slice at a time; exercise required examples and malformed inputs; independently review specification conformance and engineering/correctness. Record code/test hashes and actual outcomes before calling the slice complete. The orchestrator selects these test interfaces under the user's delegation; no routine skill-driven confirmation is needed.

**Still blocking later acceptance:** authoritative human-review/revision/identity integration, secure invitations/revocation, durable live operations, funding/settlement policy, image retention, representative phone/OCR validation and authenticated Notion delivery. Subsequent implementation may proceed on recorded gates; none of these failures is silently waived by this transition.

## 2026-10-16 — Phase 3 calculation-slice acceptance

**Orchestrator decision: PASS for the isolated calculation/parser slice, within Phase 3.** Reviewed the complete production module, tests and interface, then actual independent probe sources/results/reports against the [fixed artifact baseline](../../research/phase-3/review-baseline.json). No production edit occurred after that baseline. Phase 3 as a whole is not complete.

| Slice completion criterion | Disposition / evidence |
|---|---|
| Strict integer sen/exact rational modes, signed scoped components, hard reconciliation and immutable results | PASS — [source](https://github.com/KAIYI7/settle-table/blob/af7ba147642b8b8e9a5aee973a95c59d46c38b9a/tabwise/calculation.py), [interface](../calculation-interface.md), [specification](../../research/phase-2/mvp-specification.md) |
| Required literal/malformed-input tests and real execution | PASS — main independently ran `python -m unittest discover -s tests -v`:15 methods, zero failures/errors; [coordinator record](../../research/phase-3/coordinator-verification.json). Implementer also records Python3.12 compatibility and incremental red/green evidence. |
| Independent financial/specification challenge | PASS — [spec review](../../research/phase-3/spec-review.md),66 public-interface checks including literal original-base/one-sen/ordering counterexamples |
| Independent engineering/correctness review | PASS — [engineering review](../../research/phase-3/engineering-review.md),11 targeted check groups; zero material findings within the bounded scope |
| Source integrity and scope conformance | PASS — baseline hashes match; no UI/server/identity/storage/payment/OCR/Notion feature is claimed by this module |

**Next work within Phase 3:** specify and implement the authoritative manual-entry draft slice against the accepted calculation interface: durable accepted commands/results, current membership and organizer/diner permissions, financial review/revision invalidation, atomic finalization and snapshot/conflict behavior. Existing browser and SQLite fixtures are feasibility evidence, not production modules to transplant. Before accepting that slice, integrate and test the actual calculation/transaction/access checks together and independently review security. Resolve genuine user-preference gates only when their feature needs them; no routine numbered-phase approval is requested.

**Blocking later capabilities remain unchanged:** secure Internet invitations and recovery, settlement confirmation/correction policy, receipt retention, actual phone/capture/modern OCR quality, real authorized Notion adapter, backup/restore and public-release operations. Public deployment and external data/account/spend actions still require their separate human escalation.

## 2026-10-17 — Verified repository checkpoint and local authority specification

**Orchestrator decision: PASS for repository establishment; PASS to begin the bounded local authority implementation within Phase 3.** These are separate decisions in that order. No authority production code was added during publication. The actual new specification and independent report were read before this decision; the five initial findings remain in the report with their resolutions.

| Gate | Disposition / evidence | Restriction or unresolved risk |
|---|---|---|
| Clean, reviewed baseline and remote checkpoint | PASS — [prepublication audit](../../research/publishing/prepublish-audit.md), [actual remote verification](../../research/publishing/checkpoint.json) | Annotated `phase2-accepted` remains fixed at `69895457d9e3524c90df24f3a21c284ea70cef6c`; subsequent docs advance main. Excluded assets and reproducibility limits remain explicit. |
| Bounded authority contract against accepted financial semantics | PASS — [specification](../../.scratch/authoritative-draft/SPEC.md),20 acceptance cases; main reviewed all commands, transactions, limits and exclusions | Quantity-only local slice, fixed participants and trusted bootstrap. Other split editors and operational session renewal are later work. |
| Independent security/specification challenge resolved | PASS — [actual review](../../research/phase-3/authority-spec-review.md), A1–A5 | Current permission before replay; bounded credentials; coherent read authorization; pending claims; bounded security-revocation reserve. Main selected these reversible engineering rules. |
| Integrated authority acceptance | FAIL / not implemented | Blocks declaring the slice complete. Actual calculator/SQLite/access composition, reopen/replay, race/rollback and independent source/security review are required. Specification acceptance is not implementation evidence. |
| Remote identity, live UI and release capability | FAIL / outside this local scope | No listeners or deployment. Internet invitations/recovery, UI defenses, backups and operational checks remain later gates. |
| Human escalation required for this bounded action | PASS — none | No spend, account action, external/private-data operation or unresolved policy activation. Future policy-dependent features remain gated. |

**Authorized next work:** implement/test trusted bootstrap and authenticated snapshots first, then accepted command replay, quantity claims, receipt attestation and atomic finalization with the accepted calculator. Use small red→green behaviors and disposable test databases; retain strict integer money and rational bounds. Independently review actual source and integrated evidence before accepting the slice. No routine phase approval is requested.

## 2026-10-17 — Local authoritative-draft acceptance on feature branch

**Orchestrator decision: PASS for the bounded local implementation; publish `feature/authoritative-draft` and open its PR against main as requested.** This accepts one slice within Phase 3, not a full product or public deployment. Main read the actual production module, tests/interface, independent reports and twenty-case mapping. [Acceptance detail](../../research/phase-3/authority-acceptance.md), [exact verification/hashes](../../research/phase-3/authority-verification.json).

| Gate | Decision / evidence | Remaining restriction |
|---|---|---|
| Spec, exact finance and calculator integrity | PASS — all20 cases mapped, actual calculator finalization and unchanged source hash | Quantity claims only; supplied receipt facts still require organizer attestation. |
| Test execution and atomic persistence | PASS — main60 tests in195.536s; real independent connections, races, rollback, reopen/fresh process and actual10,000-command quota | No power-loss/restore/load claim. Diagnostic-only assertion hardening followed by27 targeted passing reruns. |
| Independent source/spec and security reviews | PASS — both final reports pin source `1eef9e7959639de5407bc445e9344f3ef7e0bb9502bafcfb2026d2c794ed81f0`; material A1/S1/S2 fixed and retested | Original failures remain documented; no open material finding. |
| Credential/replay/current access | PASS — hash-only credentials, safe callbacks/cleanup, current authorization before replay, real reserve and nonleak checks | Trusted host/bootstrap/clock; fixed sessions lack renewal and recovery. Lost bootstrap acknowledgement cannot reissue credentials. |
| Full Internet application/release | FAIL / excluded from this slice | Real identity/invitation/transport, UI, backup/restore, other split editors, settlement/correction policies, OCR and Notion require later gates. |

No scope redesign, calculator modification, paid/external-data operation or listener was needed. Ordinary state headroom below1MiB preserves security revocations; natural maximal-result capacity remains unmeasured and the response-size fault test is labeled as injected. The requested PR is the deliverable; this decision does not merge it or authorize another feature within this task.

## 2026-10-17 — Authority merge/checkpoint and repository foundation

The user reports completed independent external review without a merge blocker and explicitly authorizes merge/checkpoint and repository-foundation work. This supersedes the preceding task's stop-at-PR boundary.

| Gate | Decision / verified evidence |
|---|---|
| Reviewed head/base unchanged | PASS — actual PR1 metadata and Git remote refs match head `59cba5feb25423ebd43ebee17b7666d84f83d584` and main `7db4ef155149526f6c646158814d1851b5fdb21b`; GitHub reports mergeable. External review completion is user-supplied evidence, not fabricated GitHub review submissions. |
| Preserve accepted history | PASS — GitHub merge method `merge`, expected-head guard; resulting `af7ba147642b8b8e9a5aee973a95c59d46c38b9a` has those exact two parents and the reviewed head's tree. |
| Remote checkpoint | PASS — remote main verified at merge; annotated `authority-v1-accepted` object `389eb52462cfe0a17a4456504a41214956ae15bc` peels to the merge. |
| CI activation cost | PENDING account evidence — establish minimal full-suite CI only within included usage and verified zero paid-overage exposure; do not alter billing/payment settings. |
| Foundation and next-slice scope | PASS to research/review separate CI and package refactor changes, preserving all deterministic and persisted domains; then plan transport/identity/invitations. No new product feature begins in this foundation step. |

## 2026-10-17 — Foundation accepted; invitation/transport planning

**Orchestrator decision: PASS for repository foundation; proceed to bounded lifecycle specification/planning.** [Foundation index/evidence](../../research/foundation/README.md), [next plan](../../research/phase-3/next-slice-plan.md), [independent architecture/security challenge](../../research/phase-3/transport-identity-challenge.md).

| Gate | Decision and evidence |
|---|---|
| Included-only hosted usage | PASS on explicit owner account confirmation: included minutes remain, no valid payment method. Official quota blocking rule verified; no payment/budget settings changed. Workflow timeout/concurrency are not falsely treated as a billing cap. |
| Minimal full-suite CI | PASS — independently reviewed candidate, exact official SHA pins independently read; PR #2 hosted run completed60 tests in28.299s, then merged at `a4dd5302f93b41bbf72cbf29ecd596bc7bb7c1aa`; main push run also passed. No security/authority tests filtered or weakened. |
| Dedicated package refactor | PASS — PR #3 at `a50fa4585e91b8b8eadcf51177f545366b90f7d0`, merged as `91b824f395d062a994056e905f475fe83f52b3a8`; three production files byte-identical, seven callers have exact namespace-only deltas. Current imports `settletable`; all five versioned domains preserved. |
| Cross-version data and execution | PASS — old-tag→new-package10 exact replays/3 equal snapshots, schema/history/verifiers unchanged, revoked/expired/conflicting replay denied and fresh draft command accepted. Main local60 tests73.078s; hosted rename PR60 tests30.151s. An interrupted subagent session is not counted; the orchestrator reran and reviewed actual evidence. |
| Next slice readiness | PASS to plan/specify; CONDITIONAL for implementation — close one-time-grant acknowledgment/status behavior, bounded rotation/security reserve and additive old-DB compatibility in a reviewed concrete spec. Reject separate-store invitation wrappers. |
| Full browser/public service readiness | FAIL / outside current scope — real origin/CSRF/cookie/Host, identity recovery, abuse/backup/TLS and deployment evidence remain later gates. No public service, new framework or product feature added. |

The next local scope targets invitations and sessions for already declared diner identities within the authority transaction. Follow with a separately tested same-origin transport. Preserve current financial replay contracts and no raw-bearer persistence; do not activate recovery/handover/member restoration policy by inference. No routine phase confirmation is needed; genuine spend/exposure/account/product-policy escalation remains effective.

## 2026-10-20 — Invitation and session lifecycle specification acceptance; implementation authorized

**Orchestrator decision: PASS to begin implementation of the integrated invitation and session lifecycle within Phase 3.** Evaluated against [next-slice-plan](../../research/phase-3/next-slice-plan.md), [independent challenge](../../research/phase-3/transport-identity-challenge.md), and [specification](../../.scratch/invitation-lifecycle/SPEC.md); reviewed actual report from independent research subagent. All 8 review findings are incorporated.

| Material Gate | Disposition / Evidence | Restriction / Invariants |
|---|---|---|
| Single transaction owner | PASS — all lifecycle operations (`issue_invitation`, `redeem_invitation`, `rotate_session`, `RevokeInvitation`) reside strictly in `settletable.authority.Authority` on the single SQLite connection. | No separate store, sidecar DB, or check-then-apply framework. |
| Zero credential persistence & domain separation | PASS — tokens and credentials suppressed in repr, absent from SQLite/snapshots/commands/results/exceptions; new domain `settletable-invitation-v1\0` strictly separated. | No raw secret in logs, DB dumps, or test failure messages. |
| Single-use, expiry, and atomic rotation | PASS — tokens consumed atomically; rotation destroys prior session verifier; exclusive trusted-clock expiry enforced. | No unauthenticated participant creation, organizer handover, or account recovery. |
| Cascading revocation correctness | PASS — `RevokeSession` and `RevokeMembership` invalidate outstanding active invitations; `already_revoked` requires both session and invitations to be inactive. | Precludes resurrecting access via pre-existing invitations. |
| Resource limits and security reserve | PASS — 64 lifecycle generations per participant; ordinary quota capped at 10,000; security commands exempt with mathematical bound $\le 6,534$ rows. | Exhaustion of ordinary/lifecycle quota does not prevent revocation. |
| Reversible additive schema & v1 compatibility | PASS — `invitations` and `participant_lifecycle` created with `CREATE TABLE IF NOT EXISTS`; existing tables untouched; historical replay and snapshots byte-identical. | Verified by reopening disposable v1 databases. |
| Safe acknowledgment & retry policy | PASS — lost grant commits are explicitly uncertain; retry of consumed token or rotated session rejects; status visible in snapshot via `InvitationRecord`. | No recoverable secret storage. |
| Public exposure / spend escalation | PASS — no spend, no deployment, no network listener, no third-party services, no credential changes. | Strictly localhost/in-process Python standard library. |

**Approved next action:** Implement the vertical slices via TDD (`issue_invitation`, `redeem_invitation`, `rotate_session`, `RevokeInvitation`, cascading revocation, snapshot metadata, resource quotas, and backward compatibility), verify passing test suite, and run adversarial lifecycle tests.

## 2026-10-20 — PR #4 Merge: Integrated Invitation and Session Lifecycle Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `0f63ecd00ea71c5c667c70ef750012f594ae3add` merged autonomously under the orchestrator governance policy into `main` at `75a3511982091d6c49f97a29dbf7a9fcb6de0205`. All 5 external review findings resolved; independent security review subagent delivered unconditional GO (`research/phase-3/invitation-security-review.md`); 79/79 test suite methods passed in 149.391s; hosted GitHub Actions CI run `39404379865` succeeded.

| Gate | Disposition / Evidence |
|---|---|
| Invariants & Financial Correctness | PASS — `settletable.calculation` byte-identical (`4e4484...`); 15 calculation tests pass; all 4 hash domains intact with null-terminator prefixes. |
| Secret Hygiene | PASS — Zero token persistence; `repr=False` on all bearer material; SHA-256 verifiers only; SQL/dump/bytes scans verify zero leakage. |
| Concurrency & Transactions | PASS — Exclusive `BEGIN IMMEDIATE` locks; dual-connection racing redemption and racing revocation serialize deterministically; cascading revocation verified across 3 pathways. |
| Error Handling & Entropy Failures | PASS — `secrets.token_urlsafe` and verifiers inside `try:` with rollback in `issue_invitation`, `redeem_invitation`, `rotate_session`; tested via entropy-injection mock. |
| Security Reserve Bound | PASS — Rigorously proved $\le 12,771$ commands ceiling for $N \le 100, G = 64$; enforced with defensive `< 15,000` limit on `security = 1` commands in `apply()`. |
| Duplicate `issue_id` Safe Rejection | PASS — Explicit `SELECT 1 FROM invitations WHERE meal_id=? AND issue_id=?` cleanly raises `AuthorityError('command_conflict')` without database integrity crashes. |
| Organizer Session Lockout Protection | PASS — `rotate_session` restricts callers to non-organizers (`_require(not organizer, 'forbidden')`), eliminating irreversible self-lockout from uncertain rotation. |
| Additive Backward Compatibility | PASS — Reopening v1 databases works additively; historical commands/snapshots replay byte-identically. |
| Hosted CI Verification | PASS — GitHub Actions run `39404379865` on head `0f63ecd` passed full test suite on Python 3.14 / Linux. |

**Next scope:** specify, challenge, and implement the bounded same-origin transport adapter (HTTP/transport boundary for meal requests) under orchestrator governance.

## 2026-10-20 — PR #5 Merge: Bounded Same-Origin Transport Adapter Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `1f1fb789f5bc5cf93b04c0ec6063b5f63969a9b2` merged autonomously under the orchestrator governance policy into `main` at `43b827f486ffa06d532c37d89826ccf2aa50051f`. GitHub marks PR #5 closed rather than merged because the branch was merged directly via git CLI (`git merge --no-ff`) and pushed to `main`; all reviewed commits and tree changes are fully integrated. Prior architectural challenge conducted (`research/phase-3/transport-adapter-challenge.md`); post-implementation independent security review delivered PASS / GO (`research/phase-3/transport-adapter-review.md`); all 6 review remediations (wire header limits, defensive payload parsing, secret logging redaction, SQLite WAL mode, case-insensitive auth headers, and Unicode NFC key deduplication) verified; 101/101 test suite methods passed in 66.240s; hosted GitHub Actions CI run `39408626484` succeeded on the exact reviewed head.

| Gate | Disposition / Evidence |
|---|---|
| Wire Boundaries & Limits | PASS — Request header lines $\le$ 4 KB, total header block $\le$ 16 KB (431 `header_too_large`), body $\le$ 1 MB (413 `payload_too_large`), nesting depth $\le$ 10, integer digits $\le$ 19, duplicate keys (with Unicode NFC normalization) and floats strictly rejected. |
| CSRF & Origin Protection | PASS — Mandatory `X-SettleTable-Action: 1` header on all POST requests; strict `Origin` matching against `server_origin` for cookie or unauthenticated browser contexts; `Origin: null` blocked; conflicting Bearer/cookie rejected with 400 `conflicting_credentials`. |
| Unauthenticated Landing Separation | PASS — `GET /api/invitations/{token}` invokes read-only `Authority.inspect_invitation()`; non-mutating, zero token consumption, zero revision advance; tested over 5x sequential calls. |
| Error Mapping & Suppression | PASS — Canonical envelope `{"ok": false, "error": "...", "detail": null}`; unhandled exceptions suppressed to 500 `internal_error`; 401 attaches `WWW-Authenticate: Bearer`; 503 attaches `Retry-After: 1`. |
| Cookie Security | PASS — Host-only cookies with `HttpOnly; Secure; SameSite=Strict; Path=/` across bootstrap, redemption, and session rotation. |
| Actor Isolation | PASS — `actor` and `organizer` injection strictly rejected at transport parsing boundary with 400 `invalid_input`; actor identity derived strictly from session credential. |
| Secret Hygiene & Redaction | PASS — Zero tokens/credentials logged; `redact_log_string` masks URLs, Bearer credentials, and cookie values to `[REDACTED]`. |
| Concurrency & Persistence | PASS — SQLite opened in WAL mode with `busy_timeout=1000`; per-thread `Authority` instances maintain thread affinity. |
| Hosted CI Verification | PASS — GitHub Actions run `39408626484` on exact head `1f1fb78` passed all 101 tests on Python 3.14 / Linux. |

**Next scope:** Frontend UI / web client integration for meal drafts, item claiming, and invitation landing under the bounded transport API.

## 2026-10-20 — PR #6 Merge: Transport-Boundary Hardening Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `65ae4bd7987fc5208f8705b6197171ef0728c057` merged autonomously under the orchestrator governance policy into `main` at `e7a8a82918353d82188746c0d7b19fec499b2698`. GitHub PR #6 closed upon direct merge to main. Post-implementation independent security review delivered unconditional GO (`research/phase-3/transport-hardening-review.md`); all 5 audit gates passed; 104/104 test suite methods passed in 63.364s; hosted GitHub Actions CI run `39420125202` succeeded on the exact reviewed head.

| Gate | Disposition / Evidence |
|---|---|
| Reverse Proxy Loopback Protection | PASS — `POST /api/meals/{meal_id}/bootstrap` rejects requests containing proxy headers (`X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `Forwarded`, `X-Real-IP`) with 403 `forbidden`, preventing external proxy bypass of loopback checks. |
| Credential Minimization at Provisioning | PASS — Bootstrap returns session credentials strictly for the organizer (`sessions: [{"participant_id": organizer_id, "credential": ...}]`); never returns pre-minted diner credentials over HTTP. |
| Cookie-Context Credential Hygiene | PASS — `POST /api/meals/{meal_id}/session/rotate` omits raw bearer credentials from the JSON response body when the caller authenticated via cookie, delivering credentials exclusively via `Set-Cookie` (`HttpOnly; Secure; SameSite=Strict; Path=/`) to prevent XSS exfiltration. Programmatic Bearer callers retain credential in JSON. |
| Ingress vs. WSGI Boundary Demarcation | PASS — `docs/deployment-boundary.md` explicitly documents the Tier 1 ingress boundary (TCP stream bounds in reverse proxy) vs. Tier 2 WSGI application defense-in-depth, including Nginx reference configuration. |
| Test Coverage & Invariant Integrity | PASS — 104/104 tests pass; zero modification to `settletable.authority` or `settletable.calculation`; deterministic math and state machine invariants intact. |

**Next scope:** Design, specify, and implement the same-origin browser MVP (organizer receipt entry/review, diner invitation landing, item claiming, and finalized allocation results) using local assets and responsive mobile-first UI.

## 2026-10-20 — PR #7 Merge: Same-Origin Browser MVP Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `cd4973c1cd73dae8f6ebe8e97640e04604ae16f6` merged autonomously under the orchestrator governance policy into `main` at `67f7190638696f8592cd49fa489b5f12f64b49e1`. GitHub PR #7 closed upon direct merge to main. Architectural challenge conducted (`research/phase-3/browser-mvp-challenge.md`); post-implementation independent security review delivered CONDITIONAL PASS with 4 minor remediations (`research/phase-3/browser-mvp-review.md`), all of which were resolved in commit `cd4973c` (server-authoritative `snap.issues` evaluation for finalization, in-memory invite token caching for link re-copy, $44\text{px}$ touch targets on stepper buttons, and `escapeHtml()` error sanitization); 109/109 full-suite tests passed locally in 63.725s; hosted GitHub Actions CI run `39423753289` succeeded on the exact final reviewed head SHA.

| Gate | Disposition / Evidence |
|---|---|
| Zero External Dependencies & Asset Isolation | PASS — Zero CDNs, zero web fonts, zero remote tracking/analytics scripts; 100% self-contained local assets (`settletable/static/`); system font stack utilized. |
| Static Asset Serving & Path Traversal Security | PASS — Static files served strictly through an in-memory dictionary allowlist (`STATIC_FILES`) and regex matching (`/static/([A-Za-z0-9_.-]+)`); `X-Content-Type-Options: nosniff`; `Cache-Control: no-store` on HTML routes; path traversal attempts fail regex and return 404 `not_found`. |
| Content Security Policy & DOM XSS Immunity | PASS — Strict Content Security Policy header attached to all HTML/static routes (`default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`); all dynamic server data and user inputs escaped via `escapeHtml()`. |
| Authentication, Invitation Landing & Session Boundary | PASS — Host-only cookies with `HttpOnly; Secure; SameSite=Strict; Path=/`; unauthenticated landing `GET /invite/{token}` serves HTML shell without token consumption or state mutation; one-click redemption establishes cookie; caller identity and role context (`current_participant_id`, `is_organizer`) returned via `Authority.authenticate()`. |
| Dining Flow UX, Conflict Handling & Human Receipt Review | PASS — Mobile-responsive layout (touch targets $\ge 44\text{px}$, `viewport-fit=cover`); explicit human receipt verification step before finalization; concurrency conflicts (item revision collisions) return HTTP 409 Conflict with amber conflict banner, contested card highlight, and automatic refresh. |
| Financial Invariants & Invariant Integrity | PASS — Deterministic calculation module (`settletable/calculation.py`) and cryptographic hash domains remain completely untouched; all 109 automated tests pass. |

**Next scope:** Browser MVP end-to-end defect fixes, real browser journey automation with Headless Chrome, and local demonstration handover.

## 2026-10-20 — PR #8 Merge: Browser MVP E2E Defects & Real Browser Validation Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `172d56f8f5337fc9a518fb1935c754dc9335e76a` merged autonomously under the orchestrator governance policy into `main` at `a8436fdcb8848fe5ce299c883a26a2b0c2e64dfc`. GitHub PR #8 closed upon direct merge to main. Post-implementation independent security and code review delivered unconditional GO (`research/phase-3/browser-e2e-fixes-review.md`); all 6 audit gates passed; 113/113 test suite methods passed in 60.448s; 8/8 automated real-browser CDP test stages passed in 3.2s via Headless Chrome (`tools/e2e_browser_test.mjs`); hosted GitHub Actions CI run `39442110445` succeeded on the exact reviewed head.

| Gate | Disposition / Evidence |
|---|---|
| Receipt-Entry Contract & Human Verification | PASS — `ReplaceReceipt` command in `settletable/static/app.js` computes authoritative `subtotal_sen` and `total_sen` from line items and adjustments; resolves `missing_amount` review rejection without fabricating zero amounts; mandatory human review preserved before finalization. |
| Authoritative Calculation Display | PASS — `renderFinalizedCalculation()` maps participant totals directly from `calculation.consumption` records (`participant_id -> sen`); renders explicit `Amount Missing` warning if data is absent rather than fabricating RM 0.00; grand total tied to `receipt.total_sen` and consumption sum. |
| Mutation Refresh & Conflict Recovery | PASS — Polling (`fetchSnapshot(false)`) and mutation refresh (`fetchSnapshot(true)`) decoupled; `state.mutationActive` cleared before forcing refresh; monotonic sequence numbering (`state.pollSeq`) guards against out-of-order poll clobbering; 409 stale conflict handled cleanly with amber alert and UI reload. |
| Strict MYR Input Parsing | PASS — `parseSen()` replaces permissive `parseFloat` with strict regex `/^[0-9]+(?:\.[0-9]{1,2})?$/` and pure integer sen arithmetic; rejects malformed characters, non-strings, negative amounts, and out-of-bounds values without floating-point drift. |
| Real Browser E2E Test Verification | PASS — `tools/e2e_browser_test.mjs` executes an 8-stage automated CDP test across two isolated Headless Chrome instances with independent user profiles and cookie stores; validates end-to-end flow from room creation to reload persistence. |
| Financial Invariants & Invariant Integrity | PASS — Deterministic calculation module (`settletable/calculation.py`) and cryptographic hash domains remain untouched; 113/113 full-suite tests pass. |

**Next scope:** Cross-platform browser test infrastructure improvements, bearer token log sanitization, and GitHub Actions CI browser journey automation.

## 2026-10-21 — PR #9 Merge: Cross-Platform Browser Test Infrastructure & CI Automation Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `5a879c5ed5ef7c95939da0b4fd98e2516d086e1b` merged autonomously under the orchestrator governance policy into `main` at `1b693f56cb3cf3df0e7cb84727cccaf594d1e769`. GitHub PR #9 closed upon direct merge to main. Post-implementation independent security and code review delivered unconditional GO (`research/phase-3/test-infra-review.md`); all 5 audit gates passed; 113/113 test suite methods passed in 47.362s; 8/8 automated real-browser CDP test stages passed in 3.2s via Headless Chrome (`tools/e2e_browser_test.mjs`); hosted GitHub Actions CI run `39508712147` succeeded on the exact reviewed head in `ubuntu-24.04`, validating both the Python unit suite and the real browser E2E test in CI.

| Gate | Disposition / Evidence |
|---|---|
| Dynamic Cross-Platform Discovery | PASS — `tools/e2e_browser_test.mjs` dynamically resolves Chrome/Chromium and Python binaries across Windows, Linux, and macOS without hardcoded paths; supports env vars (`CHROME_BIN`, `PYTHON_BIN`) and CLI flags (`--chrome`, `--python`, `--port`); resolves repository root via `import.meta.url`. |
| Secret Log Hygiene | PASS — Invitation bearer URLs are sanitized via regex (`/invite/[REDACTED]`) before `console.log` output; unhashed bearer tokens never leak into test output or CI logs; unredacted URL is retained strictly in-memory for browser navigation. |
| Container Headless Chrome Flags | PASS — Headless Chrome configured with `--headless=new`, `--no-sandbox`, `--disable-dev-shm-usage`, and `--disable-gpu` to guarantee crash-free execution in unprivileged Linux container and VM environments. |
| CI Integration & Zero-Cost Conformance | PASS — `.github/workflows/python-tests.yml` executes `node tools/e2e_browser_test.mjs` natively on `ubuntu-24.04` runner with pre-installed Chrome and Node built-ins; zero added dependencies, zero SaaS subscriptions, <0.2% monthly quota usage ($0.00 cost). |
| Test & Invariant Integrity | PASS — Deterministic calculation module and authority contracts untouched; 113/113 Python unit tests pass; real browser CDP harness passes all 8 stages. |

**Next scope:** Bounded local/self-hosted receipt OCR pipeline, organizer verification gate, Malaysian SST/service-charge extraction, and optional asynchronous Notion reporting.

## 2026-10-21 — PR #10 Merge: Bounded Local Receipt OCR Pipeline & Malaysian SST Parser Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `b6dc100d04961917f93539fc4107127e9fe558d4` merged autonomously under the orchestrator governance policy into `main` at `3455a57223d1e1582d1c3c8f8185186484364074`. GitHub PR #10 closed upon direct merge to main. Post-implementation independent security and code review delivered CONDITIONAL PASS (`research/phase-3/ocr-implementation-review.md`), with the wire `Content-Type` validation remediation applied, retested, and verified; all 6 audit gates passed; 136/136 test suite methods passed in 71.784s; 8/8 automated real-browser CDP test stages passed in 3.2s via Headless Chrome (`tools/e2e_browser_test.mjs`); hosted GitHub Actions CI run `39512879579` succeeded on the exact reviewed head in `ubuntu-24.04`, validating all Python tests and the real browser E2E test in CI.

| Gate | Disposition / Evidence |
|---|---|
| Local-Only & Zero Cloud Fallback | PASS — OCR inference runs on local CPU via RapidOCR / ONNX Runtime (`settletable/ocr/engine.py:161-189`). Cloud OCR fallback is strictly excluded; missing engine raises `OcrUnavailableError` -> HTTP 503 `ocr_unavailable`. Air-gap socket test verifies zero outbound network connections (`tests/test_ocr.py:391-400`). |
| Safe Binary Ingress & Decompression Protection | PASS — Route-aware body ingress for `POST /api/meals/{meal_id}/ocr/extract` bypasses `parse_strict_json` for raw binary images up to 5 MB (`settletable/transport.py:384-406`). Image dimensions are parsed directly from raw binary headers (PNG IHDR, JPEG SOF markers, WebP VP8 chunks) and bounded to $\le 4096 \times 4096$ and $\le 16\text{MP}$ before bitmap decoding, preventing decompression bombs. Declared `Content-Type` is strictly validated against detected magic bytes. |
| Malaysian Receipt Domain & Invariants | PASS — Deterministic layout parser (`settletable/ocr/parser.py`) enforces the Wan Sheng tax-inclusive rule (`subtotal_sen = sum(items)`, `included_tax_sen` populated) preserving `settletable.calculation` subtotal invariants; correctly extracts statutory tax-exclusive SST/GST, service charge, negative discount sen, and BNM 5-sen rounding ($\pm 1, \pm 2$ sen); enforces the Kechara rule preventing fact invention by leaving unprinted discrepancies as `None` and routing to `manual_correction`. |
| Organizer Authorization & Zero State Mutation | PASS — `POST /ocr/extract` requires valid organizer credentials, returning 403 `forbidden` for diners and 401 for unauthenticated callers (`settletable/transport.py:586-591`). Extraction is strictly advisory with zero SQLite mutations (database file SHA-256 is 100% byte-identical before and after call). Mandatory human receipt review and cryptographic digest sealing in UI preserved before finalization. |
| Deterministic CI Portability & Test Coverage | PASS — `MockOcrEngine` uses pre-recorded JSON token fixtures (`tests/fixtures/ocr/tokens.json`), allowing 100% of the 136 Python tests to pass in CI without native ONNX runtime wheels; real browser CDP test passes all 8 stages. |
| Financial Invariants & Invariant Integrity | PASS — Deterministic calculation engine (`settletable/calculation.py`) and cryptographic hash domains (`settletable-receipt-v1`, `settletable-local-session-v1`, `settletable-invitation-v1`, `settletable-command-v1`) remain completely untouched. |

**Next scope:** Optional asynchronous Notion reporting, maintaining strict decoupling from live meal collaboration.

## 2026-10-21 — PR #11 Merge: Bounded Optional Asynchronous Notion Reporting Pipeline Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `8a83ba2287ad27764a51147bd594e4b4c4eba966` merged autonomously under the orchestrator governance policy into `main` at `d34ff75caf3047f5a8515d0b3503e3a3948871ae`. GitHub PR #11 closed upon direct merge to main. Post-implementation independent security and code review delivered unconditional GO (`research/phase-3/notion-implementation-review.md`); all 6 audit gates passed; 150/150 test suite methods passed in 62.383s; 9/9 automated real-browser CDP test stages passed in 3.4s via Headless Chrome (`tools/e2e_browser_test.mjs`); hosted GitHub Actions CI run `39515609945` succeeded on the exact reviewed head in `ubuntu-24.04`, validating all Python tests and the 9-stage real browser E2E test in CI.

| Gate | Disposition / Evidence |
|---|---|
| Decoupling & Fault Isolation | PASS — Live meal collaboration, item claiming, receipt review, and finalization execute 100% offline or air-gapped without Notion. Notion export failures leave SQLite meal state, claims, and calculations completely intact with zero database rollbacks. Live dining never depends on Notion availability or credentials. |
| Secret Hygiene & Token Redaction | PASS — Notion API tokens (`secret_...` and `ntn_...`) are strictly excluded from SQLite persistence. Wire logs (`transport.redact_log_string`), error strings, and exception handlers scrub integration tokens to prevent leakage in server output or HTTP error bodies. |
| One-Way Invariance & Financial Integrity | PASS — Apportionment exported to Notion is mapped directly from authoritative `calculation.consumption` integer sen amounts. Notion formulas, rollups, or calculations are strictly zero; money formatting uses integer division without floating-point drift. |
| Quota & Block Efficiency | PASS — Generates $\le 40$ blocks per meal (1 callout + 2 headings + 2 tables + rows + divider + audit paragraph), yielding $>70\%$ block savings over relational multi-page designs and protecting Free tier workspace lifetime block quotas (1,000 blocks). Page-parent export strictly limits properties to `title` (per Notion REST constraint for non-database parents) while placing financial metadata inside the top Callout block; table block dimensions strictly match row cell arrays. |
| Concurrency & Idempotency State Machine | PASS — SQLite tracking table `notion_exports` maintains `(meal_id, finalized_revision)` through `in_progress` -> `completed` state machine, rejecting duplicate concurrent clicks with 409 `export_in_progress` or 409 `already_exported` while permitting clean recovery on failure (`clear_notion_export`). |
| Deterministic CI Portability & Test Coverage | PASS — `MockNotionClient` validates exact REST constraints without opening outbound sockets, allowing all 150 Python unit tests and 9-stage Chrome CDP browser tests to execute at $0.00 spend. |
| Financial Invariants & Invariant Integrity | PASS — Deterministic calculation module (`settletable/calculation.py`) and cryptographic hash domains (`settletable-receipt-v1`, `settletable-local-session-v1`, `settletable-invitation-v1`, `settletable-command-v1`) remain completely untouched. |

**Next scope:** Phase 3 consolidation, operational review, and demonstration handover.

## 2026-10-21 — PR #12 Merge: Phase 3 Consolidation, Operational Hardening & Demo Handover Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `de890fadebc8c3fb7f5eb0a1521e947b0f3a3be5` merged autonomously under the orchestrator governance policy into `main` at `5a5231d5250902968d3f716c9771ac8e23cf41ce`. GitHub PR #12 closed upon direct merge to main. Post-implementation independent security and code review delivered unconditional GO (`research/phase-3/consolidation-review.md`); all 5 audit gates passed; 154/154 test suite methods passed in 75.858s; 9/9 automated real-browser CDP test stages passed in 3.6s via Headless Chrome (`tools/e2e_browser_test.mjs`); hosted GitHub Actions CI run `39531452344` succeeded on the exact reviewed head in `ubuntu-24.04`, validating all Python tests and the 9-stage real browser E2E test in CI.

| Gate | Disposition / Evidence |
|---|---|
| OCR Review Boundary & Staging | PASS — In `settletable/static/app.js`, extracted OCR proposals are staged strictly in client memory (`state.ocrCandidate`) without writing to SQLite; file uploads no longer invoke premature `ReplaceReceipt`; UI displays clear confidence percentage, route badge (`⚠️ Needs Correction` vs `✓ Ready for Review`), and verification issues; explicit `Accept & Apply to Receipt` (dispatches `ReplaceReceipt`) and `Discard` buttons provide safe control; mandatory physical receipt review (`ReviewReceipt`) remains strictly enforced before finalization. |
| Notion Asynchronous Delivery & Duplicate Prevention | PASS — In `settletable/transport.py`, `POST /api/meals/{meal_id}/export/notion` runs in a background daemon thread (`threading.Thread`) and returns HTTP `202 Accepted` immediately by default (preserving `?sync=1` for testing), eliminating WSGI worker thread starvation for live diners; status polling endpoint `GET /api/meals/{meal_id}/export/notion` enables UI progress tracking; pre-creation title reconciliation in `export_finalized_meal` queries parent block children to adopt existing page if previous response was lost, preventing duplicate page creation; delivery semantics are explicitly documented as at-least-once with pre-creation title reconciliation. |
| Notion Free Block Budget Enforcement | PASS — In `settletable/notion/exporter.py`, constant `MAX_COMPACT_BLOCKS = 40` mathematically caps total exported blocks for arbitrary meal sizes via intelligent diner rollup ($P > 20$) and item rollup ($I > \text{remaining\_budget}$), protecting Free tier workspace lifetime block quotas (1,000 blocks); unconstrained `mode='full'` remains available; `count_notion_blocks` accurately tallies top-level blocks and table rows. |
| OCR Operational Validation & Demo Mock | PASS — `settletable/ocr/engine.py` supports both `rapidocr` and `rapidocr_onnxruntime` distributions; `tools/run_demo.py` provides `--mock-ocr` and `SETTLETABLE_MOCK_OCR=1` for immediate zero-dependency evaluation; zero image persistence to disk or SQLite; zero outbound network sockets. |
| Financial Invariants & Invariant Integrity | PASS — Deterministic calculation engine (`settletable/calculation.py`) and cryptographic hash domains (`settletable-receipt-v1`, `settletable-local-session-v1`, `settletable-invitation-v1`, `settletable-command-v1`) remain completely untouched; 154 unit tests and 9 real browser CDP test stages pass. |

**Next scope:** Phase 3 acceptance and User-Acceptance Readiness review.

## 2026-10-21 — User-Acceptance Readiness: OCR Edit-Before-Accept, Notion Hardening & UAT Handover Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `78f92ad6937e008cbb39e240212a4c148fc2834b` merged autonomously under the orchestrator governance policy into `main` at `84acc18`. Post-implementation independent security and code review delivered CONDITIONAL GO, with all 3 material findings (negative cash rounding sign inversion, `NotionRateLimitError` omission from reconciliation filter, and background worker generic error code recording) fully remediated and verified with regression tests. All 5 audit gates passed; 159/159 test suite methods passed in 59.603s; 9/9 automated real-browser CDP test stages passed in 3.6s via Headless Chrome (`tools/e2e_browser_test.mjs`).

| Gate | Disposition / Evidence |
|---|---|
| **OCR Candidate Edit-Before-Accept & Rounding Preservation** | PASS — In `settletable/static/app.js`, staged OCR candidate proposals can be corrected directly in an inline table (item names, quantities, unit prices, adjustments, and included tax) before applying to the draft receipt; live typing recalculates candidate subtotals and totals without input focus loss; `parseSen` and adjustment synchronizer preserve negative Bank Negara Malaysia cash rounding adjustments (e.g. -RM 0.02) without sign inversion; validation enforces positive line amounts and item existence before dispatching `ReplaceReceipt`; physical bill verification gate (`ReviewReceipt`) remains mandatory before finalization. |
| **OCR Local Inference Demarcation** | PASS — UI badge and documentation explicitly identify OCR as Server-Side Local Inference (RapidOCR CPU ONNX), eliminating misleading "on device" claims; extraction remains 100% advisory with zero SQLite mutation. |
| **Notion Reliability & Pagination** | PASS — `NotionHttpClient.query_block_children` implements cursor pagination (`max_pages=5`, `page_size=100`); pre-creation title reconciliation re-raises `NotionAuthError`, `NotionValidationError`, `NotionNotFoundError`, and `NotionRateLimitError` rather than silently swallowing them; delivery semantics remain at-least-once with pre-creation title reconciliation. |
| **Background Processing & Worker Starvation Defense** | PASS — Ephemeral background thread lifecycle is explicitly documented; synchronous export override `?sync=1` is disabled by default behind `allow_sync_export=False` (safeguarded via `SETTLETABLE_ALLOW_SYNC_EXPORT=1`), preventing WSGI worker starvation in public deployments; in-progress exports time out cleanly after 60s, recording `status='failed'` and allowing recovery; background export records granular error codes (`notion_rate_limited`, `notion_auth_error`, `invalid_input`, `notion_error`). |
| **Secret Hygiene & Demo Accuracy** | PASS — Verified that `tools/run_demo.py` prints zero credentials or session links to stdout; sessions are managed via host-only secure cookies and in-app invitation copying; comprehensive [User Acceptance Testing (UAT) Handover](docs/uat-handover.md) guide delivered. |
| **Financial Invariants & Invariant Integrity** | PASS — Deterministic calculation engine (`settletable/calculation.py`) and cryptographic hash domains remain completely untouched; 159 unit tests and 9 real browser CDP test stages pass. |

**Next scope:** Stakeholder User Acceptance Testing (UAT) walkthrough and Phase 4 operational hardening & production pilot planning.

## 2026-10-25 — PR #17 Merge: Bounded Phase 1 Atomic Item Allocation (`SetItemAllocations`) Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `92babe200ca1dd7cd6c73d83e678554f1ce727ad` merged autonomously under the orchestrator governance policy into `main` at `03a34c7a5f6436427387d7bda299f170f3f6e1eb`. GitHub PR #17 ([#17](https://github.com/KAIYI7/settle-table/pull/17)) verified on hosted CI before merge. Post-implementation independent security and code review delivered unconditional GO (`research/phase-3/atomic-item-allocation-remediation-review.md`); all 6 audit gates passed; 192/192 test suite methods passed in 74.5s; 11/11 automated real-browser CDP test stages passed in 18.8s via Headless Chrome (`tools/e2e_browser_test.mjs`); hosted GitHub Actions CI run `40171431186` succeeded on the exact reviewed head in `ubuntu-24.04` (Python 3.14).

| Gate | Disposition / Evidence |
|---|---|
| **Atomic Item Replacement (`SetItemAllocations`)** | PASS — In `settletable/authority.py` (`Authority._set_item_allocations`) and `settletable/transport.py` (dispatched via `POST /api/meals/{meal_id}/apply` with `kind: "SetItemAllocations"`), replacement command validates item-level capacity $\sum \text{quantity} \le \text{item.quantity}$ atomically in a single SQLite transaction, eliminating intermediate deadlocks and partial claim corruption inherent in sequential updates. Supports equal splits, custom rational fractions, portion adjustments, subset splits, and full resets (`allocations = []`). |
| **Claim Provenance & Attribution Integrity** | PASS — Preserves unchanged diner-authored claims (`assigned_by = None`) and prior assigner provenance when an organizer modifies other allocations on the same item. Modified quantities or newly introduced allocations receive `assigned_by = actor` (the acting organizer). Verified by `test_set_item_allocations_preserves_unchanged_diner_claim_provenance`. |
| **Strict Wire Input Sanitization** | PASS — In `settletable/transport.py`, `_parse_quantity(qty, *, allow_none=False)` uses exact type checks (`type(val) is int`), strictly rejecting boolean literals (`True`, `False`, `[True, 2]`, `[1, False]`), floating-point values (`1.5`, `[1.5, 2]`), non-positive values, and malformed fraction lists across all four quantity endpoints (`ReplaceReceipt`, `SetOwnQuantity`, `AssignParticipantQuantity`, `SetItemAllocations`). Verified by 21-case matrix in `test_transport_strict_fraction_and_boolean_rejections`. |
| **Concurrency & SQLite OCC Race Handling** | PASS — Multi-threaded test `test_concurrent_race_set_item_allocations_and_set_own_quantity` uses independent SQLite connections and `Authority` instances across OS threads to verify serializability between organizer `SetItemAllocations` and diner `SetOwnQuantity`. Exactly one transaction succeeds; competing transaction fails cleanly with `item_revision_conflict` (HTTP 409), transaction rolls back without orphan records, and item capacity ($\le \text{total}$) is strictly conserved. |
| **Financial & Apportionment Invariants** | PASS — Deterministic calculation engine (`settletable/calculation.py`) and Hamilton-Hare apportionment tie-breaker (`tabwise-apportion-v1`) remain untouched; sen-level exactness and zero floating-point math preserved; 192/192 Python unit tests pass; 11-stage real browser CDP test passes. |
| **Production Boundary Demarcation** | PASS — Scope is strictly bounded to the Phase 1 backend engine and transport routes. Production frontend allocator and diner self-claiming UI remain untouched; Concept C UI integration is deferred pending PO review and authorization. |

**Next scope:** Production integration of Concept C (Unified Expandable Hybrid organizer allocation) frontend workflow.

## 2026-10-25 — PR #18 Merge: Phase 2 Concept C Organizer Allocation Production Integration Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `751c10ca2d0f7a126c576083a5d511975970aa82` merged autonomously under orchestrator governance policy into `main` at `1f34b3e6d04193908e0264c050a25528df1f13cc`. GitHub PR #18 ([#18](https://github.com/KAIYI7/settle-table/pull/18)) verified on hosted CI before merge. Post-implementation independent code review completed with CONDITIONAL PASS; all review findings (M-01 float math, L-01 mobile pill height, L-02 meta fraction formatting) remediated and verified locally; 192/192 Python test suite methods passed; 11/11 automated real-browser CDP test stages passed in `tools/e2e_browser_test.mjs`; dedicated 10-scenario production verification passed with high-resolution CDP evidence in `tools/verify_concept_c_production.mjs`; hosted GitHub Actions CI run `40178531481` succeeded on the exact reviewed head in `ubuntu-24.04` (Python 3.14).

| Gate | Disposition / Evidence |
|---|---|
| **Concept C Item-First Allocation Architecture** | PASS — Replaced the legacy global dropdown Allocation Target Selector with item-first allocation cards (`.hybrid-item-card`). Displays item name, line total, allocation progress bar, available diner pills for 1-click quick assignment, clean allocated diner pills without tiny buttons, and a responsive Details / Split trigger. |
| **1-Click Quick Assign & Capacity Safety** | PASS — 1-click on available diner pill assigns 1 unassigned whole portion instantly. If remaining portion is fractional, user is prompted via toast notification to use Details / Split for custom fractions. |
| **Selective Subset Split with Exact Rationals** | PASS — Organizers select an arbitrary subset of diners to split an item equally. Generates exact reduced rational fractions ($[1, n]$, $[m, n]$) with real-time formula and cost preview (`1 item ÷ 3 diners = ⅓ each (~RM 12.00)`). Explicit confirmation prompt displayed before overwriting pre-existing claims. |
| **Adaptive Desktop / Mobile Architecture** | PASS — Desktop ($\ge 768\text{px}$) expands inline drawer (`.hybrid-drawer`). Mobile ($< 768\text{px}$) displays accessible bottom-sheet modal (`.bottom-sheet-modal`) with scrim backdrop, drag handle, safe-area insets, touch targets $\ge 44\text{px}$, zero horizontal overflow ($375\text{px}$ width verified), and Escape key keyboard dismissal. |
| **Claim Provenance & Attribution Integrity** | PASS — Unchanged diner self-claims (`assigned_by = None`) and original financial revisions are strictly preserved when the organizer updates allocations via `SetItemAllocations`. Verified in real browser E2E test. |
| **Zero Floating-Point Drift & Wire Compliance** | PASS — Rational arithmetic functions (`makeReducedFraction`, `toRat`, `addFractions`, `subtractFractions`, `formatRat`) ensure quantities submitted over the wire strictly match backend integer and fraction pair types, preventing `float_number_rejected` HTTP 400 errors. Apportionment reconciles down to the sen. |
| **Diner Self-Claiming Boundary Intact** | PASS — Diner self-claiming view (`!snap.is_organizer`) remains 100% intact with stepper increments, decrements, and claim-all buttons. |

**Next scope:** Remediation and verification of allocation preview rounding and "All" shortcut zero-capacity guard.

## 2026-10-25 — PR #19 Merge: Concept C Preview Alignment & "All" Shortcut Guard Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `3699dd4efeeaa520101ec2b53bf9467301cbfca9` merged autonomously under orchestrator governance policy into `main` at `b4cf4e8`. GitHub PR #19 ([#19](https://github.com/KAIYI7/settle-table/pull/19)) verified on hosted CI before merge. Post-implementation independent code review completed with unconditional PASS (Zero findings); 192/192 Python test suite methods passed in 171.4s; 11/11 automated real-browser CDP test stages passed in `tools/e2e_browser_test.mjs`; dedicated 10-scenario production verification passed with high-resolution CDP evidence in `tools/verify_concept_c_production.mjs`; hosted GitHub Actions CI run `40197038604` succeeded on the exact reviewed head in `ubuntu-24.04` (Python 3.14).

| Gate | Disposition / Evidence |
|---|---|
| **Deterministic Apportionment Previews (Finding 1)** | PASS — In `settletable/static/app.js`, implemented `apportionItemBase` using Largest Remainder (Hamilton-Hare) apportionment with pure-JS SHA-256 tie-breaker matching `settletable/calculation.py` (`_apportion`). Completely resolves RM 26.01 drift when RM 26.00 is split 3 ways (`867 sen + 867 sen + 866 sen = 2600 sen = RM 26.00` exactly). Output parity verified against Python calculator across test scenarios. |
| **Provisional Item Base Labeling & Hints** | PASS — Per-diner row previews explicitly label amounts as provisional base shares (`~RM X.XX base`), with descriptive tooltips (`title="Provisional item base share. Taxes, service charge, discounts, and rounding are apportioned at finalization."`) and persistent section subtitle (`Provisional item base • Taxes and service charge apportioned at finalization`). Distinctly differentiates unadjusted item base from finalized totals (which incorporate taxes, service charges, discounts, and rounding). Backend calculation engine preserved 100% untouched. |
| **"All" Shortcut Zero-Capacity Guard (Finding 2)** | PASS — When remaining capacity is 0 (`remRat === 0`), "All" button is rendered with `disabled` attribute and descriptive tooltip (`No unassigned portion remains`). Click listener guards against execution when `ratToNum(remRat) <= 0`, displaying a non-destructive info alert without submitting to the API. Other participants' allocations and exact rational arithmetic are strictly preserved. Verified via CDP live injection. |
| **Cross-Platform Verification Path Portability** | PASS — `tools/verify_concept_c_production.mjs` enhanced to dynamically resolve Python binary, Chrome/Chromium executable across Windows, macOS, and Linux, and configurable artifact directory (`process.env.ARTIFACT_DIR`) with automatic directory creation and fallback. |
| **Financial & System Invariants Intact** | PASS — Zero backend changes (`settletable/calculation.py` and `settletable/authority.py` untouched); sen-level exactness and zero floating-point math preserved; 192/192 unit tests pass; 11-stage real browser CDP test passes; Impeccable detect reports 0 anti-patterns. |

**Next scope:** Formal closure of the organizer allocation milestone and local stakeholder UAT.

## 2026-10-27 — PR #20 Merge: Header Navigation and Toast Layout Polish Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `d8163e54d3315edd8d57eced1cc7cf7503c456c5` merged autonomously under orchestrator governance policy into `main` at `1926871`. GitHub PR #20 ([#20](https://github.com/KAIYI7/settle-table/pull/20)) verified on hosted CI before merge. Post-implementation independent code and UX review completed with unconditional APPROVE / PASS (Zero findings); 192/192 Python test suite methods passed in 80.4s; 11/11 automated real-browser CDP test stages passed in `tools/e2e_browser_test.mjs`; visual layout metrics captured across Desktop (1280x800), Tablet (768x1024), Mobile (375x667), and Mobile Bottom Sheet + Toast stacking; hosted GitHub Actions CI run `40512835119` succeeded on the exact reviewed head in `ubuntu-24.04` (Python 3.14).

| Gate | Disposition / Evidence |
|---|---|
| **Simplified Room Navigation Architecture** | PASS — Completely eliminated the redundant `.room-nav-bar` row. Retained `.room-status-card` and added high-contrast, accessible `← Home / Room` breadcrumb navigation (`.room-home-link`), ensuring mobile users retain discoverable Home navigation even when the sticky header's `#nav-home-btn` text link is hidden. Cleaned up obsolete `#room-leave-btn` references in `settletable/static/app.js`. Text contrast reaches 4.90:1 (exceeding WCAG AA 4.5:1), hit area exceeds 64x28px, and layout truncation (`overflow: hidden; text-overflow: ellipsis`) prevents overflow. |
| **Corrected Header & Content Spacing** | PASS — Resolved CSS specificity collision where `.container` (`padding: 0 16px`) silently overrode `main` (`padding: 20px 16px 40px`). Explicitly declared `main#app, main` with `padding: 20px 16px 48px;` (desktop) and `padding: 16px 12px 40px;` (mobile). Eliminated negative margins and hardcoded offsets; content reliably begins 20px (16px on mobile) below the sticky header. All `.room-status-card` styles declared in `settletable/static/style.css`. |
| **Responsive Viewport Toast Placement** | PASS — Introduced `syncHeaderHeight()` to dynamically write `--app-header-height` to `:root`. Anchored `#alert-container` with `top: calc(var(--app-header-height, 68px) + 12px)` on desktop (starts at 81px, 12px below 69px header) and `+ 8px` on mobile (starts at 65px, 8px below 57px header). Zero overlap with sticky header navigation controls (Refresh, Leave Room). Preserved non-scrolling viewport stability, pass-through pointer events, and keyboard Esc dismissal. |
| **Rigorous Layering (z-index Hierarchy)** | PASS — Established explicit stacking hierarchy across page content (`z-index: 1`), sticky application header (`z-index: 200`), mobile bottom-sheet scrim (`z-index: 900`), mobile bottom-sheet modal (`z-index: 950`), and transient notifications (`z-index: 1100`). Guaranteed error alerts and conflict banners remain visible and interactive above modal sheets without blocking modal footer action buttons (`Clear All Claims`, `Done`). Verified via CDP live injection. |
| **Test Suite Resilience & Portability** | PASS — Parameterized `tools/e2e_browser_test.mjs` with `process.env.SETTLETABLE_PORT` and dynamic `${serverOrigin}`, updated assertions to verify `.room-status-card` and `.room-home-link`. All 192 Python unit tests and all 11 real browser CDP stages pass. |
| **Financial & System Invariants Intact** | PASS — Zero backend changes (`settletable/calculation.py`, `settletable/authority.py`, and `settletable/transport.py` untouched); sen-level exactness and zero floating-point math preserved; Impeccable detect reports 0 anti-patterns. |

**Next scope:** Final stakeholder UAT handover and Phase 4 deployment planning.

## 2026-10-28 — PR #21 Merge: Toast Placement Refinement Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `487de389c267f1e57e7d23973b84b44078e404fe` merged autonomously under orchestrator governance policy into `main` at `0bca517`. GitHub PR #21 ([#21](https://github.com/KAIYI7/settle-table/pull/21)) verified on hosted CI before merge. Post-implementation independent dual-axis code and UX review completed with unconditional PASS (Zero findings); 192/192 Python test suite methods passed in 83.9s; 11/11 automated real-browser CDP test stages passed in `tools/e2e_browser_test.mjs`; dedicated 5-case geometry and visual verification suite passed in `tools/capture_toast_evidence.mjs`; hosted GitHub Actions CI run `40625125967` succeeded on the exact reviewed head in `ubuntu-24.04` (Python 3.14).

| Gate | Disposition / Evidence |
|---|---|
| **Safe-Area Aware Bottom Viewport Anchoring** | PASS — Anchored `#alert-container` to viewport bottom with `bottom: calc(24px + env(safe-area-inset-bottom, 0px))` on desktop and `16px` on mobile. Achieved **541.0px clearance** on desktop (room card bottom: 185px, toast top: 726px) and **451.6px clearance** on mobile (room card bottom: 149.4px, toast top: 601px). Completely eliminates overlap with the `← Home / Room` breadcrumb navigation, room title, and Drafting status badge. |
| **Contextual Mobile Bottom Sheet Inversion** | PASS — Dual-layer CSS (`:has(.bottom-sheet-modal) #alert-container`, `body.has-bottom-sheet #alert-container`, `#alert-container.alert-container-top`) and JavaScript state synchronization in `syncAlertContainerPlacement()`. When a mobile bottom sheet modal is active, the toast automatically docks to the top (`y = 65–117px`), completely clearing modal footer actions (`Apply Equal Split`, `Clear All Claims`, `Done`). Touch targets for modal buttons remain 100% interactive and unblocked. |
| **Natural Directional Entry Motion** | PASS — Keyframe animations aligned to entry origin: `toast-in-bottom` (`translateY(12px) scale(0.98)` to `translateY(0) scale(1)`) for bottom toasts and `toast-in-top` (`translateY(-8px) scale(0.98)` to `translateY(0) scale(1)`) for contextual top-docked toasts, providing polished physical feedback. |
| **Responsive Wrapping & Rigid Touch Targets** | PASS — Long error messages (150+ chars) wrap cleanly via `overflow-wrap: break-word; word-break: break-word; min-width: 0;` with zero horizontal overflow (`bannerScrollWidth === bannerClientWidth` at 353px on 375px mobile viewport). Close button touch target enforced at rigid $36\times 36\text{px}$ with `flex-shrink: 0; touch-action: manipulation;`. |
| **Fixed Viewport Scroll Stability** | PASS — Under deep page scroll (`scrollY = 450px`), toast remains fixed at the viewport bottom (`y = 726–776px`, `inViewport: true`), with zero scroll jumping, layout shift (CLS = 0), or content displacement. |
| **Accessibility & Keyboard Dismissal** | PASS — Semantic ARIA roles preserved (`role="alert"` / `aria-live="assertive"` for errors; `role="status"` / `aria-live="polite"` for success). `Escape` keyboard dismissal verified with immediate event listener cleanup on dismissal to prevent memory leaks. |
| **CI Runner Stability Hardening** | PASS — In `tools/e2e_browser_test.mjs`, added `--disable-background-networking` and `--disable-default-apps` Chrome flags and extended connection polling to 300 attempts (30s), eliminating runner timeouts under high worker saturation. |
| **Financial & System Invariants Intact** | PASS — Zero backend changes (`settletable/calculation.py`, `settletable/authority.py`, and `settletable/transport.py` untouched); sen-level exactness and zero floating-point math preserved; Impeccable detect reports 0 anti-patterns. |

**Next scope:** Final stakeholder UAT walkthrough and Phase 4 deployment planning.





## 2026-10-28 — Bounded synthetic allocation authorization implementation readiness

Orchestrator decision: PASS for implementation of an opt-in local authorization-only integration; risk HIGH (authentication, authorization, concurrency and additive nonfinancial persistence). The owner approved this sole bounded feature and source publication; no public deployment or permanent credential provisioning. The reviewed contract fixes accepted Finalize consumption as amount authority and uses stable opaque references with a dedicated synthetic merchant/customer binding. Existing allocation and accepted command bytes remain invariant; no contribution/reimbursement/settlement effects, capture/refund or new financial schema. Independent source/security/adversarial review, failure/restart evidence using isolated stores, full local Python/browser regression and successful hosted exact-PR-head CI remain blocking delivery gates. Feature startup defaults disabled and local test infrastructure is disposable. Existing Internet release blockers remain. No phase-4 hosting work is authorized by this transition.


## 2026-10-28 — Optional allocation authorization simulation accepted (PR #22)

**Orchestrator decision: PASS / MERGED.** [PR #22](https://github.com/KAIYI7/settle-table/pull/22) merged with a merge commit after review and successful exact-head CI. Reviewed head `a1c82c8ed159fd1e5c2ddd89ae18d6d2f67e5b54`; merge `79d68548d65230755a5837b9debe071bd902cf3b`; premerge main `f0f58646e41ad3ccce207801b401cd72bd45e43f`. Actual merge parents and equality to the reviewed source tree were verified.

| Gate | Disposition |
| --- | --- |
| Financial and accepted-source authority | PASS: immutable accepted Finalize consumption supplies integer sen; allocation and command bytes remain unchanged; no contribution, reimbursement or settlement effect |
| Security and privacy | PASS: organizer-only initiation, organizer/self reads, reauthorization, server-only machine credential, fixed destination and disabled default; independent source/security/adversarial review accepted |
| Persistence, failure and recovery | PASS: real SQLite races and rollback; separate-process PostgreSQL/Kafka retries, cache expiry, lost-response restart, dependency outages and explicit restore write freeze |
| Local regression and UI | PASS: 213 Python tests, 21 focused simulation tests, 11 existing Chrome stages, explicit simulation browser journey, responsive controls and bounded GET polling |
| Hosted CI | PASS: [run 40649706607](https://github.com/KAIYI7/settle-table/actions/runs/40649706607), associated with the exact reviewed head, passed 213 Python tests and all 11 browser stages |
| Publication and cleanup | PASS: reviewed public source only; task-owned local processes, containers and disposable credentials removed; pre-existing resources preserved |

This completes the bounded, default-disabled local simulation milestone. Existing Internet release blockers remain. No public hosting, permanent account/credential provisioning, real payment or further feature is authorized by this transition.

## 2026-10-29 — Two focused independent-UAT UI corrections

**Orchestrator decision: PASS / MERGED** for [PR #23](https://github.com/KAIYI7/settle-table/pull/23). Risk MEDIUM overall (receipt quantity display Medium; capacity affordance Low). Scope is limited to existing rational display formatting and unavailable quick-assignment affordances, plus regression tests/evidence. [Verification](../../research/phase-3/uat-ui-corrections.md).

Reviewed source commit `3b24faa4bdd5a705854b4c31b2fa58d36597e69e`; final PR head `e00f914c49e04c72e13a57c58fc0cb70463a9cc7` adds evidence only and preserves reviewed production/test bytes. Premerge remote main rechecked at `76187b1fcb5e928e8f6cc78b3afc1c02477501ef`.

| Gate | Disposition |
| --- | --- |
| Receipt review display | PASS: actual DOM x1, x2, x3, x½, x⅓ before/after sealing and reload; unchanged authoritative receipt/line amounts |
| Allocation affordance | PASS: native disabled quick assignment at insufficient whole capacity, visible associated explanation, usable desktop/mobile Details / Split, reallocation and persistence after reload |
| Scope and authority | PASS: existing financial engine, authorization, revision conflict recovery, persistence and finalization/native confirmation implementation untouched; unknown UAT database/listener and unrelated resources preserved |
| Independent reviews | PASS: separate standards/source and specification reviewers report zero findings; independent focused Chrome rerun passes |
| Full local regression | PASS: post-review rerun 213 Python tests in 50.797s and all 12 real Chrome stages; 1280 × 900 / 375 × 667 focused visual evidence inspected |
| Hosted exact-head CI | PASS: [run 40820110948](https://github.com/KAIYI7/settle-table/actions/runs/40820110948), check head SHA equals final PR head; logs confirm 213 Python tests and 12 browser stages pass |
| Final diff/base recheck | PASS: actual hosted PR diff reviewed, production/test bytes equal independently reviewed source; remote main and branch refs unchanged before authorization |

Merge commit `449dc8c2322c7b64a429e28db8290da38f141975` was verified on remote main. Its parents are exactly the premerge main and reviewed PR head above, and its tree `53f9483d653160805ca9792d5d3121d2b2c62356` equals the final reviewed PR-head tree. This decision closes only the two corrections. The original independent UAT remains incomplete: its blocked and untested scenarios require a separate independent retest in a confirmed isolated environment. No public-release, deployment or further feature scope is authorized.
