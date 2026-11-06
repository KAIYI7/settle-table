# SettleTable — Low-Cost, Mostly-Available MVP Deployment Plan

**Document:** `docs/plans/MVP_RELEASE_AND_DEPLOYMENT.md`  
**Date:** 2026-11-06 (Revised from 2026-11-05 baseline)  
**Status:** PROPOSED / Architecture & Roadmap Revision Record  
**Repository Checkpoint:** `de450929e98beabec87987ec9d26fcad78a92968`  
**Product Owner Preference:** Free or near-zero recurring cost (prefer RM0/month); mostly-available hosting on Windows machine; invited-friend audience.

---

## 1. Executive Summary & Strategy Pivot

Following the initial deployment preparation report (`de45092`), the Product Owner reconsidered the hosting strategy. The previous plan prioritized commercial cloud platforms (Fly.io at ~$7–$14/mo, Hetzner VPS at ~$4/mo, Railway at ~$8–$11/mo). 

**The deployment strategy is hereby revised to prioritize low-cost, mostly-available self-hosting on the owner's Windows hardware:**
- **Cost Target:** RM0/month recurring hosting fees. A modest annual domain registration/renewal fee (~RM45–RM70/year) may be considered separately, but no spending is currently authorized.
- **Availability Target:** Mostly available. The application is reachable when the Windows host, Docker daemon, network tunnel, and residential internet connection are operating. Occasional downtime (e.g. host sleep, reboots, internet hiccups) is explicitly acceptable. 24/7 SLA is unnecessary.
- **Audience:** The Product Owner and invited friends (restricted pilot), not unrestricted anonymous public users.
- **Accessibility:** Zero-software diner experience: diners must be able to collaborate using ordinary mobile and desktop browsers without installing VPN clients.
- **Architectural Continuity:** Retain the single-instance Python standard-library WSGI adapter (`settletable.transport`), local SQLite WAL database, local filesystem receipt photo storage, CPU ONNX RapidOCR pipeline, and deterministic mathematical engine (`tabwise-apportion-v1`).

An enduring HTTPS origin, repeatable startup, durable data persistence, safe browser sessions, access controls, and off-host backups take priority over always-on cloud compute.

---

## 2. Phase A — Release Readiness Investigation & Defect Verification

Each architectural component was re-inspected against the actual implementation at `de45092`. Findings are labeled using the project's evidence classification:
- **`[VERIFIED]`**: Inspected directly in source code or proven by passing tests.
- **`[OBSERVED]`**: Confirmed operational behavior or measured runtime characteristic.
- **`[INFERENCE]`**: Logical architectural conclusion or necessary deployment deduction.
- **`[UNKNOWN]`**: Unmeasured or dependent on external environment factors.

### 2.1 Investigation & Defect Verification Matrix

| Capability / Boundary | Verified Status & Evidence | Classification | Impact on Self-Hosted Pilot |
|---|---|---|---|
| **Organizer Session TTL Defect** | `Authority.bootstrap()` in `settletable/authority.py:807` defaults to `session_ttl=3600` (1 hour) and caps at `86400` (24 hours). The previous documentation claim of a 7-day TTL (`604800s`) was **false**. | `[VERIFIED]` | **P1 Defect**: An organizer loses session authorization after 60 minutes. Because no recovery mechanism exists, meals become permanently un-finalizable. Session TTL must be aligned and made configurable up to 7 days. |
| **Administrative Bootstrap Usability Defect** | `tools/bootstrap_meal.py` prints a raw 43-character session credential string to stdout. The browser client relies entirely on `HttpOnly; SameSite=Strict` cookies (`settletable_session`) and has no route or UI to import a raw token. | `[VERIFIED]` | **P1 Defect**: Running the CLI does not establish a working browser session for the organizer. An organizer clicking `/#/meal/{id}` receives `401 invalid_session`. A secure, single-use Organizer Claim Link (analogous to invitation redemption) is required. |
| **Backup Atomicity Limitation** | `tools/backup_restore.py` runs `sqlite3.Connection.backup()` and then copies photos from disk *sequentially afterward*. | `[VERIFIED]` | **P1 Defect**: This is not an atomic hot backup. If a photo is uploaded or deleted during the copy, DB and filesystem desynchronize. A formal quiescence/maintenance consistency protocol is required. |
| **Restore Verification Defect** | `tools/backup_restore.py restore` copies files without checking whether the application is running and holding SQLite WAL locks, and does not verify restored photo hashes against the database table. | `[VERIFIED]` | **P1 Defect**: Restoring over an active SQLite process risks corruption. Restore must enforce application quiescence and cross-verify photo hashes against the database manifest. |
| **Dockerfile Redirection & Error Masking** | `Dockerfile:20` has unquoted `gunicorn>=21.2.0`, which invokes shell redirection in bash. Line 23 has `|| true` on RapidOCR cache generation, silently masking build-time model download failures. | `[VERIFIED]` | **P2 Defect**: Packaging bugs must be corrected (`"gunicorn>=21.2.0"`, remove `|| true`, ensure non-root permission to model cache directory). |
| **CI Container Test Absence** | `.github/workflows/python-tests.yml` runs unit tests and Node.js CDP tests directly on ubuntu-24.04 without testing the `Dockerfile` build or container startup. | `[VERIFIED]` | **P2 Defect**: Container build and smoke test must be added to CI to guarantee reproducibility. |
| **Loopback Meal Bootstrap Ingress Protection** | `POST /api/meals/{id}/bootstrap` rejects requests with proxy headers (`X-Forwarded-For`, etc.) or non-loopback `REMOTE_ADDR` with `403 Forbidden`. | `[VERIFIED]` | **Sound Invariant**: Prevents arbitrary public meal creation over tunnels. External access must remain blocked. |
| **Exact-Origin CSRF Protection** | Mutating requests enforce `X-SettleTable-Action: 1` and exact origin matching against `SETTLETABLE_SERVER_ORIGIN`. | `[VERIFIED]` | **Sound Invariant**: Guarantees browser CSRF defense over tunnels. `SETTLETABLE_SERVER_ORIGIN` must match the public tunnel domain. |
| **SQLite WAL Single-Instance Boundary** | SQLite runs with `PRAGMA journal_mode=WAL` and `busy_timeout=1000`. Thread-local connections serialize database transactions safely. | `[VERIFIED]` | **Sound Invariant**: Single-process multi-threaded Gunicorn (`--workers 1 --threads 4`) correctly enforces single-instance locking. |
| **RapidOCR Resource Overhead** | CPU inference uses ~150–300 MB baseline RAM, peaking to 500 MB–1 GB during multi-megapixel image processing. | `[VERIFIED]` / `[OBSERVED]` | **Host Requirement**: The Windows self-hosting machine (typically 8–32 GB RAM) has ample headroom compared to constrained free cloud tiers. |
| **Diner Invitation & Join Workflows** | `/invite/{token}` and `/join/{meal_id}` function cleanly over public HTTPS without loopback requirements. | `[VERIFIED]` | **Sound Invariant**: Ready for invited diners over public tunnels. |

---

## 3. Phase B — Hosting Architecture Comparison (Low-Cost / Mostly-Available)

### 3.1 Target Evaluation Criteria
1. **Direct Recurring Cost**: Strictly prefer RM0/month.
2. **Domain Requirement & Annual Fee**: Does the option require an owned custom domain (e.g. ~$10–$15/year), or does it provide a free stable subdomain?
3. **Guest / Diner Friction**: Can diners participate via ordinary mobile browsers without installing VPN clients, configuring profiles, or creating third-party accounts?
4. **Stable Public HTTPS Origin**: Does the hostname remain identical across reboots, host sleeps, and tunnel reconnections (essential for exact-origin CSRF and invitation links)?
5. **Security & Access Control**: Can the pilot be restricted to invited friends while shielding the host machine from unrestricted Internet probing?
6. **Provider Limits**: Are bandwidth quotas, request caps, and connection limits adequate for dining sessions with 5 MB receipt photo uploads?

### 3.2 Access Gateway Comparison Matrix

| Gateway Option | Direct Hosting Fee | Domain Prerequisite & Cost | Guest / Diner Experience | Stable URL Across Restarts | Provider Quotas & Limits | Verdict |
|---|---|---|---|---|---|---|
| **Windows Docker + Cloudflare Named Tunnel + Cloudflare Access** | **$0 / month** | **Required:** Custom domain (~$10–$15/yr / ~RM45–RM70/yr) pointed to Cloudflare DNS. | **Zero Software:** Ordinary browser. Access can be restricted via Email OTP PIN (allowlist of friends' emails) or open tunnel relying on app tokens. | **YES**: Permanent custom FQDN (e.g. `settletable.example.com`). Reconnects automatically on boot. | Cloudflare Zero Trust free tier: **Up to 50 users**. **Unmetered bandwidth**. | **PRIMARY RECOMMENDATION (If Domain Approved or Owned)** |
| **Windows Docker + Tailscale Funnel** | **$0 / month** | **None (RM0/yr):** Uses auto-assigned `*.ts.net` MagicDNS subdomain. | **Zero Software:** Public internet traffic routes through Tailscale edge to local port. Diners open standard browser. | **YES**: Permanent stable FQDN (e.g. `node.tailnet.ts.net`) with automated Let's Encrypt TLS. | Tailscale Personal: **Free for up to 6 users**, unlimited user devices. Relay throughput limits apply on DERP relays if direct path unavailable. | **PRIMARY RECOMMENDATION (Strict RM0 / No Domain Spend)** |
| **Windows Docker + Tailscale Serve (Private Tailnet)** | **$0 / month** | None (RM0/yr) | **High Friction:** Every diner **must install Tailscale**, create a Tailscale account, and accept a device share. | **YES**: Stable tailnet IP/name. | Generous free tier limits. | **REJECTED for General Pilot** (Violates PO requirement for zero-software diner browser access). |
| **ngrok Free Development Domain** | **$0 / month** | None (RM0/yr) for 1 assigned dev domain. | **Poor / Interstitial:** Visitors must click through an ngrok anti-phishing interstitial warning page. Breaks mobile flow. | **YES**: 1 static domain provided on free tier. | **TIGHT LIMITS**: **1 GB/month bandwidth**, **20k requests/month**. 1 dining session with multiple 5MB photos & polling quickly exhausts quota. | **FALLBACK ONLY (High Quota Risk)** |
| **Cloudflare Quick Tunnel** | **$0 / month** | None | Ordinary browser. | **NO**: Random URL (`*.trycloudflare.com`) generated per connection. Changes on every restart or disconnect. | Intended for temporary debugging only. | **REJECTED for Persistent Pilot** (Fails stable URL requirement). |
| **Paid Cloud VPS / PaaS (Fly.io, Hetzner, Railway)** | $4.10 – $14.75 / month | Optional or included | Ordinary browser. | YES | Unlimited / standard VPS quotas. | **DEFERRED** (Superseded by PO low-cost preference). |

### 3.3 Gateway Decisions & Recommendations

1. **Finalized Primary Architecture (Accepted by Product Owner):**
   - **Windows Docker + Cloudflare Named Tunnel (`cloudflared`)**:
     - Dedicated SettleTable subdomain under a custom domain (e.g. `settle.yourdomain.com`).
     - Automated edge TLS termination managed by Cloudflare with zero certificate renewal overhead.
     - **No Cloudflare Access pre-authentication for diners**: Diners access the app directly via standard mobile/desktop browsers without third-party email OTP friction, preserving seamless dining room collaboration.
     - **Authoritative Application Security**: SettleTable's built-in defense-in-depth remains authoritative (loopback-only meal bootstrap, exact-origin CSRF validation, unguessable 43-character invitation tokens, and organizer-controlled join requests).
     - **Cost Target**: RM0/month hosting subscription; modest annual domain registration/renewal fee (~RM45–RM70/year) accepted in principle.
     - *Note*: No domain purchase, DNS change, or external tunnel activation is authorized until Stage B live cutover.

2. **Documented Fallback Architecture:**
   - **Tailscale Funnel**:
     - Permanent stable FQDN (`*.ts.net`), automated Let's Encrypt TLS, RM0/year total spend (zero domain cost).
     - Reserved strictly as an immediate fallback if domain provisioning is delayed or local network environments block Cloudflare tunnel traffic.

3. **Emergency Temporary Fallback:**
   - **ngrok Free**: Reserved strictly as a temporary diagnostic fallback, noting its 1 GB/month bandwidth cap and anti-phishing interstitial warning page.

---

## 4. Re-evaluation of Existing Deployment Artifacts (`de45092`)

| Deliverable | Merged State (`de45092`) | Action | Justification & Adaptation Required |
|---|---|---|---|
| `settletable/transport.py` (`/healthz`) | Lightweight health check endpoint | **KEEP** | Essential for Docker `HEALTHCHECK`, tunnel health monitoring, and smoke testing. |
| `settletable/wsgi.py` | Production WSGI entrypoint with env vars | **KEEP** | Cleanly loads `SETTLETABLE_DB_PATH`, `SETTLETABLE_STORAGE_DIR`, `SETTLETABLE_SERVER_ORIGIN`, and `SETTLETABLE_ALLOWED_HOSTS`. |
| `deploy/env.template` | Environment variable documentation | **ADAPT** | Update default origin to reflect self-hosted tunnel domains (`*.ts.net` or custom domain). Document session TTL. |
| `Dockerfile` | Multi-stage Python 3.12 image | **CORRECT** | Fix shell redirection syntax (`"gunicorn>=21.2.0"`), remove `|| true` masking on OCR pre-cache, verify non-root cache permissions. |
| `docker-compose.yml` | Single-instance service with volume | **ADAPT** | Pin to loopback (`127.0.0.1:8000:8000`), configure named volume for Windows Docker Desktop, add tunnel sidecar service definition if applicable. |
| `deploy/caddy/Caddyfile` | Caddy reverse proxy template | **ADAPT / DEFER** | If using Cloudflare Tunnel or Tailscale Funnel, ingress TLS is terminated by the tunnel agent. Caddy can be retained as an optional local defense-in-depth proxy or omitted to minimize complexity. |
| `deploy/nginx/nginx.conf` | Linux Nginx reverse proxy template | **DEFER** | Tailored for dedicated Linux VPS deployments; unnecessary for Windows self-hosting with tunneling. |
| `tools/backup_restore.py` | Hot backup & disaster recovery utility | **CORRECT** | Remove misleading "atomic hot backup" claim; implement a safe quiescence protocol; verify photo hashes against SQLite manifest; prevent restore over running application; add off-host copy support. |
| `tools/bootstrap_meal.py` | CLI administrative meal bootstrap | **CORRECT** | Currently prints an unusable raw token. Must generate a secure, single-use Organizer Claim Link that establishes the browser `settletable_session` cookie cleanly. |
| `tools/deployment_smoke_check.py` | Automated 8-point smoke test suite | **KEEP** | Excellent automated validation of healthz, static assets, security headers, and CSRF/Origin enforcement over tunnels. |
| `README.md` | Comprehensive project documentation | **ADAPT** | Update deployment section to focus on Windows self-hosting and tunneling; clearly state licensing status and operational limitations. |
| `SECURITY.md` | Threat model & disclosure policy | **KEEP** | Accurately describes the two-tier boundary and application security invariants. |
| `CHANGELOG.md` | Revision history across PRs | **KEEP** | Accurate record of historical releases and merged pull requests. |

---

## 5. Deployment-Hardening Backlog (Pre-Pilot Requirements)

Before any external deployment or invited-friend pilot is authorized, the following technical defects must be remediated in code and validated with automated tests:

### Priority 1: High Pilot Risk (Security & Continuity)
1. **Organizer Session Continuity & Browser Claim Flow**:
   - Create an authorized, bounded Organizer Claim mechanism (e.g. `POST /api/meals/{id}/claim-organizer/{token}`) that issues the `settletable_session` HttpOnly cookie directly to the organizer's browser upon first access.
   - Update `tools/bootstrap_meal.py` to output this secure claim URL.
   - Add automated adversarial tests: single-use enforcement, expiry enforcement, and replay rejection.
2. **Session TTL Alignment**:
   - Align `settletable/authority.py:807` session TTL with product requirements: permit configuring `session_ttl` up to 7 days (604,800 seconds) for dining meals, while keeping sensible defaults.
   - Ensure organizer sessions do not abruptly expire after 1 hour during an active dinner.
3. **Quiescent Backup & Verified Restore Protocol**:
   - Refactor `tools/backup_restore.py`: replace the false "atomic hot backup" claim with a documented, verified quiescence protocol (brief application write pause or read-only lock during photo sync).
   - Ensure `restore` explicitly checks for active application processes holding the database open and refuses to overwrite live databases.
   - Ensure `restore` validates every restored photo's SHA-256 hash against the SQLite `receipt_photos` table.
   - Add CLI options to copy backups to an off-host directory (e.g. secondary disk or cloud drive).

### Priority 2: Medium Pilot Risk (Packaging & Reliability)
4. **Dockerfile Corrections & Verified Model Caching**:
   - Fix `Dockerfile`: quote `"gunicorn>=21.2.0"`.
   - Remove `|| true` on RapidOCR cache step so failures fail the build loudly.
   - Ensure `/home/settletable/.cache` or `/app` permissions permit non-root `settletable` user to load ONNX models.
5. **CI Container Test Harness**:
   - Add a step to `.github/workflows/python-tests.yml` to build the `Dockerfile` and execute `tools/deployment_smoke_check.py` against the running container on the Ubuntu runner.
6. **Windows Host Restart & Lifecycle Documentation**:
   - Document Windows power settings (preventing sleep during scheduled dining events), Docker Desktop startup settings (`Start Docker Desktop when you log in`, `restart: unless-stopped`), and tunnel reconnection behavior.

---

## 6. Revised 4-Stage Release Roadmap & Acceptance Gates

```
┌────────────────────────────────────────────────────────────────────────┐
│             STAGE A: Local Reliability & Security Hardening            │
│  - Correct Organizer Claim Flow & Session TTL                          │
│  - Correct Backup/Restore Quiescence & Photo Hash Verification         │
│  - Correct Dockerfile Syntax & Pre-cached OCR Verification             │
│  - Add Container Build & Smoke Tests to CI                             │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Autonomous Orchestrator Merge (No External Access)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│          STAGE B: Mostly-Available, Low-Cost Hosting Preparation       │
│  - Configure Selected Tunnel (Tailscale Funnel or Cloudflare Tunnel)   │
│  - Verify Windows Host Docker Desktop & Tunnel Auto-Reconnect          │
│  - Test Exact-Origin CSRF & Ingress Headers with Stable Hostname       │
│  - Prepare Operational Runbook for Downtime & Reconnection             │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Product Owner Authorization Required
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   STAGE C: Restricted Online Pilot                     │
│  - Pilot with Invited Friends using Synthetic Receipts First           │
│  - End-to-End Multi-Device Journey (Mobile + Desktop Browsers)         │
│  - Real Receipt OCR, Collaboration, Settlements & Photo Zoom           │
│  - Off-Host Backup and Disaster Recovery Simulation                    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Product Owner Authorization Required
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                 STAGE D: Official GitHub Tagged Release                │
│  - Product Owner Decision on Repository Visibility (Private vs Public) │
│  - Product Owner Decision on Software License Grant                    │
│  - Tag and Publish Official Release v1.0.0                             │
└────────────────────────────────────────────────────────────────────────┘
```

### Stage A Gate: Local Reliability & Security Hardening
- **Scope:** Correct P1 and P2 defects in code, packaging, and tests.
- **Criteria:**
  - [x] Organizer can claim authority via browser link; single-use and expiry verified.
  - [x] Session TTL configurable up to 30 days (defaulting to 7 days); documented accurately.
  - [x] Backup creates consistent snapshots under quiescence; restore enforces stopped application contract (`--confirm-stopped` + health probe), stages files in isolation, archives previous dataset, and verifies post-cutover SHA-256 hashes.
  - [x] Staged restore failure injection proves automated rollback to previous valid dataset without data destruction.
  - [x] Token redaction verified across application logging, query parameters, authorization headers, and cookie logs. Clean POST `/api/organizer-claims/inspect` and `/api/meals/{id}/organizer-claims/claim` prevent token exposure in web server / reverse proxy request lines.
  - [x] CLI outputs single-use Organizer Browser Setup Link containing ephemeral claim secret presented once on stdout; persistent session credentials never leaked.
  - [x] `Dockerfile` builds cleanly without `|| true`; container runs RapidOCR inference as non-root user.
  - [x] CI builds container and passes `tools/deployment_smoke_check.py` (11 checks).
  - [x] 309 Python tests pass; independent security review passes.
- **Authority:** Autonomous under orchestrator governance. Zero external traffic.
- **Status:** **PASS / COMPLETED (PR #47 + Corrective Review PR #48)**. Stage A local hardening prerequisites are fully met. Product Owner decision finalized: **Cloudflare Named Tunnel (`cloudflared`)** with custom domain (Tailscale Funnel fallback). Ready for Stage B external hosting gateway preparation.

### Stage B Gate: Mostly-Available Hosting Preparation
- **Scope:** Prepare Windows Docker + Tunnel configuration, operational runbooks, and synthetic reverse-proxy verification.
- **Criteria:**
  - [x] Selected gateway configured: Cloudflare Named Tunnel (`cloudflared`) via remotely-managed token mode in Docker Compose (`with-cloudflared` profile), pinned to tested stable release `cloudflare/cloudflared:2026.10.7`.
  - [x] Locally-managed alternative documented with inactive template (`deploy/cloudflare/config.template.yml`) and guide (`deploy/cloudflare/README.md`).
  - [x] Windows host operations runbook completed (`docs/runbooks/windows_host_operations.md`): power/sleep prevention, Docker Desktop auto-start, crash consistency, WAN outage auto-reconnect, and stopped-container disaster recovery.
  - [x] Stopped-container consistent backup and verified restore protocol documented with Docker volume handling; non-destructive end-to-end drill verified using isolated synthetic Docker volumes (`tools/verify_isolated_docker_drill.py`).
  - [x] Synthetic reverse-proxy / Cloudflare ingress test suite implemented (`tests/test_reverse_proxy_ingress.py` - 9 tests passing):
    - [x] Public custom domain Host validation (settle.example.com accepted; foreign/spoofed hosts return 400 invalid_host).
    - [x] Exact-origin CSRF protection under public HTTPS (HTTPS origin matches; HTTP scheme mismatch, foreign origins, and null origins return 403; missing action header returns 400).
    - [x] Cloudflare forwarding headers (CF-Connecting-IP, CF-Ray, CF-Visitor, X-Forwarded-Proto) processed cleanly.
    - [x] External meal bootstrap rejected with 403 Forbidden on ANY proxy forwarding headers (including CF-Connecting-IP, True-Client-IP, X-Cluster-Client-IP).
    - [x] Unauthenticated access to private meal data and receipt photos denied (401 invalid_session).
    - [x] Private API and receipt photo responses never cached by shared intermediaries (`Cache-Control: no-store` and `private, no-cache, no-store, must-revalidate`).
    - [x] Secret tokens completely redacted from application request logs.
    - [x] Abuse protections verified: header limits (431), payload boundaries (413), and integer bounds (400).
    - [x] Deny-by-default behavior for unmatched ingress hostnames.
  - [ ] Live external activation: Stable HTTPS FQDN verified live across computer reboots and tunnel restarts (Requires Product Owner authorization to purchase domain, configure DNS, and start tunnel).
- **Authority:** Autonomous configuration dry-run and offline preparation; opening tunnel to external traffic strictly requires Product Owner authorization.
- **Status:** **PASS (Offline Preparation Complete & Verified)**. Offline templates, Docker Compose tunnel profile, Windows operational runbooks, synthetic ingress test suites, and isolated Docker recovery drill are fully verified. Live external deployment remains stopped pending Product Owner domain purchase and activation authorization.

### Stage C Gate: Restricted Online Pilot (`v0.9.0-beta.1`)
- **Scope:** Live testing with Product Owner and invited friends.
- **Criteria:**
  - [ ] Friends access application via ordinary mobile browsers without installing VPN software.
  - [ ] Real OCR scans Malaysian dining receipts on host CPU with correct SST/service charge detection.
  - [ ] Collaborative allocations, multi-payer contributions, and peer reimbursements persist across host restarts.
  - [ ] Off-host backup copy verified by restoring onto a clean secondary directory.
- **Authority:** Explicit Product Owner authorization required.

### Stage D Gate: Official GitHub Tagged Release (`v1.0.0`)
- **Scope:** Public presentation, release tagging, and project governance.
- **Criteria:**
  - [ ] Product Owner explicit decision on repository visibility (Private vs Public).
  - [ ] Product Owner explicit decision on open-source licensing grant (or retaining All Rights Reserved).
  - [ ] Pre-publication audit (`tools/audit_repository.py`) passes with 0 findings.
  - [ ] Tag `v1.0.0` signed and pushed.
- **Authority:** Strictly requires Product Owner human escalation.

---

## 7. Stage B Implementation Rationale & Connector Topology

### 7.1 Cloudflare Management Mode Analysis

1. **Remotely-Managed Tunnels (Selected & Recommended)**:
   - **Mechanism**: The tunnel and its public hostnames are created and managed via the Cloudflare Zero Trust Dashboard (or API/Terraform). The local connector container runs with a single tunnel token: `cloudflared tunnel --no-autoupdate run --token <TUNNEL_TOKEN>`.
   - **Rationale**:
     - Eliminates local credential JSON files and certificate bundles from the repository and host filesystem.
     - Provides a single source of truth: routing and DNS are managed centrally on Cloudflare's edge.
     - Docker Compose integration requires only passing `CLOUDFLARE_TUNNEL_TOKEN` via environment variable or `.env`.
     - Zero configuration drift or desynchronization between local YAML files and remote Cloudflare routing.
2. **Locally-Managed Tunnels (Documented Alternative)**:
   - **Mechanism**: Uses a local YAML configuration file (`deploy/cloudflare/config.template.yml`) and credentials JSON file generated by `cloudflared tunnel create`.
   - **Trade-offs**: Introduces competing sources of configuration between local files and Cloudflare DNS, requires mounting credentials files into Docker containers on Windows, and increases the risk of accidental secret leakage. Kept as an offline template for reference only.

### 7.2 Connector Topology Analysis

1. **Topology A: Docker Compose Bridge Network (Selected & Recommended)**:
   - `cloudflared` runs as a container service (`settletable_tunnel`) alongside `settletable_app` on the shared Docker bridge network (`tabwise_default`).
   - Ingress target: `http://settletable:8000`.
   - Port `8000` on the Windows host remains bound to `127.0.0.1:8000` solely for local operator health probes and administrative CLI commands.
   - External traffic never touches the host's physical network adapter directly.
2. **Topology B: Native Windows Service (Documented Alternative)**:
   - `cloudflared.exe` installed directly on Windows and registered as a Windows Service pointing to `http://127.0.0.1:8000`.
   - Kept as an optional alternative for operators who prefer native Windows service management over containerized connectors.

### 7.3 Application-Level Abuse Controls & Pre-Activation Ingress Invariants

Review of publicly reachable endpoints under a custom domain:
1. **Join Requests (`POST /api/meals/{meal_id}/join-requests`)**:
   - Protected by bounded table limits: max 20 active pending requests per meal, max 100 historical records (`resource_limit`).
   - Constant-time anti-enumeration response (`invalid_join_target`) across invalid, organizer, or inactive targets.
   - Duplicate prevention rejects concurrent requests for the same participant (`active_join_request_exists`).
   - Unauthenticated join requests do not bump meal revision.
2. **Organizer Claims (`/api/organizer-claims/*`)**:
   - Inspection (`POST /api/organizer-claims/inspect`) takes unguessable 43-character token, hashes with domain-separated salt before DB lookup, and returns `valid: false` for nonexistent tokens without credentials.
   - Redemption is single-use (`consumed = 1`) inside `BEGIN IMMEDIATE`, rotating credentials and revoking prior claims.
3. **Receipt Uploads & OCR Processing**:
   - Strictly restricted to authenticated organizers (`is_org == True`). Public unauthenticated requests and regular diners receive 401/403 and cannot trigger OCR or upload files.
   - Strict MIME validation (JPEG, PNG, WebP) and magic byte header validation (`validate_image_payload`).
   - Request size boundary capped at `MAX_BODY_BYTES` (50MB).
4. **Pre-Activation Ingress Verification Checks**:
   - Cache-Control: Dynamic API responses enforce `Cache-Control: no-store`; receipt photos enforce `Cache-Control: private, no-cache, no-store, must-revalidate`. Intermediary caching on Cloudflare edge is bypassed.
   - Request Boundaries: 4KB single header limit (431), 16KB total headers limit (431), 50MB body limit (413).
   - Host & Origin Defense-in-Depth: Application enforces exact origin matching on mutating requests (`X-SettleTable-Action: 1` + Origin/Referer matching `SETTLETABLE_SERVER_ORIGIN`) and allowed hostnames (`SETTLETABLE_ALLOWED_HOSTS`).
   - Loopback Bootstrap Invariant: Ingress blocks `/api/meals/*/bootstrap` with HTTP 403 Forbidden upon detecting any proxy forwarding headers (`CF-Connecting-IP`, `True-Client-IP`, `X-Forwarded-*`).

---

## 8. Future Manual Deployment Checklist (Product Owner Authorization Boundaries)

When the Product Owner decides to proceed to live external hosting, the following sequential checklist defines the exact actions requiring human authority versus automated steps:

| Step | Action | Authority Required | Description / Command |
|---|---|---|---|
| **1** | **Domain Registration** | **Product Owner Authorization** | Register custom domain name (e.g. `example.com`) at registrar of choice (~RM45–RM70/year). Delegate nameservers to Cloudflare. |
| **2** | **Zero Trust Tunnel Creation** | **Product Owner Authorization** | In Cloudflare Zero Trust dashboard (*Networks > Tunnels*), create a new Named Tunnel (e.g. `settletable-prod`). |
| **3** | **Public Hostname Route** | **Product Owner Authorization** | Add public hostname in dashboard: Subdomain `settle`, Domain `example.com`, Service `HTTP`, URL `settletable:8000`. |
| **4** | **Configure Local `.env`** | Operator / PO | Copy `deploy/env.template` to `.env`. Set `CLOUDFLARE_TUNNEL_TOKEN=<token>`, `SETTLETABLE_SERVER_ORIGIN=https://settle.example.com`, and `SETTLETABLE_ALLOWED_HOSTS=settle.example.com,localhost:8000,127.0.0.1:8000,settletable:8000`. Ensure `.env` read permissions are restricted. |
| **5** | **Start Tunnel Connector** | **Product Owner Authorization** | Launch services with tunnel profile: `docker compose --profile with-cloudflared up -d`. |
| **6** | **Live Ingress Verification** | Automated / Operator | Run deployment smoke checks against live public endpoint: `python tools/deployment_smoke_check.py --url https://settle.example.com`. |
| **7** | **Restricted Pilot Launch** | **Product Owner Authorization** | Bootstrap meal locally via `python tools/bootstrap_meal.py bootstrap --meal-id <id>`, claim organizer session via setup link, issue invitation links to invited friends, and conduct restricted pilot (`v0.9.0-beta.1`). |
