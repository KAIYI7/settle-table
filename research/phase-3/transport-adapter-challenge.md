# Independent Architecture and Security Challenge: Bounded Same-Origin Transport Adapter

**Target Document**: `C:\LKY_Project\TabWise\.scratch\transport-adapter\SPEC.md`  
**Target Component**: `settletable.transport`  
**Review Date**: 2026-10-20  
**Reviewer**: Independent Architecture & Security Challenger  
**Determination**: **CONDITIONAL PASS (REVISE SPEC BEFORE IMPLEMENTATION)**

---

## 1. Executive Summary & Determination

The draft specification (`.scratch/transport-adapter/SPEC.md`) provides a well-conceived defense-in-depth model for exposing `settletable.authority.Authority` over HTTP. Its principles—strict wire boundary limits, rejection of duplicate keys and floats, separation of unauthenticated landing GET from mutating redemption POST, custom header CSRF defense, and opaque session cookies—align directly with the security requirements defined in `research/phase-3/transport-identity-challenge.md`.

However, an adversarial and architectural audit reveals **five blocking flaws** and several operational hazards that will cause runtime crashes, interface mismatches, or security regressions if implemented as currently drafted:

1. **Broken Redemption Route (`POST /api/invitations/{token}/redeem`)**: The route and empty body `{}` omit `meal_id`. However, `Authority.redeem_invitation(token, meal_id)` strictly requires `meal_id` as a positional argument. As drafted, the transport layer cannot invoke the authority method.
2. **Missing Read-Only Authority Inspection Seam**: `GET /api/invitations/{token}` specifies non-mutating validation and metadata lookup, but `Authority` possesses no public inspection method. Reaching directly into `_db` from transport violates the single-transaction encapsulation invariant established in Phase 3.
3. **SQLite Thread-Safety & Concurrency Hazard**: `Authority` instances are explicitly bound to their owning thread (`Authority.__doc__`: *"One SQLite connection; each instance may be used by its owning thread"*). Running a multi-threaded HTTP server (`ThreadingHTTPServer` or multi-threaded WSGI) sharing an `Authority` instance will cause `sqlite3.ProgrammingError` or transactional corruption.
4. **Incomplete Error Mapping (18 Unmapped Domain Errors)**: The spec maps only 9 error codes. `Authority` raises over 25 distinct `AuthorityError` codes (e.g. `item_revision_conflict`, `financial_revision_conflict`, `already_revoked`, `finalized`, `invalid_input`). Unmapped codes would collapse into unhandled 500 errors.
5. **Programmatic Bearer vs. Origin Enforcement Conflict**: The spec mandates strict `Origin` matching for all POST requests. Standard programmatic HTTP clients (`curl`, scripts) do not transmit an `Origin` header, causing all programmatic mutating requests to fail with `403 Forbidden` unless special rules or headers are documented.

**Gate Determination: CONDITIONAL PASS**. Implementation should proceed once the specification is updated with the remediations detailed below.

---

## 2. Wire Boundary & Parser Limits Challenge

| Wire Limit Parameter | Spec Limit | Challenger Evaluation & Edge Case Findings |
|---|---|---|
| **Header Block Size** | 16,384 bytes (16 KB) | **HAZARD**: Python `http.server.BaseHTTPRequestHandler` defaults to `_MAXHEADERS = 100` and line buffer `_MAXLINE = 65536`. Subclassing without overriding `parse_request` will permit 64 KB lines. Must explicitly enforce 16 KB total block read limit. |
| **Individual Header Line** | 4,096 bytes (4 KB) | **CRITICAL**: Standard `rfile.readline()` will read up to 65,536 bytes before failing. The adapter must pass `readline(4097)` or buffer in a bounded stream to avoid memory exhaustion attacks. |
| **Request Body Size** | 1,048,576 bytes (1 MB) | **CHALLENGE**: The spec states *"Enforce ... before memory allocation or JSON parsing"*. If `Content-Length` is missing on POST, the server must reject with `411 Length Required`. If `Content-Length > 1,048,576`, reject immediately with `413 Payload Too Large` without reading the stream. If `Transfer-Encoding: chunked` is received, either reject with `501 Not Implemented` or stream-count bytes with an immediate abort at byte 1,048,577. |
| **HTTP Desync / Smuggling** | Not specified | **VULNERABILITY**: Requests containing both `Content-Length` and `Transfer-Encoding` must be rejected immediately with `400 Bad Request` per RFC 7230 §3.3.3. |
| **Duplicate JSON Keys** | Disallowed (`duplicate_key`) | **SOUND**: Requires `json.loads(..., object_pairs_hook=_reject_duplicates)`. **Edge Case**: Keys must be validated under Unicode NFC normalization before uniqueness checks to prevent visual/canonical spoofing. |
| **Number Handling** | Disallowed float/NaN/Inf (`invalid_number`) | **SOUND BUT SUBTLE**: Python `json.loads` accepts `NaN`, `Infinity`, and floats by default. Must pass `parse_constant=None` and `parse_float=_reject_float`. **Integer Limit**: Large integers (e.g. $10^{5000}$) can cause quadratic CPU exhaustion; integer string length must be bounded to 19 digits (matching signed 64-bit bounds `_revision` and `_money`). |
| **JSON Nesting Depth** | 10 levels (`malformed_json`) | **IMPLEMENTATION GAP**: CPython `json.loads` does not expose a recursion/depth limit parameter. Enforcing 10 levels requires either a lightweight bracket-depth scanner over the byte buffer before parsing or a custom decoder. |

---

## 3. Authentication, Cookie Management & CSRF Defense Challenge

### 3.1 Cookie Path Scoping Pitfall (`Path=/api/meals/{meal_id}`)
- **The Issue**: RFC 6265 path matching is prefix-based, but does **not** provide origin security isolation. Code on any path of the same origin can read or overwrite cookies on any sub-path.
- **Usability Conflict**: If a user participates in Meal A (`/api/meals/m1`) and Meal B (`/api/meals/m2`), the browser maintains distinct cookies with the same name `settletable_session`. If an API route or page is served outside `/api/meals/{meal_id}` (e.g. `/` or `/api/invitations/...`), the session cookie is omitted by the browser.
- **Recommendation**: Scope cookie names with the meal ID (`settletable_session_{meal_id}=<cred>; Path=/; HttpOnly; Secure; SameSite=Strict`) OR use `Path=/api/meals/{meal_id}/` (with trailing slash) and ensure API callers handle routing consistently.

### 3.2 `SameSite=Strict` and Top-Level Deep Links
- **The Issue**: Invitations and meal links are received via external applications (messaging, email, calendar). When clicked, the browser executes a top-level cross-site GET. Under `SameSite=Strict`, the browser strictly strips all cookies.
- **Evaluation**: For the unauthenticated invitation flow, this is harmless because the diner does not yet hold a session. However, an **already-authenticated diner** clicking a shared meal link will have their cookie omitted on the initial GET request, appearing unauthenticated.
- **Resolution**: Clarify in the architecture that the frontend single-page application (SPA) loads unauthenticated assets first, and subsequent in-app `fetch()` calls (which are same-origin) will attach the `SameSite=Strict` cookie.

### 3.3 CSRF Origin and Header Defense
- **Custom Header `X-SettleTable-Action: 1`**: Excellent defense. Standard HTML forms cannot set custom headers, and cross-origin `fetch` with custom headers triggers a mandatory preflight `OPTIONS` request.
- **Origin Validation Algorithm**:
  1. If `Origin` is present: normalize (strip trailing slash, parse scheme, host, port) and strictly compare against configured server origin.
  2. If `Origin: null` (sandboxed iframes, local files): **MUST REJECT** with `403 Forbidden` (`origin_mismatch`).
  3. If `Origin` is missing on POST:
     - Check `Referer`. If `Referer` origin matches configured origin, allow; otherwise reject.
     - Note: Because responses set `Referrer-Policy: no-referrer`, same-origin page navigations might omit `Referer`. However, modern browsers always send `Origin` on `fetch(..., {method: 'POST'})`.
- **Bearer Token Exception**:
  - Programmatic callers using `Authorization: Bearer <cred>` do not transmit `Origin` headers.
  - The spec must clarify: Programmatic requests bearing `Authorization: Bearer` and **no cookies** are exempt from `Origin` checking, but MUST still supply `X-SettleTable-Action: 1` for consistent API contract enforcement.

### 3.4 Conflicting Credentials Precedence
- What if a request provides **both** `Cookie: settletable_session=<Alice>` and `Authorization: Bearer <Bob>`?
- The spec is currently silent.
- **Requirement**: The adapter must reject requests with conflicting credentials with `400 Bad Request` (`conflicting_credentials`). If credentials match identically, the request proceeds.

---

## 4. Unauthenticated Landing GET vs. Redemption POST Boundary

### 4.1 Missing `meal_id` on Redemption Route (BLOCKING DEFECT)
- **Draft Spec**:
  - `POST /api/invitations/{token}/redeem`
  - Body: `{}`
  - Action: Calls `Authority.redeem_invitation(token, meal_id)`
- **The Defect**: `Authority.redeem_invitation` requires `meal_id` (`authority.py:624`). The URL path `/api/invitations/{token}/redeem` does not contain `meal_id`, and the body is `{}`. The adapter has no deterministic source for `meal_id`.
- **Remediation Options**:
  - **Preferred**: Change endpoint to `POST /api/meals/{meal_id}/invitations/{token}/redeem` with body `{}`.
  - **Alternative**: Require body `{"meal_id": "<meal_id>"}` on `POST /api/invitations/{token}/redeem`.

### 4.2 Missing Read-Only `Authority.inspect_invitation` (BLOCKING DEFECT)
- **Draft Spec**: `GET /api/invitations/{token}` looks up invitation row by verifier without mutating.
- **The Defect**: `Authority` provides `issue_invitation`, `redeem_invitation`, and `snapshot` (which requires an existing participant's credential). There is NO method to inspect an invitation token without redeeming it.
- **Remediation**: The adapter must NOT execute ad-hoc SQL against `Authority._db`. `Authority` must be extended with:
  ```python
  def inspect_invitation(self, token: str) -> InvitationInspection: ...
  ```
  Returning `valid: bool`, `meal_id: str | None`, `participant_name: str | None`, `expires: float | None`, `reason: str | None`.

### 4.3 URL Path Token Exposure
- Tokens are 43-character base64url secrets (256-bit entropy). Placing them in the URL path `/api/invitations/{token}` causes standard HTTP access loggers to write the raw secret to disk.
- **Requirement**: The transport logging adapter must implement regex path redaction:
  `re.sub(r'(/api/invitations/)[A-Za-z0-9_-]{43}', r'\1[REDACTED]', path)`.

---

## 5. Comprehensive Error Mapping & Secret Redaction

### 5.1 Complete `AuthorityError` to HTTP Status Code Mapping

The draft spec omits 18 domain error codes. Below is the complete normative mapping:

| HTTP Status | Error Codes |
|---|---|
| **400 Bad Request** | `invalid_input`, `malformed_json`, `duplicate_key`, `invalid_number`, `missing_action_header`, `conflicting_credentials`, `invalid_command_kind`, `missing_receipt`, `missing_amount`, `subtotal_mismatch`, `receipt_total_mismatch`, `discount_over_base`, `zero_base`, `pending_claim`, `incomplete_quantity`, `quantity_capacity`, `claim_missing`, `unknown_item`, `review_required`, `calculation_rejected`, `unsupported_command`, `invalid_invitation` |
| **401 Unauthorized** | `invalid_session` *(MUST include `WWW-Authenticate: Bearer error="invalid_token"` header)* |
| **403 Forbidden** | `forbidden`, `origin_mismatch` |
| **409 Conflict** | `command_conflict`, `revision_conflict`, `financial_revision_conflict`, `item_revision_conflict`, `receipt_digest_conflict`, `active_invitation_exists`, `already_revoked`, `finalized`, `claimed_item_deletion`, `retired_source`, `source_kind_conflict`, `meal_exists` |
| **411 Length Required**| `missing_content_length` |
| **413 Payload Too Large**| `payload_too_large` |
| **429 Too Many Requests**| `resource_limit` |
| **431 Request Header Fields Too Large** | `header_too_large` |
| **500 Internal Server Error** | `storage_error`, `internal_error` |
| **503 Service Unavailable** | `commit_uncertain`, `busy` *(MUST include `Retry-After: 1` header)* |

### 5.2 Secret Redaction Invariants
1. **Request Headers**: Redact `Authorization` and `Cookie` values.
2. **Response Headers**: Redact `Set-Cookie` value in logs.
3. **URL Paths**: Redact `/api/invitations/{token}`.
4. **Response Bodies**: Never log response bodies of `/bootstrap`, `/session/rotate`, `/redeem`, or `/invitations` at any log level.
5. **Exception Handling**: Unhandled exceptions must never return stack traces or raw strings; map to `{"ok": false, "error": "internal_error", "detail": null}`.

---

## 6. Concurrency, Threading, and Architecture Pitfalls

1. **SQLite Thread Affinity**:
   - `Authority` connections use `sqlite3.connect` without cross-thread safety.
   - **Mandate**: In a multi-threaded server, each worker thread must maintain its own `Authority` instance (thread-local or per-request connection), with SQLite WAL mode and bounded `timeout=1.0` handling file serialization.
2. **DNS Rebinding & Host Header Validation**:
   - The adapter must validate `Host` against configured allowed hosts (e.g. `localhost:8000`, `127.0.0.1:8000`). Mismatches must reject with `400 Bad Request`.
3. **Loopback Binding Security**:
   - Default listener bind address must strictly be `127.0.0.1` (or `::1`).
   - The `/bootstrap` route must reject any request where `remote_addr` is not loopback.
4. **Fraction JSON Serialization**:
   - `DraftSnapshot` contains `Fraction` instances. Standard `json.dumps()` will raise `TypeError`. The snapshot serializer must explicitly map `Fraction` to `[numerator, denominator]` or float/int as appropriate.
5. **Slowloris Attack Prevention**:
   - Socket read timeout must be configured (e.g. `timeout = 5.0`) on incoming client connections.

---

## 7. Actionable Adversarial Test Matrix

Prior to accepting the transport adapter, the following 12 automated test cases must be implemented and pass:

1. **Header Boundary**: Send a 4,097-byte single header line -> Expect `431 Request Header Fields Too Large`.
2. **Header Block**: Send 17 KB total headers -> Expect `431 Request Header Fields Too Large`.
3. **Payload Boundary**: Send body of 1,048,577 bytes -> Expect `413 Payload Too Large` without consuming full stream.
4. **Smuggling Prevention**: Send both `Content-Length` and `Transfer-Encoding: chunked` -> Expect `400 Bad Request`.
5. **Duplicate Keys**: Send `{"command_id": "c1", "command_id": "c2", ...}` -> Expect `400 Bad Request` (`duplicate_key`).
6. **Float Rejection**: Send `{"expected_revision": 1.0}` or `{"quantity": 1.5}` -> Expect `400 Bad Request` (`invalid_number`).
7. **CSRF Origin Mismatch**: POST with `Origin: https://malicious.com` -> Expect `403 Forbidden` (`origin_mismatch`).
8. **CSRF Missing Header**: POST without `X-SettleTable-Action: 1` -> Expect `400 Bad Request` (`missing_action_header`).
9. **Idempotent Landing**: GET `/api/invitations/{token}` 5 consecutive times -> Token remains unconsumed and valid.
10. **Redemption Isolation**: Two concurrent POST redemptions on the same token -> Exactly one succeeds (`200 OK`), second fails (`400 Bad Request` `invalid_invitation`).
11. **Secret Masking**: Inspect server stdout/file logs after bootstrap, invitation, and redemption -> Raw tokens and credentials must be absent or replaced with `[REDACTED]`.
12. **Conflicting Credentials**: Send `Cookie: settletable_session=<credA>` and `Authorization: Bearer <credB>` -> Expect `400 Bad Request` (`conflicting_credentials`).

---

## 8. Summary of Recommendations for SPEC.md

1. Update Section 2 & 3 route definitions:
   - Route `POST /api/invitations/{token}/redeem` -> Change to `POST /api/meals/{meal_id}/invitations/{token}/redeem` (or specify body `{"meal_id": "..."}`).
2. Specify the read-only inspection contract in `Authority`:
   - Add prerequisite task: Implement `Authority.inspect_invitation(token)` in `settletable.authority`.
3. Add Host validation and DNS rebinding protections to Section 2.
4. Clarify programmatic Bearer token caller behavior regarding `Origin`.
5. Replace the partial error mapping in Section 4 with the complete 25+ code mapping.
6. Specify the multi-threading / SQLite connection management pattern.
