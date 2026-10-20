# Specification: SettleTable Mobile-Friendly Same-Origin Browser MVP

**Status:** Draft Specification for Phase 3/4 Frontend MVP  
**Branch:** `feature/browser-mvp`  
**Dependencies:** `settletable.authority`, `settletable.transport` (WSGI)  
**Security & Design Standards:** Zero CDNs, zero external analytics, same-origin assets, CSRF protection (`X-SettleTable-Action: 1`), HttpOnly host-only session cookies.

---

## 1. Overview & Objectives

The Browser MVP provides a responsive, mobile-first, zero-dependency user interface for SettleTable, allowing real users on mobile devices or desktop browsers to execute the complete dining workflow:
1. **Organizer Provisioning**: Create a meal with named participants.
2. **Receipt Entry & Review**: Input items and line amounts, calculate subtotal and taxes, and explicitly confirm human receipt review (`ReviewReceipt`).
3. **Invitation Hub**: Generate and copy single-use diner invitation links (`/invite/{token}`).
4. **Diner Invitation Landing & Redemption**: Unauthenticated landing view inspecting invitation validity without token consumption, followed by one-click redemption establishing a host-only `settletable_session` cookie.
5. **Item Claiming & Conflict Handling**: Real-time diner claiming interface with visual capacity bars, fraction/quantity adjustments (`SetOwnQuantity`), and visible stale-claim conflict indicators.
6. **Finalization & Bill Breakdown**: Once all items are claimed, the organizer finalizes the meal (`Finalize`), locking claims and displaying the deterministic cent-conserving financial breakdown for each diner.

---

## 2. Static Asset Architecture & WSGI Routing

`SettleTableApp` in `settletable/transport.py` is extended with a secure static file server:

### 2.1 Route Map
- `GET /` -> Serves `settletable/static/index.html` (SPA shell) with `Cache-Control: no-store, no-cache, must-revalidate`
- `GET /invite/([A-Za-z0-9_-]{43})` -> Serves `settletable/static/index.html` (token passed via URL path to client router)
- `GET /static/{filename}` -> Serves static assets strictly matching an in-memory allowlist:
  ```python
  STATIC_FILES = {
      'style.css': ('text/css; charset=utf-8', 'style.css'),
      'app.js': ('application/javascript; charset=utf-8', 'app.js'),
      'favicon.svg': ('image/svg+xml', 'favicon.svg'),
  }
  ```
  Any request to `/static/{filename}` not in `STATIC_FILES` immediately returns `404 Not Found`.

### 2.2 Security & Path Traversal Mitigations
- In-memory allowlist: Discard dynamic filesystem path resolution to eliminate Windows drive-letter casing mismatches or NTFS Alternate Data Stream (`::$DATA`) risks.
- Security Headers attached to all static and HTML responses:
  - `Content-Type`: standard MIME types (`text/html; charset=utf-8`, `text/css; charset=utf-8`, `application/javascript; charset=utf-8`, `image/svg+xml`)
  - `Content-Security-Policy`: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: no-referrer`
  - `Cache-Control: no-cache` (or `no-store` on HTML routes)

### 2.3 Session Context in Snapshot Envelope ("Who Am I")
To allow client-side role derivation without compromising `HttpOnly` cookie security:
- `GET /api/meals/{meal_id}/snapshot` includes in its JSON response:
  ```json
  {
      "ok": true,
      "meal_id": "...",
      "current_participant_id": "O",
      "is_organizer": true,
      ...
  }
  ```
- This allows client-side JavaScript to unambiguously know which participant in the snapshot corresponds to the current session upon page refresh, enabling exact role derivation and claim highlighting.

---

## 3. Client User Flows & States

### 3.1 Organizer Receipt Entry & Review
- **Input Fields**: Item label, quantity (default 1), line amount in sen/cents (formatted as RM 0.00).
- **Fractional/Integer Wire Rule**: Quantities must strictly serialize as integers (e.g. `1`) or `[numerator, denominator]` pairs (e.g. `[1, 2]`); never JavaScript floats.
- **Adjustments**: Optional Service Charge (sen) and Tax / SST (sen).
- **Human Review Step**:
  - Displays calculated subtotal, taxes, and total.
  - Binds to the server-computed authoritative `snapshot.receipt_digest` (client does not compute SHA-256 binary digests).
  - Requires explicit organizer click: *"I confirm receipt totals match the paper bill"*.
  - Calls `POST /api/meals/{meal_id}/apply` with `ReviewReceipt(expected_financial_revision=..., receipt_digest=snapshot.receipt_digest)`.

### 3.2 Invitation Hub
- Displays a card for each participant with active invitation status:
  - Uninvited -> Button: *"Create Invite Link"* (calls `POST /api/meals/{meal_id}/invitations`).
  - Active -> Displays link `https://<origin>/invite/<token>` with a *"Copy Link"* button.
  - Joined -> Displays green badge: *"Joined via session"*.

### 3.3 Diner Landing, Joining & URL Sanitization
- Route: `/invite/{token}` (HTML shell loads, JS parses token from `window.location.pathname`).
- Calls `GET /api/invitations/{token}` (non-mutating inspection).
- If valid: shows meal ID, participant name, and expiration time. Button: *"Join Meal as [Name]"*.
- Clicking button calls `POST /api/meals/{meal_id}/invitations/{token}/redeem` with `X-SettleTable-Action: 1`.
- Browser receives `Set-Cookie: settletable_session=<cred>; HttpOnly; Secure; SameSite=Strict; Path=/`.
- **Immediate URL Sanitization**: Client calls `window.history.replaceState(null, '', '/#/meal/' + mealId)` upon redemption to purge the single-use token from the URL bar and avoid refresh lockouts.

### 3.4 Item Claiming & Stale Claim Conflicts
- Lists all receipt items with:
  - Total quantity vs. Claimed quantity.
  - Current diner's portion with `+`, `-`, and `Claim 100%` buttons.
  - Other diners' claiming chips.
- Auto-polling: Polling `GET /snapshot` every 3 seconds, paused when `document.visibilityState === 'hidden'`. In-flight mutations discard stale poll responses.
- **Stale Claim / Concurrency Handling**:
  - When submitting `SetOwnQuantity`, client sends `expected_item_revision` and `expected_financial_revision`.
  - If another diner modified the item or receipt concurrently, API returns **409 Conflict** (`item_revision_conflict` or `financial_revision_conflict`).
  - Client surfaces an immediate Amber/Red conflict banner: *"Item was updated by another diner. Latest amounts updated."* and automatically refreshes snapshot.

### 3.5 Finalization & Allocation Results
- When all items have `claimed_quantity == total_quantity` and review is confirmed, organizer can tap *"Finalize Meal"*.
- Calls `POST /api/meals/{meal_id}/apply` with `Finalize`.
- Client renders the final apportionment:
  - Grand total, subtotal, taxes/service charges.
  - Per-diner breakdown table: itemized costs, allocated taxes/discounts, total amount owed in RM.

---

## 4. UI/UX & Mobile Constraints

- **Zero CDNs**: Zero remote scripts, stylesheets, or web fonts. Completely self-contained.
- **Touch-Friendly**: Minimum touch target size $44 \times 44\text{px}$ for all buttons and inputs.
- **Color System**:
  - Surface: Dark slate theme (`#0f172a`, `#1e293b`) with clean typography.
  - Accents: Emerald (`#10b981`) for success/claimed, Amber (`#f59e0b`) for review/partial, Rose (`#f43f5e`) for conflict/error, Indigo (`#6366f1`) for primary actions.
- **Defensive DOM Manipulation**: All user-supplied strings (names, item labels) rendered via `textContent` or text nodes; zero unsafe `innerHTML`.
