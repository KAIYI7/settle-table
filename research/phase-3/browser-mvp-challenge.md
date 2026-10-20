# Independent Frontend Architecture & Security Challenge Report: SettleTable Browser MVP

**Target Specification**: `C:\LKY_Project\TabWise\.scratch\browser-mvp\SPEC.md`  
**Target Codebase**: `C:\LKY_Project\TabWise` (`settletable.transport`, `settletable.authority`)  
**Target Output Document**: `C:\LKY_Project\TabWise\research\phase-3\browser-mvp-challenge.md`  
**Challenger Role**: Independent Frontend Architecture and Security Challenger  
**Determination**: **CONDITIONAL PASS (APPROVED PENDING MANDATORY SPEC REMEDIATIONS)**

---

### Executive Summary

The proposed Same-Origin Browser MVP specification (`SPEC.md`) provides a lean, elegant, zero-dependency architecture for SettleTable's client experience. It correctly leverages host-only `HttpOnly; SameSite=Strict; Secure` session cookies, enforces mandatory custom action headers (`X-SettleTable-Action: 1`), and isolates unauthenticated invitation token inspection from state mutation.

However, a rigorous architectural and adversarial audit has identified **4 blocking design defects** and **3 high-priority UX/security risks** that must be addressed in the specification prior to implementation in Phase 4:

1. **The "Who Am I" Session Context Gap (Critical)**: `GET /api/meals/{meal_id}/snapshot` does not return the authenticated caller's participant ID. Because session cookies are `HttpOnly` and cannot be read by JavaScript, the client state machine cannot determine which participant in the snapshot is the logged-in user upon page reload or direct URL entry. Consequently, role derivation (organizer vs diner) and portion claim rendering (own claims vs others) break on browser refresh.
2. **Status Code Contract Mismatch (High)**: `SPEC.md` Section 3.4 specifies that concurrency conflicts return `400 item_revision_conflict` or `400 financial_revision_conflict`. In reality, `settletable/transport.py` lines 58–59 explicitly maps these errors to **HTTP 409 Conflict**. The frontend error handler and documentation must be aligned to HTTP 409.
3. **URL Path vs Hash Routing Desync on Invitation Landing (High)**: Section 2.1 serves `index.html` at `GET /invite/{token}`, but Section 3.3 routes to `#/invite/:token`. If the diner lands on `/invite/{token}` and redeems, navigating to `#/meal/:mealId` leaves the URL as `/invite/{token}#/meal/:mealId`. On page refresh (F5), the browser re-requests the invite token, which is now reported as `consumed`, trapping the user on an error screen despite possessing an active session cookie.
4. **Static Asset Traversal & Windows Filesystem Edge Cases (Medium-High)**: Relying on dynamic path resolution on Windows is vulnerable to drive letter case mismatches (`C:\` vs `c:\`), NTFS Alternate Data Streams (`app.js::$DATA`), and path normalization quirks. A strict static asset allowlist dictionary must be used instead.
5. **Missing Content Security Policy (Medium)**: To technically enforce the "Zero CDNs / zero external calls" requirement, a strict CSP header must be added.
6. **Receipt Digest Generation Ambiguity (Medium)**: Section 3.1 states the client "Generates receipt digest". The client cannot and should not attempt to replicate Python's binary SHA-256 wire serialization; it must bind to the authoritative `receipt_digest` already computed and returned by the server snapshot.
7. **Fractional Wire Representation Hazard (Medium)**: `transport.py`'s `_reject_float` rejects standard JSON floating point numbers with `400 invalid_number`. Frontend inputs for quantities must strictly serialize as integers or `[numerator, denominator]` pairs.

---

### Detailed Findings & Technical Challenges

#### 1. Static Asset Serving & WSGI Routing (`settletable.transport`)

- **Path Traversal Vulnerability Analysis**:
  - Relying on dynamic path math on Windows can hit drive letter casing quirks or NTFS Alternate Data Streams.
  - SettleTable has a strictly fixed set of static files (`index.html`, `style.css`, `app.js`, `favicon.svg`). Use an explicit in-memory allowlist:
    ```python
    STATIC_FILES = {
        'style.css': ('text/css; charset=utf-8', 'style.css'),
        'app.js': ('application/javascript; charset=utf-8', 'app.js'),
        'favicon.svg': ('image/svg+xml', 'favicon.svg'),
    }
    ```
    Any request to `/static/{filename}` not in `STATIC_FILES` immediately returns 404.

- **MIME Types & Security Headers**:
  - Mappings required: `.html` -> `text/html; charset=utf-8`, `.css` -> `text/css; charset=utf-8`, `.js` -> `application/javascript; charset=utf-8`, `.svg` -> `image/svg+xml`.
  - Content Security Policy header attached to static and HTML responses:
    `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`

- **Routing Dispatch for `/` and `/invite/{token}`**:
  - `GET /`: Serves `settletable/static/index.html`.
  - `GET /invite/([A-Za-z0-9_-]{43})`: Serves `settletable/static/index.html`.
  - Malformed tokens return `404 Not Found`.

---

#### 2. Client-Side State Machine & Routing Architecture

- **Token Transition & Sanitization**:
  - When the diner lands on `https://<origin>/invite/{token}`, the token is read from `window.location.pathname`.
  - Client inspects via `GET /api/invitations/{token}`.
  - Upon redemption (`POST /api/meals/{meal_id}/invitations/{token}/redeem`), client executes:
    `window.history.replaceState(null, '', '/#/meal/' + mealId);`
  - This purges the consumed token from the URL bar and prevents page refresh desync.

- **The "Who Am I" & Role Derivation Gap**:
  - `GET /api/meals/{meal_id}/snapshot` must include `current_participant_id` and `is_organizer` in the response envelope so the client knows which participant is logged in and what role to render.

- **Session Detection & Cookie Collisions**:
  - If a user opens a meal and receives 401 Unauthorized, client displays a clear "Session Expired" / "Request New Invite" banner.

---

#### 3. Concurrency Conflict UX & Data Integrity

- **Stale Claim Handling (`item_revision_conflict`)**:
  - Aligned to HTTP 409 Conflict.
  - When 409 is returned, client fetches latest snapshot, highlights the contested item in amber, and prompts: *"Item was updated by another diner. Latest amounts updated."*

- **Polling Architecture**:
  - Auto-poll `GET /snapshot` every 3 seconds.
  - Pause polling when `document.visibilityState === 'hidden'`.
  - Mutex/sequence guard: discard stale poll responses that were in flight during user mutations.

- **Human Receipt Review Enforcement**:
  - Client does NOT compute SHA-256 wire digests. It binds to the authoritative `snapshot.receipt_digest` computed by `Authority`.
  - Confirmation checkbox required before submitting `ReviewReceipt`.

---

#### 4. Zero-Dependency & Mobile Standards

- Zero CDNs, system font stack.
- Viewport tag with `viewport-fit=cover`.
- Touch targets $\ge 44 \times 44\text{px}$.
- Fractional quantities serialized as integer or `[numerator, denominator]` pairs, never floats.

---

### Audit Gate Determination: CONDITIONAL PASS

All 7 remediations are approved and must be integrated into `SPEC.md` and implementation.
