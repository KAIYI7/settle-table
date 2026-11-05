# Changelog

All notable changes to SettleTable are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Proposed v1.0.0] - Official Release Candidate

### Added
- Comprehensive GitHub documentation overhaul, architecture overview, and technology stack breakdown in `README.md`.
- `SECURITY.md` establishing vulnerability disclosure policies, threat model, and two-tier ingress security boundaries.
- Formal release acceptance gates in `docs/plans/MVP_RELEASE_AND_DEPLOYMENT.md`.

---

## [Proposed v0.9.0-beta.1] - Restricted Deployment Pilot

### Added
- Standard production WSGI application entrypoint (`settletable/wsgi.py`) with environment-based configuration (`SETTLETABLE_DB_PATH`, `SETTLETABLE_STORAGE_DIR`, `SETTLETABLE_SERVER_ORIGIN`, `SETTLETABLE_ALLOWED_HOSTS`).
- Lightweight health check probe (`/healthz` and `/api/healthz`) for container orchestrators and reverse proxies.
- Production containerization: `Dockerfile` (non-root `settletable` user, pre-cached RapidOCR models, volume mount `/data`), `docker-compose.yml`, and `.dockerignore`.
- Reference Tier 1 reverse proxy configurations:
  - Caddy (`deploy/caddy/Caddyfile`): Automated HTTPS, strict HSTS, 10MB body limit, `/bootstrap` route blocking.
  - Nginx (`deploy/nginx/nginx.conf`): Wire buffer bounds, `client_max_body_size 10M`, loopback-only bootstrap access.
- Safe environment template (`.env.example`) documenting all production variables.
- Hot backup and disaster recovery utility (`tools/backup_restore.py`) using SQLite Online Backup API (`sqlite3.backup()`) and atomic receipt photo directory synchronization.
- Administrative meal bootstrap CLI (`tools/bootstrap_meal.py`) for host/container provisioning without external HTTP exposure.
- Automated deployment smoke check suite (`tools/deployment_smoke_check.py`).

---

## [PR #46] - Mobile Amount Field Clipping Remediation

### Fixed
- Remediated Android Chrome (POCO F6) visual clipping of negative monetary values (e.g. `-0.01` rendering as `-0.0`) in the OCR candidate adjustments editor by expanding the details grid column to `minmax(0, 1fr) 118px` and input width to `118px` across container queries and media query fallbacks.

---

## [PR #45] - Mobile UX Audit Remediation

### Fixed
- Resolved complimentary item flex row layout overflow on 320px–375px screens with scoped wrapping and word-breaking.
- Harmonized Notion password inputs (`input[type="password"]`) with design system tokens (44px min-height, dark background, active focus outline).
- Expanded home breadcrumb link and review confirmation checkbox to compliant $\ge 44 \times 44\text{px}$ mobile touch targets.

---

## [PR #44] - Suggested Peer Transfer Prefill Navigation

### Added
- Renamed transfer prefill button to "Use Suggestion" (`.prefill-transfer-btn`) for cognitive clarity.
- Context-aware auto-scrolling to the reimbursement form with sticky header clearance and heading focus.
- Polite live-region status banner (`#prefill-transfer-banner`) confirming prefill without auto-opening virtual keyboards.

---

## [PR #43] - Context-Aware Workflow Navigation and Focus Transitions

### Added
- Smooth contextual navigation and programmatic focus management across key workflow milestones:
  - OCR acceptance transitions to Receipt Review checkbox.
  - Review sealing transitions to Item Allocation (or Finalization if all items allocated).
  - Meal finalization transitions to Final Apportionment Summary.
- Dual-layer `prefers-reduced-motion` compliance.

---

## [PR #42] - Complimentary Zero-Priced Items Support

### Added
- Supported RM0.00 complimentary items (e.g. Warm Water, Ice Water) on receipts without requiring diner portion allocation.
- Calculation engine allows empty share collections for zero-priced items.
- Informational `.is-complimentary` badges in both Diner and Organizer UI views.

---

## [PR #41] - Financial Form Select Dropdown Chevron Polish

### Added
- Enhanced native `<select>` form controls with crisp inline SVG chevrons, expanded padding clearance, and active focus rings.

---

## [PR #40] - Mobile Stepper Touch Target Compliance

### Fixed
- Expanded numeric steppers and allocation buttons to $\ge 44 \times 44\text{px}$ touch targets meeting WCAG 2.5.5 standards.

---

## [PR #37] - Peer Settlement Tracking & Suggested Transfers

### Added
- Greedy transfer optimization algorithm minimizing total transactions needed to settle all net balances.
- Partial peer reimbursement recording, validation, and reversal.
- Historical settlement ledger persisted to SQLite `peer_transfers` table.

---

## [PR #36] - Multi-Payer Contributions & Net Balance Reconciliation

### Added
- Multi-payer contribution recording with payment method tracking (Cash, Card, E-Wallet, Bank Transfer).
- Real-time net balance reconciliation: $\text{Net Balance} = \text{Total Contributed} - \text{Total Consumed}$.
- Immutably audited `payer_contributions` table in SQLite with sqlite triggers preventing deletes.

---

## [PR #32 - PR #35] - Receipt Photo Retention & Zoom Viewer

### Added
- Crash-consistent receipt photo storage on server filesystem with metadata recorded in SQLite.
- Interactive full-screen pan and zoom viewer modal with mouse wheel and drag support.
- Optional Notion export upgrade attaching original receipt photo files into exported pages.

---

## [PR #13 - PR #31] - Core Collaboration, OCR & Notion MVP

### Added
- Zero-dependency vanilla ES2022 / HTML / CSS browser client.
- Offline RapidOCR engine on CPU with Malaysian SST / service charge parser.
- Optional asynchronous Notion financial exporter with table blocks.
- Dual diner invitation flows: pre-minted token links (`/invite/{token}`) and general join requests (`/join/{meal_id}`).
- Concept C organizer-authorized allocation and diner item claiming.
- Strict two-tier ingress and defense-in-depth transport boundary.
