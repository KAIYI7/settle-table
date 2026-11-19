# SettleTable — Future Improvements & Product Roadmap

**Document:** `docs/plans/FUTURE_IMPROVEMENTS_ROADMAP.md`  
**Status:** PROPOSED / BACKLOG & REFERENCE RECORD  
**Author:** Antigravity / SettleTable Orchestrator  
**Date:** 2026-11-19  
**Repository Baseline:** `main` (commit `9e63178` / PR #65 `06c0fee`)  
**Domain:** Operational Resilience, Dining Ergonomics, Offline PWA, Multi-Meal Identity  

---

## 1. Executive Summary & Current State Baseline

SettleTable is currently operating as a stable, verified, production-ready web application (`https://settle.kybuilds.com`). Across the foundation laid from initial research through recent milestones:
- **Financial Apportionment**: Exact sen-level deterministic rounding with cent conservation (`tabwise-apportion-v1`) and support for RM0.00 complimentary items.
- **Local OCR Extraction**: CPU ONNX RapidOCR pipeline extracting items, Malaysian SST, and service charges with privacy-safe review and full-screen zoom inspection.
- **Collaborative Settlement**: Multi-payer counter bill funding, peer reimbursements with two-party confirmation invariants, and synthetic checkout demonstrations.
- **Zero-Friction Access**: Cloudflare Turnstile anti-bot protection, nanoid-tokenized public room creation, personal diner invitations, and general join links with approval/cancellation workflows.
- **Information Hierarchy**: Refined, diner-friendly language without developer jargon, unnested card structures, and responsive mobile layouts (320px–430px).
- **Verification**: 480 Python unit/integration tests and 10 native Chrome CDP end-to-end browser regression suites passing 100%.

There are **zero blocking defects** currently impeding dinner bill splitting. However, as real-world usage expands, opportunities exist to improve operational resilience, reduce settlement friction at restaurant tables, and address browser session limitations.

This document serves as the durable backlog and architectural reference for future improvements.

---

## 2. Core Architectural Invariants (Non-Negotiable)

Any future enhancement documented here must strictly respect these established architectural invariants:

1. **Strict Non-Custodial Boundary**: SettleTable calculates fair splits and tracks self-attested settlements. It never holds, moves, escrows, or directly processes banking/credit card transactions.
2. **Mathematical Determinism & Cent Conservation**: The sum of all diner shares must always equal the receipt total to the exact integer cent/sen ($$\sum \text{shares} = \text{total\_sen}$$).
3. **First-Class Zero-Session Guest Dining**: Diners must always be able to join a room, claim items, view apportionments, and report payments without creating an account or installing native software.
4. **Single-Database SQLite WAL Atomicity**: State changes, audit logs, and memberships must execute within atomic SQLite transactions without external database dependencies.
5. **Defense-in-Depth & Data Privacy**: Receipt images and personal dining data remain private to the room participants; external web reporting (Notion) remains strictly opt-in and view-only.

---

## 3. Tier 1: Operational Resilience & Automated Health (Necessary)

These improvements protect production availability and prevent data loss on the self-hosted Windows hardware.

### 3.1 Off-Host Encrypted Backup Synchronization
- **Problem**: `tools/backup_restore.py` currently executes atomic SQLite backups and stores receipt photos locally on the host's physical disk (`settletable_data` volume). If host hardware experiences drive failure, data could be lost.
- **Proposed Architecture**:
  - Implement Stage C1-A from `docs/plans/MVP_RELEASE_AND_DEPLOYMENT.md`: an automated, daily/post-event off-host backup script.
  - Snapshot the SQLite DB via `sqlite3.Connection.backup()` during quiet hours, bundle with the receipt storage directory, encrypt using AES-GCM (via `cryptography` or 7-Zip CLI with a user-owned passphrase), and upload to Google Drive or OneDrive using rclone or provider CLI.
  - Zero sensitive database bytes stored unencrypted outside the primary host.

### 3.2 Automated Cloudflare Tunnel Health Alerting
- **Problem**: SettleTable is exposed via a Cloudflare Named Tunnel (`cloudflared`) on residential internet. If the Windows host reboots for system updates, enters sleep mode, or experiences a network interruption, the service becomes unreachable without notifying the operator.
- **Proposed Solution**:
  - Configure Cloudflare Zero Trust Tunnel Health notifications (built-in Cloudflare dashboard feature) to dispatch a webhook alert to Telegram, Discord, or Email whenever tunnel connector status changes from `HEALTHY` to `DOWN`.
  - Zero application code changes required; purely operational configuration.

### 3.3 Proactive Session Expiry Notification
- **Problem**: Organizer sessions have a configurable TTL (1 hour to 7 days). If an organizer leaves a room open on their mobile browser across days, an expired cookie causes unexpected `401 invalid_session` when attempting an action.
- **Proposed Solution**:
  - In `settletable/static/app.js`, compare `Date.now()` against the session expiration timestamp returned in the snapshot metadata.
  - If fewer than 15 minutes remain, render a discrete banner: *"Your organizer session will expire soon. [Extend Session] or save your [Emergency Recovery Link]"*.
  - Clicking "Extend Session" invokes `POST /api/meals/{meal_id}/session/refresh` (if authenticated) to rotate the session TTL cleanly.

---

## 4. Tier 2: Real-World Dining & Settlement Ergonomics (High Impact)

These features dramatically reduce friction during the actual dining and payment experience.

### 4.1 DuitNow QR & Creditor Payment Handles on Peer Settlements (⭐️ Quick Win)
- **Problem**: When a meal is finalized, SettleTable tells Bob: *"Pay RM 14.50 to Alice"*. Bob must leave the browser, open WhatsApp, message Alice for her bank details or DuitNow QR, wait for her reply, and open his banking app.
- **Proposed Solution**:
  - In the **Peer Settlements & Reimbursements** card, allow any creditor (e.g. Alice) to optionally provide a **Payment Handle**:
    1. A short text note (e.g., `DuitNow: 012-3456789 (Maybank)` or `Touch 'n Go eWallet`).
    2. An optional uploaded DuitNow QR image (stored locally in `settletable_data/qrs/{participant_id}.png`).
  - When Bob reviews his suggested transfer to Alice, the card displays:
    - Alice's payment handle text with a 1-click **[📋 Copy]** button.
    - A **[📱 Show QR Code]** modal allowing Bob to scan Alice's DuitNow QR directly from his banking app.
  - Bob then taps **[💸 I've Sent Payment]**, which triggers the existing collaborative confirmation workflow.
- **Safety & Invariant Preservation**:
  - Strictly non-custodial: SettleTable does not process, verify, or touch the bank transaction.
  - Stored strictly per-meal or per-session; no cross-meal tracking without explicit user consent.
  - Input sanitized to prevent XSS.

### 4.2 Progressive Web App (PWA) & Offline Receipt Shell
- **Problem**: Restaurant dining rooms and basements frequently suffer from spotty mobile reception. If a diner refreshes the browser while signal is lost, the page fails to load.
- **Proposed Solution**:
  - Introduce `manifest.json` and a lightweight Service Worker (`sw.js`).
  - **Asset Caching**: Cache HTML, CSS, JavaScript, and icons locally via Cache-First strategy. The app shell opens instantly in < 200ms regardless of network connectivity.
  - **Offline Snapshot Cache**: Persist the latest fetched meal snapshot in `localStorage` or IndexedDB. If offline, the diner can still review their item portions, split amounts, and receipt summary without network errors.
  - **"Add to Home Screen"**: Allows organizers and frequent diners to launch SettleTable in full-screen standalone mode without browser URL chrome.

---

## 5. Tier 3: Receipt Ingestion & Regional Adaptations (Product Depth)

### 5.1 Multi-Page / Long Receipt OCR Stitching
- **Problem**: Long receipts at banquets, hotpot, or dim sum restaurants often require multiple photos (e.g. Page 1 for food items, Page 2 for drinks and taxes/service charges). SettleTable currently supports only one receipt photo per scan.
- **Proposed Solution**:
  - In the **Receipt Scanner** staging card, add an **[📷 Add Another Receipt Photo]** action before final confirmation.
  - The server processes each image through RapidOCR, merges extracted line items with deduplication prompts, and sums taxes/service charges into a single staged candidate.
  - All uploaded receipt images are preserved in the meal's photo archive and rendered in the fullscreen zoom viewer with a thumbnail carousel.

### 5.2 Multi-Currency & Configurable Formatting
- **Problem**: Malaysian Ringgit (`RM` / `MYR`) and 2-decimal sen arithmetic are hardcoded throughout UI templates (`RM ${(sen/100).toFixed(2)}`).
- **Proposed Solution**:
  - Add an optional currency selector during meal room creation (`MYR`, `SGD`, `USD`, `EUR`, `GBP`, `JPY`, etc.).
  - Backend math remains purely integer-based (storing fractional cents/sen in the smallest standard unit). For zero-decimal currencies (e.g. JPY), format without decimals.
  - UI templates dynamically format using `Intl.NumberFormat(locale, { style: 'currency', currency })`.

---

## 6. Tier 4: Multi-Meal Architecture & Persistent Identity

### 6.1 "My Meals" Dashboard & Passwordless Accounts
- **Problem**: Detailed comprehensively in [ACCOUNT_IDENTITY_AND_MY_MEALS.md](ACCOUNT_IDENTITY_AND_MY_MEALS.md). A single `settletable_session` cookie clobbers previous meals. Users who dine out multiple times a week cannot see their active tables in one browser profile.
- **Proposed Solution**:
  - Implement the proposed `ACCOUNT_IDENTITY_AND_MY_MEALS.md` specification:
    - Add an optional `accounts` and `account_sessions` layer in SQLite.
    - Passwordless authentication (Email Magic Links or WebAuthn / Passkeys).
    - Centralized **"My Meals"** dashboard listing:
      - Active meals awaiting allocation or review.
      - Finalized meals with outstanding balances owed or receivable.
      - Archived meals with Notion reports.
    - Diners without accounts continue to use the existing zero-friction guest invitation flow.
- **Status**: Formally proposed and architected; awaiting Product Owner scheduling.

---

## 7. Prioritization & Implementation Slices

| Phase | Feature | Effort | Impact | Dependencies |
|---|---|---|---|---|
| **Slice 1 (Immediate)** | **DuitNow QR & Payment Handle on Peer Settlement** | Low (~1–2 days) | Very High | None (Extends existing `peer_transfers` UI) |
| **Slice 1 (Immediate)** | **Cloudflare Tunnel Health Alerting** | Low (< 1 hour) | High | None (Cloudflare dashboard config) |
| **Slice 2 (Next)** | **Lightweight PWA & Offline App Shell** | Medium (~2–3 days) | High | Manifest & Service Worker |
| **Slice 2 (Next)** | **Off-Host Encrypted Backup Automation** | Medium (~2 days) | High | Host rclone / cloud storage setup |
| **Slice 3 (Later)** | **Multi-Page Receipt OCR Stitching** | Medium (~3–4 days) | Medium | Multi-photo staging in `Authority` |
| **Slice 3 (Later)** | **Multi-Currency UI Formatting** | Low-Med (~2 days) | Medium | Client `Intl.NumberFormat` refactor |
| **Slice 4 (Major)** | **Account Identity & "My Meals" Dashboard** | High (~1–2 weeks) | Very High | Full `ACCOUNT_IDENTITY_AND_MY_MEALS.md` execution |

---

## 8. Cross-References

- **Multi-Meal Identity Architecture**: [docs/plans/ACCOUNT_IDENTITY_AND_MY_MEALS.md](ACCOUNT_IDENTITY_AND_MY_MEALS.md)
- **Deployment & Backup Strategy**: [docs/plans/MVP_RELEASE_AND_DEPLOYMENT.md](MVP_RELEASE_AND_DEPLOYMENT.md)
- **Experimental Checkout Demo**: [docs/checkout-demo.md](../checkout-demo.md)
- **Project Governance & Decisions**: [docs/agents/phase-transitions.md](../agents/phase-transitions.md)
- **Current Project Status**: [PROJECT_STATUS.md](../../PROJECT_STATUS.md)
