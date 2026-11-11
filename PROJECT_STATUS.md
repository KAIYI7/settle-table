# Project status

Updated 2026-11-11. Project: **SettleTable**. Authority: [orchestrator governance](docs/agents/governance.md). Decisions: [transition ledger](docs/agents/phase-transitions.md).

- **Current phase:** Secure Public Self-Service Meal Creation Complete (PR #67). Enabled low-friction public self-service meal room creation directly from desktop or mobile browsers at `https://settle.kybuilds.com` without account registration, email verification, or host terminal CLI access: (1) **Separated Ingress Boundary**: Preserved strict loopback-only restrictions on administrative bootstrap (`POST /api/meals/{meal_id}/bootstrap`) while introducing a dedicated public creation endpoint (`POST /api/meals/public-create`) accessible behind Cloudflare Tunnel without 403 Forbidden errors; (2) **Anti-Squatting Cryptographic Room IDs**: Generated unguessable room IDs (`slug-entropy`, e.g. `friday-hotpot-595f719c42`) with 40 bits of cryptographic entropy (`secrets.token_hex(5)`), preventing URL enumeration, collision, and room squatting while preserving human-readable restaurant titles; (3) **Defense-in-Depth Abuse Prevention**: Implemented server-side kill switch (`SETTLETABLE_PUBLIC_CREATION_ENABLED=0` fail-closed default); Cloudflare Turnstile bot verification with server-side Siteverify, token replay cache (300s TTL), and strict action/hostname validation; CSP updated to permit `https://challenges.cloudflare.com`; sliding-window IP rate limiter (burst 2/120s, hourly 5/1h, daily 10/24h) with memory leak pruning; global database capacity limits (max 100 total meals, max 25 meals/day); input length bounds (title max 60 chars, organizer max 40 chars, max 20 diners) and control character rejection; and completed idempotency caching that bypasses rate limits on network retries; (4) **Organizer Authority & Multi-Meal Session Resolution**: Creator immediately gains authenticated organizer session cookie (`HttpOnly; Secure; SameSite=Strict; Path=/`) and receives a 256-bit single-use recovery token; frontend maintains a local device registry (`settletable_recent_meals`) in `localStorage` allowing organizers to switch rooms and restore organizer credentials with 1-click without requiring an account database; (5) **Testing & Independent Review**: Test suite expanded by 25 automated tests in `tests/test_public_creation.py` and `tests/test_reverse_proxy_ingress.py`; mobile viewport Headless Chrome E2E suite (`tools/verify_public_creation_flow.mjs`) 100% passed; repository security audit clean (0 findings); independent code and security review approved merge with verdict PASS. Merge commit: PR #67 (`722ec0d`).
- **Completed:** Phase 0 research/skills; feasible Phase 1; revised Phase 2 independent challenge and browser/SQLite probes; Phase 3 calculator and local authority with tests and independent reviews; repository CI (PR #2), namespace refactor (PR #3), integrated invitation/session lifecycle (PR #4), bounded same-origin transport adapter (PR #5), transport-boundary hardening (PR #6), same-origin browser MVP (PR #7), browser MVP E2E defect fixes (PR #8), cross-platform browser test infrastructure with CI automation (PR #9), bounded local OCR pipeline with Malaysian SST parser (PR #10), bounded optional asynchronous Notion reporting pipeline (PR #11), Phase 3 consolidation and operational review (PR #12), User-Acceptance Readiness milestone, Scanned receipt editor UI/UX polish (PR #13), Organizer-authorized allocation & zero-session dining (PR #14), Dual diner invitation methods with general meal join requests (PR #15), General join request abuse hardening (PR #16), Scanned candidate editor Notion polish (PR #17), Staged editor usability refinements (PR #18), Mobile header touch target & compact alert polish, Contextual feedback & viewport notification polish, Bounded Phase 1 atomic item allocation (PR #17), Phase 2 Concept C organizer allocation production integration (PR #18), Concept C preview alignment & "All" shortcut guard (PR #19), Header navigation and toast layout polish (PR #20), Toast placement refinement (PR #21), Focused UAT financial scope, modal accessibility, and conflict recovery (PR #24), Local OCR parser hardening, RapidOCR compatibility, and Notion redirect defense (PR #26), Notion table row schema compliance and export diagnostics (PR #28), Malaysian restaurant receipt OCR corrections (PR #30), OCR fixture privacy sanitization and all-items scope guard (PR #31), Receipt photo retention, interactive zoom modal, and optional Notion photo export (PR #32), Receipt photo reliability hardening, crash consistency, integrity, and Notion in-place upgrade (PR #33), Receipt photo CSP and Chromium UnicodeSets meal ID pattern fixes (PR #34), Browser reload synchronization and receipt DOM readiness hardening (PR #35), Multi-payer contributions & net balance reconciliation (PR #36), Suggested peer transfers, partial reimbursements & settlement tracking (PR #37), Conflict recovery reload context renewal & CI suite expansion (PR #38), Targeted numeric stepper & financial UX clarity refinement (PR #39), Mobile stepper touch target compliance & verification (PR #40), Financial form dropdown chevron polish (PR #41), RM0.00 complimentary items without mandatory allocation (PR #42), Context-aware workflow navigation and focus (PR #43), Suggested peer transfer prefill navigation (PR #44), Mobile UX audit remediation (PR #45), Mobile amount field clipping remediation (PR #46), Low-Cost Mostly-Available MVP Deployment Plan Revision, Stage A Local Reliability & Security Hardening (PR #47), Stage A Post-Merge Corrective Hardening (PR #48), Stage B Offline Hosting Preparation (PR #49), Stage B Operational Runbook Corrections (PR #50), Stage B Final Pre-Activation Reconciliation (PR #51), Stage B Confirmed Domain & Hostname Alignment (PR #52), Stage B Configurable Data Volume for Synthetic Pilot Isolation (PR #53), Stage B2 Controlled Cloudflare Activation & External Verification Pilot (PR #54), Stage C0 Diner Invitation Security Hardening (PR #55), Stage C0 Supervised Browser UAT Acceptance & Security Finalization (PR #56), Stage C1 Restricted Invited-Friends Pilot Preparation (PR #57), Stage C1 Final Safety Corrections (PR #58), Stage C1-A Offline Real-Volume Initialization & Google Drive Encrypted Backup Protocol, Stage C1-B First Real-Meal Pilot & Post-Event Closure, Windows Host Lifecycle Controller & Portfolio README Refresh (PR #59), Lifecycle Controller Reliability Hardening & README Reconciliation (PR #60), Final Lifecycle Controller Verification Safeguards (PR #61), Public Portfolio Showcase & Recruiter Demonstration (PR #62), Public Portfolio Showcase Content Polish (PR #63), Post-Finalization UX & Diner Access Improvements (PR #64), Notion Timeout & Retry Concurrency Safety Hardening (PR #65), Host Lifecycle Controller Execution Policy Resolution (PR #66), and Secure Public Self-Service Meal Creation (PR #67).

## Secure Public Self-Service Meal Creation (PR #67)

- **Separated Ingress Boundary**:
  - Investigated cause of HTTP 403 `forbidden` when using the "Create Meal Room" form at `https://settle.kybuilds.com`. Confirmed backend intentionally restricts `POST /api/meals/{meal_id}/bootstrap` to local loopback and rejects Cloudflare reverse-proxy headers (`CF-Connecting-IP`, `X-Forwarded-For`).
  - Implemented dedicated public creation pathway `POST /api/meals/public-create` in `settletable/public_creation.py` and `settletable/transport.py`, accepting public ingress behind Cloudflare tunnel without weakening administrative bootstrap loopback boundaries.
- **Unguessable Cryptographic Room IDs**:
  - Public creation sanitizes human-entered meal titles into URL-safe slugs and appends 10 random hex characters (40 bits of cryptographic entropy via `secrets.token_hex(5)` = 1.099 trillion combinations), rendering room URLs unguessable.
  - Verifies ID uniqueness transactionally against SQLite before creation.
  - Rejects arbitrary user-supplied custom meal IDs on external requests, permitting custom IDs strictly from unproxied local loopback calls.
- **Multi-Layer Anti-Abuse Defenses**:
  - Server-side kill switch: `SETTLETABLE_PUBLIC_CREATION_ENABLED=0` default fails closed with HTTP 503 `public_creation_disabled`.
  - Cloudflare Turnstile Bot Verification: integrates official Turnstile Siteverify (`https://challenges.cloudflare.com/turnstile/v0/siteverify`) with 5s timeout, SHA-256 token replay prevention cache (300s TTL), and strict action and hostname validation.
  - Content Security Policy (CSP): updated `transport.py` static headers to permit `https://challenges.cloudflare.com` across `script-src`, `frame-src`, and `connect-src`.
  - Sliding-Window IP Rate Limiter: enforces burst (2 in 120s), hourly (5 in 1h), and daily (10 in 24h) limits per client IP (`CF-Connecting-IP` > `X-Forwarded-For` > `REMOTE_ADDR`), with thread-safe lock management and empty scanner record cleanup.
  - Capacity Limits: enforces global cap of 100 meals in SQLite (HTTP 507 `capacity_exceeded`) and max 25 meals created per day.
  - Input Validation & Character Sanitization: limits titles to 60 characters, organizer names to 40 characters, diners to max 20 participants, rejects unicode control characters, and prevents case-insensitive duplicate names.
  - Idempotency & Deduplication: validates `idempotency_key` (max 64 chars, regex `^[A-Za-z0-9_-]+$`); caches completed responses for 10 minutes; bypasses rate limiting for completed retries, ensuring mobile double-taps or network retries succeed with HTTP 201 without 429 errors.
- **Organizer Authority & Multi-Meal Session Resolution**:
  - Sets authenticated organizer session cookie `settletable_session` (`HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=session_ttl`) upon creation.
  - Generates 256-bit emergency recovery URL (`/#/claim-organizer/<token>`) using `secrets.token_urlsafe(32)` stored hashed in SQLite with single-use redemption.
  - Implemented local device registry in frontend `localStorage` (`settletable_recent_meals`), tracking recent meal IDs, titles, and organizer claim links with 1-click room reentry and instant access restoration without an account database.
  - Hardened restore button navigation to hash anchors and same-origin paths.
- **Automated Verification & Review**:
  - 25 automated unit tests in `tests/test_public_creation.py` and `tests/test_reverse_proxy_ingress.py` covering kill switch, turnstile validation, rate limiting, capacity caps, idempotency retries, room squatting defense, CSP, and ingress boundary isolation.
  - Headless Chrome CDP test (`tools/verify_public_creation_flow.mjs`) verified full mobile creation, receipt entry, allocation, invitation issuance, and local storage reentry.
  - Repository security audit clean (0 findings).
  - Independent code and security review evaluated HIGH risk classification and approved merge with verdict PASS. Merged autonomously to `main` via `--no-ff`. Merge commit: `722ec0d`.

## Host Lifecycle Controller Execution Policy Resolution & Companion App Support (PR #66)

- **Execution Policy Resolution**:
  - Replicated root cause where default Windows execution policy (`Restricted`) prevents `tools/SettleTable-Control.ps1` from loading, throwing `PSSecurityException: UnauthorizedAccess` on unconfigured developer hosts.
  - Implemented `tools/SettleTable-Control.cmd` with scoped process bypass (`-NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0SettleTable-Control.ps1" %*`), requiring zero administrator elevation and leaving machine and user registry settings untouched.
  - Added detection for modern PowerShell (`pwsh.exe`) with transparent fallback to built-in `powershell.exe`.
  - Enforced robust path quoting (`"%~dp0SettleTable-Control.ps1"`) for directory paths with spaces, full argument forwarding (`%*`), and deterministic exit code propagation (`exit /b %ERRORLEVEL%`).
- **Interactive PowerShell Experience**:
  - Documented the Microsoft-sanctioned user-scoped policy configuration (`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`) and process-scoped bypass in `tools/SettleTable-Control.ps1` header comment block and `README.md`.
  - Updated fallback usage message in `tools/SettleTable-Control.ps1` to display both `.ps1` and `.cmd` execution options.
- **Companion App & Stream Deck Quick Actions**:
  - Added Quick Actions configuration guide in `README.md` defining command targets (`start-local`, `start-public`, `stop-public`, `stop-all`, `status`) with reliable exit code handling.
- **Automated Test Suite Expansion**:
  - Added 6 new automated tests in `tests/test_settletable_control.py` (total module count: 34 tests; repo total: 396 tests):
    - `test_cmd_launcher_file_exists_and_structure`: static structure and flag verification.
    - `test_cmd_launcher_help_action_exits_zero`: help action verification via `.cmd`.
    - `test_cmd_launcher_invalid_action_exits_one`: unknown action exit code 1 verification.
    - `test_cmd_launcher_status_action_with_mocks`: status probe execution, mock output verification, and token masking assertion.
    - `test_cmd_launcher_resolves_root_from_external_cwd`: external working directory resolution.
    - `test_restricted_execution_policy_resolution`: reproduction of unbypassed restricted policy failure and verified resolution via launcher.
- **Showcase & Metric Alignment**:
  - Reconciled automated test counts to 396 tests across `README.md` and `docs/index.html`.
  - Updated lifecycle controller card in `docs/index.html` to reference both `.ps1` and `.cmd` entry points.
- **Verification & Review**:
  - Independent code, security, and operational review verdict: PASS. Merged autonomously to `main` via `--no-ff`.

## Notion Timeout & Retry Concurrency Hardening (PR #65)

- **Two-Layer Notion Overlap Protection**:
  - Investigated edge case where an asynchronous Notion export exceeds the 75s timeout and the organizer retries while the original background worker is still running. Confirmed two real vulnerabilities in unmitigated concurrent execution: (a) status overwrite defect where a lagging worker failing at second 80 unconditionally wiped `completed` status and `page_id`/`page_url` to `failed`, and (b) duplicate Notion page creation when both workers executed `create_page` against Notion API concurrently.
  - Implemented Layer 1 (In-process thread tracking & double-checked locking in `settletable/transport.py`): tracks `_export_threads` per `(meal_id, finalized_revision)` under `_export_lock`. Fast-path check at request start and double-checked lock immediately before worker thread creation return HTTP 202 `in_progress` if an active thread is running, preventing duplicate thread spawns. Inside `_bg_export()`, completion check exits cleanly if another worker completed the export with the same digest.
  - Implemented Layer 2 (Database-level conditional conflict resolution in `settletable/authority.py`): added `WHERE notion_exports.status != "completed"` to `record_notion_export_failed` and `record_notion_export_in_progress`, ensuring lagging failures can never overwrite a completed export record or blank out Notion URLs.
  - Added targeted concurrency regression tests in `tests/test_notion.py`: `test_record_notion_export_failed_does_not_overwrite_completed_status`, `test_overlapping_async_export_requests_reuse_active_thread_and_prevent_duplicates`, `test_concurrent_post_export_double_checked_lock_prevents_duplicate_workers`, and `test_lagging_worker_after_75s_timeout_cannot_overwrite_completed_retry`.
- **Synthetic Post-Finalization UAT (`tests/test_post_finalization_uat.py`)**:
  - Implemented isolated automated test suite verifying all post-finalization behaviors:
    - Receipt photo sharing toggle: organizer enables (200), diners view shared photo (200), organizer disables (200), diners blocked (403), unauthenticated blocked (401), non-organizer cannot toggle (403).
    - Diner funding and balance accuracy: verified exact mathematical balances across underfunded (3850 sen unfunded), funded by organizer Alice (0 sen unfunded, Bob owes 1100), and settled (Bob owes 0, Charlie owes 2200).
    - Non-organizer mutations strictly forbidden: rejected `RecordContribution`, `ReverseContribution`, `RecordTransfer`, and `ReverseTransfer` with `forbidden` (403).
    - Notion export privacy: organizer receives private `page_id` and `page_url`; diner receives status `completed` with private URL strictly omitted; organizer registers view-only public link (`https://notion.site/*`), diner views public URL; non-organizer cannot modify public URL; organizer clears public link.
    - Cross-meal boundary enforcement: cross-meal diner David is blocked from accessing Meal 1 receipt photo, sharing settings, Notion export status, and public link (401/403).
- **Historical SQLite Schema Upgrade Verification**:
  - Created isolated SQLite database with pre-PR #64 schema (omitting `public_url` in `notion_exports` and `share_with_diners` in `receipt_photos`).
  - Populated pre-existing finalized meal, receipt photo blob, and completed Notion export.
  - Instantiated `Authority`: verified automatic schema upgrade via `PRAGMA table_info`, zero data loss, default `share_with_diners = 0`, and full backwards-compatibility.
- **Real-Data Deployment Readiness Procedure**:
  - Verified Docker Compose image caching semantics: controller startup (`start-local` / `start-public`) does NOT rebuild changed code automatically.
  - Documented explicit image build, pre-upgrade encrypted Google Drive backup, pre-flight volume verification, and atomic rollback plan.
- **Independent Senior Review**:
  - Review identified Finding SEC-01 (TOCTOU in thread tracking). Resolved via double-checked locking in commit `0ea1cfe`.
  - Updated review verdict: **APPROVE**. Full test suite: 390 tests passing. Merged to `main` via `--no-ff`. Merge commit: `8c5aeb9`.

## Post-Finalization UX & Diner Access Improvements (PR #64)

- **Notion Export Reliability & Diner Visibility**:
  - Implemented persistent export status and report URL preservation across snapshot polling, UI updates, and session reloads.
  - Formatted prominent "Open Report in Notion ↗" call-to-action button, collapsing the full parent ID and token configuration form into `<details>` once archived.
  - Aligned backend export timeout to 75.0s and frontend polling to 70s, ensuring reliable status convergence and preventing unintended duplicate exports.
  - Automatically resumes observation of `in_progress` exports upon browser reload or session restoration without premature timer cancellation.
  - Added diner-visible Notion archive indicator, strictly withholding integration tokens, credentials, and private Notion workspace URLs.
  - Authorized organizer to register a view-only published Notion web link (`https://*.notion.site/*` or `https://*.notion.so/*`), validating HTTPS scheme, domain constraints, and max 512 character length.
- **Authoritative Ledger & Diner Settlement Clarity**:
  - Maintained organizer-attested financial ledger integrity: diners are strictly prohibited from mutating cashier contributions or peer transfers (`RecordContribution`, `ReverseContribution`, `RecordTransfer`, `ReverseTransfer` return 403 `forbidden`).
  - Added personalized diner outstanding balance banner showing clear individual obligations (owing, owed, settled, or unfunded restaurant blocker).
  - Reused existing suggested transfer apportionment without creating synthetic debtors or creditors.
  - Added role notices explaining that diners should notify the organizer after paying externally so the organizer can attest the record.
- **Organizer-Controlled Receipt Photo Sharing**:
  - Sharing defaults to disabled (`share_with_diners = 0`), including backwards-compatible defaults for existing finalized meals.
  - Organizer can explicitly toggle sharing post-finalization with a prominent merchant receipt privacy warning.
  - Authenticated active meal participants receive read-only access to `GET /api/meals/{meal_id}/receipt/photo` when enabled.
  - Diners cannot access photos before finalization and never gain upload, replacement, or deletion permissions.
  - Unauthenticated, inactive, revoked, and cross-meal sessions strictly blocked (401 / 403).
  - Stored in `receipt_photos.share_with_diners`, preserving 100% financial calculation immutability, revision counts, and finalized revision hashes.
- **Quality, Security & Verification**:
  - Full automated Python test suite expanded to 384 tests (`Ran 384 tests in 119.3s, OK`), covering all sharing states, token privacy, diner forbidden mutations, timeout semantics, and financial invariance.
  - Headless Chrome CDP tests passed with 100% success (`tools/verify_receipt_photo_flow.mjs`, `tools/verify_peer_settlement_flow.mjs`, and `tools/e2e_browser_test.mjs`).
  - Repository security audit clean (`tools/audit_repository.py` reported 0 findings).
  - Independent Senior Code & Security Review evaluated HIGH risk classification and approved merge; Finding M-01 resolved and verified prior to merge. Reviewed head: `649a7a3`. Merged to `main` via `--no-ff`.


## Public Portfolio Showcase Content Polish (PR #63)

- **Mathematical Formula Rendering (`docs/index.html`, `docs/assets/style.css`)**:
  - Replaced unrendered raw LaTeX notation (`$$\text{Net Balance}...$$` and `$\sum...$`) with an accessible, semantic HTML element (`.formula-box` with `role="math"` and descriptive `aria-label`).
  - Utilized clean Unicode mathematical entities (`&minus;` for subtraction and `&sum;` for summation).
  - Explicitly specified the domain condition under which net balances conserve to zero: *"When the cashier bill is fully funded (total paid equals receipt total), largest-remainder apportionment guarantees that the sum of all individual net balances is exactly RM0.00 (&sum; Net Balances = RM0.00), with zero floating-point penny drift."*
  - Verified zero external runtime libraries (e.g., MathJax, KaTeX) introduced; zero raw LaTeX remains in the showcase.
- **Technical Terminology Precision**:
  - Replaced "Air-Gapped Optical Recognition" with "Server-Side Offline Receipt OCR", correctly reflecting local CPU execution with RapidOCR ONNX while acknowledging host internet connectivity via Cloudflare tunnel.
  - Corrected session cookie description to specify an authenticated `HttpOnly; Secure; SameSite=Strict` cookie transmitted over TLS and validated against SHA-256 verifiers on the server, removing inaccurate claims of application-layer cookie encryption.
  - Replaced "Greedy Minimum-Transfer Heuristic" with "Greedy Settlement Suggestions" to avoid unproven claims of transfer sequence minimality.
- **Recruiter-Facing Hero Section**:
  - Updated page title and hero headline to *"Restaurant Bill Splitting Engineered for Mathematical Precision"*.
  - Refined subtitle to immediately communicate the core value proposition (self-hosted expense engine, offline OCR, zero-install mobile guest collaboration, and exact cent-conserving financial apportionment) to technical recruiters and engineering managers alike.
- **Quality & Verification**:
  - Validated HTML5 tag nesting and CSS syntax with zero errors.
  - Confirmed all 7 demo assets load correctly.
  - Clean repository security audit (0 findings).
  - Full test suite passed locally (371/371 tests).
  - Independent review verdict: PASS. Reviewed head: `0279699`.

## Public Portfolio Showcase & Recruiter Demonstration (PR #62)

- **Public Repository Visibility Reconciliation**:
  - Reconciled `README.md`, `docs/uat-handover.md`, and project governance records to reflect that `KAIYI7/settle-table` is now public on GitHub for technical portfolio evaluation by Product Owner decision.
  - Verified anonymous unauthenticated access to the repository (`https://github.com/KAIYI7/settle-table` returning HTTP 200 OK).
  - Preserved All Rights Reserved copyright and stated zero open-source redistribution or licensing grant is authorized.
- **Repository Security & Confidentiality Audit**:
  - Executed heuristic and content audits across all 342 tracked files and full Git commit history (`scratch/scan_repo_secrets.py`, `scratch/audit_tracked_files.py`, and `tools/audit_repository.py`).
  - Confirmed 0 exposed credentials, tokens, private keys, passwords, or real dining data.
- **Recruiter Demonstration Walkthrough Assets**:
  - Automated Chrome CDP capture suite (`tools/capture_recruiter_demo.mjs`) ran against an isolated Docker container executing real RapidOCR ONNX inference and the full application stack.
  - Captured 6 authentic walkthrough stages:
    1. `01-room-setup.png`: Organizer Room Setup & Ingress Boundary.
    2. `02-candidate-review.png`: Server-Side Offline OCR & Malaysian Candidate Review.
    3. `03-portion-allocation.png`: Granular Portion Allocation with Rational Fractions.
    4. `04-mobile-diner-view.png`: Zero-Install Mobile Diner Interaction via URL Fragment Token.
    5. `05-payer-reconciliation.png`: Multi-Payer Cashier Reconciliation & Exact Net Balances.
    6. `06-peer-settlement.png`: Suggested Peer Settlement Transfers & Repayment Tracking.
  - Generated animated walkthrough overview `docs/assets/demo/walkthrough.gif` via containerized PIL.
  - 100% synthetic fixtures used; zero contact with production volume `settletable_data`.
- **Always-Accessible Public Showcase (`https://kaiyi7.github.io/settle-table/`)**:
  - Built fast, responsive, zero-framework static showcase at `docs/index.html` with `docs/assets/style.css` and `.nojekyll`.
  - Added GitHub Actions Pages deployment workflow (`.github/workflows/pages.yml`).
  - Highlights core problem, value proposition, authentic visual walkthrough, backend engineering achievements, architecture topology, and verified testing evidence.
- **Portfolio README Experience Refresh (`README.md`)**:
  - Added prominent showcase, repository, and live deployment links at top of README.
  - Embedded animated walkthrough GIF and 6 authentic walkthrough screenshots.
  - Reconciled test suite count to 371 passing tests.
  - Disclosed on-demand hosting status (HTTP 530 / Error 1033 when host connector is offline).
- **Independent PR Review Verdict: PASS**:
  - Independent code, security, and documentation review confirmed verdict PASS.
  - All 371 tests pass locally and in GitHub Actions CI. Merged autonomously to `main` via `--no-ff`.

## Final Lifecycle Controller Verification Safeguards (PR #61)

- **Docker Query Verification Contract (`tools/SettleTable-Control.ps1`)**:
  - `Get-RunningContainerIds` refactored to return structured result (`Success`, `Error`, `Ids`).
  - `stop-public`, `stop-all`, and `start-local` fail closed if `docker ps` query fails rather than treating query failure as proof of zero running containers.
- **Production Preflight Protection**:
  - Ambient environment variable bypasses removed.
  - `-SkipPreflight` and `-PreflightCmd` strictly prohibited against production Docker (`$DockerCmd -eq "docker"`), preventing accidental volume check bypasses in live operations.
- **Partial Public-Activation Rollback Verification**:
  - Active rollback verification on both local health check failure and public edge HTTPS probe failure.
  - Reports critical diagnostics if tunnel container cannot be confirmed inactive.
- **Automated Mock Test Suite (`tests/test_settletable_control.py`)**:
  - Expanded to 28 automated tests covering failed `docker ps` queries after stop commands, initial docker query failures, and production rejection of test-only flags.
  - All 371 tests pass locally and in GitHub Actions CI (`ALL_CI_SUCCESS`).
- **Independent PR Review Verdict: PASS**:
  - Subagent review verified query contract, fail-closed guards, preflight restrictions, and rollback reporting.
  - Merged autonomously to `main`.

## Lifecycle Controller Reliability Hardening & README Reconciliation (PR #60)

- **PowerShell Lifecycle Controller Hardening (`tools/SettleTable-Control.ps1`)**:
  - **Docker Exit Code Checks & Container Verification**: `stop-public` and `stop-all` capture command output, verify `$LASTEXITCODE -eq 0`, and query `Get-RunningContainerIds` to confirm that `settletable_tunnel` and `settletable_app` have actually stopped.
  - **Pre-Emptive Tunnel Shutdown**: `start-local` stops the Cloudflare tunnel and confirms it is inactive *before* performing volume pre-flight checks and starting the application, with a final fail-closed guard preventing accidental exposure.
  - **Health Enforcement & Tunnel Rollback**: `start-public` enforces local container health (`/healthz` returning 200 OK) before verifying public edge connectivity. If local health fails, it immediately rolls back and stops the tunnel connector.
  - **Edge Status Differentiation**: Distinguishes local container deactivation from edge status codes (HTTP 530 Tunnel Inactive, 000 Unreachable, 200 In-flight/Cached).
  - **Pipeline Stream Purity**: External command stdout is captured locally or redirected, keeping the PowerShell return pipeline clean and ensuring exact boolean return evaluations and non-zero script exit codes.
  - **Test Isolation**: Added `-PreflightCmd` and `-SkipPreflight` (supporting `SETTLETABLE_SKIP_VOLUME_PREFLIGHT=1` and `SETTLETABLE_SKIP_PREFLIGHT=1`) for hermetic mock execution without host volume requirements.
- **Portfolio README Reconciliation (`README.md`)**:
  - Replaced "Air-Gapped Receipt OCR" with "Server-Side Offline Receipt OCR".
  - Replaced claim of minimal transfer sequence with "Heuristically computes suggested reimbursement transfers to reduce transaction overhead".
  - Clarified private repository status and authorized collaborator access.
- **Hermetic Automated Test Coverage (`tests/test_settletable_control.py`)**:
  - Expanded from 6 to 23 comprehensive unit tests using mocked Docker, Curl, and Preflight scripts.
  - Covers daemon down, stop failures, lingering containers, health probe timeouts, public tunnel rollback, edge probe failures, preflight failures, invalid actions, and secret protection.
  - All 366 tests pass locally and in GitHub Actions CI.
- **Independent PR Review Verdict: PASS**:
  - Subagent review verified exit code propagation, fail-closed guards, hermetic tests, and security boundaries.
  - CI verified on exact head SHA (`f4ab520`): `docker-smoke` and `tests` both succeeded. Merged autonomously to `main`.

## Windows Host Lifecycle Controller & Portfolio README Refresh (PR #59)

- **Portfolio-Oriented README Refresh (`README.md`)**:
  - Communicates SettleTable as a tested, functional, self-hosted dining expense management MVP.
  - Documents verified deployment architecture: Python 3.14 WSGI, SQLite WAL, RapidOCR ONNX, Cloudflare Named Tunnel (`https://settle.kybuilds.com`).
  - Explicitly documents on-demand hosting model and HTTP 530 / Error 1033 tunnel offline status when host connector is stopped.
  - Highlights real technical achievements: cent conservation (`tabwise-apportion-v1`), air-gapped local OCR, fragment diner invitations (`/#/invite/<token>`), multi-payer reconciliation, greedy peer settlements, and 7-Zip AES-256 encrypted Google Drive backups.
  - Reconciled test counts to 349 automated tests and 13/13 deployment smoke checks.
  - Verified tracked synthetic screenshot fixtures; ensured private repository and All Rights Reserved copyright preservation.
- **Windows Host Lifecycle Controller (`tools/SettleTable-Control.ps1`)**:
  - Practical PowerShell controller supporting both interactive menu and non-interactive CLI automation.
  - `start-local`: Launches local container (127.0.0.1:8000), stops Cloudflare tunnel, and verifies local `/healthz` probe.
  - `start-public`: Verifies real volume pre-flight (`--mode real`), starts application and Cloudflare tunnel, verifies local and edge HTTPS (`https://settle.kybuilds.com/healthz`), and displays public URL.
  - `stop-public`: Stops Cloudflare connector while keeping local app accessible.
  - `stop-all`: Stops application and tunnel cleanly, preserving all Docker volumes and SQLite records, with backup reminder.
  - `status`: Displays container states, local health probe, public edge status, and volume target without printing secrets.
  - Paths resolved relative to script root (`$PSScriptRoot`); supports execution from any working directory.
- **Automated Test Coverage (`tests/test_settletable_control.py`)**:
  - 6 tests verifying script presence, help flags, invalid command handling, status reporting, secret redaction, and external directory execution.
  - All 349 tests pass locally and in GitHub Actions CI. Independent review verdict: PASS. Merged autonomously to `main`.

## Stage C1-B: First Real-Meal Pilot & Post-Event Closure

- **Product Owner Real-World UAT Verdict: PASS (Owner-Observed Evidence)**:
  - Organizer meal bootstrap executed on Windows host terminal; single-use setup link activated in browser.
  - Paper restaurant receipt uploaded, RapidOCR line item extraction verified, Malaysian SST/service charge confirmed.
  - Fragment-based diner invitation links distributed to diners via private chat (`/#/invite/<token>`).
  - Diners accessed the room from separate physical devices, redeemed invitations, claimed item portions, and confirmed real-time balance calculations.
  - Performance and responsiveness acceptable; tested functionality worked correctly.
- **Production Data Verification & Application Quiescence**:
  - Running stack verified mounted to `settletable_data` with `.volume_identity = settletable_data`.
  - Authoritative records verified intact: 1 meal, 4 participants, 4 sessions, 3 invitations, 1 organizer claim, 16 command events, 1 payer contribution, 2 peer transfers, and 1 receipt photo.
  - Zero private credentials, attendee names, receipt contents, or financial amounts logged or exposed in transcripts.
  - Application cleanly quiesced (`docker compose stop settletable`) to guarantee zero in-flight modifications.
- **Consistent Snapshot & Verification**:
  - Snapshot generated at `20261108_123746Z` via disposable container mounting `settletable_data`.
  - Manifest (`manifest_20261108_123746Z.json`), database (`settletable_20261108_123746Z.sqlite`, 180,224 bytes), and photo directory (`receipt_photos_20261108_123746Z/`, 1 file) verified.
  - SQLite `PRAGMA integrity_check;` returned `ok`; bit-for-bit SHA-256 match on database and photo assets.
- **AES-256 Header-Encrypted 7-Zip Archive**:
  - Encrypted archive created: `settletable_backup_20261108_123746Z.7z` (855,088 bytes) with LZMA2 + AES-256 header encryption (`-mhe=on`).
  - Passphrase entered directly by Product Owner via interactive console prompt; zero password exposure in arguments or logs.
  - Header encryption verified: archive fails closed when inspected without passphrase.
  - Archive integrity verified via `7z t` (`Everything is Ok`).
  - Explaining Windows 11 Explorer: built-in Compressed Folder viewer does not support encrypted 7z; 7-Zip File Manager and CLI handle decryption correctly.
- **Google Drive Cloud Durability Verification**:
  - Archive copied to Google Drive (`<GDRIVE_BACKUPS_DIR>`) with `Copy-Item -ErrorAction Stop`.
  - Bit-for-bit SHA-256 parity confirmed (`71673E47D3B85647FED4E76AA71FF5DEB36FA8B06CE66F0410C2425529F705AE`).
  - Google DriveFS metadata verified: permanent cloud resource ID assigned (`12VUc8etjr4Y1vJmnZNIDowf6qj9nq8L_`), operations queue count 0, cloud durability confirmed.
- **Public Ingress Shutdown & Volume Preservation**:
  - Cloudflare tunnel stopped (`docker compose stop cloudflared`).
  - Proved closure: `curl -i https://settle.kybuilds.com/healthz` returns `HTTP/1.1 530 error code: 1033`. Zero containers running.
  - Both `settletable_data` and `settletable_synthetic_data` Docker volumes safely preserved.
- **Recommendation for Subsequent Mostly-Available Operation**:
  - Supervised on-demand pilot succeeded with zero defects.
  - When Product Owner is ready for mostly-available operation, the stack is already configured with `restart: unless-stopped`.
  - Regular post-gathering quiescent snapshots and 7-Zip encrypted Google Drive uploads should continue as standard operating procedure.

## Stage C1-A: Offline Real-Volume Initialization & Google Drive Encrypted Backup Protocol

- **Offline Real-Volume Initialization & Validation**:
  - `SETTLETABLE_DATA_VOLUME=settletable_data` explicitly configured in `.env` and verified via `tools/verify_volume_target.py --mode real`.
  - Database schema initialized offline (`tools/bootstrap_meal.py init-db`) creating clean SQLite database and `.volume_identity` marker (`settletable_data`).
  - Baseline quiescent backup executed and synced to Google Drive (`<GDRIVE_BACKUPS_DIR>`) with permanent cloud resource IDs assigned.
  - Production volume `settletable_data` remains completely unmounted, empty (0 meals, 0 receipts), and isolated from public ingress.
- **Encrypted Backup & Recovery Protocol (7-Zip AES-256 + Google Drive)**:
  - Documented strict single-snapshot scoping (`manifest_${timestamp}.json`, `settletable_${timestamp}.sqlite`, `receipt_photos_${timestamp}`).
  - Standardized 7-Zip CLI arguments (`7z a [switches] <archive> <inputs>`) with AES-256 encryption and header encryption (`-mhe=on`).
  - Documented PowerShell Docker bind-mount variable interpolation wrapping (`"${decryptedDir}:/backups"` and `"${hostBackupDir}:/backups"`).
  - Added exit-code validation (`if ($LASTEXITCODE -ne 0) { throw ... }`) across backup generation, archive creation, archive integrity testing, and disaster recovery restoration.
  - Formally differentiated local DriveFS cache writing (transient `local-*` ID) from verified remote cloud durability (0 pending operations, permanent cloud resource ID, and taskbar notification "Everything is up to date").
  - Executed end-to-end synthetic verification drill validating encryption, password prompting, archive testing, Google Drive upload, decryption, and restore verification with bit-for-bit SHA-256 matching.
- **Repository Health & Readiness**:
  - All 343 unit, calculation, and security tests pass locally.
  - Zero repository audit findings (`tools/audit_repository.py --stage`).
  - Public ingress remains offline (HTTP 530 / Error 1033). Ready for Product Owner real-data pilot authorization.

## Stage C1: Final Safety Corrections (PR #58)

- **Fail-Closed Volume Pre-Flight (`tools/verify_volume_target.py`)**:
  - Mode `real` strictly asserts `SETTLETABLE_DATA_VOLUME=settletable_data`.
  - Mode `synthetic` strictly asserts `SETTLETABLE_DATA_VOLUME=settletable_synthetic_data`.
  - Custom or unexpected volumes fall through to failure (exit code 1) instead of permissive pass.
  - Conflict between `.env` and Docker Compose service resolution is actively detected and aborted.
  - Actively validates in-container storage ownership (`UID=10001, GID=10001`) and write permissions on `/data` and `/data/receipt_photos` without mutating existing data.
  - Added comprehensive negative and positive unit tests in `tests/test_verify_volume_target.py` (8/8 tests passing).
- **Volume Identity Marker Integrity Guard (`settletable/wsgi.py`)**:
  - Detects existing datasets (database file exists or photos exist) missing `.volume_identity` and fails closed (`RuntimeError`) instead of silently ignoring.
  - Malformed or unreadable (`OSError`, `JSONDecodeError`) identity markers raise `RuntimeError` rather than bypassing checks.
  - Missing or blank `volume_name` in marker JSON raises `RuntimeError`.
  - Genuinely fresh volumes initialize `.volume_identity` safely via atomic file replacement (`.volume_identity.tmp.<uuid>` -> `.volume_identity`).
  - Added 6 new unit tests in `tests/test_wsgi_volume_guard.py` (11/11 tests passing).
- **Pristine Database Schema Initialization (`tools/bootstrap_meal.py init-db`)**:
  - Added `init-db` subcommand to safely initialize `settletable.sqlite` and WAL mode on pristine volumes in an isolated local container without public ingress.
  - Verified initialization, marker creation, baseline backup, and disaster recovery restoration in isolated Docker drill.
- **Operational Runbook & Storage Security (`docs/runbooks/windows_host_operations.md`)**:
  - Documented pristine DB initialization in Section 6 and Section 9 (Pre-Flight checklist).
  - Clarified distinction between local offsite copy completion and asynchronous cloud sync durability (OneDrive/Google Drive sync status).
  - Documented confidentiality protections for real receipts and financial data: NTFS ACLs, BitLocker drive encryption, and cloud storage MFA/2FA.
- **Test Suite**:
  - All 343 unit, calculation, and security tests pass locally. Primary volume `settletable_data` remains completely unmounted and empty.

## Stage C1: Restricted Invited-Friends Pilot Preparation (PR #57)

- **Operational Lifecycle Documented**:
  - Two-phase lifecycle established: (1) Supervised, on-demand activation for the inaugural live meal; (2) Transition to mostly-available background operation with `restart: unless-stopped` and Docker Desktop auto-start.
  - Windows host downtime resilience documented: SQLite WAL crash consistency, 7-day session TTLs, and automatic Cloudflare Tunnel reconnection without session loss or data corruption.
- **Storage Volume Isolation & In-Container Contamination Defense**:
  - Verified `settletable_data` storage ownership (`UID=10001 GID=10001`) and non-root read/write/delete permissions.
  - Added in-container volume identity marker guard (`/data/.volume_identity` in `settletable/wsgi.py`): container startup immediately aborts if mounted volume marker does not match `SETTLETABLE_DATA_VOLUME`, permanently preventing accidental cross-volume contamination.
  - Implemented pre-flight volume verification utility (`tools/verify_volume_target.py`) with `--mode real`, `--mode synthetic`, and `--mode auto` assertions.
- **Off-Host Quiescent Backup & Verified Disaster Recovery**:
  - Enhanced `tools/backup_restore.py` with `--copy-to` / `--offsite-dir` to create verified backup copies on secondary drives or cloud-synced folders (`OneDrive`).
  - Updated isolated Docker drill (`tools/verify_isolated_docker_drill.py`) to verify backup, secondary offsite copy, and disaster recovery restoration directly from offsite storage without touching production volumes.
- **Live HTTPS Retest of PR #56 Invariants**:
  - Verified PR #56 fragment-based invitation workflow over live HTTPS (`https://settle.kybuilds.com`): organizer setup via clean body, diner invitation inspection via `POST /api/invitations/inspect`, redemption via `POST /api/meals/{meal_id}/invitations/redeem`, diner snapshot access, 400 rejection on consumed invitation replay, and 403 rejection on diner administrative attempts.
  - Public ingress immediately stopped and verified deactivated (`HTTP 530 / Error 1033`). All test tokens verified consumed or revoked.
- **Stage C1 Executable Checklist**:
  - Documented 11-step executable operational checklist in `docs/runbooks/windows_host_operations.md` covering pre-flight volume verification, meal bootstrap, receipt photo capture, RapidOCR confirmation, fragment invitation sharing via private chats, and post-event offsite backup.
- **Test Coverage**:
  - All 328 unit, calculation, and security tests pass locally.

## Stage C0: Supervised Browser UAT Acceptance & Security Finalization (PR #56)

- **Product Owner Supervised UAT Verdict: PASS**:
  - Tested across Windows desktop browser (Chrome/Edge) and physical mobile phone over cellular mobile data.
  - Verified organizer session activation, receipt ingestion, RapidOCR, verification, item assignment, mobile diner invitation redemption without Cloudflare Access, diner portion claims, financial calculation, session persistence on reload, and role restrictions.
  - Performance acceptable; zero functional or usability defects observed.
- **Immediate Public Ingress Deactivation Verified**:
  - Public Cloudflare connector stopped immediately (`docker compose stop cloudflared`).
  - Proved closure: `curl -i https://settle.kybuilds.com/healthz` returns `HTTP/1.1 530 error code: 1033`. Zero containers running.
  - Cloudflare tunnel definition, DNS route (`settle.kybuilds.com`), and synthetic data volume preserved.
- **Credential Review & Volume Protection**:
  - All synthetic test claims and invitations in `settletable_synthetic_data` verified consumed or revoked (0 active/unconsumed tokens in SQLite).
  - Primary application volume `settletable_data` remained completely untouched, empty, and unmounted throughout testing.
- **Strict Body Token Security Invariant (Eliminated URL Token Fallback)**:
  - Removed client fallback in `settletable/static/app.js` that previously fell back to token-in-URL requests on network/HTTP errors.
  - Browser client strictly uses JSON-body endpoints (`/api/invitations/inspect`, `/api/meals/{meal_id}/invitations/redeem`, `/api/organizer-claims/inspect`, `/api/meals/{meal_id}/organizer-claims/claim`) without ever degrading to unshielded URL paths.
  - Added regression test `test_browser_assets_do_not_contain_url_token_fallbacks` in `tests/test_transport.py` (322/322 tests passing).
  - Legacy server endpoint compatibility in `settletable/transport.py` preserved for external callers.

## Stage C0: Diner Invitation Security Hardening & Supervised Browser UAT Preparation (PR #55)

- **Focused Security Investigation on Invitation Tokens**:
  - Investigated diner invitation token exposure through Cloudflare edge, upstream reverse proxy access logs, and browser navigation.
  - Distinguished potential exposure from verified leakage: zero leakage occurred during Stage B2 testing; however, HTTP path tokens (`/invite/{token}`, `GET /api/invitations/{token}`, `POST /api/meals/{meal_id}/invitations/{token}/redeem`) could be logged in plain text by intermediate CDNs or access logs prior to redemption.
- **Privacy & Ingress Hardening Implemented**:
  - **Fragment-Based Invitation Links**: Switched generated invitation links in the UI and CLI to `/#/invite/{token}`. The token is confined to the client-side URL hash and never transmitted across HTTP request lines.
  - **Clean JSON-Body Inspection**: Added `POST /api/invitations/inspect` accepting `{"invitation_token": token}` in JSON body; treated as unauthenticated read-only query without CSRF requirements.
  - **Clean JSON-Body Redemption**: Added `POST /api/meals/{meal_id}/invitations/redeem` accepting `{"invitation_token": token}` in JSON body with CSRF Origin and `X-SettleTable-Action: 1` verification.
  - **100% Backward Compatibility**: Maintained existing `/invite/{token}` HTML shell serving, `GET /api/invitations/{token}` legacy inspection, and `POST /api/meals/{meal_id}/invitations/{token}/redeem` legacy redemption.
  - **Logging Redaction**: Enhanced `redact_log_string` to redact `invitation_token` in JSON payloads and `/redeem` in URL paths.
- **Verification & Test Coverage**:
  - 321/321 unit and integration tests passing (`tests/test_transport.py`, `tests/test_browser_mvp_e2e.py`).
  - Added Checks 12 and 13 to `tools/deployment_smoke_check.py` (13/13 passing).
  - Production Docker image `settletable:latest` rebuilt with updated code.

## Stage B2: Controlled Cloudflare Activation & External Verification Pilot (PR #54)

- **Authorized External Activation Conducted**:
  - Remotely-managed Cloudflare Named Tunnel `settletable-pilot` connected from Windows host container (`cloudflare/cloudflared:2026.10.7@sha256:4955524aeaa379e154023d5a027c250f7b35041a2e7e950cf13f144bc9b9c5ba`).
  - Target public endpoint: `https://settle.kybuilds.com`.
  - Service resolution: `http://settletable:8000` via Compose bridge network.
- **Volume & Data Isolation Enforced**:
  - Synthetic pilot executed against isolated Docker volume `settletable_synthetic_data` (PR #53).
  - Primary application volume `settletable_data` remained completely untouched, empty, and unmounted.
- **Full External Verification Invariants Passed (18/18)**:
  1. Edge TLS handshake & healthcheck (`cf-ray: SIN`, `server: cloudflare`): PASS (200).
  2. Browser HTML shell without Cloudflare Access login barrier: PASS (200).
  3. Unauthenticated meal snapshot denial: PASS (401 `invalid_session`).
  4. Unauthenticated receipt photo download denial: PASS (401 `invalid_session`).
  5. Public `/bootstrap` attempt blocked by proxy header defense: PASS (403 `forbidden`).
  6. Mutating POST with foreign `Origin` rejected: PASS (403 `origin_mismatch`).
  7. Mutating POST missing `X-SettleTable-Action: 1` rejected: PASS (400 `missing_action_header`).
  8. Organizer claim inspection via clean POST: PASS (200, `valid=True`, `meal_id='synthetic-pilot-20261107'`).
  9. Organizer claim redemption & session cookie acquisition (`settletable_session`, `HttpOnly`, `SameSite=Strict`): PASS (200).
  10. Replay attack on consumed claim token rejected: PASS (409 `organizer_claim_consumed`).
  11. Authenticated organizer fetches snapshot (`is_organizer=True`, `Cache-Control: no-store`): PASS (200).
  12. Organizer issues diner invitation token for `D1`: PASS (201).
  13. Diner redeems invitation token & acquires isolated guest session: PASS (200).
  14. Diner fetches snapshot with isolated guest permissions (`is_organizer=False`): PASS (200).
  15. Diner denied organizer administrative actions: PASS (403 `forbidden`).
  16. Real RapidOCR extraction inside production container on synthetic receipt (`tests/fixtures/ocr/images/synthetic_clear.png`): PASS (200, extracted 2 items, candidate total and photo metadata returned).
  17. Receipt photo download & caching invariants (`image/png`, `private, no-cache, no-store, must-revalidate`, `cf-cache-status: DYNAMIC`): PASS (200).
  18. Guest diner denied receipt photo download: PASS (403 `forbidden`).
- **Smoke Check Browser User-Agent Compatibility**:
  - `tools/deployment_smoke_check.py` updated with standard browser User-Agent to avoid Cloudflare Error 1010 during automated diagnostics. 11/11 smoke checks pass locally and through Cloudflare edge.
- **Restart & Recovery Verified**:
  - Tunnel connector restarted (`docker compose restart cloudflared`): reconnected instantly, 11/11 smoke checks pass.
  - Application container restarted (`docker compose restart settletable`): session persisted, 11/11 smoke checks pass.
- **Clean Public Deactivation Enforced**:
  - Tunnel connector stopped (`docker compose stop cloudflared`).
  - Proved immediate closure of public ingress: `curl -i https://settle.kybuilds.com/healthz` immediately returns `HTTP 530 error code: 1033` (Cloudflare tunnel disconnected).
  - All local containers cleanly shut down (`docker compose down`).
  - Zero raw secrets or claim tokens logged or leaked.

## Confirmed Domain Decision: kybuilds.com & Target Hostname: settle.kybuilds.com

- **Confirmed Domain Purchase & Registration**:
  - Product Owner confirmed purchase and registration of `kybuilds.com` through Cloudflare Registrar.
  - Final confirmed public HTTPS endpoint: `https://settle.kybuilds.com`.
  - Step 1 of Pre-Activation Checklist in `docs/plans/MVP_RELEASE_AND_DEPLOYMENT.md` marked `[CONFIRMED / COMPLETED]`.
- **Configuration Templates & Operational Runbook Aligned**:
  - Updated `deploy/env.template`:
    - `SETTLETABLE_SERVER_ORIGIN=https://settle.kybuilds.com`
    - `SETTLETABLE_ALLOWED_HOSTS=settle.kybuilds.com,127.0.0.1:8000,localhost:8000,settletable:8000`
  - Updated `deploy/cloudflare/README.md` and `deploy/cloudflare/config.template.yml` to target `settle.kybuilds.com`.
  - Updated `docs/runbooks/windows_host_operations.md` operational commands and smoke tests to target `https://settle.kybuilds.com`.
- **Synthetic Ingress Verification Against Confirmed Hostname**:
  - Updated `tests/test_reverse_proxy_ingress.py` test fixture to use `https://settle.kybuilds.com` and `settle.kybuilds.com`.
  - All 9 synthetic ingress security tests passing: Host header validation, exact-origin CSRF mitigation, Cloudflare header forwarding, proxy loopback bootstrap blocking, and deny-by-default on unmatched hostnames (`kybuilds.com`, subdomains, external IPs).
- **Strict Operational Hold Maintained**:
  - Zero external tunnels created or activated.
  - Zero DNS records modified in Cloudflare.
  - Zero public tests initiated.
  - Live external activation strictly deferred pending explicit Product Owner authorization.

## Accepted Stage B final pre-activation reconciliation checkpoint

- **Production Volume Isolation Proved Without Touching Primary Volume**:
  - Refactored `tools/verify_isolated_docker_drill.py` to completely eliminate mounting or accessing `settletable_data`.
  - Audited all recorded Docker command invocations to ensure `settletable_data` was never referenced.
  - Verified destination volume contains zero existing user files prior to restore.
  - Verified destination volume strict containment and isolation post-restore (contains strictly and only `settletable.sqlite` and `receipt_photos/<filename>`).
  - Proved volume independence via `docker volume inspect`.
- **Image Reproducibility via Cryptographic Digest Pinning**:
  - Pinned `cloudflare/cloudflared:2026.10.7@sha256:4955524aeaa379e154023d5a027c250f7b35041a2e7e950cf13f144bc9b9c5ba` in `docker-compose.yml`.
  - Digest corresponds to multi-arch manifest list covering both `linux/amd64` and `linux/arm64`, guaranteeing byte-for-byte immutability across platforms.
- **Request-Size Documentation Reconciled**:
  - Reconciled documentation with actual constants in `settletable/transport.py`: JSON API payloads capped at `MAX_BODY_BYTES` (1 MB / 1,048,576 bytes); binary receipt photos and OCR extraction capped at `MAX_IMAGE_BYTES` (5 MB / 5,242,880 bytes).
- **Public Reachability Semantics Clarified**:
  - Clarified Gate 2 vs Gate 3: Gate 2 (`v0.9.0-beta.1`) achieves **public network reachability** via Cloudflare Named Tunnel without Cloudflare Access, while native organizer claim tokens and guest invitation links protect individual meals, and public `/bootstrap` is denied.
  - Gate 3 represents **unrestricted public product access & multi-tenant identity** (open signups, persistent user accounts, public discovery), which remains deferred pending the Account Identity roadmap (`ACCOUNT_IDENTITY_AND_MY_MEALS.md`).
- **Canonical Storage Path Alignment**:
  - Ensured canonical `/data/receipt_photos` is used consistently across runbooks, templates, and documentation.
- **Comprehensive 12-Item Pre-Activation Checklist Prepared**:
  - Formulated in `docs/plans/MVP_RELEASE_AND_DEPLOYMENT.md` Section 8, distinguishing items proven locally from those requiring live network verification.

## Accepted Stage B operational runbook corrections & pre-activation verification checkpoint

- **Backup & Restore CLI Alignment & Flag Aliases**:
  - Aligned documented runbook commands in `docs/runbooks/windows_host_operations.md` with actual parser in `tools/backup_restore.py`:
    - Backup canonical flags: `--db`, `--photos`, `--out-dir` (with `--storage-dir` and `--backup-dir` supported as aliases).
    - Restore canonical flags: `--manifest`, `--dest-db`, `--dest-photos`, `--confirm-stopped` (with `--manifest` accepting directory or JSON file, and `--dest-storage-dir` supported as alias).
  - Added CLI flag compatibility test in `tests/test_backup_restore.py` (`test_backup_restore_cli_flag_compatibility_and_directory_manifest`).
- **Non-Destructive Isolated Docker Recovery Drill (`tools/verify_isolated_docker_drill.py`)**:
  - Created isolated ephemeral volumes (`settletable_drill_src_*`, `settletable_drill_dest_*`) and host backup directory.
  - Seeded synthetic meal and receipt photo in source volume.
  - Executed documented backup command inside container.
  - Executed documented restore command into destination volume with `--confirm-stopped`.
  - Verified post-restore SQLite `PRAGMA integrity_check;`, receipt photo SHA-256 hash match, and organizer authentication.
  - Verified primary application volume `settletable_data` was completely untouched. Cleaned up all drill volumes.
- **Documentation Accuracy & Invariant Corrections**:
  - Corrected manifest description: SHA-256 checksummed manifest (not cryptographically signed).
  - Corrected container healthcheck status: `settletable_app: Up (healthy)`, `settletable_tunnel: Up` (daemon without healthcheck).
  - Corrected CLI administrative commands: `bootstrap_meal.py bootstrap` and `bootstrap_meal.py recover`.
  - Pinned `cloudflare/cloudflared:2026.10.7` in `docker-compose.yml` for deployment reproducibility.
  - Formulated WSL2 resource settings as adjustable recommendations based on host RAM.
  - Documented connector token confidentiality for `.env`.
- **Internal Docker Network Resolution Verification**:
  - Verified internal DNS service name resolution on Compose bridge network (`tabwise_default`): test container resolved `http://settletable:8000/healthz` and received HTTP 200 `{"ok":true,"status":"healthy"}` without exposing ports.
- **Application Abuse Controls Review**:
  - Join Requests: Bounded table limits (max 20 pending / 100 historical records), anti-enumeration constant response (`invalid_join_target`), duplicate request rejection.
  - Organizer Claims: Unguessable 43-character tokens, domain-separated SHA-256 verification, single-use atomic consumption, prior unconsumed claim revocation.
  - Receipt Photos & OCR: Strictly restricted to authenticated organizers (`is_org == True`). Public visitors and diners cannot trigger OCR or upload files.
  - Pre-activation edge checks documented: Cache-Control bypass (`no-store`), request limits, Host/Origin validation, loopback `/bootstrap` blocking.
- **Verification Evidence**:
  - 319/319 Python unit, calculation, security, restore, and ingress tests passed (`python -m unittest discover tests`).
  - Isolated Docker backup/restore drill passed 100% (`tools/verify_isolated_docker_drill.py`).
  - Pre-publication audit scanner (`tools/audit_repository.py`) passed with 0 findings across all tracked files.
  - Zero external traffic or tunnel connections activated.

## Accepted Stage B offline hosting preparation checkpoint (PR #49)

- **Remotely-Managed Named Tunnel Strategy (Selected & Recommended)**:
  - Reviewed official Cloudflare documentation via Context7 MCP: remotely-managed tunnels (configured via dashboard with a tunnel token) are Cloudflare's primary recommended pattern for containerized deployments.
  - Eliminates local credential JSON files, private keys, and configuration drift between local files and Cloudflare DNS edge routing.
  - Inactive locally-managed template (`deploy/cloudflare/config.template.yml`) and comprehensive architectural guide (`deploy/cloudflare/README.md`) provided for offline reference.
- **Docker Compose Integration**:
  - Added optional `cloudflared` connector service to `docker-compose.yml` under profile `with-cloudflared`.
  - Topology A (Selected): container runs on shared Docker bridge network (`tabwise_default`) and connects internally to `http://settletable:8000`. Host port 8000 remains bound to `127.0.0.1:8000` solely for host-level health checks and admin bootstrap CLI.
  - Verified Docker Compose configuration syntax with `docker compose config` and `docker compose --profile with-cloudflared config`.
- **Environment Template & Ingress Configuration**:
  - Updated `deploy/env.template` with `CLOUDFLARE_TUNNEL_TOKEN`, `SETTLETABLE_SERVER_ORIGIN=https://settle.example.com`, and `SETTLETABLE_ALLOWED_HOSTS=settle.example.com,127.0.0.1:8000,localhost:8000,settletable:8000`.
  - Clearly documented that Cloudflare Access is NOT enabled or required.
- **Windows Host Operations & Disaster Recovery Runbook**:
  - Authored `docs/runbooks/windows_host_operations.md` covering:
    - Host power and sleep prevention during active dining sessions (`powercfg /change standby-timeout-ac 0` or PowerToys Awake).
    - Docker Desktop auto-start settings and WSL2 resource sizing (`.wslconfig`).
    - SQLite WAL crash-consistency and automatic WAL replay on restart.
    - Automatic exponential backoff reconnection behavior during residential WAN drops.
    - Explicit stopped-container consistent backup and verified disaster recovery restore protocols against persistent Docker volumes.
    - Emergency troubleshooting cheatsheet and organizer recovery commands.
- **Reverse-Proxy & Cloudflare Ingress Security Hardening & Tests**:
  - Added Cloudflare client IP headers (`HTTP_CF_CONNECTING_IP`, `HTTP_TRUE_CLIENT_IP`, `HTTP_X_CLUSTER_CLIENT_IP`) to `proxy_headers` in `settletable/transport.py` to ensure `/api/meals/*/bootstrap` strictly rejects external requests.
  - Enhanced query string secret redaction in `redact_log_string()` to match parameter tokens at the start of query strings (`^token=...`), preventing token exposure in WSGI access logs.
  - Authored dedicated 9-test synthetic ingress suite `tests/test_reverse_proxy_ingress.py`:
    - Public custom domain Host validation (settle.example.com accepted; foreign hosts return 400 invalid_host).
    - Exact-origin CSRF protection under public HTTPS (HTTPS origin matches; HTTP scheme mismatch, foreign origins, and null origins return 403; missing action header returns 400).
    - Cloudflare forwarding headers (CF-Connecting-IP, CF-Ray, CF-Visitor, X-Forwarded-Proto) processed cleanly.
    - External meal bootstrap rejected with 403 Forbidden on ANY proxy forwarding headers.
    - Unauthenticated access to private meal data and receipt photos denied (401 invalid_session).
    - Private API and receipt photo responses never cached by shared intermediaries (`Cache-Control: no-store` and `private, no-cache, no-store, must-revalidate`).
    - Secret tokens completely redacted from application request logs.
    - Abuse protections verified: header limits (431), payload boundaries (413), and integer bounds (400).
    - Deny-by-default behavior for unmatched ingress hostnames.
- **Future Manual Deployment Checklist (PO Authorization Boundaries)**:
  - Explicitly defined the 7 sequential steps from domain purchase to restricted pilot launch, clearly segregating automated actions from those requiring explicit Product Owner approval.
- **Verification Evidence**:
  - 318/318 Python unit, calculation, security, restore, and ingress tests passed (`python -m unittest discover tests`).
  - 11/11 automated deployment smoke checks passed (`tools/deployment_smoke_check.py`).
  - Pre-publication audit scanner (`tools/audit_repository.py`) passed with 0 findings across all tracked files.
  - Zero external traffic or tunnel connections activated.

## Accepted Stage A post-merge corrective hardening checkpoint (PR #48)

- **PR #48 Merged**: Reviewed head merged autonomously under orchestrator governance into `main`. GitHub Actions CI passed on exact head and post-merge `main`.
- **Finding 1 — Restore Safety Contract & Active-Application Detection**:
  - Corrected `check_restore_safety()` in `tools/backup_restore.py`. Replaced the insufficient assumption that SQLite lock acquisition proves process inactivity with an explicit stopped-container protocol.
  - Requires operator confirmation flag `--confirm-stopped` to proceed.
  - Actively probes local HTTP health check endpoint (`http://127.0.0.1:8000/healthz`); aborts immediately if a live server responds.
  - Inspects Docker daemon for running `settletable_app` container; aborts if container is active.
  - Validates SQLite exclusive locking (`PRAGMA locking_mode=EXCLUSIVE; BEGIN EXCLUSIVE;`) to catch active transactions.
- **Finding 2 — Staged Restore, Controlled Cutover & Rollback**:
  - Implemented isolated staged restore in temporary directory on the destination volume (`.restore_staging_{uuid}`).
  - Pre-flight verifies database checksum, `PRAGMA integrity_check;`, photo checksums, and absence of extraneous unmanifested files.
  - Archives previous destination database, WAL sidecars, and receipt photos to `.pre_restore_archive_{uuid}` before cutover.
  - Controlled cutover moves staged files into destination paths and verifies post-cutover database and photo integrity.
  - Automatically rolls back previous dataset from archive if cutover validation fails (failure injection verified in `test_staged_restore_failure_injection_rolls_back_destination`).
  - Prunes orphaned destination photos into archive without polluting restored state.
  - Documented filesystem multi-path atomicity limitation honestly in code and docs.
- **Finding 3 — Comprehensive Token Redaction & Clean Endpoints**:
  - Enhanced `redact_log_string()` in `settletable/transport.py` covering invitation paths, organizer claim paths, HTML landing routes, Authorization headers, session cookies, Notion secrets, query string parameters, and JSON payload fields.
  - Added clean `POST /api/organizer-claims/inspect` accepting `{ "claim_token": "..." }` in request body.
  - Updated `POST /api/meals/{meal_id}/organizer-claims/claim` to accept `claim_token` in request body.
  - Updated client `settletable/static/app.js` to send tokens in request bodies, ensuring secret bearer tokens never appear in web server, reverse proxy (Caddy/Nginx), or Gunicorn request URL lines.
  - Updated `tools/bootstrap_meal.py` and `README.md` to accurately state that the CLI emits a single-use claim link containing an ephemeral secret on stdout once to the administrator.
- **Finding 4 — Verification Scope Accuracy**:
  - Accurately distinguished hosted CI scope (309 Python tests + Docker container build & smoke check) from out-of-CI tests (real Chrome CDP regression suites, mobile UX viewport audit, physical Android Chrome UAT on POCO F6, and real RapidOCR CPU inference).
- **Finding 5 — Finalized Hosting Architecture**:
  - Finalized Product Owner decision recorded: Windows host with Docker + Cloudflare Named Tunnel (`cloudflared`) with custom domain (e.g. `settle.yourdomain.com`).
  - Confirmed zero-login diner access without Cloudflare Access (SettleTable application auth authoritative).
  - Tailscale Funnel (`*.ts.net`) preserved as secondary fallback.
- **Verification Evidence**:
  - 309/309 Python unit, calculation, security, and restore tests passed in 118s (`python -m unittest discover tests`).
  - 11/11 automated deployment smoke checks passed (`tools/deployment_smoke_check.py`).
  - Pre-publication audit scanner (`tools/audit_repository.py`) passed with 0 findings across all tracked files.
  - Independent HIGH-risk review completed with **PASS** verdict.

## Accepted Stage A local reliability & security hardening checkpoint (PR #47)

- **PR #47 Merged**: Reviewed head `e1f16265be34a61e81b299606a0d649cd802125c` merged autonomously under orchestrator governance into `main` ([merge commit 02107e2](https://github.com/KAIYI7/settle-table/commit/02107e22cde0924590125b0c37f679d50f593542)). GitHub Actions CI passed on exact head ([run 42155144910](https://github.com/KAIYI7/settle-table/actions/runs/42155144910)) and post-merge `main`.
- **Organizer Browser Provisioning & Recovery Lifecycle**:
  - Implemented `organizer_claims` SQLite schema with unique `(meal_id, issue_id)` constraint, verifier index, and cascade on delete.
  - Implemented domain-separated token hashing (`_organizer_claim_verifier` with salt `settletable-organizer-claim-v1\0`) to avoid leaking plaintext tokens in SQLite.
  - Implemented single-use atomic redemption (`consumed = 1`) inside `BEGIN IMMEDIATE` transaction, session rotation, and revision bumping.
  - Implemented safe unauthenticated inspection (`GET /api/organizer-claims/{token}`) returning only public metadata without credentials.
  - Implemented CSRF-protected redemption endpoint (`POST /api/meals/{meal_id}/organizer-claims/{token}/claim`) setting `Set-Cookie: settletable_session=<cred>; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=<ttl>`.
  - Configured `SETTLETABLE_SESSION_TTL` environment variable with bounds validation (1 to 2,592,000s) and safe default of 7 days (604,800s).
  - Hardened `tools/bootstrap_meal.py` stdout to print a single-use Organizer Browser Setup Link (`/#/claim-organizer/<token>`) instead of leaking raw bearer tokens.
  - Added CLI subcommand `python tools/bootstrap_meal.py recover --meal-id <id>` for emergency host-level recovery without direct database editing.
  - Added client routing (`/#/claim-organizer/:token`) and Organizer Panel emergency recovery link generator with one-click clipboard copy.
- **Provably Consistent Quiescent Backup & Verified Restore**:
  - Replaced misleading "atomic hot backup" claim with `perform_quiescent_backup()`: acquires `BEGIN IMMEDIATE` write lock on source database, inspects `receipt_photos` records, verifies physical photo files and SHA-256 hashes on disk, copies photos to backup directory, executes `sqlite3.backup()` from a read-only WAL snapshot connection while lock is held, verifies backup integrity, commits, and writes verified `manifest_{timestamp}.json`.
  - Implemented `check_database_unlocked()` testing target database with `BEGIN IMMEDIATE` (100ms busy timeout) before restoring, aborting with a clear error if SettleTable is currently running.
  - Implemented `perform_verified_restore()` validating manifest checksums, backup DB `PRAGMA integrity_check`, photo hashes on disk against DB records, clearing existing WAL sidecars (`.sqlite-wal`, `.sqlite-shm`) to prevent WAL replay corruption, and re-verifying destination integrity.
- **Docker, Gunicorn & RapidOCR Packaging Fixes**:
  - Fixed Dockerfile line 24 shell redirection bug: `"gunicorn>=21.2.0"`.
  - Configured `RAPIDOCR_CACHE_DIR` and `NUMBA_CACHE_DIR` owned by non-root `settletable:settletable` user.
  - Removed `|| true` on RapidOCR cache step to ensure failures during model download are loud.
  - Verified non-root container execution (`uid=10001(settletable)`).
- **CI Container Build & Smoke Verification**:
  - Added `docker-smoke` job to `.github/workflows/python-tests.yml`.
  - Expanded `tools/deployment_smoke_check.py` to 10 automated checks (including claim shell routes and invalid token rejection).
- **Verification Evidence**:
  - 303/303 Python unit and integration tests passed in 108s (`python -m unittest discover tests`).
  - All 12 real browser CDP test stages passed (`node tools/e2e_browser_test.mjs --port 8989`).
  - Live Docker container passed 10/10 deployment smoke checks.
  - Pre-publication audit script (`tools/audit_repository.py`) passed with 0 findings across 16 staged files and 332 tracked files.
  - Independent HIGH-risk Security & Adversarial Review completed with **PASS** verdict (0 BLOCKERS, 0 WARNINGS).

## Accepted low-cost mostly-available deployment strategy revision checkpoint

- **Deployment Strategy Pivoted**: Product Owner updated requirements to prioritize RM0/month hosting on existing Windows hardware with mostly-available availability, zero-software diner browser access, and off-host backup durability. Commercial cloud services (Fly.io, Hetzner, Railway) deferred.
- **Revised Deployment Plan**: Documented in [`docs/plans/MVP_RELEASE_AND_DEPLOYMENT.md`](docs/plans/MVP_RELEASE_AND_DEPLOYMENT.md).
- **Corrected Release Readiness Findings**:
  - `[VERIFIED]` *Session TTL Defect*: `Authority.bootstrap` in `settletable/authority.py:807` defaults to `session_ttl=3600` (1 hour) and caps at 86,400s (24 hours). The previous 7-day documentation claim was incorrect. Aligning session TTL is required before multi-hour dining sessions.
  - `[VERIFIED]` *Organizer Bootstrap Usability Defect*: `tools/bootstrap_meal.py` prints a raw token but provides no browser claim or redemption mechanism. A bounded Organizer Claim flow is required to issue `settletable_session` HttpOnly cookies to the organizer's browser.
  - `[VERIFIED]` *Backup Atomicity Limitation*: `tools/backup_restore.py` runs `sqlite3.backup()` and copies photos sequentially afterward. A formal quiescence/maintenance consistency protocol is required rather than claiming atomic hot backups.
  - `[VERIFIED]` *Restore Verification Defect*: Restore must verify photo SHA-256 hashes against the database manifest and refuse to overwrite actively running SQLite instances.
  - `[VERIFIED]` *Dockerfile Packaging Defects*: Unquoted `gunicorn>=21.2.0` shell redirection and RapidOCR `|| true` masked build errors identified for remediation.
- **Reassessed Hosting Options**:
  - *Primary A (If Domain Approved/Owned)*: Windows Docker + Cloudflare Named Tunnel + Cloudflare Access (unmetered bandwidth, free tier up to 50 users, ~$10–$15/year domain fee).
  - *Primary B (Strict RM0 / No Domain Spend)*: Windows Docker + Tailscale Funnel (permanent stable `*.ts.net` URL, automated Let's Encrypt TLS, RM0/year, zero diner software).
  - *Fallback*: ngrok Free (1 GB/mo bandwidth cap, interstitial warning page).
- **Reassessed 4-Gate Governance Model**:
  - Gate 1 (Reproducible Local Release): **PASS** (296 Python tests pass; 9 browser CDP suites pass).
  - Gate 2 (Restricted Online Pilot `v0.9.0-beta.1`): **BLOCKED / HARDENING REQUIRED** (Requires executing Stage A local hardening backlog: organizer claim flow, session TTL, backup quiescence protocol, Dockerfile fixes, and PO access path selection).
  - Gate 3 (Publicly Reachable Application): **BLOCKED / DEFERRED** (Requires Account Identity roadmap).
  - Gate 4 (Public GitHub Repository `v1.0.0`): **BLOCKED / ESCALATED** (Requires PO licensing and visibility decisions).
- **Verification Evidence**:
  - 296/296 Python unit tests passed in 102s (`python -m unittest discover tests`).
  - 8/8 automated deployment smoke checks passed (`tools/deployment_smoke_check.py`).
  - Programmatic hot backup, WAL checkpointing, PRAGMA integrity check, and restoration verified with live test.
  - Administrative bootstrap CLI verified with test meal generation and invitation pre-minting.
  - Pre-publication audit script (`tools/audit_repository.py`) passed with 0 findings across all tracked files.
  - Independent Code & Security Review completed with **PASS** verdict and 0 blocking/warning findings.

## Accepted mobile amount field clipping remediation checkpoint (PR #46)

- **PR #46 Merged**: Reviewed head `9a1b9265ebf9158c84c8767acc9ab73c9f636bf8` merged autonomously under orchestrator governance into `main` ([merge commit 0c53edc](https://github.com/KAIYI7/settle-table/commit/0c53edc3189941677fa58e1f9e6964d9ff043dde)). GitHub Actions CI passed on exact head ([run 41990625154](https://github.com/KAIYI7/settle-table/actions/runs/41990625154)) and post-merge `main` ([run 41990929986](https://github.com/KAIYI7/settle-table/actions/runs/41990929986)).
- **Physical Android UAT Finding Remediated**:
  - Remediated the product owner's physical Android UAT finding on Google Chrome / POCO F6 where negative monetary amounts such as `-0.01` visually clipped as `-0.0` in the OCR candidate adjustments editor.
- **Root Cause & Geometry**:
  - In `settletable/static/style.css`, `.ocr-adj-field-amount .ocr-amount-wrapper` was fixed at `width: 95px` and `.ocr-adj-field-details` at `grid-template-columns: minmax(0, 1fr) 95px` across both `@container ocrCard (max-width: 539px)` and `@media (max-width: 639px)`.
  - With a ~36px RM currency prefix and 16px internal input padding, the input's `clientWidth` was only 57px. Monospace text for `-0.01` is 58px and `-12.34` is 66px, causing `scrollWidth > clientWidth` and clipping the trailing digit or minus sign off-screen.
- **Solution & Responsive Implementation**:
  - Expanded `.ocr-adj-field-details` `grid-template-columns` from `minmax(0, 1fr) 95px` to `minmax(0, 1fr) 118px` in both container query and media query fallbacks.
  - Expanded `.ocr-adj-field-amount .ocr-amount-wrapper` width from `95px` to `118px`.
  - Refined horizontal padding for `.ocr-currency-prefix` and `.ocr-amount-wrapper input` from `0 8px` to `0 6px`.
  - Increases input `clientWidth` from 57px to 84px, affording 18-26px of headroom for 5-7 character negative values (e.g. `-0.01`, `-0.02`, `-1.23`, `-12.34`, `-123.45`).
  - Preserved 44px touch-target height on mobile inputs and selects.
  - Type select width remains generous (100px at 320px; 170px at 390px POCO F6 scale).
  - Desktop layout (>639px) uses its dedicated 130px column unaffected.
  - Strict compliance with AGENTS.md: zero `overflow-x: hidden` used to conceal defects; zero font-size reduction.
  - Core financial calculation, validation, SQLite storage, and Notion export completely untouched.
- **Verification Evidence**:
  - 294/294 Python unit tests passed.
  - Dedicated Stage 2b in `tools/verify_mobile_ux_remediation.mjs` verified across 320×568, 375×667, 390×844 (POCO F6 scale), and 430×932: zero clipping (`scrollWidth <= clientWidth`), zero horizontal page overflow (`docScrollWidth <= targetWidth`), prefix non-overlap, and select adequacy.
  - Full regression test suites passed 100%: `verify_ux_polish.mjs`, `verify_complimentary_items_flow.mjs`, `verify_context_aware_navigation.mjs`, `e2e_browser_test.mjs`.
  - Visual evidence captured: `before_mobile_amount_clipping_375.png`, `before_mobile_amount_clipping_390.png`, `after_mobile_amount_clipping_375.png`, `after_mobile_amount_clipping_390.png`.
  - Independent code review completed and passed with 0 blocking findings.


## Accepted mobile UX audit remediation checkpoint (PR #45)

- **PR #45 Merged**: Reviewed head `20950a40e60b47bd25b51ccf29da011b36e879c8` merged autonomously under orchestrator governance into `main`. GitHub Actions CI passed on exact head ([run 41981944321](https://github.com/KAIYI7/settle-table/actions/runs/41981944321)).
- **P1: Complimentary Item Overflow Remediation**:
  - Root cause: `.item-header` flex row lacked flex wrapping and `min-width: 0`, combined with wide `.complimentary-badge` (~170px) and item meta causing 74px overflow on 320px screens and 18px on 375px screens.
  - Solution: Scoped `flex-wrap: wrap; row-gap: 6px;` and `flex-shrink: 1; max-width: 100%;` to `.item-card.is-complimentary` and `.hybrid-item-card.is-complimentary`. Added `overflow-wrap: break-word; word-break: break-word;` to item labels and `.complimentary-badge`.
  - Review section cards: Extracted semantic `.review-item-row`, `.review-item-label-group`, and `.review-item-price-group` with scoped `.is-complimentary` wrapping.
  - Preserved paid item visual alignment: paid item prices remain pinned top-right beside wrapping titles (`flex-shrink: 0; text-align: right;`).
  - Strict compliance with AGENTS.md: zero `overflow-x: hidden` used to conceal defects.
- **P2: Notion Password Input Harmonization**:
  - Root cause: `input[type="password"]` was omitted from shared form input styling in `style.css`, rendering `#notion-token` with browser-default 20px height, white background, and unstyled borders.
  - Solution: Added `input[type="password"]` to shared form selectors, harmonizing `#notion-token` with 44px min-height, dark background (`--bg-input`), 10px 14px padding, 10px border radius, and active focus outline.
  - Zero modifications to token handling, auth, storage, masking, or Notion export backend.
- **P3: Home Breadcrumb & Review Checkbox Touch Targets**:
  - Root cause: `.room-home-link` interactive area had 4px 6px padding and 28px min-height, failing the mobile 44px touch target requirement.
  - Solution: Scoped `.room-home-link` interactive target to 44px on mobile via `@media (max-width: 768px)` (`min-height: 44px; padding: 8px 10px; margin: -6px -8px; touch-action: manipulation;`), preserving compact 28px height on desktop viewports (>768px).
  - Review checkbox: Extracted `.review-confirm-label` with `min-height: 44px; display: flex; align-items: center; gap: 10px; touch-action: manipulation;` and 18×18px checkbox, ensuring accessible touch target.
  - Sticky header clearance and contextual navigation scroll destinations from PR #43 and PR #44 verified fully intact.
- **Verification Evidence**:
  - 294/294 Python unit tests passed in 86s.
  - Dedicated 7-stage automated browser suite `tools/verify_mobile_ux_remediation.mjs` passed 100% across all 6 target viewports: 320×568, 375×667, 390×844, 430×932, 768×1024, and 667×375 landscape. Zero horizontal overflow in both organizer and diner views.
  - Bounding rects and visual evidence captured: `after_p1_complimentary_320.png`, `after_p1_complimentary_375.png`, `after_paid_item_layout_375.png`, `after_diner_view_complimentary_375.png`, `after_p2_notion_token_375.png`, `after_p3_breadcrumb_375.png`.
  - Full regression test suites passed 100%: `verify_ux_polish.mjs`, `verify_complimentary_items_flow.mjs`, `verify_context_aware_navigation.mjs`.
  - Independent review completed: Standards Review (PASS), Spec Review (PASS after desktop-scoping and selector refinement).
  - Exact PR head CI passed on `20950a4` ([run 41981944321](https://github.com/KAIYI7/settle-table/actions/runs/41981944321)).
  - Post-merge CI passed on `e909eca` ([run 41982235579](https://github.com/KAIYI7/settle-table/actions/runs/41982235579)).

## Accepted suggested peer transfer prefill navigation checkpoint (PR #44)

- **PR #44 Merged**: Reviewed head `ac8bea9a1025e579714f34d3fd11c022c1cdb807` merged autonomously under orchestrator governance into `main`. GitHub Actions CI passed on exact head (tests check run: `conclusion=success`).
- **Suggested Transfer Action Clarity**:
  - Renamed the suggestion prefill button from `Record Payment` to `Use Suggestion` (`.prefill-transfer-btn`), eliminating ambiguity and preventing users from assuming that clicking the button immediately records a reimbursement.
- **Context-Aware Reimbursement Form Navigation**:
  - Automatically scrolls to the Record Confirmed Peer Reimbursement form (`#record-transfer-form`) using `navigateToWorkflowSection()`.
  - Added `#record-transfer-form` to CSS `scroll-margin-top: calc(var(--app-header-height, 68px) + 16px)` on desktop and `calc(var(--app-header-height, 56px) + 12px)` on mobile ($\le 640$px), ensuring clean clearance below the sticky application header.
- **Mobile Touch Usability & Virtual Keyboard Suppression**:
  - Focuses `#record-transfer-heading` (`tabindex="-1"`) with `{ preventScroll: true }`, giving immediate screen reader announcement and keyboard context without auto-focusing `#transfer-amount-input` (which would trigger the mobile virtual keyboard and obscure the form).
  - Outlines `#record-transfer-heading:focus-visible` with 2px indigo focus ring matching design system standards.
- **Accessible Prefill Status Banner**:
  - Renders a polite live-region status banner (`#prefill-transfer-banner`, `role="status"`, `aria-live="polite"`): `"ℹ️ Details pre-filled. Review and confirm the reimbursement below."` inside the reimbursement form card.
  - Automatically dismisses the banner upon submission or snapshot refresh.
- **Form Lifecycle & Financial Isolation**:
  - Preserves manual editing of debtor, creditor, amount, and reference notes before confirming.
  - `#record-transfer-btn` remains the sole trigger executing `RecordTransfer`.
  - Core financial calculations, SQLite authority, funding logic, and Notion export remain 100% untouched.
- **Verification Evidence**: 294/294 Python unit tests passed; dedicated 8-stage headless Chrome CDP test suite `tools/verify_peer_settlement_flow.mjs` passed 100% (verifying desktop/mobile prefill navigation, sticky header clearance, heading focus, virtual keyboard suppression, banner display, manual editing, and scroll stability across refresh); full regression suites (`verify_context_aware_navigation.mjs`, `verify_multi_payer_flow.mjs`, `verify_complimentary_items_flow.mjs`, `verify_conflict_recovery.mjs`, `verify_ux_polish.mjs`, `e2e_browser_test.mjs`) passed 100%; independent code review PASS with 0 blocking/warning findings; hosted GitHub Actions CI completed with `conclusion=success` on exact PR head `ac8bea9`.

## Accepted context-aware workflow scroll and focus navigation checkpoint (PR #43)

- **PR #43 Merged**: Reviewed head `bfa7c8aae7a4c77a7e037e783cff9280276febea` merged autonomously under orchestrator governance into `main`. GitHub Actions CI passed on exact head ([run 41816588612](https://github.com/KAIYI7/settle-table/actions/runs/41816588612)).
- **Context-Aware Workflow Navigation & Focus Transitions**:
  - **Action A (OCR Acceptance)**: After accepting OCR candidates (`#ocr-accept-btn`), smoothly navigates to the Human Receipt Review card (`#review-section`) and places programmatic focus on the review verification checkbox (`#review-confirm-check`).
  - **Action B (Review Approval)**: After approving and sealing receipt review (`#review-submit-btn`), inspects the refreshed snapshot state:
    - If paid items need allocation, navigates to Item Allocation (`#allocation-section`) and focuses `#allocation-heading`.
    - RM0.00 complimentary items are ignored for allocation completeness; receipts containing only complimentary items bypass allocation.
    - If all paid items are allocated and finalization is available, navigates to Seal & Finalize Meal (`#finalize-section`) and focuses `#finalize-btn`.
    - If blocking issues exist, navigates to `#finalize-section` and highlights the actionable warning (`.finalize-warning`).
  - **Action C (Finalization)**: After finalizing the meal (`#finalize-btn`), smoothly navigates to Final Apportionment Summary (`#apportionment-section`) and places focus on `#apportionment-heading`.
- **Accessibility & Viewport Clearance**:
  - Accounts for the sticky header using CSS `scroll-margin-top: calc(var(--app-header-height, 68px) + 16px)` on desktop and `12px` on mobile, synced with header metrics.
  - Dual-layer `prefers-reduced-motion` compliance: CSS `scroll-behavior: auto !important` and JS `behavior = 'auto'` when reduced motion is preferred.
  - Programmatic focus calls `focus({ preventScroll: true })` inside defensive try/catch to avoid secondary scroll jumps.
  - Non-interactive headings and warnings carry `tabindex="-1"` and accessible `:focus-visible` styling.
- **Viewport Stability & Non-Interference**:
  - Background polling (`pollSnapshot()`), manual header refresh (`#manual-refresh-btn`), and failed/rejected mutations never move the viewport.
  - Authoritative calculation engine, SQLite authority schema, and Notion exporter remain 100% untouched.
- **Verification Evidence**: 294/294 Python unit tests passed; dedicated 8-stage headless Chrome CDP suite `tools/verify_context_aware_navigation.mjs` passed 100%; full regression suites (E2E browser, complimentary items flow, numeric steppers & UX polish, conflict recovery) passed 100%; independent code review PASS with 0 blocking/warning findings; hosted GitHub Actions CI completed with `conclusion=success` on exact PR head [run 41816588612](https://github.com/KAIYI7/settle-table/actions/runs/41816588612).

## Accepted RM0.00 complimentary items without mandatory allocation checkpoint (PR #42)

- **PR #42 Merged**: Reviewed head `6edcef49c00e4bc8f154c0bf1a56390225253fe1` merged autonomously under orchestrator governance into `main`. GitHub Actions CI passed on exact head ([run 41804800476](https://github.com/KAIYI7/settle-table/actions/runs/41804800476)).
- **Informational RM0.00 Receipt Items Preserved**:
  - Receipt items with `line_sen === 0` (e.g. Warm Water, Ice Water) are preserved on the receipt as informational records rather than financial liabilities.
  - Receipt review and meal finalization no longer block on unallocated complimentary items; `Authority._issues()` strictly skips zero-priced items when checking quantity completeness.
  - Calling `SetOwnQuantity`, `AssignParticipantQuantity`, or `SetItemAllocations` on zero-priced items is rejected with machine-readable `complimentary_item`.
- **Calculation Engine Split Contract**:
  - In `settletable/calculation.py`, `_split()` permits an empty share collection if and only if `amount == 0 and len(split.shares) == 0`, returning `()`. Paid items with empty shares continue to raise `CalculationError("collection_bound")`.
  - Adjustments scoped exclusively to zero-priced items evaluate to a zero base and trigger `CalculationError("zero_base")`.
  - All-zero receipts finalize cleanly with RM0.00 total and RM0.00 consumption.
- **Frontend & OCR Integrity**:
  - Manual Add Item allows explicit RM0.00 while rejecting negative or malformed prices. Toast indicates `Added "<Item>" (Complimentary · RM 0.00) ✓`.
  - OCR staging in `syncCandidateInputs()` distinguishes valid `0` from parse errors, preventing empty/invalid strings from silently falling back to 0. Acceptance validation blocks candidates with invalid prices.
  - DOM presentation: Complimentary item cards render `.is-complimentary` styling with `Complimentary · RM 0.00` price badges and `Complimentary · No allocation needed` badges, while suppressing allocation steppers, quick-assign pills, and progress bars in both Diner and Organizer views.
- **Notion Export Compliance**:
  - Zero-priced items with no shares display `"Complimentary"` instead of `"Unclaimed"` in Notion compact and full meal blocks.
- **Verification Evidence**: 301/301 Python unit tests passed; dedicated 6-stage headless Chrome CDP test `tools/verify_complimentary_items_flow.mjs` passed 100%; independent code review PASS with 0 blocking/warning findings; hosted GitHub Actions CI completed with `conclusion=success` on exact PR head [run 41804800476](https://github.com/KAIYI7/settle-table/actions/runs/41804800476).
- **Product-Owner Confirmed Integration & UAT Evidence**:
  1. The product owner personally confirmed successful real-world testing of: actual local receipt OCR, human verification and diner allocations, financial finalization, original receipt photo preview and zoom, and live Notion financial export with the original receipt photo included.
  2. The product owner personally completed and confirmed all 8/8 manual UAT checks for Multi-Payer Contributions and Peer Settlements in Microsoft Edge: RM60.48 restaurant bill fully funded; Alice consumed RM30.00 and contributed RM40.00; Bob consumed RM30.48 and contributed RM20.48; correct RM10.00 peer reimbursement suggestion generated; partial RM4.00 repayment tracked with RM6.00 remaining; reversal and replacement of a reimbursement recorded correctly; final zero outstanding balances achieved; and funding and settlement history persisted across page refreshes. (Recorded as product-owner-confirmed UAT evidence, not formal independent acceptance).
- **Active objective:** Multi-Payer Contributions, Net Balance Reconciliation, Suggested Peer Transfers, Partial Reimbursements & Settlement Tracking complete and merged.
- **Blocking gates:** Live Internet production release needs operational backup/restore, external deployment infrastructure, device validation, and privacy boundary approval. Local atomic access/calculation/persistence, dual invitation lifecycle, organizer allocation authority, transport boundaries, browser UI, local OCR processing, optional Notion reporting, and independent security gates pass within the bounded authority contract.
- **Nonblocking risks for this phase:** Modern held-out Malaysian OCR accuracy, real-phone camera/offline performance, original dataset rights, raw authenticated Notion REST/actual workspace limits, real hosting costs. These block relevant release/integration claims, not local validation.
- **Architecture/stack:** Path C; Python standard-library `settletable` package with WSGI transport adapter (`SettleTableApp`), single-host SQLite local authority in WAL mode, RapidOCR local CPU ONNX engine, optional decoupled Notion exporter (`settletable.notion`), and zero-dependency vanilla ES2022 / HTML / CSS browser frontend. The source move preserves the historical `tabwise-apportion-v1` deterministic contract and all existing security/canonical domains.
- **Independent UAT status:** The 29 October computer-use UAT remains incomplete. Its blocked/untested finalization, export, collaboration, mobile/accessibility and negative scenarios require a separate independent retest in a confirmed isolated environment. Engineering regression results do not mark those scenarios passed.
- **Next work:** Maintain production baseline, address any user feedback, or prepare for formal independent UAT retesting.

## Accepted financial form select dropdown chevron polish checkpoint (PR #41)

- **PR #41 Merged**: Reviewed head `5ec6ae03b322eaf3b3ef336ec54548dc9991a98a` merged autonomously under orchestrator governance into `main`. GitHub Actions CI passed on exact head ([run 41783878095](https://github.com/KAIYI7/settle-table/actions/runs/41783878095)).
- **Subtle SVG Dropdown Chevron & Text Clearance**:
  - In `settletable/static/style.css`, enhanced native `<select>` form controls across SettleTable, including `#payer-participant-select`, `#payer-method-select`, `#transfer-sender-select`, and `#transfer-receiver-select`.
  - Suppressed platform/browser default arrows with `appearance: none`, `-webkit-appearance: none`, `-moz-appearance: none`, and `select::-ms-expand { display: none; }`.
  - Embedded crisp inline SVG chevron (`#94a3b8`) with `background-position: right 15px center;` (meeting the 14–16px inset specification) and `16px 16px` size.
  - Expanded right padding to `42px`, guaranteeing an 11px clear gap between the option text/ellipsis and the chevron icon.
  - Enhanced active focus indicator (`select:focus`) with a brighter chevron (`#f8fafc`) matching the `--border-focus` ring and indigo glow.
  - Added disabled state styling (`select:disabled`) with `opacity: 0.6; cursor: not-allowed;` and a muted `#64748b` chevron.
  - Preserved long participant name containment with `max-width: 100%; min-width: 0; text-overflow: ellipsis; white-space: nowrap;`.
- **Zero JavaScript Dropdown Replacement**: Native `<select>` elements, keyboard navigation, accessibility tree, and mobile touch pickers preserved 100%.
- **Production Calculation Engine Untouched**: `settletable/calculation.py` remains 100% byte-untouched. Zero floating-point arithmetic.
- **Verification Evidence**: 290/290 Python unit tests passed; 8/8 headless Chrome multi-payer tests passed; 8/8 headless Chrome peer settlement tests passed; expanded 8-stage suite `tools/verify_ux_polish.mjs` passed 100% with real CDP computed style and bounding rect assertions; independent code review APPROVE with 0 findings; hosted GitHub Actions CI completed with `conclusion=success` on exact PR head [run 41783878095](https://github.com/KAIYI7/settle-table/actions/runs/41783878095).

## Accepted mobile stepper touch target compliance & verification checkpoint (PR #40)

- **PR #40 Merged**: Reviewed head `49cd56d5aee43f99fa4657866e29274abc99b951` merged autonomously under orchestrator governance into `main`. GitHub Actions CI passed on exact head ([run 41657355223](https://github.com/KAIYI7/settle-table/actions/runs/41657355223)).
- **Effective $\ge 44 \times 44$px Mobile Stepper Touch Targets**:
  - In `settletable/static/style.css`, updated `.numeric-stepper .stepper-btn`, `.ocr-qty-btn`, `.quantity-stepper.numeric-stepper button`, and `.quantity-stepper.numeric-stepper .stepper-btn` to `width: 44px; min-width: 44px; height: 44px; min-height: 44px;`.
  - Updated stepper containers to `width: 128px; min-width: 128px; height: 44px;` with input/display at `width: 40px; min-width: 40px; height: 44px;` (accommodating $44\text{px} + 40\text{px} + 44\text{px} = 128\text{px}$).
  - Adjusted `.ocr-cand-item-row` grid template columns to `128px 1fr 44px;` in both container query and media query breakpoints.
  - Added `flex-wrap: wrap; gap: 8px;` to `.claim-actions` to prevent multi-button overflow on narrow screens.
- **Dedicated CDP Touch-Target Bounding Rectangle Verification (`tools/verify_ux_polish.mjs`)**:
  - Expanded test suite from 6 to 7 stages with actual real-browser CDP bounding rectangle measurements under 375px mobile viewport:
    - Scanned OCR receipt item stepper (`.ocr-qty-dec`, `.ocr-qty-inc`): measured $44 \times 44$px with typographic minus `−`.
    - Manual Add Item stepper (`#new-item-qty-dec`, `#new-item-qty-inc`): measured $44 \times 44$px with typographic minus `−`.
    - Diner portion stepper (`.hybrid-step-btn[data-step="-1"]`, `.hybrid-step-btn[data-step="1"]`): measured $44 \times 44$px with typographic minus `−`.
  - Document scroll width verified at exactly 375px (`document.documentElement.scrollWidth === 375`), confirming zero horizontal page overflow, clipping, or overlapping controls.
- **Production Calculation Engine Untouched**: `settletable/calculation.py` remains 100% byte-untouched. Zero floating-point arithmetic.
- **Verification Evidence**: 290/290 Python tests passed; 12/12 real-browser CDP test stages passed; conflict recovery, financial export, multi-payer funding, and peer settlement browser suites passed; dedicated 7-stage suite `tools/verify_ux_polish.mjs` passed 100% with real measured CDP bounding rects; independent code review APPROVE with 0 findings; hosted GitHub Actions CI completed with `conclusion=success` on exact PR head [run 41657355223](https://github.com/KAIYI7/settle-table/actions/runs/41657355223).

## Accepted targeted numeric stepper and financial UX clarity refinement checkpoint (PR #39)

- **PR #39 Merged**: Reviewed head `d0e85af491a581f36c31ea16f297716bc48c82d6` merged autonomously under orchestrator governance into `main`. GitHub Actions CI passed on exact head ([run 41650957160](https://github.com/KAIYI7/settle-table/actions/runs/41650957160)).
- **Unified Numeric Stepper Component**: Implemented cohesive `.numeric-stepper` across Manual Add Item (`#new-item-qty`), Scanned OCR editor (`.ocr-qty-stepper`), and Diner Portions (`.quantity-stepper`). Styled with dark-mode container borders, focus rings, and proper typographic minus (`−` / U+2212) matching plus (`+`). Preserves direct typing and auto-disables decrement at minimum value 1.
- **Financial Feature Copy Clarifications**:
  - *Restaurant Funding*: Added prompt *"Who paid the restaurant bill? Record how much each person actually paid at the counter."* and clarified column headers to `Participant`, `Amount Consumed`, `Paid to Restaurant`, `Base Net (Paid − Consumed)`, `Status`.
  - *Peer Settlement*: Added prompt *"Who needs to reimburse whom? Suggested transfers help everyone pay their fair share after the restaurant bill has been covered."*, prominent disclaimer that transfers and repayments are organizer-recorded (not independently bank-verified), and clarified column headers to `Participant`, `Base Net (Bill)`, `Reimbursed Others`, `Received from Peers`, `Still Owed / Recoverable`, `Status`.
- **Product-Owner Confirmed Edge UAT Evidence**: Recorded confirmed results for all 8/8 manual UAT checks in Microsoft Edge (RM60.48 fully funded, Alice/Bob contributions, RM10 reimbursement suggestion, partial RM4 repayment, reversal/replacement, zero final balances, and refresh persistence) as integration evidence, explicitly noting it is not formal independent acceptance.
- **Responsive Layout & Touch Accessibility**: Implemented responsive `.add-item-grid` stacking on mobile ($\le 600$px and 375px viewports) with $\ge 44$px touch targets and zero horizontal overflow.
- **Production Calculation Engine Untouched**: `settletable/calculation.py` remains 100% byte-untouched. Zero floating-point math added; currency inputs remain exact decimal text inputs without spinners.
- **Verification Evidence**: 290/290 Python tests passed; 12/12 real-browser CDP test stages passed; conflict recovery, financial export, multi-payer funding, and peer settlement browser suites passed; dedicated 6-stage suite `tools/verify_ux_polish.mjs` passed 100%; independent code review APPROVE with 0 findings; hosted GitHub Actions CI completed with `conclusion=success` on exact PR head [run 41650957160](https://github.com/KAIYI7/settle-table/actions/runs/41650957160).

## Accepted conflict recovery reload context renewal and CI expansion checkpoint (PR #38)

- **PR #38 Merged**: Reviewed head `79c684d7b6d615ea8689725a05a0c9bd7df03522` merged autonomously under orchestrator governance into `main`. GitHub Actions CI passed on exact head ([run 41622668317](https://github.com/KAIYI7/settle-table/actions/runs/41622668317)).
- **Post-Merge CI Failure Reconciled (Run 41618774152)**: Reconciled `TypeError: Cannot read properties of null (reading 'claims')` in `tools/verify_conflict_recovery.mjs` line 302 after `await a.reload()`.
- **CDP Reload Context Renewal Guarantee**: In `tools/verify_conflict_recovery.mjs` (and standardized across `verify_financial_export.mjs`, `verify_multi_payer_flow.mjs`, and `verify_peer_settlement_flow.mjs`), `CDPPage.prototype.reload` sets `window.__reloading_marker = true` before sending `Page.reload` and waits for `window.__reloading_marker === undefined`. Guarantees context recreation across reloads and eliminates race condition where post-reload assertions evaluated on stale pre-reload contexts.
- **Explicit Observable DOM Readiness in Conflict Recovery**: Line 302 waits for `Boolean(typeof state !== 'undefined' && state?.snapshot?.claims?.length === 2 && document.getElementById('add-item-form'))` before accessing `state.snapshot.claims`, eliminating property dereferencing before client state initialization.
- **CI Suite Expansion**: Added `--headless=new` and `--remote-debugging-address=127.0.0.1` to `tools/verify_multi_payer_flow.mjs` and `tools/verify_peer_settlement_flow.mjs`, enabling reliable headless execution in Ubuntu CI. Integrated both multi-payer funding and peer settlement suites directly into `.github/workflows/python-tests.yml`.
- **Production Code Untouched**: `settletable/calculation.py` and all backend/frontend application code remain 100% byte-untouched.
- **Verification Evidence**: 290/290 Python tests passed; 12/12 real-browser CDP test stages passed; conflict recovery, financial export, multi-payer funding, and peer settlement browser suites passed; independent review APPROVE with 0 findings; hosted GitHub Actions CI completed with `conclusion=success` on exact PR head [run 41622668317](https://github.com/KAIYI7/settle-table/actions/runs/41622668317).

## Accepted suggested peer transfers and settlement tracking checkpoint (PR #37)

- **PR #37 Merged**: Reviewed head `ad0c5a9c166fa18d7f0ca7277545097bf9defde4` merged autonomously under orchestrator governance into `main`. GitHub Actions CI passed on exact head ([run 41618225730](https://github.com/KAIYI7/settle-table/actions/runs/41618225730)).
- **Deterministic Peer Settlement Suggestions**: Greedily matches largest debtors to largest creditors in `settletable/settlement.py`, generating minimal and explainable peer reimbursement transfers. Guarantees mathematical cent conservation $\sum_{p \in \mathcal{P}} \text{OutstandingNet}(p) \equiv -\text{UnfundedAmount}$ unconditionally via runtime assertion.
- **Additive SQLite Transfer Ledger & Triggers**: Created `peer_transfers` table in SQLite with database triggers `prevent_peer_transfers_delete` and `prevent_peer_transfers_tamper`. Historical records are never deleted; adjustments require explicit `ReverseTransfer` commands.
- **Over-Settlement & Invariant Guards**: `RecordTransfer` validates sender is debtor ($< 0$), receiver is creditor ($> 0$), `sender_id != receiver_id`, and strictly caps `amount_sen <= min(-sender_debt, receiver_credit)`. Bipartite matching ensures acyclic, deadlock-free transfers.
- **Cross-Feature Balance Guard**: In `Authority._reverse_contribution`, rejects with `active_peer_transfers_exist` if reversing a restaurant contribution would reduce a participant's active contributions below the peer reimbursements they have already received.
- **Organizer UI**: Interactive Peer Settlement card in finalized meal view displaying: All Debts Settled / Reimbursements Pending status badges, unfunded restaurant bill blocker notice, suggested peer transfer cards with "Record Payment" pre-fill button, organizer confirmation form with debtor/creditor dropdowns and optional notes, outstanding net balance reconciliation table, and recorded reimbursement ledger with strikethroughs for reversed transfers. Fully responsive across desktop and 375px mobile viewports.
- **Verification Evidence**: 290/290 Python tests passed (`python -m unittest discover tests`); 16/16 dedicated settlement unit tests passed (`tests/test_settlement.py`); 12/12 real-browser CDP test stages passed (`tools/e2e_browser_test.mjs`); 8/8 headless Chrome peer settlement flow tests passed (`tools/verify_peer_settlement_flow.mjs`); 8/8 headless Chrome multi-payer funding flow tests passed (`tools/verify_multi_payer_flow.mjs`). Calculation engine remains 100% byte-untouched. Independent Standards and Spec reviews returned APPROVE.

## Accepted multi-payer contributions & net balance reconciliation checkpoint (PR #36)

- **PR #36 Merged**: Reviewed head `9fce84a9a4aba68f0dcde6fdd48a2a26edb45183` merged autonomously under orchestrator governance into `main`. GitHub Actions CI passed on exact head ([run 41612866522](https://github.com/KAIYI7/settle-table/actions/runs/41612866522)).
- **Multi-Payer Additive Ledger & Triggers**: Created `payer_contributions` table in SQLite with database triggers `prevent_payer_contributions_delete` and `prevent_payer_contributions_tamper` (including `payment_method` immutability). Contributions are durable, auditable, and immutable; adjustments require explicit `ReverseContribution` commands.
- **Deterministic Cent Conservation**: $\sum_{p \in \mathcal{P}} \text{Base Net Balance}(p) \equiv \text{Total Contributed} - \text{Receipt Total} \equiv -\text{Unfunded Amount}$ enforced unconditionally via runtime assertion in `compute_net_balances`. Includes post-finalization revoked participants in net balance calculations.
- **Notion Cache Decoupling & Historical Backfill**: Notion export lookup decouples from mutable live `revision` by binding to immutable `finalized_revision`. In `Authority.apply`, historical meals finalized prior to schema update automatically backfill `finalized_revision = state['revision']` on post-finalization commands.
- **Responsive UI Card**: Restaurant Funding card renders funding progress, Not/Partially/Fully Funded status badges, net balance reconciliation table with creditor/debtor badges, Fill Remaining shortcut, overpayment rejection, and audited contribution ledger with strikethrough reversals.
- **Verification Evidence**: 273/273 Python tests passed (`python -m unittest discover tests`); 12/12 real-browser CDP test stages passed (`tools/e2e_browser_test.mjs`); 8/8 headless Chrome multi-payer and funding flow tests passed (`tools/verify_multi_payer_flow.mjs`).


## Accepted browser reload synchronization and receipt DOM readiness checkpoint (PR #35)

- **Post-Merge CI Failure Reconciled (Run 41596925620)**: Reconciled `TypeError: Cannot read properties of undefined (reading 'querySelectorAll')` in `tools/e2e_browser_test.mjs` line 283 during `runUiRegressions()` after reload.
- **CDP Reload Context Renewal Guarantee**: In `CDPPage.prototype.reload`, sets `window.__reloading_marker = true` before sending `Page.reload` and waits for `window.__reloading_marker === undefined`. Because Chrome destroys the old window execution context during navigation and creates a fresh window object where the marker is undefined, this eliminates the race condition where callers evaluated post-reload assertions against dying pre-reload contexts.
- **Explicit Observable DOM Readiness & Forensics in `checkReceiptDom`**: In `tools/e2e_browser_test.mjs`, upgraded `checkReceiptDom` to poll `page.waitFor` until both the `Receipt & Charges` card container and all 5 `Quantity case` rows are physically present in the DOM before evaluating. If missing, formats an explicit diagnostic error detailing visible card titles and `#app` inner text instead of throwing an unhandled property dereference.
- **Production Code Untouched**: `settletable/calculation.py` and all server transport/authority/static assets remain 100% byte-untouched.
- **Verification Evidence**: 257/257 Python tests passed (`python -m unittest discover tests`); 12/12 real-browser CDP test stages passed (`tools/e2e_browser_test.mjs`); 8/8 headless Chrome receipt photo & pattern tests passed (`tools/verify_receipt_photo_flow.mjs`); independent review APPROVE with 0 findings; hosted GitHub Actions CI completed with `conclusion=success` on exact PR head [run 41600343451](https://github.com/KAIYI7/settle-table/actions/runs/41600343451).

## Accepted receipt photo CSP and meal ID pattern fixes checkpoint (PR #34)

- **Defect 1 Resolution (CSP `blob:` Image Source Support)**: In `settletable/transport.py`, updated Content Security Policy header to `img-src 'self' data: blob:;`. Retained strict constraints on `default-src 'self'`, `script-src 'self'`, `connect-src 'self'`, `frame-ancestors 'none'`, and all headers. In `settletable/static/app.js`, added `beforeunload` event listener that revokes `state.localPhotoUrl` if starts with `blob:`, guaranteeing zero memory leaks on page reload or navigation away.
- **Defect 2 Resolution (Modern Chromium UnicodeSets Meal ID Pattern)**: In `settletable/static/app.js`, corrected HTML pattern attribute inside JS template literal `renderWelcome()` from `pattern="[A-Za-z0-9_-]+"` to `pattern="[A-Za-z0-9_\\-]+"` so the rendered HTML attribute evaluates to `pattern="[A-Za-z0-9_\-]+"` (valid under UnicodeSets RegExp `v` flag compilation in modern Chromium). Preserved exact accepted characters: ASCII letters, digits, underscore, and hyphen; rejected spaces and punctuation; 0 console syntax errors.
- **Browser Regression Testing & Real Image Decoding Verification**:
  - In `tools/verify_receipt_photo_flow.mjs`, implemented genuine decodable PNG buffer generator (`makeMinimalPngBuffer`) using `node:zlib` emitting valid IHDR, IDAT, and IEND chunks (100x100 RGB).
  - Added `assertImageLoaded(page, selector, description)` asserting `img.complete === true`, `img.naturalWidth > 0`, `img.naturalHeight > 0`, `window.__cspViolations.length === 0`, and `window.__imageErrors.length === 0`.
  - Added Stage [1/8] testing Meal ID pattern compliance and invalid character rejections directly in headless Chrome.
  - Asserted successful image decoding across staged OCR thumbnail (`blob:`), staged zoom modal (`blob:`), attached photo card, refreshed page (`/api/meals/{mealId}/receipt/photo`), and finalized receipt viewer. Zero CSP violations, zero image errors, and zero console regex errors.
  - In `tools/e2e_browser_test.mjs`, resolved reload race condition in capacity regression test to guarantee DOM element availability before asserting disabled state.
- **Verification Evidence**: 257/257 Python tests passed (`python -m unittest discover tests`); 8/8 headless Chrome receipt photo & pattern tests passed (`tools/verify_receipt_photo_flow.mjs`); 12/12 real-browser CDP tests passed (`tools/e2e_browser_test.mjs`); calculation engine remains 100% byte-untouched; independent code & security review APPROVE with 0 findings; hosted GitHub Actions CI completed with `conclusion=success` on exact PR head [run 41596591754](https://github.com/KAIYI7/settle-table/actions/runs/41596591754).

## Accepted receipt photo reliability hardening checkpoint (PR #33)

- **Finding 1 Resolution (Explicit Photo Inclusion Failure Handling)**: In `settletable/transport.py`, `authority.get_receipt_photo()` is invoked synchronously prior to recording in-progress or launching export. Missing photos immediately raise HTTP 404 (`photo_not_found`) and corrupted photos raise HTTP 500 (`photo_corrupted`), preventing silent fallback to text-only exports and preventing recording export completion falsely. In `settletable/notion/exporter.py`, defensive checks reject exports with `missing_receipt_photo_data` if `include_receipt_photo=True` without photo payload.
- **Finding 2 Resolution (Atomic Durability, Missing-File Recovery & SHA-256 Checksum)**: In `settletable/authority.py` (`store_receipt_photo`), inverted operations to atomically move staging file (`tmp_path.replace(dest_path)`) *before* committing SQLite transaction. On failure, unlinks newly created destination file and rolls back SQLite. Replaced old files are unlinked only after successful commit. In `get_receipt_photo()`, validates `len(data) == byte_size` and `hashlib.sha256(data).hexdigest() == sha256`, raising `photo_corrupted` on tampering or truncation. In `snapshot()`, verifies file existence on disk (`photo_path.is_file()`), safely reporting `has_receipt_photo=False` if disk files are unlinked or unmounted.
- **Finding 3 Resolution (Notion In-Place Upgrade, Idempotency & Compact Budget)**: Uniquely tags `export_digest` with `:photo=0` vs `:photo=1`. When an export requests photo inclusion for an existing text-only export, SettleTable queries existing blocks, uploads the photo, and appends the single `image` block in-place using `client.append_block_children()` on the existing page, preventing duplicate Notion pages. Unconditionally reserves 6 base blocks in compact mode so that upgrading a text-only report with an image block strictly maintains total blocks $\le 40$ blocks (`MAX_COMPACT_BLOCKS`). Preserves idempotent no-ops for repeated exports.
- **Verification Evidence**: 257/257 Python tests passed (`python -m unittest discover tests`); 25/25 dedicated receipt photo and reliability tests passed (`tests/test_receipt_photo.py`); 7/7 headless Chrome receipt photo tests passed (`tools/verify_receipt_photo_flow.mjs`); 12/12 real-browser CDP tests passed (`tools/e2e_browser_test.mjs`); calculation engine remains 100% byte-untouched; independent review APPROVE with 0 findings.

## Accepted receipt photo retention, interactive zoom modal, and optional Notion export checkpoint (PR #32)

- PR #32 implementation reviewed against all 10 challenge remediations from `research/phase-3/receipt-photo-architecture-challenge.md` and requirements from `.scratch/receipt-photo-and-notion-export/SPEC.md`.
- **Local Receipt Photo Storage & Isolation**: Created `receipt_photos` table and private directory `<db_dir>/receipt_photos/`. Binary image bytes strictly excluded from `meals.state`, snapshots, and audit logs. Filenames strictly synthesized as `{safe_meal_id}_{sha256[:16]}.{ext}`, sanitizing path separators and Windows Alternate Data Streams (ADS). All serving resolves `target_path.is_relative_to(storage_dir.resolve())`. Temporary files cleaned up reliably on failure.
- **Organizer-Only Access Control & CSRF**: Enforced authenticated organizer authority across `POST /ocr/extract`, `POST /receipt/photo`, `GET /receipt/photo`, and `DELETE /receipt/photo` (401 for unauthenticated, 403 for diners/non-members). Extended `X-SettleTable-Action: 1` and Origin/Referer matching to all `POST` and `DELETE` methods.
- **Finalized Meal Immutability**: `store_receipt_photo` and `delete_receipt_photo` acquire SQLite `BEGIN IMMEDIATE` locks and assert `state.get('calculation') is None`, rejecting mutations on finalized meals with HTTP 409 `finalized`. Organizers retain read-only GET access post-finalization.
- **Calculation Engine Invariance**: `settletable/calculation.py` remains 100% byte-untouched. Photo storage and deletion produce 0 changes to `receipt_digest` or financial apportionment math.
- **Responsive Preview & Zoom Modal UI**: Implemented responsive preview bar during OCR candidate staging and attached receipt photo card in organizer view with View & Zoom, Replace Photo, and Remove Photo. Added accessible `#receipt-modal` with zoom in/out/reset, mouse wheel zoom, drag-to-pan, touch support, and Escape key dismissal. Preserved photo access after finalization.
- **Notion 2-Step File Upload & Budget**: Implemented Notion official 2-step single-part file upload API (`POST /v1/file_uploads` then `POST /v1/file_uploads/{id}/send` with standard library multipart) and referenced via `image.file_upload.id` block. Enforced compact block budget reserving 6 non-table blocks to guarantee total page blocks remain $\le 40$ blocks without assertion failure.
- **View-Only Sharing Guidance & Privacy Warning**: Added organizer checkbox `[ ] Include original receipt photo in Notion report` (default OFF, enabled only when photo exists). Rendered verified 4-step manual "Publish to web" guidance upon export with an explicit privacy warning regarding confidential data exposure.
- **Verification Evidence**: 249/249 Python tests passed (`python -m unittest discover tests`); 17/17 dedicated receipt photo tests passed (`tests/test_receipt_photo.py`); 12/12 automated real-browser CDP test stages passed (`tools/e2e_browser_test.mjs`); dedicated 7-stage headless Chrome receipt photo suite passed (`tools/verify_receipt_photo_flow.mjs`); independent review APPROVE (`research/phase-3/receipt-photo-independent-review.md`) with 0 critical/high/medium findings.

## Accepted OCR fixture privacy sanitization and all-items scope guard checkpoint (PR #31)

- [PR #31](https://github.com/KAIYI7/settle-table/pull/31) reviewed source head `3d5f05c580b6a2edcaf7e67bda521cd4516c5fb2`; merge `7ca36be35006e296683765288acecc26cec4e210` verified on remote `main`. The merge preserves both parents and exact tree contents.
- **OCR Fixture Privacy Sanitization**: Sanitized 17 identifying business and visit-specific tokens in `tests/fixtures/ocr/tokens.json` (`brewhouse_receipt.png`) into synthetic Malaysian dining equivalents (brand name, operating entity, registration, street address, contact info, tax ID, check ID, table) without modifying 2D bounding boxes, confidence scores, menu items, line totals, financial summary, or tax summary table.
- **All-Items Scope Guard**: Synchronized `eligible_item_ids` for `all_items` adjustments in `settletable/static/app.js` (`add-item-form`) upon manual item addition, satisfying backend authority requirements and eliminating client-side `invalid_input` rejections while leaving `fixed_items` unaffected.
- **Authority Invariant Regression**: Added regression assertion in `tests/test_authority.py` confirming `ReplaceReceipt` commands with incomplete `all_items` adjustments are strictly rejected with `AuthorityError('invalid_input')`.
- **Low-Priority Display Observations Recorded**:
  1. *Merchant Logo Noise*: Decorative graphics and adjacent background text in the logo area can yield partial noise tokens in pre-filled candidate merchant names (editable in UI).
  2. *Modifier Concatenation*: Multi-line dish options (e.g. `- Side Dish x 1`) are merged onto the parent item row with an em-dash (`— Side Dish`).
  3. *Menu Code Preservation*: Printed menu codes (e.g. `F38`, `F62`, `VL`) remain within extracted item labels.
  4. *Zero-Priced Legitimate Items*: Complimentary items (e.g. `Ice Water RM 0.00`) are extracted as 0-sen items, preserving exact receipt reconciliation while remaining deletable by the organizer.
- **Verification Evidence**: 232 full-suite Python tests passed in 65.0s; 12 automated real-browser CDP test stages passed; financial scope and conflict recovery browser suites passed; independent code review (conversation `c8bb5895-516a-4bff-8f41-6df5c04f3052`) returned APPROVE with zero critical/high/medium findings; [hosted exact-head CI run 41467848944](https://github.com/KAIYI7/settle-table/actions/runs/41467848944) completed successfully on `3d5f05c580b6a2edcaf7e67bda521cd4516c5fb2`.
- **Operational Boundary**: Git history preserved intact without rewrites. Real OCR extraction succeeded for The Brew House receipt; video capture did not complete finalization. Mandatory human verification and organizer seal preserved.

## Accepted Malaysian restaurant receipt OCR corrections checkpoint (PR #30)

- [PR #30](https://github.com/KAIYI7/settle-table/pull/30) reviewed source head `03574cbff7687808fcb6ac2bbcf769ff47cffe72`; merge `f1661188845d086f5217d68bbee26d7103fe9830` verified on remote `main`. The merge preserves both parents and exact tree contents.
- **Currency-Prefixed Negative Numbers**: Enhanced `MONEY_PATTERN` regex and `parse_sen` to parse negative currency numbers (e.g. `-RM0.02`, `-RM 0.02`, `RM -0.02`, `(RM 0.02)`) without floating-point conversion, yielding exact `-2` sen for BNM rounding.
- **Post-Total Tax Summary Isolation**: Guarded bill adjustment parsing with a `total_found` barrier and `TAX SUMMARY` block detector, preventing informational tax basis breakdown tables (such as taxable basis RM 169.20 printed beneath the grand total) from overwriting extracted bill adjustments (`tax_sen`).
- **Item Label & Modifier Cleaning**: Added `clean_item_label` to strip trailing currency markers (`RM`, `MYR`, `$`), trailing modifier multipliers (`x 1`, `× 1`), and leading item multipliers, normalizing modifier lines with clean em-dashes (` — `).
- **Spatial Row Clustering**: Upgraded `group_lines_into_rows` using vertical bounding-box overlap (`overlap >= min_h * 0.35` and `|y - r_mid_y| <= min_h * 0.55`) so multi-line modifiers cluster reliably without contaminating adjacent items.
- **Granular Mismatch Feedback**: Enhanced frontend mismatch alert and scan toasts to detail exact computed charges sum vs printed bill total and exact discrepancy in sen.
- **Verification Evidence**: 232 full-suite Python tests passed (including dedicated Brew House receipt regression and monetary parser tests); 12 automated real-browser CDP test stages passed; financial scope and conflict recovery browser suites passed; independent code review (conversation `e5bdaee4-90ba-45c4-8257-3da97ef76b78`) returned APPROVE with zero critical/high/medium findings; [hosted exact-head CI run 41416668397](https://github.com/KAIYI7/settle-table/actions/runs/41416668397) completed successfully on `03574cbff7687808fcb6ac2bbcf769ff47cffe72`.
- **Operational Boundary**: Zero authentic receipt images, ONNX models, virtualenvs, or personal paths committed. Genuine commercial receipt tokens stored as synthetic 2D bounding boxes in `tests/fixtures/ocr/tokens.json`.

## Accepted Notion table row schema and error diagnostics checkpoint (PR #28)

- [PR #28](https://github.com/KAIYI7/settle-table/pull/28) reviewed source head `02302e95bba8ce9adab621d9c523e59f09d31ffe`; merge `5c0a8d88e049d956241dd23328cc2ef4af499858` verified on remote `main`. The merge preserves both parents and exact tree contents.
- **Notion Block Schema Compliance**: Formatted all 9 `table_row` child block constructors across compact and full formats with `"object": "block"`, conforming strictly to the Notion REST API specification for table children blocks and preventing HTTP 400 `validation_error`.
- **Mock Client Parity**: Added strict table row block validation to `MockNotionClient.create_page`, ensuring mock tests enforce identical schema constraints and prevent test/runtime drift.
- **Granular Export Diagnostics**: Disentangled Notion HTTP 404 (`page_not_found`, unshared/missing page) from HTTP 400 (`validation_error`), returning sanitized, descriptive error strings in `export_digest` so users receive immediate, actionable feedback in the UI.
- **Verification Evidence**: 230 full-suite Python tests passed (including 4 new regression tests covering block schemas and error diagnostics); 12 automated real-browser CDP test stages passed; independent code review (conversation `ecebd01c-1413-4d68-a9a7-cf720a72e231`) returned APPROVE with zero critical/high/medium findings; [hosted exact-head CI run 41386556198](https://github.com/KAIYI7/settle-table/actions/runs/41386556198) completed successfully on `02302e95bba8ce9adab621d9c523e59f09d31ffe`.
- **Operational Boundary**: Live Notion workspace credentials and calls remain strictly on the user's local instance; zero credentials, personal tokens, or authentic receipts committed or leaked.

## Accepted OCR parsing and Notion redirect security checkpoint (PR #26)

- [PR #26](https://github.com/KAIYI7/settle-table/pull/26) reviewed source head `d65d383857229600252a7c1d206bb5e59280a0f1`; merge `e06f606d5f9ff822ce54de7334fe9bc4daf1e63b` verified on remote `main`. The merge preserves both parents and exact tree contents.
- **Local OCR Parser & RapidOCR Compatibility**: Guarded summary line triggers (`SUBTOTAL`, `ROUNDING`, `DISCOUNT`, `SERVICE CHARGE`, `SST/GST`) to require non-empty monetary amounts so table column headers do not terminate line item scanning prematurely; added trailing item quantity parsing with non-zero safeguards; added polymorphic return handling for `RapidOCROutput` dataclass (`rapidocr` 3.10+) as well as `(result_list, elapse_list)` tuple / list variants (`rapidocr_onnxruntime`).
- **Notion Redirect Defense**: Installed `DisallowRedirectHandler` on `NotionHttpClient._opener` to block HTTP 301/302/303/307/308 redirects, eliminating risk of Bearer token forwarding leakage across redirect chains. Notion REST API version stable at `2022-06-28`.
- **Reproducible Setup & Documentation**: Added `requirements-ocr.txt` (pinned dependencies: `rapidocr-onnxruntime>=1.2.3`, `onnxruntime>=1.17.0`, `pillow`, `numpy`, `shapely`, `pyclipper`, `opencv-python-headless`), `docs/ocr-setup.md` for dedicated environment setup, and `docs/notion-smoke-test.md` specifying explicit product owner setup, permissions, and synthetic test data protocol.
- **Verification Evidence**: 226 full-suite Python tests passed (including 5 new regression tests); 12 automated real-browser CDP test stages passed; independent code review (conversation `dd8929f9-5be4-467c-8547-cd29620df349`) returned APPROVE (0 critical, 0 high, 0 medium findings; 2 low polish points remediated); [hosted exact-head CI run 41314417879](https://github.com/KAIYI7/settle-table/actions/runs/41314417879) completed successfully on `d65d383857229600252a7c1d206bb5e59280a0f1`.
- **Operational Boundary**: Live Notion workspace access and token usage remain strictly gated behind explicit user authorization. No real private receipt data committed or shared externally. Full local MVP acceptance, physical-mobile, screen-reader, and independent UAT retest remain outstanding.

## Accepted focused independent-UAT UI corrections (PR #23)

- [PR #23](https://github.com/KAIYI7/settle-table/pull/23) reviewed source `3b24faa4bdd5a705854b4c31b2fa58d36597e69e`; final head `e00f914c49e04c72e13a57c58fc0cb70463a9cc7` adds evidence only. Merge `449dc8c2322c7b64a429e28db8290da38f141975` verified remotely with both expected parents and a tree equal to the final PR head.
- Receipt & Charges uses existing `formatRat`: x1, x2, x3, x½ and x⅓. Quick assignment is visibly/native disabled when a whole portion is unavailable; associated explanation and existing desktop/mobile Details / Split support reallocation.
- [Evidence and independent reviews](research/phase-3/uat-ui-corrections.md): 213 Python tests and 12 Chrome stages pass after review; standards and specification reviews PASS with zero findings; independent focused browser rerun PASS. [Hosted exact-head CI](https://github.com/KAIYI7/settle-table/actions/runs/40820110948) passed 213 tests and all 12 browser stages.
- Financial engine, authoritative quantities/amounts, organizer authorization, conflict behavior and finalization/native confirmation code unchanged. Unknown UAT database/listener and unrelated resources preserved. Original independent UAT remains incomplete; separate independent retest required. No release/deployment authorization.

## Repository checkpoint

- Repository: [KAIYI7/settle-table](https://github.com/KAIYI7/settle-table); project name SettleTable. Local filesystem directory unchanged.
- Baseline commit: [`69895457d9e3524c90df24f3a21c284ea70cef6c`](https://github.com/KAIYI7/settle-table/commit/69895457d9e3524c90df24f3a21c284ea70cef6c), `chore: establish SettleTable project baseline`.
- Annotated checkpoint: [`phase2-accepted`](https://github.com/KAIYI7/settle-table/tree/phase2-accepted); tag object `42acff45556c3a0ed6fd85ab751cfdba25791023`.
- Verified 2026-10-17: remote `main` and peeled tag target both equal the baseline SHA; local tag object type is `tag`. [Audit](research/publishing/prepublish-audit.md), [remote verification](research/publishing/checkpoint.json).
- This status update follows the baseline commit; later documentation/work commits may advance `main` while the checkpoint tag remains fixed at the accepted baseline.

**Accepted slice evidence:** [interface](docs/calculation-interface.md); 15 test methods pass in the main agent's run; [66 independent spec checks](research/phase-3/spec-review.md) and [11 engineering probe groups](research/phase-3/engineering-review.md) pass. No material review finding remains for the bounded calculation contract. These counts are functional checks, not statistical accuracy or coverage estimates.

## Accepted authority checkpoint

- PR #1 reviewed head: `59cba5feb25423ebd43ebee17b7666d84f83d584`; premerge main: `7db4ef155149526f6c646158814d1851b5fdb21b`. Both matched actual remote refs and GitHub metadata before merge.
- Merge commit: [`af7ba147642b8b8e9a5aee973a95c59d46c38b9a`](https://github.com/KAIYI7/settle-table/commit/af7ba147642b8b8e9a5aee973a95c59d46c38b9a). Its two parents are exactly premerge main and reviewed head, preserving the small implementation history. The merged tree equals the reviewed head.
- Annotated checkpoint: [`authority-v1-accepted`](https://github.com/KAIYI7/settle-table/tree/authority-v1-accepted); tag object `389eb52462cfe0a17a4456504a41214956ae15bc`. Actual remote main and peeled tag target verified 2026-10-17 at the merge SHA; local object type is `tag`. Subsequent documentation/foundation commits may advance main without moving this checkpoint.
- [Local authority evidence](research/phase-3/authority-acceptance.md): 60 full-suite methods pass, with independent source/spec and security review and material findings resolved. This records bounded local acceptance, not Internet identity or full-product readiness.

## Accepted invitation and session lifecycle checkpoint (PR #4)

- PR #4 reviewed head: `0f63ecd00ea71c5c667c70ef750012f594ae3add`; premerge main: `7253cf9e2888802d00fb037f2a1fbcd517868e73`.
- Merge commit: [`75a3511982091d6c49f97a29dbf7a9fcb6de0205`](https://github.com/KAIYI7/settle-table/commit/75a3511982091d6c49f97a29dbf7a9fcb6de0205). Merged autonomously under orchestrator governance policy.
- Verified evidence: 79 full-suite methods pass locally; [independent security review](research/phase-3/invitation-security-review.md) records unconditional PASS/GO across all gates and all 5 post-implementation review findings; hosted GitHub Actions run [39404379865](https://github.com/KAIYI7/settle-table/actions/runs/39404379865) completed successfully on the exact PR head SHA.
- [Invitation acceptance evidence](research/phase-3/invitation-acceptance.md) and [invitation specification](.scratch/invitation-lifecycle/SPEC.md). Single SQLite transaction boundary preserved; zero bearer secret persistence; deterministic math unchanged.

## Accepted same-origin transport adapter checkpoint (PR #5)

- PR #5 reviewed head: `1f1fb789f5bc5cf93b04c0ec6063b5f63969a9b2`; premerge main: `52c6f731cbb2818610eb6793f0b2f15e81d773ee`.
- Merge commit: [`43b827f486ffa06d532c37d89826ccf2aa50051f`](https://github.com/KAIYI7/settle-table/commit/43b827f486ffa06d532c37d89826ccf2aa50051f). Merged autonomously under orchestrator governance policy (GitHub PR #5 closed upon direct merge to main).
- Verified evidence: 101 full-suite methods pass locally in 66.240s; [independent architecture challenge](research/phase-3/transport-adapter-challenge.md) and [post-implementation security review](research/phase-3/transport-adapter-review.md) record PASS/GO across all gates and all 6 remediations; hosted GitHub Actions run [39408626484](https://github.com/KAIYI7/settle-table/actions/runs/39408626484) completed successfully on the exact PR head SHA.
- [Transport specification](.scratch/transport-adapter/SPEC.md) and [transport implementation](settletable/transport.py). Wire limits (header 4 KB/16 KB, body 1 MB, depth 10, int 19 digits), CSRF defense (`X-SettleTable-Action: 1`, strict origin check), unauthenticated landing isolation (`Authority.inspect_invitation`), and host-only secure cookies enforced.

## Accepted transport hardening checkpoint (PR #6)

- PR #6 reviewed head: `65ae4bd7987fc5208f8705b6197171ef0728c057`; premerge main: `b0ca641659424751f727c9d9685121b6d9e03d4d`.
- Merge commit: [`e7a8a82918353d82188746c0d7b19fec499b2698`](https://github.com/KAIYI7/settle-table/commit/e7a8a82918353d82188746c0d7b19fec499b2698). Merged autonomously under orchestrator governance policy (GitHub PR #6 closed upon direct merge to main).
- Verified evidence: 104 full-suite methods pass locally in 63.364s; [independent security review](research/phase-3/transport-hardening-review.md) records unconditional PASS/GO across all 5 audit gates; hosted GitHub Actions run [39420125202](https://github.com/KAIYI7/settle-table/actions/runs/39420125202) completed successfully on the exact PR head SHA.
- [Deployment boundary document](docs/deployment-boundary.md) establishes Tier 1 ingress stream limits vs Tier 2 WSGI defense-in-depth; loopback bootstrap rejects proxy headers (`X-Forwarded-*`); provisioning returns strictly organizer credentials; session rotation omits raw bearer tokens from JSON in cookie contexts.

## Accepted same-origin browser MVP checkpoint (PR #7)

- PR #7 reviewed head: `cd4973c1cd73dae8f6ebe8e97640e04604ae16f6`; premerge main: `b5900f892cb86fc50a1bb73507d9d7e50275525b`.
- Merge commit: [`67f7190638696f8592cd49fa489b5f12f64b49e1`](https://github.com/KAIYI7/settle-table/commit/67f7190638696f8592cd49fa489b5f12f64b49e1). Merged autonomously under orchestrator governance policy (GitHub PR #7 closed upon direct merge to main).
- Verified evidence: 109 full-suite methods pass locally in 63.725s; [independent architecture challenge](research/phase-3/browser-mvp-challenge.md) and [post-implementation review](research/phase-3/browser-mvp-review.md) record PASS/GO across all 6 audit gates with all 4 remediations verified; hosted GitHub Actions run [39423753289](https://github.com/KAIYI7/settle-table/actions/runs/39423753289) completed successfully on the exact final PR head SHA.
- [Browser MVP specification](.scratch/browser-mvp/SPEC.md) and frontend implementation (`settletable/static/`). Zero external CDNs/fonts, strict Content-Security-Policy, DOM XSS immunity (`escapeHtml()`), $44\text{px}$ touch targets, human receipt confirmation digest binding, HTTP 409 Conflict handling, and deterministic cent-conserving calculation breakdown.

## Accepted browser MVP E2E fixes and real browser validation checkpoint (PR #8)

- PR #8 reviewed head: `172d56f8f5337fc9a518fb1935c754dc9335e76a`; premerge main: `c15a07204f447738bc0cb9d75e47854cf468249a`.
- Merge commit: [`a8436fdcb8848fe5ce299c883a26a2b0c2e64dfc`](https://github.com/KAIYI7/settle-table/commit/a8436fdcb8848fe5ce299c883a26a2b0c2e64dfc). Merged autonomously under orchestrator governance policy (GitHub PR #8 closed upon direct merge to main).
- Verified evidence: 113 full-suite methods pass locally in 60.448s; 8/8 automated real-browser CDP test stages pass in 3.2s via Headless Chrome (`tools/e2e_browser_test.mjs`); [independent security and code review](research/phase-3/browser-e2e-fixes-review.md) records unconditional PASS/GO across all 6 audit gates; hosted GitHub Actions run [39442110445](https://github.com/KAIYI7/settle-table/actions/runs/39442110445) completed successfully on the exact final PR head SHA.
- Key fixes: receipt-entry `ReplaceReceipt` contract supplies authoritative `subtotal_sen` and `total_sen` without fabricating zero amounts; `renderFinalizedCalculation` maps participant totals directly from `calculation.consumption` records; mutation handlers decouple forced snapshot refresh and sequence numbering guards against out-of-order poll clobbering; strict integer MYR input parsing rejects malformed strings and float drift.

## Accepted cross-platform browser test infrastructure & CI automation checkpoint (PR #9)

- PR #9 reviewed head: `5a879c5ed5ef7c95939da0b4fd98e2516d086e1b`; premerge main: `49f966c5c007c089cbb6f183cf53549cf06aa7c2`.
- Merge commit: [`1b693f56cb3cf3df0e7cb84727cccaf594d1e769`](https://github.com/KAIYI7/settle-table/commit/1b693f56cb3cf3df0e7cb84727cccaf594d1e769). Merged autonomously under orchestrator governance policy (GitHub PR #9 closed upon direct merge to main).
- Verified evidence: 113 full-suite methods pass locally in 47.362s; 8/8 automated real-browser CDP test stages pass in 3.2s via Headless Chrome (`tools/e2e_browser_test.mjs`); [independent security and code review](research/phase-3/test-infra-review.md) records unconditional PASS/GO across all 5 audit gates; hosted GitHub Actions run [39508712147](https://github.com/KAIYI7/settle-table/actions/runs/39508712147) completed successfully on the exact final PR head SHA in `ubuntu-24.04`, validating both Python tests and real browser E2E journeys in CI.
- Key improvements: dynamic cross-platform discovery for Chrome and Python binaries eliminating hardcoded paths; invitation bearer token redaction in console logs (`/invite/[REDACTED]`); container flags (`--headless=new`, `--no-sandbox`, `--disable-dev-shm-usage`, `--disable-gpu`); zero-extra-spend CI integration without paid test cloud services.

## Accepted bounded local OCR pipeline and Malaysian SST parser checkpoint (PR #10)

- PR #10 reviewed head: `b6dc100d04961917f93539fc4107127e9fe558d4`; premerge main: `0847e51f0436894371fa4fce23be2a9d2bf58054`.
- Merge commit: [`3455a57223d1e1582d1c3c8f8185186484364074`](https://github.com/KAIYI7/settle-table/commit/3455a57223d1e1582d1c3c8f8185186484364074). Merged autonomously under orchestrator governance policy (GitHub PR #10 closed upon direct merge to main).
- Verified evidence: 136 full-suite methods pass locally in 71.784s; 8/8 automated real-browser CDP test stages pass in 3.2s via Headless Chrome (`tools/e2e_browser_test.mjs`); [independent architecture challenge](research/phase-3/ocr-architecture-challenge.md) and [post-implementation security review](research/phase-3/ocr-implementation-review.md) record PASS across all 6 audit gates with all remediations verified; hosted GitHub Actions run [39512879579](https://github.com/KAIYI7/settle-table/actions/runs/39512879579) completed successfully on the exact final PR head SHA in `ubuntu-24.04`.
- Key capabilities: local CPU inference via RapidOCR/ONNX Runtime with zero cloud vision fallback; route-aware binary ingress on `POST /api/meals/{meal_id}/ocr/extract` bypassing JSON parsing; raw binary header dimension checks protecting against decompression bombs ($\le 4096 \times 4096$, $\le 16\text{MP}$); strict wire MIME type vs magic byte verification; organizer authorization requirement (403 for diners, 401 unauthenticated); zero database mutation on advisory extraction; Malaysian dining receipt domain parsing (Wan Sheng tax-inclusive rule preserving calculation subtotal invariants, Kechara rule preventing fact invention, statutory SST/service charges, BNM $\pm 1, \pm 2$ sen rounding); mandatory UI human receipt verification and cryptographic digest sealing before finalization; deterministic CI test replay using token fixtures without native ONNX wheels.

## Accepted bounded optional asynchronous Notion reporting checkpoint (PR #11)

- PR #11 reviewed head: `8a83ba2287ad27764a51147bd594e4b4c4eba966`; premerge main: `a06142ce9ec60a927fa1e1ec074d0089a8183141`.
- Merge commit: [`d34ff75caf3047f5a8515d0b3503e3a3948871ae`](https://github.com/KAIYI7/settle-table/commit/d34ff75caf3047f5a8515d0b3503e3a3948871ae). Merged autonomously under orchestrator governance policy (GitHub PR #11 closed upon direct merge to main).
- Verified evidence: 150 full-suite methods pass locally in 62.383s; 9/9 automated real-browser CDP test stages pass in 3.4s via Headless Chrome (`tools/e2e_browser_test.mjs`); [independent architecture challenge](research/phase-3/notion-architecture-challenge.md) and [post-implementation security review](research/phase-3/notion-implementation-review.md) record unconditional GO/PASS across all 6 audit gates with all 7 remediations verified; hosted GitHub Actions run [39515609945](https://github.com/KAIYI7/settle-table/actions/runs/39515609945) completed successfully on the exact final PR head SHA in `ubuntu-24.04`.
- Key capabilities:
  1. **Strict Decoupling & Fault Isolation**: Live meal collaboration, item claiming, receipt review, and finalization execute 100% offline or air-gapped without Notion. Notion export failures leave SQLite meal state, claims, and calculations completely intact with zero database rollbacks.
  2. **Secret Hygiene & Token Redaction**: Notion API tokens (`secret_...` and `ntn_...`) are strictly excluded from SQLite persistence. Wire logs (`transport.redact_log_string`), error strings, and exception handlers scrub integration tokens to prevent leakage in server output or HTTP error bodies.
  3. **One-Way Canonical Projection & Financial Invariance**: Apportionment exported to Notion is mapped directly from authoritative `calculation.consumption` integer sen amounts. Notion formulas, rollups, or calculations are strictly zero; money formatting uses integer division without floating-point drift.
  4. **Block-Quota Efficiency (Compact Default)**: Generates $\le 40$ blocks per meal (1 callout + 2 headings + 2 tables + rows + divider + audit paragraph), yielding $>70\%$ block savings over relational multi-page designs and protecting Free tier workspace lifetime block quotas (1,000 blocks).
  5. **REST Schema Constraints**: Page-parent export strictly limits properties to `title` (per Notion REST constraint for non-database parents) while placing financial metadata inside the top Callout block; table block dimensions strictly match row cell arrays.
  6. **Concurrency & Idempotency State Machine**: SQLite tracking table `notion_exports` maintains `(meal_id, finalized_revision)` through `in_progress` -> `completed` state machine, rejecting duplicate concurrent clicks with 409 `export_in_progress` or 409 `already_exported` while permitting clean recovery on failure (`clear_notion_export`).
  7. **WSGI Worker Starvation Defense**: Synchronous `time.sleep` on HTTP 429/503 `Retry-After` is strictly capped at $\le 2.0$ seconds (max 2 retries, 5s cumulative timeout).
  8. **Deterministic CI Portability**: `MockNotionClient` validates exact REST constraints without opening outbound sockets, allowing all 150 Python unit tests and 9-stage Chrome CDP browser tests to execute at $0.00 spend.

## Accepted Phase 3 consolidation and operational review checkpoint (PR #12)

- PR #12 reviewed head: `de890fadebc8c3fb7f5eb0a1521e947b0f3a3be5`; premerge main: `edeb0e82daeb7fe44a9582d92ee0bc835aa9488a`.
- Merge commit: [`5a5231d5250902968d3f716c9771ac8e23cf41ce`](https://github.com/KAIYI7/settle-table/commit/5a5231d5250902968d3f716c9771ac8e23cf41ce). Merged autonomously under orchestrator governance policy (GitHub PR #12 closed upon direct merge to main).
- Verified evidence: 154 full-suite methods pass locally in 75.858s; 9/9 automated real-browser CDP test stages pass in 3.6s via Headless Chrome (`tools/e2e_browser_test.mjs`); [independent security and code review](research/phase-3/consolidation-review.md) records unconditional GO across all 5 audit gates; hosted GitHub Actions run [39531452344](https://github.com/KAIYI7/settle-table/actions/runs/39531452344) completed successfully on the exact final PR head SHA in `ubuntu-24.04`.
- Key consolidations & operational hardening:
  1. **OCR Candidate Review Boundary & Staging**: Browser stages extracted OCR proposals strictly in client memory (`state.ocrCandidate`) without writing to SQLite. File uploads no longer trigger automatic `ReplaceReceipt`. The UI renders clear confidence scores, route badges (`⚠️ Needs Correction` vs `✓ Ready for Review`), and verification issues. Explicit `Accept & Apply to Receipt` (dispatches `ReplaceReceipt`) and `Discard` buttons ensure organizer intentionality, and mandatory physical receipt review (`ReviewReceipt`) remains strictly required before meal finalization.
  2. **Decoupled Asynchronous Notion Delivery**: `POST /api/meals/{meal_id}/export/notion` executes in a background daemon thread (`threading.Thread`) and returns HTTP `202 Accepted` immediately by default (preserving `?sync=1` for testing), completely preventing WSGI worker thread starvation for live diners during external API latency. Export progress is pollable via `GET /api/meals/{meal_id}/export/notion`.
  3. **Pre-Creation Title Reconciliation & Delivery Semantics**: Exporter queries parent block children prior to creating a Notion page; if a page titled `🍽️ SettleTable: {merchant} ({meal_id})` already exists, it adopts that page ID and avoids creating duplicate pages on lost responses. Semantics are explicitly documented as at-least-once with pre-creation title reconciliation (no false claims of exactly-once delivery across non-transactional REST APIs).
  4. **Free Block Budget Enforcement**: Compact mode mathematically bounds total exported blocks to $\le 40$ blocks for arbitrary meal sizes (tested with 25 diners and 60 items) via intelligent rollup rows (`"Other diners (N participants)"` and `"Other receipt items (N items)"`), protecting multi-member Notion Free workspace lifetime block limits (1,000 blocks). Unconstrained breakdowns remain available via `mode='full'`.
  5. **OCR Operational Validation & Zero-Dependency Local Demo**: `RapidOcrEngine` seamlessly supports both `rapidocr` and `rapidocr_onnxruntime` distributions. `tools/run_demo.py` provides a `--mock-ocr` flag allowing evaluators to experience the complete local demonstration out of the box with zero native ML or ONNX dependencies.
  6. **Invariant Integrity**: `settletable/calculation.py` remains 100% byte-untouched; cryptographic hash domains (`settletable-receipt-v1`, `settletable-local-session-v1`, `settletable-invitation-v1`, `settletable-command-v1`) are completely intact.

## Accepted User-Acceptance Readiness Checkpoint

- Feature branch reviewed head: `78f92ad6937e008cbb39e240212a4c148fc2834b`; premerge main: `df0fcdbeeeecba0d6b67bcfa0faeb0cfdcf2d752`.
- Merge commit: [`84acc18`](https://github.com/KAIYI7/settle-table/commit/84acc18). Merged autonomously under orchestrator governance policy.
- Verified evidence: 159 full-suite methods pass locally in 59.603s; 9/9 automated real-browser CDP test stages pass in 3.6s via Headless Chrome (`tools/e2e_browser_test.mjs`); independent security and code review completed with all 3 material findings resolved and verified by regression tests.
- Key user-acceptance readiness capabilities:
  1. **OCR Edit-Before-Accept Experience**: Staged OCR proposals can be corrected directly in an inline table (item names, quantities, unit prices, adjustments, and included tax) before applying to the draft receipt. Live typing recalculates candidate subtotals and totals in real time. Dynamic add/delete buttons permit adding missing items or removing misrecognitions. Validation enforces positive line amounts and item existence before dispatching `ReplaceReceipt`. Physical bill verification gate (`ReviewReceipt`) remains mandatory before finalization.
  2. **Negative BNM Cash Rounding Preservation**: Input parser (`parseSen`) and candidate synchronizer support negative minor units, ensuring Bank Negara Malaysia cash rounding adjustments (e.g. -RM 0.02) preserve sign and do not invert during candidate editing or recalculation.
  3. **Local Inference Demarcation**: UI badge and documentation explicitly identify OCR as Server-Side Local Inference (RapidOCR CPU ONNX), eliminating misleading "on device" claims.
  4. **Notion API Reliability & Pagination**: `NotionHttpClient.query_block_children` implements cursor pagination (`max_pages=5`, `page_size=100`). Pre-creation title reconciliation re-raises `NotionAuthError`, `NotionValidationError`, `NotionNotFoundError`, and `NotionRateLimitError` rather than silently suppressing them.
  5. **Background Processing & Worker Starvation Defense**: Ephemeral thread lifecycle is explicitly documented. The synchronous export override `?sync=1` is disabled by default behind `allow_sync_export=False` (configured via `SETTLETABLE_ALLOW_SYNC_EXPORT=1`), preventing WSGI worker starvation in public environments. In-progress exports time out cleanly after 60s, recording `status='failed'` and allowing clean recovery. Background export records granular error codes (`notion_rate_limited`, `notion_auth_error`, `invalid_input`, `notion_error`).
  6. **Secret Hygiene & Demo Accuracy**: Verified that `tools/run_demo.py` prints zero credentials or session links to stdout; sessions are managed via host-only secure cookies and in-app invitation copying. Comprehensive [User Acceptance Testing (UAT) Handover](docs/uat-handover.md) guide delivered.
  7. **OCR Acceptance Rationale & Scope Defense**: Fixed `Action rejected: invalid_input` on candidate acceptance by preserving adjustment rationale across candidate synchronization and supplying safe non-empty fallback rationales in `_build_command`, strictly satisfying authority `_text(rationale, 500)` constraints. Sanitized `eligible_item_ids` against candidate item IDs with all-item fallback. Verified by regression unit tests (`tests/test_transport.py`), independent review (unconditional GO), and real browser Chrome CDP acceptance testing (`tools/e2e_browser_test.mjs`). Commit [`33b0d0a`](https://github.com/KAIYI7/settle-table/commit/33b0d0a).
  8. **Session Navigation & Safe Exit**: Implemented explicit Home navigation and participant identification (`👑 Organizer` or `🍽️ Diner`) in the top header and room navigation bar. Added a safe session-exit mechanism (`Leave Room` buttons triggering `POST /api/session/clear` with `Max-Age=0` Set-Cookie headers) preventing users from feeling trapped in active diner sessions. Added a prominent `⚠️ Same-Browser Profile Notice` alert on invitation landing screens explaining that redeeming an invitation in the current browser replaces the active session and advising separate browser profiles for multi-user UAT testing. Preserved zero-backdoor and secret hygiene invariants. Verified by unit tests (`test_session_clear_endpoint_clears_cookie_safely`), independent review (unconditional GO), and real browser CDP multi-context tests. Commit [`30723ca`](https://github.com/KAIYI7/settle-table/commit/30723ca).

## Accepted scanned receipt editor UI/UX polish checkpoint (PR #13)

- PR #13 reviewed head: `1b0a36c`; premerge main: `fdbf617`.
- Merge commit: [`c0a9b1d`](https://github.com/KAIYI7/settle-table/commit/c0a9b1d). Merged autonomously under orchestrator governance policy.
- Verified evidence: 163 full-suite methods pass locally in 96.6s; 9/9 automated real-browser CDP test stages pass in 3.4s via Headless Chrome (`tools/e2e_browser_test.mjs`); independent code and UX review completed with unconditional GO; hosted GitHub Actions run [39688094458](https://github.com/KAIYI7/settle-table/actions/runs/39688094458) completed successfully on the exact PR head SHA.
- Key improvements (Objective 1):
  1. **Responsive Dual Layout**: Desktop ($1280 \times 800$) displays a spacious, clean table with explicit "Line Total (RM)" header and calculated unit-price estimates (`@ RM X.XX ea`). Narrow/mobile viewports ($< 640\text{px}$, verified at $375 \times 667$) seamlessly transform into stacked CSS Grid cards without DOM tearing, keeping identical input element IDs and maintaining focus.
  2. **Touch Targets & Spacing**: All mobile interactive buttons (remove item, add item, accept, discard) satisfy standard touch targets ($\ge 44 \times 44\text{px}$).
  3. **Preserved Invariants**: Inline editing, keyboard navigation, signed adjustments (Bank Negara Malaysia cash rounding -RM 0.02), live totals synchronization, and Accept/Discard workflows completely preserved.

## Accepted organizer-authorized allocation & zero-session dining checkpoint (PR #14)

- PR #14 reviewed head: `0caaaa0`; premerge main: `c0a9b1d`.
- Merge commit: [`ffade26`](https://github.com/KAIYI7/settle-table/commit/ffade26). Merged autonomously under orchestrator governance policy.
- Verified evidence: 167 full-suite methods pass locally in 62.7s; 10/10 automated real-browser CDP test stages pass in 3.6s via Headless Chrome (`tools/e2e_browser_test.mjs`); independent security, financial correctness, and concurrency review completed with unconditional GO; hosted GitHub Actions run [39693700070](https://github.com/KAIYI7/settle-table/actions/runs/39693700070) completed successfully on the exact PR head SHA.
- Key capabilities (Objective 2):
  1. **Organizer Allocation Command (`AssignParticipantQuantity`)**: Authoritative command in `settletable.authority` allowing organizers to assign, update, or remove quantities for any eligible active participant in the meal without requiring diner sessions.
  2. **Auditability & Non-Impersonation**: Persists `Claim.assigned_by = actor` so organizer allocations are clearly distinguished from diner self-claims in the audit trail without impersonating diners or forging diner sessions.
  3. **Strict Concurrency & Capacity Enforcement**: Enforces `expected_item_revision` (HTTP 409 Conflict on stale edits) and strict rational capacity bounds (`quantity_capacity` HTTP 400 if allocated quantity exceeds total receipt items).
  4. **Zero-Session Dining & Notion Workflow**: An organizer can fully allocate an entire receipt to named diners, review, seal, finalize, and export to Notion without any diners needing to log in, redeem links, or receive cookies.
  5. **Collaborative & Visual Feedback**: UI provides participant target dropdown (`#allocation-target-select`), item status badges (`✓ Fully Allocated`, `⚠️ N unassigned`), and visual claim chips distinguishing `[Organizer Assigned]` from `[Diner Claim]`.

## Accepted dual diner invitation & general meal join requests checkpoint (PR #15)

- PR #15 reviewed head: `1ca165e`; premerge main: `ffade26`.
- Merge commit: [`b0807ba`](https://github.com/KAIYI7/settle-table/commit/b0807ba). Merged autonomously under orchestrator governance policy.
- Verified evidence: 179 full-suite methods pass locally in 42.3s; 11/11 automated real-browser CDP test stages pass in 3.8s via Headless Chrome (`tools/e2e_browser_test.mjs`); independent security, authorization, and concurrency review completed with unconditional GO; hosted GitHub Actions run [39704284608](https://github.com/KAIYI7/settle-table/actions/runs/39704284608) completed successfully on the exact PR head SHA.
- Key capabilities (Objective 3):
  1. **Dual Invitation Coexistence**: Preserves existing personal one-time invitation links (`/invite/{token}`) while introducing a general meal join link (`/join/{meal_id}`).
  2. **Organizer-Approved Verification**: Unauthenticated diners open the meal join link and enter their registered display name. The request enters `pending` state; matching a display name alone grants zero access. The organizer reviews and approves the request with a single tap in their dashboard.
  3. **Cryptographic Claim Tokens & Zero Plaintext Storage**: DINER clients receive a 32-byte cryptographically secure random token (`secrets.token_urlsafe(32)`). SQLite stores strictly the domain-separated SHA-256 verifier (`settletable-join-claim-v1`). Once approved, the diner client claims the request via single-use atomic consumption, setting an authenticated HttpOnly session cookie and transitioning directly into the meal view.
  4. **Anti-Impersonation & Backdoor Defense**: Organizers cannot be requested or joined via diner join requests (`organizer_join_prohibited` HTTP 403), strictly eliminating any organizer recovery backdoors. Unauthenticated `/join/{meal_id}` leaks zero diner names, participant IDs, or receipt data.
  5. **Concurrency & Revocation Safety**: Concurrently racing claims are serialized atomically (exactly one succeeds, duplicate claims fail with `invalid_join_request`). Participant deactivations (`RevokeMembership` and `RevokeSession`) immediately invalidate all pending and approved join requests.
  6. **Token Transport Hardening**: Status polling transmits tokens via `X-Claim-Token` request headers rather than URL query strings, preventing access log leakage. Log redaction (`redact_log_string`) scrubs all sensitive claim tokens.

## Accepted general join request hardening & UAT closure checkpoint (PR #16)

- PR #16 reviewed head: `01b0a61`; premerge main: `f7c83e4`.
- Merge commit: [`24bd9ae`](https://github.com/KAIYI7/settle-table/commit/24bd9ae). Merged autonomously under orchestrator governance policy.
- Verified evidence: 182 full-suite methods pass locally in 73.3s; 11/11 automated real-browser CDP test stages pass in `tools/e2e_browser_test.mjs`; independent security, authorization, and anti-enumeration review completed with unconditional GO; hosted GitHub Actions run [39710140107](https://github.com/KAIYI7/settle-table/actions/runs/39710140107) completed successfully on the exact PR head SHA.
- Key capabilities:
  1. **Anti-Enumeration Defense**: Unified all non-eligible target conditions (unknown diner name, organizer name, ambiguous name, inactive diner) into indistinguishable `AuthorityError('invalid_join_target')` (HTTP 400 Bad Request) and uniform client error messaging, neutralizing roster and organizer role probing.
  2. **Pending Request Invalidation Protection**: Duplicate submissions for a participant with an active pending request are rejected with `AuthorityError('active_join_request_exists')` (HTTP 409 Conflict) rather than canceling the pending request, neutralizing denial of service against awaiting diners.
  3. **Bounded Resource Defenses Against Table Flooding**: Enforces strict table-level quotas: active pending ceiling (< 20) and lifetime table ceiling (< 100), raising `AuthorityError('resource_limit')` (HTTP 429 Too Many Requests).
  4. **Neutralization of Revision Conflict DoS**: Removed meal revision incrementing from unauthenticated `create_join_request`. Snapshot polling detects join request and invitation changes via JSON comparison, preventing unauthenticated callers from injecting revision conflicts on live diners claiming portions.
  5. **Mathematically Reconciled Walkthrough B**: Walkthrough B in `docs/uat-handover.md` is reconciled to a verified, cent-conserving fixture with 3 Nasi Lemak @ RM 12.00 (RM 36.00) + 2 Teh Tarik @ RM 3.00 (RM 6.00) = Grand Total RM 42.00, apportioned Alice RM 12.00, David RM 12.00, Emma RM 18.00 without residue.
  6. **Reconciled Startup Instructions**: Standardized startup instructions to `python tools/run_demo.py --mock-ocr --mock-notion` with default binding to `http://127.0.0.1:8000`.

## Accepted staged scanned candidate editor redesign checkpoint

- Integration: Direct two-parent `--no-ff` merge on `main` (commit [`5abab72c9fc02dbd127c3bd0336f711f5e4d32b3`](https://github.com/KAIYI7/settle-table/commit/5abab72c9fc02dbd127c3bd0336f711f5e4d32b3)); premerge main: `edcc5d408b18e07bf49b4cbc1236614778ef6f02`; feature head: `910b799e66d1ae2cece5bcd28ea5b6855f801241`. (Governance clarification: integrated directly on `main` under orchestrator governance; GitHub PR #17 was subsequently assigned to Phase 1 atomic item allocation).
- Verified evidence: 182 full-suite methods pass locally in 71.8s; 11/11 automated real-browser CDP test stages pass in `tools/e2e_browser_test.mjs`; independent UI/UX reviewer conducted critique and post-implementation review with unconditional PASS; Impeccable detect reported 0 anti-patterns; before/after screenshot evidence captured across desktop, tablet, and mobile.
- Key capabilities:
  1. **Accessible Quantity Stepper**: Segmented `[ - ] [ Value ] [ + ]` stepper with hidden browser spinner arrows, mobile-first 44px touch targets, tactile micro-feedback, free keyboard entry, and blur sanitization.
  2. **Container-Query Adjustments Grid (`@container ocrCard`)**: Eliminates nested card clutter and awkward vertical wrapping. Renders 1-row aligned 4-column grid (`1fr 140px 130px 38px`) with micro-headers on desktop ($\ge 540$px container width) and clean 2-line stacked card on mobile ($< 540$px).
  3. **Receipt Items & Unit Price Ergonomics**: Redundant desktop Unit Price column removed to expand item names by 40%; inline secondary caption `@ RM X.XX ea` conditionally displays under Line Total only when `qty > 1`.
  4. **Visual Consistency & Impeccable Craft Floor**: Ghost delete buttons transitioning softly to rose on hover; dark-theme alpha badges (`rgba(...)`) replacing light pastel pills; contrast elevated to $\ge 5.7:1$ (exceeding WCAG AA 4.5:1).
  5. **Service Charge vs SST Classification Resolution**: Verified parser and domain models maintain strict separation; added category selector auto-suggestion that updates default labels on change while strictly preserving custom user labels.

## Accepted staged candidate editor usability refinements checkpoint

- Integration: Direct two-parent `--no-ff` merge on `main` (commit [`8649544e2655470394d8f97702388c9f6e147e54`](https://github.com/KAIYI7/settle-table/commit/8649544e2655470394d8f97702388c9f6e147e54)); premerge `main` [`937779943fcf38a8dd288927aa81c5a77ddfe736`](https://github.com/KAIYI7/settle-table/commit/937779943fcf38a8dd288927aa81c5a77ddfe736); feature head [`d371e73507d4b2e8877bc3dbca34538562f27572`](https://github.com/KAIYI7/settle-table/commit/d371e73507d4b2e8877bc3dbca34538562f27572). (Governance clarification: integrated directly on `main` under orchestrator governance; GitHub does not contain a PR #18 pull request object. Pre-merge verification was executed locally; post-merge hosted CI passed on `main` push).
- Verified evidence: 182 full-suite methods pass locally in 104.7s; 11/11 automated real-browser CDP test stages pass in `tools/e2e_browser_test.mjs`; independent UI/UX reviewer conducted critique and post-implementation audit with unconditional PASS; Impeccable detect reported 0 anti-patterns; before/after screenshot evidence captured across desktop, tablet, and 375px mobile viewports.
- Key capabilities:
  1. **Locked Uniform Row Heights**: Floating estimated unit price removed from table DOM; Item Name, Qty stepper, Line Total, and Remove button are perfectly baseline-aligned across all rows; unit price estimation preserved as accessible `title` tooltip on Line Total when quantity $> 1$.
  2. **Zero-Overflow Mobile Navigation Header (375px)**: Redundant Home button hidden on mobile; single-line Leave Room button enforced (`white-space: nowrap`, 28px height); Organizer badge and participant name render cleanly without wrapping or overflow.
  3. **Mobile Adjustments Dropdown Readability**: Grid allocated `minmax(0, 1fr) 95px`, providing $\approx 170\text{px}$ to Type `<select>` for untruncated display of "Service Charge" and "BNM Rounding" while maintaining 44px touch targets.
  4. **Plain-Language Financial Copy**: Replaced internal DB architecture jargon with clear guidance ("Review scanned items, taxes, or discounts before applying them to the receipt"; "Discounts and rounding as negative").
  5. **Competing Editing Flows Paused**: Manual `#add-item-form` paused and receipt sealing disabled while an OCR candidate is staged, eliminating conflicting draft mutations.

## Accepted mobile header touch target & compact alert polish checkpoint

- Integration: Direct two-parent `--no-ff` merge on `main` (commit [`dc3cd65cbfb006560fed106dd6462024c1f604ff`](https://github.com/KAIYI7/settle-table/commit/dc3cd65cbfb006560fed106dd6462024c1f604ff)); premerge `main` [`e9f2d56`](https://github.com/KAIYI7/settle-table/commit/e9f2d56); feature head [`c3985f6`](https://github.com/KAIYI7/settle-table/commit/c3985f6). Integrated directly on `main` under orchestrator governance.
- Verified evidence: 182 full-suite unit/integration methods pass locally in 55.5s; 11/11 automated real-browser CDP test stages pass in `tools/e2e_browser_test.mjs`; independent UI/UX reviewer conducted post-implementation audit with unconditional PASS; Impeccable detect reported 0 anti-patterns; screenshot evidence captured across desktop, tablet, and 375px mobile viewports.
- Key capabilities:
  1. **Ergonomic Mobile Touch Targets ($\ge 40\text{px}$)**: Solved mobile touch target crowding without adding nested menus or shrinking text. Refresh button sized to $40\times 40\text{px}$; single-line Leave Room button sized to $40\times 92.5\text{px}$; both with `touch-action: manipulation`. Reclaimed $\approx 50\text{px}$ horizontal headroom by presenting the role as `👑 Alice` on mobile viewports ($< 640\text{px}$) while preserving full `👑 Organizer Alice` on desktop. Zero horizontal overflow at 375px width.
  2. **Compact Dismissible OCR Alert**: Reduced vertical alert height by over 50% (from $\approx 90\text{px}$ down to $46\text{px}$), keeping candidate tables above the fold on mobile devices. Preserves exact scanned item count and total amount (`✓ Scanned 2 items (RM 16.70)`). Provides an accessible, thumb-friendly $36\times 36\text{px}$ `✕` dismiss button with tactile active/focus feedback.
  3. **Preservation of OCR Candidate Editor Polish**: Retains the accepted Notion-inspired dark theme aesthetic, segmented stepper quantity controls, locked row heights, container query adjustments grid, and single editing workflow.

## Accepted contextual feedback & viewport notification polish checkpoint

- Integration: Direct two-parent `--no-ff` merge on `main` (commit [`88c1aa1e6ab1bb2e5e6569ace605cbb6aabdf8dd`](https://github.com/KAIYI7/settle-table/commit/88c1aa1e6ab1bb2e5e6569ace605cbb6aabdf8dd)); premerge `main` [`94efb86`](https://github.com/KAIYI7/settle-table/commit/94efb86); feature head [`d005766`](https://github.com/KAIYI7/settle-table/commit/d005766). Integrated directly on `main` under orchestrator governance.
- Verified evidence: 182 full-suite unit/integration methods pass locally in 104.0s; 11/11 automated real-browser CDP test stages pass in `tools/e2e_browser_test.mjs` (verifying scroll position preservation, in-situ verification banner, fixed viewport toast, and Escape key dismissal); independent UI/UX reviewer conducted post-implementation audit with unconditional PASS; Impeccable detect reported 0 anti-patterns; visual evidence captured in `screenshot_scrolled_receipt_verification.png`.
- Key capabilities:
  1. **Persistent In-Situ Receipt Verification Banner**: Immediately upon physical bill approval, the Human Receipt Review card displays a prominent, permanent confirmation banner (`#receipt-verified-status`) with reviewer identity and short digest (`✓ Receipt Verified & Sealed • Physical totals confirmed by Alice • Digest 321466e7`), cleanly distinguishing permanent authoritative status from transient action alerts.
  2. **Fixed-Position Viewport Toast (`showAlert`)**: Relocated the notification container from static document flow to a fixed-position floating toast (`top: calc(64px + env(safe-area-inset-top, 0px))`, z-index 1000). Guarantees immediate feedback visibility across all scroll offsets without forcing the page to jump or scroll to the top. Achieves zero Cumulative Layout Shift (CLS = 0) with `pointer-events: none` container and glassmorphic toast styling.
  3. **Notification Semantics & Premature Success Guarding**: Distinct semantic colorways and ARIA roles for success, error, conflict, and info (`.alert-info` added for informational messages). Removed premature success feedback during meal creation, locking submit controls until server confirmation. Implemented duplicate flash prevention.
  4. **Accessible Dismissal & Escape Handling**: Touch-friendly $36\times 36\text{px}$ `✕` close button, global `Escape` keyboard dismissal listener with clean lifecycle teardown, and accessible `aria-live` regions (`polite` for status/success, `assertive` for alert/error).

## Accepted bounded Phase 1 atomic item allocation checkpoint (PR #17)

- PR #17 reviewed head: [`92babe200ca1dd7cd6c73d83e678554f1ce727ad`](https://github.com/KAIYI7/settle-table/commit/92babe200ca1dd7cd6c73d83e678554f1ce727ad); premerge main: [`aed3d386d881f461a288db8852bd564a29a8da5c`](https://github.com/KAIYI7/settle-table/commit/aed3d386d881f461a288db8852bd564a29a8da5c).
- Merge commit: [`03a34c7a5f6436427387d7bda299f170f3f6e1eb`](https://github.com/KAIYI7/settle-table/commit/03a34c7a5f6436427387d7bda299f170f3f6e1eb). Merged autonomously under orchestrator governance policy following verified PR CI and independent code review.
- Verified evidence: 192 full-suite unit and integration test methods pass locally in 74.5s; 11/11 automated real-browser CDP test stages pass in 18.8s via Headless Chrome (`tools/e2e_browser_test.mjs`); independent security and code review completed with unconditional PASS ([review report](research/phase-3/atomic-item-allocation-remediation-review.md)); hosted GitHub Actions run [40171431186](https://github.com/KAIYI7/settle-table/actions/runs/40171431186) completed successfully on the exact PR head SHA in `ubuntu-24.04` (Python 3.14).
- Key capabilities:
  1. **Atomic Item Allocation Replacement (`SetItemAllocations`)**: Implemented `Authority._set_item_allocations` and WSGI transport command handler via `POST /api/meals/{meal_id}/apply` (`kind: "SetItemAllocations"`). Operates as an atomic replacement for an item's claims, supporting equal splits, custom rational fractions, portion increments/decrements, subset splits, and full resets (`allocations = []`). Evaluates total capacity $\sum \text{quantity} \le \text{item.quantity}$ atomically in one check, eliminating the intermediate capacity deadlocks and partial corruption inherent in sequential updates.
  2. **Claim Provenance & Attribution Preservation**: Unchanged diner-authored claims (`assigned_by = None`) and prior assigner provenance are strictly preserved when an organizer modifies other allocations on the same item. Modified quantities or newly introduced allocations receive `assigned_by = actor` (the acting organizer).
  3. **Strict Integer & Fraction Wire Validation**: Implemented `_parse_quantity(qty, *, allow_none=False)` in `settletable/transport.py` using strict exact type checks (`type(val) is int`). Rejects booleans (`True`, `False`, `[True, 2]`, `[1, False]`), floating-point numbers (`1.5`, `[1.5, 2]`), zero, negative quantities, and malformed fraction arrays across all four quantity-handling endpoints (`ReplaceReceipt`, `SetOwnQuantity`, `AssignParticipantQuantity`, `SetItemAllocations`).
  4. **Multi-Threaded Concurrency & Race Verification**: Added a dedicated multi-threaded race test (`test_concurrent_race_set_item_allocations_and_set_own_quantity`) using independent SQLite connections and `Authority` instances across OS threads. Verifies SQLite serialization, winner commit, loser `item_revision_conflict` (HTTP 409), clean transaction rollback, and capacity enforcement on retry.
  5. **Deterministic Sen Apportionment & Production Invariants**: Preserves the Hamilton-Hare apportionment tie-breaker (`tabwise-apportion-v1`), deterministic sen-level calculations, active membership validation, audit attribution, and existing financial contracts.
  6. **Production Frontend Boundary**: Production allocator and diner self-claiming UI remain untouched pending future Concept C UI integration review and explicit PO authorization.

## Accepted Phase 2 Concept C organizer allocation production integration checkpoint (PR #18)

- PR #18 reviewed head: [`751c10ca2d0f7a126c576083a5d511975970aa82`](https://github.com/KAIYI7/settle-table/commit/751c10ca2d0f7a126c576083a5d511975970aa82); premerge main: [`36f016a`](https://github.com/KAIYI7/settle-table/commit/36f016a).
- Merge commit: [`1f34b3e6d04193908e0264c050a25528df1f13cc`](https://github.com/KAIYI7/settle-table/commit/1f34b3e6d04193908e0264c050a25528df1f13cc). Merged autonomously under orchestrator governance policy following verified PR CI and independent code review.
- Verified evidence: 192 full-suite Python unit/integration test methods pass locally; 11/11 automated real-browser CDP test stages pass in `tools/e2e_browser_test.mjs`; dedicated 10-scenario production verification passes with high-resolution CDP evidence in `tools/verify_concept_c_production.mjs`; independent code review completed with CONDITIONAL PASS (remediated findings M-01, L-01, L-02); hosted GitHub Actions run [40178531481](https://github.com/KAIYI7/settle-table/actions/runs/40178531481) succeeded on the exact PR head SHA in `ubuntu-24.04` (Python 3.14); Impeccable detect reported 0 anti-patterns; visual evidence captured in `screenshot_concept_c_desktop_collapsed.png`, `screenshot_concept_c_desktop_expanded.png`, `screenshot_concept_c_selective_split.png`, `screenshot_concept_c_mobile_collapsed.png`, `screenshot_concept_c_mobile_sheet_expanded.png`, `screenshot_concept_c_finalized.png`.
- Key capabilities:
  1. **Concept C Unified Expandable Hybrid Allocation**: Replaced the legacy dropdown Allocation Target Selector with an item-first interface. Each item card displays line total, allocation progress, available diner quick-assign pills, clean allocated pills, and a clear `Details / Split` trigger.
  2. **1-Click Quick-Assign**: Unassigned whole portions can be allocated directly to an available diner in one tap. Fractional unassigned portions prompt the user to use the detailed split editor.
  3. **Selective Equal Split**: Organizers can select any arbitrary subset of diners to split an item equally. Generates exact reduced rational fractions ($[1, n]$, $[m, n]$) with real-time formula and cost preview (`1 item ÷ 3 diners = ⅓ each (~RM 12.00)`), requiring explicit confirmation when overwriting existing claims.
  4. **Adaptive Form Factor Architecture**:
     - Desktop ($\ge 768\text{px}$): Inline expandable details/split drawer (`.hybrid-drawer`).
     - Mobile ($< 768\text{px}$): Accessible bottom-sheet modal (`.bottom-sheet-modal`) with drag handle, scrim backdrop, touch targets $\ge 44\text{px}$, zero horizontal overflow, and Escape key dismissal.
  5. **Clean Pill Design**: Eliminates miniature $+$/$-$ buttons inside allocated diner pills. Pills render clean typography (`👑 Alice · 1`, `🍽️ Bob · ⅓`), opening the dedicated portion editor on tap.
  6. **Diner Claim Provenance Preservation**: Unchanged diner self-claims (`assigned_by = None`) are preserved when organizers modify other item claims.
  7. **Exact Rational Math & Strict Wire Safety**: Rational arithmetic helpers (`makeReducedFraction`, `addFractions`, `subtractFractions`, `ratToNum`, `formatRat`) ensure zero floating-point drift on the frontend and complete sen-level financial reconciliation.
  8. **Documented Route Correction**: Confirmed and corrected the API contract documentation in `PROJECT_STATUS.md` and `docs/agents/phase-transitions.md` to reference `POST /api/meals/{meal_id}/apply` (`kind: "SetItemAllocations"`).

## Accepted Concept C allocation preview alignment & "All" shortcut guard checkpoint (PR #19)

- PR #19 reviewed head: [`3699dd4efeeaa520101ec2b53bf9467301cbfca9`](https://github.com/KAIYI7/settle-table/commit/3699dd4efeeaa520101ec2b53bf9467301cbfca9); premerge main: [`7480014`](https://github.com/KAIYI7/settle-table/commit/7480014).
- Merge commit: [`b4cf4e8`](https://github.com/KAIYI7/settle-table/commit/b4cf4e8). Merged autonomously under orchestrator governance policy following verified PR CI and independent code review.
- Verified evidence: 192 full-suite Python unit/integration test methods pass locally in 171.4s; 11/11 automated real-browser CDP test stages pass in `tools/e2e_browser_test.mjs`; dedicated 10-scenario production verification passes with high-resolution CDP evidence in `tools/verify_concept_c_production.mjs`; independent code review completed with unconditional PASS (Zero findings); hosted GitHub Actions run [40197038604](https://github.com/KAIYI7/settle-table/actions/runs/40197038604) succeeded on the exact PR head SHA in `ubuntu-24.04` (Python 3.14); Impeccable detect reported 0 anti-patterns.
- Key capabilities:
  1. **Deterministic Apportionment Previews (Finding 1)**: Implemented Largest Remainder (Hamilton-Hare) apportionment matching `settletable/calculation.py` with pure-JS SHA-256 tie-breaker in `settletable/static/app.js` (`apportionItemBase`). Completely eliminated RM 26.01 drift when RM 26.00 is split 3 ways (displays `~RM 8.67 base`, `~RM 8.67 base`, `~RM 8.66 base`; sum = 2600 sen = RM 26.00 exactly).
  2. **Clear Base Cost Labeling & Tooltips**: Provisional item-level amounts are explicitly labeled with `base` (`~RM X.XX base`), accompanied by accessible tooltips and a persistent section subtitle (`Provisional item base • Taxes and service charge apportioned at finalization`), clearly distinguishing item-level unadjusted bases from finalized amounts (which incorporate taxes, service charges, discounts, and rounding). Backend calculation engine preserved 100% untouched.
  3. **"All" Shortcut Zero-Capacity Guard (Finding 2)**: Disabled the "All" fraction button with `disabled` attribute and descriptive tooltip (`No unassigned portion remains`) when other participants already consume the item's full capacity (`remRat === 0`). Guarded click event listener against execution when `ratToNum(remRat) <= 0`, alerting the organizer non-destructively and preventing over-allocation. Other participants' allocations and exact rational arithmetic are strictly preserved.
  4. **Path Portability in Verification Infrastructure**: Enhanced `tools/verify_concept_c_production.mjs` to dynamically resolve Python, Chrome/Chromium across Windows, Linux, and macOS, and utilize configurable artifact directories (`process.env.ARTIFACT_DIR`) with safe fallback to `artifacts/`. Added automated CDP verification covering both findings.

## Accepted navigation and toast layout polish checkpoint (PR #20)

- PR #20 reviewed head: [`d8163e54d3315edd8d57eced1cc7cf7503c456c5`](https://github.com/KAIYI7/settle-table/commit/d8163e54d3315edd8d57eced1cc7cf7503c456c5); premerge main: [`b1e155e`](https://github.com/KAIYI7/settle-table/commit/b1e155e).
- Merge commit: [`1926871`](https://github.com/KAIYI7/settle-table/commit/1926871). Merged autonomously under orchestrator governance policy following verified PR CI and independent code review.
- Verified evidence: 192 full-suite Python unit/integration test methods pass locally in 80.4s; 11/11 automated real-browser CDP test stages pass in `tools/e2e_browser_test.mjs`; independent code and UX review completed with unconditional APPROVE / PASS (Zero findings); hosted GitHub Actions run [40512835119](https://github.com/KAIYI7/settle-table/actions/runs/40512835119) succeeded on the exact PR head SHA in `ubuntu-24.04` (Python 3.14); Impeccable detect reported 0 anti-patterns; CDP visual verification captured on Desktop (1280x800), Tablet (768x1024), Mobile (375x667), and Mobile Bottom Sheet + Toast stacking.
- Key improvements:
  1. **Redundant Room Navigation Simplified**: Removed the secondary `.room-nav-bar` row. Retained `.room-status-card` and added high-contrast, accessible `← Home / Room` breadcrumb navigation (`.room-home-link`), ensuring mobile users retain discoverable Home navigation even when the sticky header's `#nav-home-btn` text link is hidden. Cleaned up obsolete `#room-leave-btn` references.
  2. **Corrected Header & Content Spacing**: Resolved CSS specificity glitch where `.container` (`padding: 0 16px`) silently overrode `main` (`padding: 20px 16px 40px`). Explicitly declared `main#app, main` with `padding: 20px 16px 48px;` (desktop) and `padding: 16px 12px 40px;` (mobile). Eliminated negative margins and hardcoded offsets.
  3. **Responsive Viewport Toast Placement**: Implemented `syncHeaderHeight()` to dynamically write `--app-header-height` to `:root`. Anchored `#alert-container` with `top: calc(var(--app-header-height, 68px) + 12px)` on desktop and `+ 8px` on mobile, with zero overlap over sticky header navigation controls. Preserved non-scrolling viewport stability and keyboard Esc dismissal.
  4. **Rigorous Layering (z-index Hierarchy)**: Established explicit stacking hierarchy across page content (`z-index: 1`), sticky application header (`z-index: 200`), mobile bottom-sheet scrim (`z-index: 900`), mobile bottom-sheet modal (`z-index: 950`), and transient notifications (`z-index: 1100`). Guaranteed error alerts and conflict banners remain visible and interactive above modal sheets without blocking modal footer action buttons (`Clear All Claims`, `Done`).
  5. **Test Resilience**: Parameterized `tools/e2e_browser_test.mjs` with `process.env.SETTLETABLE_PORT` and dynamic `${serverOrigin}`, updated assertions to verify `.room-status-card` and `.room-home-link`.

## Accepted toast placement refinement checkpoint (PR #21)

- PR #21 reviewed head: [`487de389c267f1e57e7d23973b84b44078e404fe`](https://github.com/KAIYI7/settle-table/commit/487de389c267f1e57e7d23973b84b44078e404fe); premerge main: [`dd73749`](https://github.com/KAIYI7/settle-table/commit/dd73749).
- Merge commit: [`0bca517`](https://github.com/KAIYI7/settle-table/commit/0bca517). Merged autonomously under orchestrator governance policy following verified PR CI and independent dual-axis code and UX review.
- Verified evidence: 192 full-suite Python unit/integration test methods pass locally in 83.9s; 11/11 automated real-browser CDP test stages pass in `tools/e2e_browser_test.mjs`; dedicated 5-case geometry and visual verification test passes in `tools/capture_toast_evidence.mjs`; independent code and UX review completed with unconditional PASS (Zero findings); hosted GitHub Actions run [40625125967](https://github.com/KAIYI7/settle-table/actions/runs/40625125967) succeeded on the exact PR head SHA in `ubuntu-24.04` (Python 3.14); Impeccable detect reported 0 anti-patterns; CDP visual evidence captured in `screenshot_toast_desktop_bottom.png`, `screenshot_toast_mobile_bottom.png`, `screenshot_toast_long_error.png`, `screenshot_toast_mobile_bottom_sheet.png`, and `screenshot_toast_scrolled_receipt.png`.
- Key capabilities:
  1. **Safe-Area Aware Bottom Viewport Anchoring**: Anchored `#alert-container` to viewport bottom via `bottom: calc(24px + env(safe-area-inset-bottom, 0px))` on desktop and `16px` on mobile. Achieved **541.0px clearance** on desktop and **451.6px clearance** on mobile from the room status card, completely eliminating overlap with the `← Home / Room` breadcrumb and room status badges.
  2. **Contextual Mobile Bottom Sheet Inversion**: Dual-layer CSS (`:has(.bottom-sheet-modal) #alert-container`, `body.has-bottom-sheet #alert-container`, `#alert-container.alert-container-top`) and JavaScript state synchronization in `syncAlertContainerPlacement()`. When a mobile bottom sheet is active, the toast automatically docks to the top (`y = 65–117px`), completely clearing modal footer actions (`Apply Equal Split`, `Clear All Claims`, `Done`).
  3. **Directional Entry Motion**: Implemented `toast-in-bottom` (`translateY(12px) scale(0.98)` to `translateY(0) scale(1)`) for bottom toasts and `toast-in-top` (`translateY(-8px) scale(0.98)` to `translateY(0) scale(1)`) for top-docked toasts, providing natural physical spatial continuity.
  4. **Multi-line Text Wrapping & Touch Target Protection**: Long error messages wrap cleanly across lines via `overflow-wrap: break-word; word-break: break-word; min-width: 0;` with zero horizontal overflow (`bannerScrollWidth === bannerClientWidth` at 353px on 375px viewport). Rigid $36\times 36\text{px}$ touch target on `.alert-close-btn` protected against shrink distortion (`flex-shrink: 0; touch-action: manipulation;`).
  5. **CI Runner Stability Hardening**: Resolved runner timeouts in `tools/e2e_browser_test.mjs` by adding `--disable-background-networking` and `--disable-default-apps` Chrome flags and doubling connection polling to 300 attempts (30s).
  6. **Accessibility & Invariant Preservation**: ARIA roles (`role="alert"` / `aria-live="assertive"` for errors; `role="status"` / `aria-live="polite"` for success), keyboard `Escape` dismissal, and deterministic financial apportionment preserved 100%.

## Repository foundation

- CI merge: `a4dd5302f93b41bbf72cbf29ecd596bc7bb7c1aa` (PR #2). `.github/workflows/python-tests.yml` runs the entire suite on PRs targeting main and pushes to main, with pinned official actions, read-only token permissions and no supplied secrets/caches/artifacts. The owner confirms included minutes remain and no valid payment method is attached; no billing setting or paid usage was enabled. [CI research/review](research/foundation/README.md).
- Namespace merge: `91b824f395d062a994056e905f475fe83f52b3a8` (PR #3). Both production files moved from `tabwise` to `settletable` with identical bytes; no hash-domain, schema or canonical/replay change. Old-package-created SQLite compatibility passes; the coordinator's renamed full suite passes60 methods in73.078s. [Refactor evidence](research/foundation/package-refactor.md).
- Hosted PR checks ran all60 tests successfully for both CI and renamed integration; main push checks also run the full suite. Exact observed runs and limits are in [foundation evidence](research/foundation/README.md). Current checkpoint tags remain fixed while main advances.

Confirmed user constraints and detailed open decisions remain in [Phase 1 requirements](research/phase-1/requirements.md). Research entry point: [index](research/README.md).

## Accepted optional allocation authorization simulation (PR #22)

- Reviewed head: [`a1c82c8ed159fd1e5c2ddd89ae18d6d2f67e5b54`](https://github.com/KAIYI7/settle-table/commit/a1c82c8ed159fd1e5c2ddd89ae18d6d2f67e5b54); merge: [`79d68548d65230755a5837b9debe071bd902cf3b`](https://github.com/KAIYI7/settle-table/commit/79d68548d65230755a5837b9debe071bd902cf3b). The merge preserves both parents and its source tree equals the reviewed head.
- Independent source, security and adversarial review passed. Local verification passed 213 Python tests, 21 focused simulation tests and 11 existing Chrome journey stages. [Hosted CI](https://github.com/KAIYI7/settle-table/actions/runs/40649706607) associated with the exact reviewed head passed all 213 Python tests and 11 browser stages.
- Separate-process synthetic PostgreSQL/Kafka/SQLite validation established stable payment identity across retries, cache expiry, lost responses and application restarts, distinct authorization outcomes, bounded dependency-outage recovery, explicit restore write freeze and browser credential isolation. Existing meal and accepted-command bytes remained unchanged; no capture, refund or journal was created by the integration.
- [Contract and configuration](docs/payment-simulation.md): organizer initiation, organizer/self reads, accepted Finalize amount authority, stable UUIDv5 identity, a nonfinancial sidecar and bounded server HTTP/polling. The feature defaults disabled. Dedicated synthetic bindings, server credentials and a retained installation namespace require explicit operator configuration for a supervised local demonstration. Public deployment and permanent credential provisioning remain outside this milestone.
