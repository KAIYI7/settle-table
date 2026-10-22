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
python tools/run_demo.py --mock-ocr --mock-notion
```

The runner binds to `127.0.0.1:8000` by default (origin `http://127.0.0.1:8000`).

Or using explicit arguments or environment variables:

```powershell
python tools/run_demo.py --host 127.0.0.1 --port 8000 --mock-ocr --mock-notion
```
or:
```powershell
$env:SETTLETABLE_MOCK_OCR="1"
$env:SETTLETABLE_MOCK_NOTION="1"
python tools/run_demo.py
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

### 3.3 Verification Methodologies: Distinction of OCR Testing Layers

To prevent ambiguity during evaluation, SettleTable explicitly distinguishes three separate OCR testing layers:

1. **Genuine Image-Upload OCR Testing**: The client browser sends a binary image payload (PNG, JPEG, WebP up to 5 MB) via `fetch('/api/meals/{meal_id}/ocr/extract', { method: 'POST', body: file, headers: { 'Content-Type': mimeType, 'X-SettleTable-Action': '1' } })`. The server WSGI transport decodes headers, verifies magic bytes and image dimensions ($\le 4096 \times 4096$, $\le 16\text{MP}$), executes server-side inference, parses Malaysian receipt layout, and returns structured candidate JSON. This tests the complete network, header validation, CSRF, and binary ingress stack. (Automated in `tools/e2e_browser_test.mjs` and `tests/test_ocr.py`).
2. **Mock-Token Extraction (`MockOcrEngine`)**: When running with `--mock-ocr`, the server bypasses heavy native ONNX/C++ model execution and replaces inference by looking up the image SHA-256 against token fixtures (`tests/fixtures/ocr/tokens.json`) or falling back to pre-configured `default_lines`. This tests the entire WSGI transport, layout parser, tax rules, and receipt modeling at $0.00 spend and zero native binary dependencies.
3. **Direct JavaScript Candidate Injection (`window.settletable.state.ocrCandidate`)**: Staging proposal objects directly in browser memory to test UI rendering, real-time input recalculation, error badges, and DOM interactions in isolated testing harnesses without incurring HTTP network roundtrips.

---

## 4. Realistic Test Meal & Expected Totals

### 4.1 Slip Details: Restoran Wan Sheng (Kuala Lumpur)

| Slip Line Item | Quantity | Line Amount (RM) | Notes |
|:---|:---:|:---:|:---|
| 1 CHICKEN RICE | 1 | RM 12.00 | Claimed by Alice (Organizer) |
| 1 ICE LEMON TEA | 1 | RM 3.20 | Claimed by Bob (Diner) |
| **Items Subtotal** | **2** | **RM 15.20** | $12.00 + 3.20$ |
| Service Charge (10%) | 1 | RM 1.52 | Proportional allocation ($15.20 \times 10\%$) |
| BNM Cash Rounding | 1 | -RM 0.02 | Bank Negara Malaysia 5-sen rounding ($16.72 \to 16.70$) |
| **Receipt Total** | | **RM 16.70** | Strict cash slip grand total ($15.20 + 1.52 - 0.02$) |

*(Informational Included SST: per Malaysian tax-inclusive restaurant rules, any included taxes are informational and do not alter subtotal invariants)*

### 4.2 Exact Deterministic Apportionment

Under the conserved integer-sen calculation engine (`settletable.calculation`):

1. **Items Base Ratio**:
   - Alice: $1200\text{ sen} / 1520\text{ sen} \approx 78.947\%$
   - Bob: $320\text{ sen} / 1520\text{ sen} \approx 21.053\%$

2. **Service Charge (152 sen)**:
   - Alice share: $\text{round}(152 \times 1200 / 1520) = \text{round}(120.0) = \mathbf{120\text{ sen}}$ (RM 1.20)
   - Bob share: $152 - 120 = \mathbf{32\text{ sen}}$ (RM 0.32)

3. **BNM Cash Rounding (-2 sen)**:
   - Alice share: $\text{round}(-2 \times 1200 / 1520) = \text{round}(-1.5789) = \mathbf{-2\text{ sen}}$ (-RM 0.02)
   - Bob share: $-2 - (-2) = \mathbf{0\text{ sen}}$ (RM 0.00)

4. **Final Individual Totals**:
   - **Alice (Organizer)**: $1200 + 120 - 2 = \mathbf{1318\text{ sen}}$ (**RM 13.18**)
   - **Bob (Diner)**: $320 + 32 + 0 = \mathbf{352\text{ sen}}$ (**RM 3.52**)
   - **Reconciled Grand Total**: $1318 + 352 = \mathbf{1670\text{ sen}}$ (**RM 16.70**)  
     *(Zero unallocated residue; exact cent conservation)*

---

## 5. End-to-End Walkthroughs

### 5.1 Walkthrough A: Collaborative Dining Scenario (Alice & Bob)

#### Step 1: Organizer Meal Provisioning
1. Open browser at `http://127.0.0.1:8000/`.
2. Fill out **Create New Meal**:
   - **Meal ID**: `dinner-friday`
   - **Your Name (Organizer)**: `Alice`
   - **Diners**: `Bob`
3. Click **Create & Provision Meal**.
4. The browser provisions the meal in SQLite, sets a host-only secure session cookie, and opens `/#/meal/dinner-friday` with the `👑 Organizer` role badge.

#### Step 2: Receipt Scanning & Edit-Before-Accept
1. In the **Receipt & Charges** card, click **📷 Scan Receipt Image**.
2. Select any image file (or dummy JPEG/PNG). The mock OCR engine parses the slip.
3. The **📋 SCANNED CANDIDATE (STAGED)** card appears in amber/green:
   - The candidate is held strictly in **client browser memory** (`state.ocrCandidate`) outside SQLite.
   - **Polished Responsive Editor**: Displays a clear desktop table with distinct **Unit Price** and authoritative **Line Total** columns, and shifts to a spacious stacked touch-friendly layout on mobile viewports ($\ge 44\text{px}$ targets).
   - **Inline Edit Experience**: Item labels, quantities, amounts in RM, and adjustment rows have editable input fields.
   - You can modify misrecognized names, adjust prices, click **✕** to remove spurious items, or click **+ Add Missing Item**.
   - Modifying prices dynamically recalculates **Candidate Subtotal** and **Candidate Total** in real time while maintaining keyboard focus.
4. Click **Accept & Apply to Receipt**. The validated receipt is applied to the SQLite draft.

#### Step 3: Human Verification & Sealing
1. Under **HUMAN RECEIPT REVIEW**, review the draft item lines against the paper bill.
2. Check the box: `[x] I confirm totals match the physical bill`.
3. Click **Approve & Seal Receipt**. The receipt digest is cryptographically sealed in SQLite.

#### Step 4: Diner Invitation & Onboarding (Two Methods)

SettleTable provides two complementary diner invitation flows:

##### Method 1: Personal One-Time Links
1. Under **Diner Invitations**, locate `Bob`.
2. Click **Create Link**. The button changes to **📋 Copy Link**.
3. Click **📋 Copy Link** (copies URL like `http://127.0.0.1:8000/invite/<43-char-token>`).
4. Open an **isolated browser window / Incognito profile** to simulate Bob's phone.
5. Navigate to the invitation URL:
   - Notice the **Same-Browser Profile Notice** warning against overwriting active organizer sessions.
   - The token is verified in SQLite without revealing other diner tokens.
6. Click **Accept & Join Meal**:
   - The single-use token is atomically consumed.
   - Bob's browser receives a diner session cookie and enters `/#/meal/dinner-friday` with the `🍽️ Diner: Bob` badge.

##### Method 2: General Meal Join Link with Organizer Approval
1. Under **General Meal Join Link**, click **📋 Copy General Join Link** (copies `http://127.0.0.1:8000/join/dinner-friday`).
2. Open a separate browser profile and navigate to the link.
3. The landing page displays the meal room identifier and a name entry field, without disclosing the participant list.
4. Enter `Bob` and submit:
   - Bob enters a pending approval waiting state with live polling.
   - Bob's browser does not receive a session cookie yet.
5. In Alice's organizer window, a **🔔 Pending Diner Join Requests** banner appears.
6. Alice verifies Bob's identity and clicks **Approve**:
   - Bob's polling window detects the approval, atomically claims the session via a one-time cryptographic claim token, and navigates into the meal as Bob.

#### Step 5: Portion Claiming & Real-Time Sync
1. In Bob's window, click **+1** under **Ice Lemon Tea**:
   - Bob's claim registers immediately with green chip `Bob: 1`.
2. In Alice's window, click **⟳ Refresh** (or observe the 2-second background poll):
   - Alice sees Bob's claim reflected in real time.
3. In Alice's window, click **+1** under **Chicken Rice**:
   - All items are now 100% claimed (progress bars reach 100%).

#### Step 6: Finalization & Result Inspection
1. In Alice's window, the **Seal & Finalize Meal** card turns green.
2. Click **Finalize & Calculate Bill**.
3. Both Alice's and Bob's windows update with the authoritative **Final Apportionment Summary**:
   - Alice: **RM 13.18**
   - Bob: **RM 3.52**
   - Grand Total: **RM 16.70** (Exact cent conservation)

#### Step 7: Optional Notion Export
1. As Alice, locate the **📤 Notion Archive & Reporting** section at the bottom.
2. Enter any dummy parent UUID (e.g., `11111111-2222-3333-4444-555555555555`).
3. Click **Export Finalized Report to Notion**.
4. The server dispatches the export to an asynchronous background worker and immediately returns HTTP 202 Accepted.
5. The UI polls status and displays:
   `✓ Export Successful! Open Report in Notion ↗`

---

### 5.2 Walkthrough B: Organizer-Managed Dining Scenario (Alice, David, Emma)

This scenario demonstrates **zero-session dining**: the organizer manages the entire receipt allocation on behalf of all diners without requiring any diner to log in, accept links, or create sessions.

#### Slip & Allocation Fixture (Mathematically Verified)
| Item | Quantity | Unit Price | Line Total | Allocation | Participant Share |
|:---|:---:|:---:|:---:|:---|:---:|
| **Nasi Lemak** | 3 | RM 12.00 | RM 36.00 | Alice (1), David (1), Emma (1) | RM 12.00 each |
| **Teh Tarik** | 2 | RM 3.00 | RM 6.00 | Emma (2) | RM 6.00 |
| **Grand Total** | **5** | | **RM 42.00** | **Alice RM 12.00, David RM 12.00, Emma RM 18.00** | **RM 42.00** |

*(Deterministic cent-conserving calculation: Alice 1200 sen + David 1200 sen + Emma 1800 sen = 4200 sen. Zero unallocated residue).*

#### Step 1: Provisioning the Managed Table
1. Open browser at `http://127.0.0.1:8000/`.
2. Fill out **Create New Meal**:
   - **Meal ID**: `lunch-managed`
   - **Your Name (Organizer)**: `Alice`
   - **Diners**: `David, Emma`
3. Click **Create & Provision Meal**.
4. Alice opens the meal room as Organizer. David and Emma are registered participants, but have zero active sessions.

#### Step 2: Receipt Entry & Sealing
1. Add items via manual entry or OCR scan:
   - Line 1: `Nasi Lemak`, Qty: `3`, Line Total: `RM 36.00`
   - Line 2: `Teh Tarik`, Qty: `2`, Line Total: `RM 6.00`
   - Total: `RM 42.00`
2. Under **HUMAN RECEIPT REVIEW**, check confirmation and click **Approve & Seal Receipt**.

#### Step 3: Organizer-Authorized Allocation (`AssignParticipantQuantity`)
1. In the **Items & Portions** card, locate the **Allocate on behalf of participant:** selector.
2. **Assign Alice's portion**:
   - Select `Alice (Organizer)`.
   - On **Nasi Lemak**, click **+1**. The chip displays `Alice: 1` (Allocated: 1/3).
3. **Assign David's portion**:
   - Change selector to `David`.
   - On **Nasi Lemak**, click **+1**. The chip displays `David: 1 (by Alice)` (Allocated: 2/3).
4. **Assign Emma's portions**:
   - Change selector to `Emma`.
   - On **Nasi Lemak**, click **+1**. The chip displays `Emma: 1 (by Alice)` (Allocated: 3/3 - Complete!).
   - On **Teh Tarik**, click **+1** twice. The chip displays `Emma: 2 (by Alice)` (Allocated: 2/2 - Complete!).
5. Notice that:
   - All 5 portions across both items are 100% allocated.
   - Claims clearly distinguish organizer assignments (`assigned_by: Alice`) from diner claims, preventing impersonation while ensuring auditability.
   - David and Emma never had to join or log in.

#### Step 4: Finalization & Result Inspection
1. Click **Finalize & Calculate Bill**.
2. The authoritative calculation engine computes individual totals:
   - **Alice (Organizer)**: **RM 12.00** (1200 sen)
   - **David**: **RM 12.00** (1200 sen)
   - **Emma**: **RM 18.00** (1800 sen)
   - **Grand Total**: **RM 42.00** (4200 sen)
3. Notice that all invariants hold: exact integer cent conservation, zero diner login overhead.

#### Step 5: Notion Export Without Diner Sessions
1. Under **Notion Archive & Reporting**, enter any parent page UUID.
2. Click **Export Finalized Report to Notion**.
3. The report exports cleanly with the exact authoritative figures (Alice RM 12.00, David RM 12.00, Emma RM 18.00).

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

### Scenario F: Accidental Same-Browser Profile Invitation Redemption & Safe Exit
- **Action**: An evaluator testing both roles accidentally opens a diner invitation link in the organizer's browser window and clicks **Accept & Join Meal**.
- **System Behavior**: The browser overwrites the host-only `settletable_session` cookie with the diner's credentials. The UI now displays the user as `🍽️ Diner: <Name>` with diner permissions.
- **Security & Authorization Invariant**: SettleTable strictly upholds the zero-backdoor and secret hygiene invariants. The system **does not** provide an insecure "Switch to Organizer" backdoor, does not store organizer credentials in localStorage, and never exposes credentials in client-side storage.
- **UI Recovery & Exit**:
  1. **Pre-Redemption Warning**: The invitation landing screen prominently displays a `⚠️ Same-Browser Profile Notice` explaining that accepting will replace the active session, with a `Cancel & Return to Home` button.
  2. **Participant Identification**: The header and room navigation bar clearly state the active user identity (e.g. `🍽️ Diner: WKX`).
  3. **Safe Session Exit**: The header and room navigation bar both provide a **Leave Room** button. Clicking it issues a `POST /api/session/clear` call, instructing the browser to delete the cookie via `Max-Age=0` and cleanly routing back to the Home screen (`#/`).
  4. **Resuming Organizer Testing**: Once the cookie is wiped, the evaluator can bootstrap a new meal room or access meals where they hold session grants.

### Scenario G: General Meal Join Request Abuse Mitigations
- **Participant Enumeration Protection**: An unauthenticated attacker attempting to probe participant presence, organizer identity, or diner status by guessing names returns the exact same indistinguishable error response (`Unable to request access for "<Name>"`, HTTP 400 `invalid_join_target`). There is zero differential leakage between unknown names, organizer names, ambiguous names, and inactive participants.
- **Pending Request Invalidation Protection**: If an active request is already awaiting organizer review for a participant, submitting a duplicate request is rejected with HTTP 409 (`active_join_request_exists`). An external attacker cannot cancel or overwrite a legitimate diner's pending request.
- **Table Flooding & Resource Exhaustion Defense**: Each meal table enforces a strict upper bound of at most 20 active pending requests and at most 100 total requests lifetime. Excess requests are rejected with HTTP 429 (`resource_limit`).
- **Revision Conflict DoS Neutralization**: Unauthenticated join requests do not mutate meal state or increment meal revisions. External request flooding cannot induce HTTP 409 `revision_conflict` on live diners making legitimate claim updates.

---

## 7. Remaining Known Limitations

1. **Local Single-Host Storage**: SettleTable currently runs on a single-node SQLite instance with WAL mode. Multi-server clustering or distributed database backends are not implemented.
2. **In-Memory Candidate Staging**: Staged OCR candidate proposals reside in the browser tab's JavaScript memory. Reloading the page before clicking "Accept" clears the candidate and requires re-selecting the image.
3. **Ephemeral Daemon Background Jobs**: Background Notion export utilizes standard Python `threading.Thread(daemon=True)`. While bounded and isolated, it does not use a persistent queuing broker (like Celery/Redis).
4. **Single Currency**: Apportionment is strictly denominated in Malaysian Ringgit (MYR integer sen). Multi-currency conversions are not currently supported.

---

## 8. PR Creation Failure Investigation & Reliable Traceability Fallback

### 8.1 Investigation Findings
During autonomous integration, attempting `gh pr create` resulted in:
```text
gh : The term 'gh' is not recognized as the name of a cmdlet, function, script file, or operable program.
```
- **Root Cause**: GitHub CLI (`gh.exe`) is not installed on this host environment.
- **Repository Visibility**: `KAIYI7/settle-table` is a private repository. Git authentication uses the Windows Git Credential Manager (`credential.helper = manager`), which secures git operations (`git push`, `git fetch`) without exposing a reusable personal access token to shell scripts or unauthenticated `curl` calls.

### 8.2 Reliable Governance Fallback Protocol
To preserve strict independent review, CI verification, and merge traceability when GitHub CLI is unavailable:
1. **Feature Branch Isolation**: All work develops on dedicated branches (e.g. `feature/user-acceptance-readiness`).
2. **Independent Subagent Audit**: Before merging, an independent subagent reviews the diff against base, checks invariants, and executes the full test suite and browser CDP suite.
3. **Remediation & Regression Tests**: Any material findings are resolved on the feature branch with corresponding regression tests.
4. **Local Verification**: The full 159-test suite and real Chrome browser E2E tests are rerun to ensure 100% pass rates.
5. **Traceable Merge (`--no-ff`)**: The feature branch is pushed to `origin`, then merged into `main` using `git merge --no-ff feature/<name> -m "..."`. This preserves the two-parent commit structure, complete commit ancestry, and PR traceability in the Git graph (`git log --graph`).
6. **Hosted CI Execution**: Pushing the feature branch and pushing the `--no-ff` merge commit to `origin/main` triggers the GitHub Actions workflow (`.github/workflows/python-tests.yml`).
7. **Durable Transition Records**: Findings, exact commit SHAs, test outcomes, and gate matrices are recorded in `research/phase-3/`, `PROJECT_STATUS.md`, and `docs/agents/phase-transitions.md`.

---

## 9. Recommended Next Product Milestone (Phase 4 Frontier)

With Phase 3 complete and User-Acceptance Readiness established, the recommended next milestone is:

**Phase 4: Operational Hardening & Production Pilot Frontier**
1. **Containerized Deployment Package**: Dockerfile and Docker Compose configurations defining Tier 1 reverse proxy ingress (Nginx TLS, 4 KB request line bounds, 1 MB upload body bounds) and Tier 2 WSGI worker boundaries.
2. **Automated SQLite Backup & Snapshotting**: Periodic automated streaming backup routines using SQLite's online backup API.
3. **Real-World Held-Out Receipt Accuracy Benchmark**: Gathering a consented held-out benchmark of Malaysian dining slips to evaluate RapidOCR CPU ONNX accuracy across lighting, folds, and thermal fading.
4. **Interactive Diner Settlement Acknowledgments**: Allowing diners to mark their calculated portion as paid (cash/DuitNow QR reference) with organizer verification.
