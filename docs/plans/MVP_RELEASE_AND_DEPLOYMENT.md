# SettleTable — Official MVP Release & Deployment Plan

**Document:** `docs/plans/MVP_RELEASE_AND_DEPLOYMENT.md`  
**Date:** 2026-11-05  
**Status:** Orchestrator Release Plan & Decision Record  
**Target Milestones:**
- Restricted Deployment Pilot: `v0.9.0-beta.1`
- Official Release Candidate: `v1.0.0`

---

## 1. Executive Summary & Context

SettleTable has completed its core functional and algorithmic scope through PR #46. The platform encompasses:
- Cent-conserving deterministic apportionment (`tabwise-apportion-v1`) with integer minor units (`sen`).
- Air-gapped local Malaysian dining receipt OCR (RapidOCR CPU ONNX) with Malaysian SST/service charge parsing.
- Crash-consistent receipt photo retention and pan/zoom preview.
- Multi-diner real-time collaboration with pre-minted invitations and general meal join requests.
- Multi-payer contributions and net balance reconciliation.
- Suggested peer transfer calculation, partial reimbursements, and settlement tracking.
- Optional decoupled asynchronous Notion financial export with original receipt photo attachments.
- Full desktop Google Chrome UAT, physical Android Chrome UAT on POCO F6, and 294 passing automated regression tests.

The account/login and "My Meals" roadmap is documented in `docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md` and remains a future architectural phase. Login implementation is **not** part of this release milestone.

The objective of this plan is to transition SettleTable from a local development/demo setup into a reproducible, deployment-ready, self-hostable MVP while strictly preserving its zero-trust boundaries and security invariants.

---

## 2. Phase A — Release Readiness Investigation & Findings

Each architectural component was inspected against the current `main` branch. Findings are labeled using the project's evidence classification:
- **`[VERIFIED]`**: Inspected directly in source code or proven by passing deterministic tests.
- **`[OBSERVED]`**: Confirmed operational behavior or measured runtime characteristic.
- **`[INFERENCE]`**: Logical architectural conclusion or necessary deployment deduction.
- **`[UNKNOWN]`**: Unmeasured or dependent on external environment factors.

### 2.1 Investigation Matrix

| Capability / Boundary | Status / Finding | Classification | Deployment Impact |
|---|---|---|---|
| **Loopback Meal Bootstrap** | `SettleTableApp._dispatch` strictly rejects `POST /api/meals/{id}/bootstrap` if `REMOTE_ADDR` is not loopback (`127.0.0.1`, `::1`, `localhost`) or if **any** proxy headers (`X-Forwarded-For`, `X-Forwarded-Proto`, etc.) are present. | `[VERIFIED]` | External web clients cannot provision new meals via public reverse proxy routes. Meals must be provisioned locally/administratively (via CLI or internal loopback tunnel). Arbitrary public meal creation is prohibited by design. |
| **Organizer Session Expiry & Recovery** | Organizer sessions have a 7-day TTL (`SESSION_TTL = 604800`s) stored in SQLite `sessions`. Tokens are opaque 43-character URL-safe strings returned once at bootstrap via `HttpOnly; SameSite=Strict` cookie. No ordinary password or email recovery exists. | `[VERIFIED]` | If an organizer clears their browser cookies, switches devices, or allows their session to expire, they permanently lose organizer authority for that meal. Ordinary recovery requires the future account roadmap. |
| **Reverse Proxy & Origin CSRF** | Mutating endpoints (`POST`, `DELETE`) require `X-SettleTable-Action: 1` and strict origin matching against `server_origin`. `HTTP_HOST` must match `allowed_hosts`. | `[VERIFIED]` | Reverse proxy must forward `Host` and `X-Forwarded-*` headers correctly. The application environment must explicitly set `SETTLETABLE_ALLOWED_HOSTS` and `SETTLETABLE_SERVER_ORIGIN` to match the public HTTPS domain; otherwise, all client mutations are blocked with HTTP 403. |
| **WSGI Serving & Concurrency** | Current runner (`tools/run_demo.py`) uses Python `wsgiref.simple_server` (single-threaded, blocking). `Authority` uses thread-local SQLite connections (`threading.local()`) and WAL mode. | `[VERIFIED]` | Production deployment requires a multi-threaded, single-process WSGI server (e.g. Gunicorn `gthread` with 1 worker process and 4–8 threads). Multi-process or multi-instance deployment is strictly prohibited due to SQLite WAL locking boundaries. |
| **SQLite WAL Single-Instance Boundary** | SQLite runs with `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=1000`, and `PRAGMA foreign_keys=ON`. Multi-reader/single-writer semantics are strictly single-host. | `[VERIFIED]` | Application **must run as exactly one instance**. Horizontal container autoscaling or running multiple replicas against a network share (NFS/CIFS) will cause database lock timeouts and potential corruption. |
| **Backups & Receipt Photo Consistency** | Metadata is in SQLite; receipt image binaries are stored as files on disk (`<db_dir>/receipt_photos/`). Simple file copying during WAL writes yields corrupted snapshots. | `[VERIFIED]` | Hot backup requires the SQLite Online Backup API (`sqlite3.backup` or `VACUUM INTO`) to safely checkpoint pages, coupled with an atomic sync of the `receipt_photos/` directory. |
| **Real Local OCR Engine & Resources** | RapidOCR uses ONNX Runtime on CPU. Model weights (~15–20 MB) are cached locally. Memory consumption: ~150–300 MB baseline, spiking to 500 MB–1 GB during multi-megapixel inference. | `[VERIFIED]` / `[OBSERVED]` | Host/container requires at least 1 GB RAM (preferably 2 GB RAM). OCR models should be pre-baked into the container image to prevent outbound download dependencies at runtime. |
| **Mock Clients & Testing Flags** | `MockOcrEngine` and `MockNotionClient` can be enabled via CLI flags or `SETTLETABLE_MOCK_*=1`. | `[VERIFIED]` | Production deployment must ensure these environment variables are unset/0 to prevent simulated mocks from handling real financial receipts. |
| **Notion Export & Token Security** | Notion export is 100% decoupled and optional. Tokens are never persisted to SQLite. `redact_log_string` scrubs tokens from all log outputs. Background daemon thread performs async export with a 60s timeout. | `[VERIFIED]` | Low operational risk. Notion connection failures or rate limits do not block or corrupt meal state. |
| **Abuse Controls & Wire Bounds** | Request bounds enforced: body $\le 1\text{MB}$ (images $\le 5\text{MB}$), headers $\le 16\text{KB}$, JSON depth $\le 10$, int digits $\le 19$. Structured error codes returned; stack traces never disclosed. | `[VERIFIED]` | Application-level defense-in-depth is solid. Ingress reverse proxy (Tier 1) must enforce connection rate limiting, slowloris defense, and raw wire buffers before requests hit WSGI. |
| **Guest Invitation & Join Flows** | Pre-minted token links (`/invite/{token}`) and general join requests (`/join/{meal_id}`) operate cleanly over public HTTPS without loopback requirements. | `[VERIFIED]` | Fully online-ready for invited diners and guest participants. |
| **Startup, Shutdown & Crash Recovery** | SQLite WAL mode automatically recovers on restart. Uncommitted temporary photo uploads are cleaned up. Background exports cleanly time out after 60s. | `[VERIFIED]` | Safe for container restarts and host reboots. A graceful shutdown hook (`SIGTERM` handler) is needed to close database connections cleanly. |

---

## 3. Phase B — Hosting Platform Comparison & Architecture

### 3.1 Evaluation Criteria
1. **Single-Instance Enforcement**: Ability to pin container/VM to exactly 1 replica without horizontal autoscaling.
2. **Persistent NVMe/SSD Storage**: POSIX-compliant persistent volume for SQLite WAL and receipt photos.
3. **RAM & CPU for Real OCR**: Sufficient memory (1–2 GB) to avoid ONNX Runtime OOM during image processing.
4. **HTTPS & Origin Integrity**: Automated TLS termination with proper Host and SNI preservation.
5. **Operational Complexity**: Setup overhead, maintenance burden, and observability.
6. **Cost Efficiency**: Estimated monthly cost for low-traffic restricted pilot.

### 3.2 Platform Comparison Matrix

| Platform | Architecture & Storage | Minimum Tier for Real OCR (1–2 GB RAM) | Estimated Monthly Cost | Pros | Cons | Recommendation Verdict |
|---|---|---|---|---|---|---|
| **Fly.io** | Containers on Firecracker microVMs. Persistent NVMe volumes (`fly volumes`) with POSIX semantics. Single machine pinning (`auto_stop_machines = false`, 1 instance). | `shared-cpu-1x` (1 GB RAM) or `shared-cpu-2x` (2 GB RAM) + 3 GB Volume | **$6.85 – $13.85 / mo**<br>($6.70 compute + $0.45 volume for 1GB; $13.39 + $0.45 for 2GB) | Built-in volume snapshotting (24h), global Anycast HTTPS, native Dockerfile build, direct SSH console (`fly ssh console`). | Ephemeral rootfs requires explicit volume mounting for `/data`; stopping machine stops billing for compute but volume charges remain ($0.15/GB/mo). | **PRIMARY RECOMMENDATION (Managed PaaS)** |
| **Small VPS (Hetzner Cloud CX22 / CAX11)** | Dedicated KVM VPS with local NVMe SSD. Full Linux root access (Ubuntu/Debian). Local Docker Compose + Caddy. | 2 vCPU, 4 GB RAM, 40 GB NVMe SSD | **~$4.10 / mo**<br>(€3.79 / mo) | Highest CPU/RAM headroom for lowest cost. Zero cold starts, complete control over Tier 1 Caddy reverse proxy, local cron backups to S3/B2, no multi-instance risk. | Requires basic server administration (OS updates, SSH hardening, firewall/ufw setup, Docker daemon management). | **PRIMARY RECOMMENDATION (Self-Hosted / VPS)** |
| **Railway** | Docker deployment with persistent volume attachment. | Hobby plan ($5 base) + usage; 1 GB RAM container + 3 GB volume | **$8.00 – $11.00 / mo**<br>($5 platform + ~$3 compute + $0.45 volume) | Git push deploy, simple UI, easy environment variable management, automatic HTTPS. | Volume pricing is per-second metered; UI makes it easy to accidentally scale replicas unless explicitly locked; fewer low-level disk controls than Fly. | **FALLBACK RECOMMENDATION** |
| **Render** | Web Service with attached Persistent Disk. Disks only available on paid plans. | Starter Service ($7.00/mo) + 3 GB Persistent Disk ($0.75/mo) | **$7.75 – $14.75 / mo**<br>(Starter 512MB is $7, Standard 2GB is $14 + disk) | Automatically enforces single-instance limit when a disk is attached. Automatic daily snapshots retained 7 days. | 512 MB Starter plan ($7/mo) risks OOM crashes during RapidOCR inference; upgrading to Standard 2 GB costs $14.75/mo. | Viable, but higher cost for adequate OCR RAM. |

### 3.3 Final Hosting Decision
- **Primary Option A (Zero-Server-Management PaaS):** **Fly.io** (`shared-cpu-1x`, 1 GB RAM, 3 GB persistent volume mounted at `/data`, deployed via Dockerfile).
- **Primary Option B (Maximum Performance & Cost Efficiency):** **Hetzner Cloud CX22** (4 GB RAM, 40 GB NVMe, Docker Compose with Caddy reverse proxy, costing ~$4.10/mo).
- **Fallback Option:** **Railway** (Hobby plan with attached persistent volume).

*Note: Per AGENTS.md, no hosting accounts, cloud resources, or billing profiles have been created. This is an evaluation and packaging preparation.*

---

## 4. Phase C — Deployment Packaging Implementation

To make SettleTable reproducible and deployment-ready without modifying core business invariants, the following packaging artifacts are prepared:

### 4.1 Production WSGI Entrypoint (`settletable/wsgi.py`)
Provides a standardized WSGI application callable that configures `SettleTableApp` strictly from environment variables:
- `SETTLETABLE_DB_PATH`: Path to SQLite database (default: `.local/settletable.sqlite` or `/data/settletable.sqlite`).
- `SETTLETABLE_STORAGE_DIR`: Path to receipt photo storage (default: `<db_dir>/receipt_photos`).
- `SETTLETABLE_SERVER_ORIGIN`: Exact public origin (e.g. `https://settletable.example.com`).
- `SETTLETABLE_ALLOWED_HOSTS`: Comma-separated list of permitted `Host` header values.
- `SETTLETABLE_ALLOW_SYNC_EXPORT`: Flag to permit synchronous Notion export in tests.
- `SETTLETABLE_MOCK_OCR` / `SETTLETABLE_MOCK_NOTION`: Explicitly disabled by default in production.

### 4.2 Lightweight Healthcheck Probe (`/healthz`)
Added to `settletable.transport`:
- Responds to `GET /healthz` and `GET /api/healthz`.
- Returns `200 OK` with JSON `{"ok": true, "status": "healthy"}`.
- Evaluated immediately after header wire bounds checks, bypassing Host header checks so internal Docker/Kubernetes health probes (`curl -f http://127.0.0.1:8000/healthz`) succeed without needing internal cluster IPs in `allowed_hosts`.

### 4.3 Containerization (`Dockerfile`, `docker-compose.yml`, `.dockerignore`)
- **Base image:** `python:3.12-slim`.
- **Security:** Runs as non-root user `settletable` (UID 10001).
- **Dependencies:** Installs standard system libraries required by OpenCV/ONNX, installs Python requirements, and pre-downloads RapidOCR models at build time so the container requires zero outbound network calls during runtime.
- **Persistence:** Declares `VOLUME ["/data"]`.
- **Server:** Runs Gunicorn with `gthread` worker (1 process, 4 threads).

### 4.4 Tier 1 Reverse Proxy Reference Configurations
- **Caddy (`deploy/caddy/Caddyfile`):** Automated HTTPS, strict HSTS, 10 MB upload body limit, and route blocking for `/api/meals/*/bootstrap`.
- **Nginx (`deploy/nginx/nginx.conf`):** Wire protection buffers, `client_max_body_size 10M`, and loopback protection.
- **Environment Template (`deploy/env.template`):** Documented template for production environment variables.

### 4.5 Hot Backup & Disaster Recovery Utility (`tools/backup_restore.py`)
- **Backup:** Connects to active SQLite database and invokes `sqlite3.Connection.backup()` to create a clean, transactionally consistent checkpointed copy without WAL dependencies. Synchronizes the `receipt_photos/` folder alongside the backup.
- **Restore:** Validates backup database integrity with `PRAGMA integrity_check`, restores database and photo directory atomically.

### 4.6 Administrative Meal Bootstrap CLI (`tools/bootstrap_meal.py`)
Because public clients cannot call `/bootstrap` over the reverse proxy, administrators can provision new meal rooms locally on the host/container:
- Connects directly to `Authority` on disk.
- Sets up organizer and initial participants.
- Generates the organizer's session token and prints diner join links securely to standard output.

### 4.7 Deployment Smoke Check Script (`tools/deployment_smoke_check.py`)
Automated verification tool that executes end-to-end checks against any local or deployed URL:
1. Healthcheck (`/healthz`).
2. Static asset delivery & MIME types (`/static/style.css`, `/static/app.js`).
3. Security headers (CSP, nosniff, Referrer-Policy).
4. Ingress boundary check (verifies `POST /api/meals/test/bootstrap` is rejected with 403 when proxy headers are present).
5. CSRF defense check (verifies mutating requests without `X-SettleTable-Action: 1` are rejected with 400).

---

## 5. Phase D — GitHub Release Polish & Repository Audit

### 5.1 Repository Description & Topics
- **Description:** *"Fair, deterministic, and cent-conserving dining bill splitter with local offline OCR, live diner collaboration, and optional Notion export."*
- **Proposed Topics:** `bill-splitter`, `receipt-ocr`, `python`, `vanilla-js`, `financial-calculator`, `sqlite-wal`, `notion-api`, `offline-first`, `deterministic-apportionment`.

### 5.2 Licensing & Intellectual Property Decision
- **Status:** **All Rights Reserved / Source Available (Non-Redistributable).**
- **Decision:** As established in `THIRD_PARTY_NOTICES.md` and research records, no project-wide open-source license (MIT/Apache) has been selected or granted by the product owner.
- **Rules:** We do **not** invent an open-source license. Third-party components retain their upstream licenses:
  - Matt Pocock skill collection: MIT (`.agents/skills/MATTPOCOCK-LICENSE.txt`).
  - PR / HumanLayer show-me: MIT (`docs/third-party/HUMANLAYER-SHOW-ME-LICENSE.txt`).
  - Impeccable skill: Apache-2.0 notice preserved; payload excluded from Git.
- **GitHub Guidance:** GitHub's terms of service permit hosting public repositories under default copyright ("All Rights Reserved"), granting visitors the right to view and fork the code on GitHub without granting a license to redistribute or commercialize it.

### 5.3 Pre-Publication Privacy & Security Audit
The repository was audited using `tools/audit_repository.py` and git history inspection:
- **Credentials & API Keys:** 0 active credentials, API tokens, or secrets exist in tracked files.
- **Private Notion Identifiers:** All test Notion IDs use synthetic hashes or `example.invalid` placeholders.
- **Excluded Payloads:** Real receipt photos, machine-specific paths, virtual environments (`.venv`), local SQLite databases (`.local/*.sqlite`), and model weights remain strictly excluded in `.gitignore`.
- **Binary Fixtures:** The only tracked image is a synthetic test fixture (`tests/fixtures/ocr/images/synthetic_clear.png`).

### 5.4 Documentation Deliverables
- Comprehensive, professional `README.md` reflecting the actual implemented state through PR #46.
- `SECURITY.md` establishing vulnerability disclosure policies, the two-tier ingress boundary, and session security.
- `CHANGELOG.md` documenting all milestones, architecture decisions, and PRs #1 through #46.

---

## 6. Phase E — Release Acceptance Gates

Four separate, independent go/no-go gates govern the release lifecycle:

### Gate 1: Reproducible Local Working Release (`v0.9.0-local`)
- [x] All 294 Python unit and adversarial tests pass (`python -m unittest discover tests`).
- [x] All 9 automated headless Chrome CDP E2E regression suites pass.
- [x] Local runner (`tools/run_demo.py`) operates cleanly with mock clients.
- [x] Real OCR setup and execution verified with local virtual environment.
- [x] Documentation, architecture specs, and user guides are accurate and complete.
- **Verdict: PASS (Ready for Local Distribution)**

### Gate 2: Restricted Online Deployment Pilot (`v0.9.0-beta.1`)
- [x] Production WSGI entrypoint (`settletable/wsgi.py`) implemented and tested.
- [x] `/healthz` endpoint verified under automated tests.
- [x] Container packaging (`Dockerfile`, `docker-compose.yml`) verified.
- [x] Reverse proxy ingress templates (Caddy, Nginx) enforcing Tier 1 wire bounds and `/bootstrap` blocking.
- [x] Hot backup and disaster recovery script (`tools/backup_restore.py`) verified against active WAL database.
- [x] Administrative bootstrap CLI (`tools/bootstrap_meal.py`) verified.
- [x] Pre-publication privacy and credentials audit passed.
- [ ] Product Owner authorization for hosting platform selection (Fly.io vs Hetzner VPS).
- **Verdict: IMPLEMENTATION READY (Awaiting PO Infrastructure Authorization)**

### Gate 3: Publicly Reachable Application
- [ ] Account / Login roadmap implemented (per `docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md`) OR administrative meal provisioning workflow accepted for hosted use.
- [ ] Domain name, DNS, and TLS certificates provisioned.
- [ ] Ingress rate limiting and IP reputation filtering configured.
- [ ] Automated offsite backup pipeline scheduled.
- [ ] Product Owner explicit authorization for public traffic and ongoing hosting expenditure.
- **Verdict: BLOCKED (Pending Account Roadmap & PO Authorization)**

### Gate 4: Public GitHub Repository & Official Tagged Release (`v1.0.0`)
- [ ] Product Owner decision on repository visibility (Private vs Public).
- [ ] Product Owner decision on software license (keep All Rights Reserved vs select Open Source license).
- [ ] Official release tag `v1.0.0` approved and signed.
- **Verdict: BLOCKED (Requires Product Owner Consequential Decision)**

---

## 7. Action Items & Boundaries

### 7.1 Autonomous Preparation Scope (Completed in this Phase)
1. Created deployment packaging: `settletable/wsgi.py`, `/healthz` endpoint in `settletable/transport.py`.
2. Created container configuration: `Dockerfile`, `docker-compose.yml`, `.dockerignore`.
3. Created reverse proxy templates: `deploy/caddy/Caddyfile`, `deploy/nginx/nginx.conf`.
4. Created operational utilities: `tools/backup_restore.py`, `tools/bootstrap_meal.py`, `tools/deployment_smoke_check.py`.
5. Created safe environment template: `deploy/env.template`.
6. Created comprehensive documentation: `README.md`, `SECURITY.md`, `CHANGELOG.md`.
7. Added unit tests for `/healthz` and WSGI configuration.
8. Executed full test suite and pre-publication audit.

### 7.2 Consequential Escalations (Requiring Product Owner Approval)
1. **Hosting Deployment:** Creating cloud hosting accounts, incurring hosting costs, or pointing DNS for a live deployment.
2. **Repository Visibility:** Changing GitHub repository from Private to Public.
3. **Licensing Decision:** Selecting or publishing an open-source license grant.
4. **Official Tagging:** Creating and pushing official release tags (`v0.9.0-beta.1` or `v1.0.0`) to GitHub.
