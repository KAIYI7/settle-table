# SettleTable User Acceptance Testing (UAT) Handover

**Document Version:** 1.0  
**Date:** 2026-10-21  
**Project:** SettleTable ([KAIYI7/settle-table](https://github.com/KAIYI7/settle-table))  
**Governance Authority:** [Project Governance](agents/governance.md)  
**Status:** User-Acceptance Readiness Complete (Pre-Phase 4 Milestone)

---

## 1. Executive Summary

SettleTable is a collaborative dining bill splitter designed for live diner collaboration, server-side local receipt OCR inference, deterministic integer-cent apportionment with cent conservation, and optional decoupled downstream Notion reporting.

Phase 3 development established the manual-first MVP, single-transaction SQLite authority, same-origin WSGI transport, zero-external-dependency browser client, Malaysian SST/service-charge OCR parser, and compact Notion exporter (&le; 40 blocks).

This User Acceptance Testing (UAT) document provides the exact operational commands, test configuration, realistic test meal scenarios, and verification steps for stakeholder evaluation.

---

## 2. Local Startup Commands & Runner Behavior

### 2.1 Starting the Evaluation Server

Run the local demo runner from the repository root:

```powershell
python tools/run_demo.py --host 127.0.0.1 --port 8000 --mock-ocr --mock-notion
```

Or using environment variables:

```powershell
$env:SETTLETABLE_MOCK_OCR="1"
$env:SETTLETABLE_MOCK_NOTION="1"
python tools/run_demo.py --host 127.0.0.1 --port 8000
```

### 2.2 Actual Runner Output & Security Behavior

When executed, the runner initializes the WSGI application and displays:

```text
============================================================
 SettleTable - Local Browser MVP Demo Server
============================================================
 URL:         http://127.0.0.1:8000
 Database:    C:\LKY_Project\TabWise\.local\demo.sqlite
 Architecture: Zero-dependency WSGI + SQLite WAL + Vanilla ES2022
============================================================
 Press Ctrl+C to stop.
```

> [!IMPORTANT]
> **Credential Privacy & Zero Bearer Secret Logging**:  
> The runner console output **does not** print organizer credentials, participant session tokens, or invitation links to `stdout`.  
> SettleTable enforces strict secret hygiene: credentials and bearer tokens are never logged or persisted. The browser automatically receives host-only session cookies (`settletable_session`) with `HttpOnly; SameSite=Strict; Path=/` upon room creation, and diner invitation links are generated and copied directly inside the organizer's web UI.

---

## 3. Mock OCR & Mock Notion Configuration

### 3.1 Mock OCR Configuration (`--mock-ocr`)

- **Purpose**: Enables immediate, air-gapped evaluation of receipt scanning and the Malaysian dining receipt parser without installing heavy machine learning libraries (RapidOCR / ONNX Runtime).
- **Inference Architecture**: **Server-Side Local Inference**, NOT on-device phone inference. Uploaded receipt images are processed locally by the SettleTable server instance. No third-party cloud vision APIs or remote image transfers are used.
- **Fixture Data**: Automatically loads the statutory Malaysian dining receipt fixture (`Restoran Wan Sheng`), containing Chicken Rice, Ice Lemon Tea, 10% service charge, and Bank Negara Malaysia (BNM) 5-sen rounding.

### 3.2 Mock Notion Configuration (`--mock-notion`)

- **Purpose**: Simulates Notion page creation and block verification in-memory with $0.00 spend and zero external network access.
- **Contract Enforcement**: Validates that all exported pages strictly comply with the Notion REST API:
  - Parent page parent (`page_id`) receives only the `title` property.
  - Compact mode bounds total blocks to $\le 40$ blocks, protecting Free tier workspace lifetime block limits (1,000 blocks).
  - Pre-creation title reconciliation prevents duplicate pages on lost network responses.
- **Delivery Semantics**: Documented as **at-least-once with pre-creation title reconciliation**. SettleTable does not falsely claim exactly-once delivery across non-transactional external REST APIs.

---

## 4. Realistic Test Meal & Expected Totals

### 4.1 Slip Details: Restoran Wan Sheng (Kuala Lumpur)

| Slip Line Item | Quantity | Line Amount (RM) | Notes |
|:---|:---:|:---:|:---|
| 1 CHICKEN RICE | 1 | RM 12.00 | Claimed by Alice (Organizer) |
| 1 ICE LEMON TEA | 1 | RM 3.50 | Claimed by Bob (Diner) |
| **Items Subtotal** | **2** | **RM 15.50** | $12.00 + 3.50$ |
| Service Charge (10%) | 1 | RM 1.55 | Proportional allocation |
| BNM Cash Rounding | 1 | -RM 0.05 | Rounding to nearest 5 sen ($17.05 \to 17.00$) |
| **Receipt Total** | | **RM 17.00** | Strict cash slip grand total |

*(Informational Included SST: RM 0.93 / 93 sen already included in food items per Malaysian tax-inclusive restaurant rules)*

### 4.2 Exact Deterministic Apportionment

Under the conserved integer-sen calculation engine (`settletable.calculation`):

1. **Items Base Ratio**:
   - Alice: $1200\text{ sen} / 1550\text{ sen} \approx 77.419\%$
   - Bob: $350\text{ sen} / 1550\text{ sen} \approx 22.581\%$

2. **Service Charge (155 sen)**:
   - Alice share: $\text{round}(155 \times 1200 / 1550) = 120\text{ sen}$ (RM 1.20)
   - Bob share: $155 - 120 = 35\text{ sen}$ (RM 0.35)

3. **Cash Rounding (-5 sen)**:
   - Alice share: $\text{round}(-5 \times 1200 / 1550) = -4\text{ sen}$ (-RM 0.04)
   - Bob share: $-5 - (-4) = -1\text{ sen}$ (-RM 0.01)

4. **Final Individual Totals**:
   - **Alice (Organizer)**: $1200 + 120 - 4 = \mathbf{1316\text{ sen}}$ (**RM 13.16**)
   - **Bob (Diner)**: $350 + 35 - 1 = \mathbf{384\text{ sen}}$ (**RM 3.84**)
   - **Reconciled Grand Total**: $1316 + 384 = \mathbf{1700\text{ sen}}$ (**RM 17.00**)  
     *(Zero unallocated residue; exact cent conservation)*

---

## 5. End-to-End Walkthrough

### Step 1: Organizer Meal Provisioning
1. Open browser at `http://127.0.0.1:8000/`.
2. Fill out **Create New Meal**:
   - **Meal ID**: `dinner-friday`
   - **Your Name (Organizer)**: `Alice`
   - **Diners**: `Bob`
3. Click **Create & Provision Meal**.
4. The browser provisions the meal in SQLite, sets a host-only secure session cookie, and opens `/#/meal/dinner-friday` with the `👑 Organizer` role badge.

### Step 2: Receipt Scanning & Edit-Before-Accept
1. In the **Receipt & Charges** card, click **📷 Scan Receipt Image**.
2. Select any image file (or dummy JPEG/PNG). The mock OCR engine parses the slip.
3. The **📋 SCANNED CANDIDATE (STAGED)** card appears in amber/green:
   - The candidate is held strictly in **client browser memory** (`state.ocrCandidate`) outside SQLite.
   - **Inline Edit Experience**: Notice that item labels, quantities, amounts in RM, and adjustment rows have editable input fields.
   - You can modify misrecognized names, adjust prices, click **✕** to remove spurious items, or click **+ Add Missing Item**.
   - Notice that changing any price or adding a fee dynamically updates **Candidate Subtotal** and **Candidate Total** in real time without losing cursor focus.
4. Click **Accept & Apply to Receipt**. The validated receipt is applied to the SQLite draft.

### Step 3: Human Verification & Sealing
1. Under **HUMAN RECEIPT REVIEW**, review the draft item lines against the paper bill.
2. Check the box: `[x] I confirm totals match the physical bill`.
3. Click **Approve & Seal Receipt**. The receipt digest is cryptographically sealed in SQLite.

### Step 4: Diner Invitation & Onboarding
1. Under **Diner Invitations**, locate `Bob`.
2. Click **Create Link**. The button changes to **📋 Copy Link**.
3. Click **📋 Copy Link** (copies URL like `http://127.0.0.1:8000/invite/<43-char-token>`).
4. Open a **separate browser window** (e.g. Incognito or Chrome/Firefox) to simulate Bob's mobile phone.
5. Paste and navigate to the invitation URL:
   - The unauthenticated landing page confirms: `Joining as: Bob`.
   - Token inspection is read-only and non-mutating.
6. Click **Accept & Join Meal**:
   - The single-use token is atomically consumed.
   - Bob's browser receives a diner session cookie and redirects to `/#/meal/dinner-friday` with the `🍽️ Diner` badge.

### Step 5: Portion Claiming & Real-Time Sync
1. In Bob's window, click **+1** under **Ice Lemon Tea**:
   - Bob's claim registers immediately with green chip `Bob: 1`.
2. In Alice's window, click **⟳ Refresh** (or wait for the 2-second background poll):
   - Alice sees Bob's claim reflected in real time.
3. In Alice's window, click **+1** under **Chicken Rice**:
   - All items are now 100% claimed (progress bars reach 100%).

### Step 6: Finalization & Result Inspection
1. In Alice's window, the **Seal & Finalize Meal** card turns green.
2. Click **Finalize & Calculate Bill**.
3. Both Alice's and Bob's windows update with the authoritative **Final Apportionment Summary**:
   - Alice: **RM 13.16**
   - Bob: **RM 3.84**
   - Grand Total: **RM 17.00**

### Step 7: Optional Notion Export
1. As Alice, locate the **📤 Notion Archive & Reporting** section at the bottom.
2. Enter any dummy parent UUID (e.g., `11111111-2222-3333-4444-555555555555`).
3. Click **Export Finalized Report to Notion**.
4. The server dispatches the export to an asynchronous background worker and immediately returns HTTP 202 Accepted.
5. The UI polls status and displays:
   `✓ Export Successful! Open Report in Notion ↗`

---

## 6. Important Failure & Recovery Scenarios

### Scenario A: Concurrency Conflict (HTTP 409)
- **Action**: Two diners attempt to claim the last remaining portion of an item simultaneously.
- **System Behavior**: SQLite's atomic transaction serializes the commands. The second claim encounters an item revision mismatch and returns HTTP 409 Conflict.
- **UI Recovery**: The contested item card glows amber, displays an alert (*"⚠️ Stale Claim Conflict: Another diner updated quantities. Refreshing..."*), and re-syncs to the authoritative snapshot.

### Scenario B: OCR Misrecognition & Discard
- **Action**: An uploaded slip is blurry, producing garbled candidate text or wrong totals.
- **System Behavior**: Because candidate staging occurs in client memory before SQLite write, the draft receipt remains 100% intact.
- **UI Recovery**: The organizer can click **Discard** to purge the candidate, or use the inline edit fields to correct the values before accepting.

### Scenario C: Server Restart & Notion Export Recovery
- **Action**: The server is restarted while a Notion export is in-progress.
- **System Behavior**: Background export threads are ephemeral daemon threads. If a process terminates mid-export, the SQLite tracking record in `notion_exports` expires after 60 seconds.
- **UI Recovery**: Status checks report `failed` or allow re-triggering. Pre-creation title reconciliation ensures that if Notion already created the page before restart, the retry adopts the existing page ID rather than creating a duplicate page.

### Scenario D: Synchronous Export Testing Override Protection
- **Security Boundary**: The testing override `?sync=1` is disabled by default in production. Passing `?sync=1` over public requests is ignored and executes asynchronously (202 Accepted), preventing malicious callers from starving WSGI worker threads. Synchronous execution requires explicit configuration (`allow_sync_export=True` or `SETTLETABLE_ALLOW_SYNC_EXPORT=1`).

### Scenario E: Consumed / Expired Invitation Protection
- **Action**: A diner attempts to open an invitation link that was already redeemed or revoked.
- **System Behavior**: The unauthenticated landing page checks the verifier in SQLite.
- **UI Recovery**: Displays a friendly error (*"This invitation was already used"* or *"This invitation was revoked by the organizer"*) with a button to return Home, without leaking session state.

---

## 7. Remaining Known Limitations

1. **Local Single-Host Storage**: SettleTable currently runs on a single-node SQLite instance with WAL mode. Multi-server clustering or distributed database backends are not implemented.
2. **In-Memory Candidate Staging**: Staged OCR candidate proposals reside in the browser tab's JavaScript memory. Reloading the page before clicking "Accept" clears the candidate and requires re-selecting the image.
3. **Ephemeral Daemon Background Jobs**: Background Notion export utilizes standard Python `threading.Thread(daemon=True)`. While bounded and isolated, it does not use a persistent queuing broker (like Celery/Redis).
4. **Single Currency**: Apportionment is strictly denominated in Malaysian Ringgit (MYR integer sen). Multi-currency conversions are not currently supported.

---

## 8. Recommended Next Product Milestone (Phase 4 Frontier)

With Phase 3 complete and User-Acceptance Readiness established, the recommended next milestone is:

**Phase 4: Operational Hardening & Production Pilot Frontier**
1. **Containerized Deployment Package**: Dockerfile and Docker Compose configurations defining Tier 1 reverse proxy ingress (Nginx TLS, 4 KB request line bounds, 1 MB upload body bounds) and Tier 2 WSGI worker boundaries.
2. **Automated SQLite Backup & Snapshotting**: Periodic automated streaming backup routines using SQLite's online backup API.
3. **Real-World Held-Out Receipt Accuracy Benchmark**: Gathering a consented held-out benchmark of Malaysian dining slips to evaluate RapidOCR CPU ONNX accuracy across lighting, folds, and thermal fading.
4. **Interactive Diner Settlement Acknowledgments**: Allowing diners to mark their calculated portion as paid (cash/DuitNow QR reference) with organizer verification.
