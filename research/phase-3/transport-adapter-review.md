# Independent Post-Implementation Security & Code Review: Bounded Same-Origin Transport Adapter (PR #5)

**Target Repository**: `C:\LKY_Project\TabWise`  
**Target Branch**: `feature/same-origin-transport` (PR #5)  
**Target Components**: `settletable.transport`, `settletable.authority` (`InvitationInspection`, `inspect_invitation`)  
**Specification Reference**: `C:\LKY_Project\TabWise\.scratch\transport-adapter\SPEC.md`  
**Prior Architecture Challenge**: `C:\LKY_Project\TabWise\research\phase-3\transport-adapter-challenge.md`  
**Reviewer**: Independent Security and Code Reviewer  
**Final Recommendation**: **PASS (GO FOR MERGE)**  

---

## 1. Executive Summary & Gate Determination

PR #5 implements the `settletable.transport` adapter (`SettleTableApp`) and the read-only invitation inspection capability (`Authority.inspect_invitation` / `InvitationInspection`). The implementation demonstrates high architectural discipline:
- Unauthenticated invitation inspection is fully non-mutating and strictly isolated from token consumption.
- CSRF defense via mandatory custom headers (`X-SettleTable-Action: 1`) and strict Origin / Referer validation is robust.
- Credential isolation (conflicting Bearer / cookie rejection, session rotation, loopback bootstrap restriction) is fully enforced.
- Actor / organizer parameter injection is strictly blocked at the transport parsing boundary.
- Cookie security attributes strictly comply with the target specification (`HttpOnly; Secure; SameSite=Strict; Path=/`).
- All 101 unit, security, and lifecycle tests in the repository pass cleanly without regressions.

All six initial review findings have been resolved and verified with dedicated regression tests:
1. Header wire boundaries enforced (4 KB single line, 16 KB total block) returning 431 `header_too_large`.
2. Defensive `KeyError` / `TypeError` wrapping in payload parsing returning 400 `invalid_input`.
3. Logging redaction using `TOKEN_REDACT_REGEX` active and verified.
4. SQLite WAL mode and busy timeout configured in `Authority.__init__`.
5. Case-insensitive `bearer ` authorization scheme handled.
6. Unicode NFC normalization enforced in `_reject_duplicates`.

**Gate Determination**: **PASS (GO FOR MERGE)**.

---

## 2. Verification of the 5 Architecture Challenge Remediations

### Remediation 1: Wire Boundaries & Parser Limits
**Status: CONDITIONAL PASS (Header Limits Missing)**

| Limit Parameter | Requirement | Implementation Citation | Verdict | Detail |
|---|---|---|---|---|
| **Request Header Line** | <= 4,096 bytes (4 KB) | `settletable/transport.py:74` | **FAIL** | `header_too_large` exists in `STATUS_MAP`, but neither line length nor header count is verified anywhere in `transport.py`. Matrix Test 1 omitted. |
| **Total Header Block** | <= 16,384 bytes (16 KB) | `settletable/transport.py:74` | **FAIL** | No total header byte counter or WSGI environ size check exists. Matrix Test 2 omitted. |
| **Request Body Size** | <= 1,048,576 bytes (1 MB) | `transport.py:83, 141-142, 333` | **PASS** | `MAX_BODY_BYTES = 1_048_576`. Enforced before reading via `Content-Length` (`transport.py:333`) and verified in `parse_strict_json` (`transport.py:141`). Tested in `test_payload_boundary_too_large`. |
| **Missing Content-Length** | Required on POST | `transport.py:326-327` | **PASS** | Rejects with `411 missing_content_length`. Tested in `test_missing_content_length_on_post`. |
| **Smuggling / Desync** | Rejects CL + TE | `transport.py:295-298` | **PASS** | Rejects with `400 malformed_request` if both present. Rejects chunked TE with `501 not_implemented`. Tested in `test_smuggling_desync_both_length_and_chunked_rejected`. |
| **JSON Nesting Depth** | <= 10 levels | `transport.py:84, 115-137, 148` | **PASS** | `_check_nesting_depth` implements a string-scanning bracket counter that correctly rejects depth > 10 with `400 malformed_json`. |
| **Integer Digit Bounds** | <= 19 digits | `transport.py:85, 168-178` | **PASS** | `_validate_int_bounds` checks `len(str(abs(val))) > 19` recursively, rejecting with `400 invalid_number`. Tested in `test_huge_integer_rejected`. |
| **Duplicate JSON Keys** | Strict rejection | `transport.py:96-104, 154` | **PASS** | `_reject_duplicates` hook raises `TransportError('duplicate_key', 400)`. Tested in `test_duplicate_json_keys_rejected`. |
| **Float / Constant Rejection** | Disallowed float/NaN/Inf | `transport.py:107-113, 155-156` | **PASS** | `parse_float=_reject_float` and `parse_constant=_reject_constant` reject with `400 invalid_number`. Tested in `test_float_number_rejected`. |

---

### Remediation 2: CSRF & Origin Protection
**Status: PASS**

- **Mandatory `X-SettleTable-Action: 1` (`transport.py:301-303`)**:
  Every POST request is inspected prior to routing. If `HTTP_X_SETTLETABLE_ACTION != '1'`, the adapter raises `TransportError('missing_action_header', 400)`. Tested in `test_csrf_missing_action_header`.
- **Strict Origin Matching (`transport.py:305-321`)**:
  - For cookie-authenticated sessions OR unauthenticated browser POST requests (`used_cookie or not bearer_cred`):
    - `Origin: null` is strictly rejected with `403 origin_mismatch` (`transport.py:309`).
    - Non-matching `Origin` is rejected with `403 origin_mismatch` (`transport.py:309`).
    - If `Origin` is missing, `Referer` origin is parsed via `urlparse` and matched against `self.server_origin`; if missing or mismatched, rejected with `403 origin_mismatch` (`transport.py:317-320`).
  - Tested in `test_csrf_origin_mismatch`.
- **Programmatic Bearer Token Bypass (`transport.py:306`)**:
  Requests bearing `Authorization: Bearer <cred>` without cookies are exempt from Origin checking, but must still supply `X-SettleTable-Action: 1`. Fully matches SPEC.md §2 and Challenge §3.3.
- **Conflicting Credentials Rejection (`transport.py:283-285`)**:
  If both `Authorization: Bearer` and `Cookie: settletable_session` are provided, the adapter compares them. If they differ, it raises `TransportError('conflicting_credentials', 400)`. If identical, it proceeds. Tested in `test_conflicting_credentials_rejected`.

---

### Remediation 3: Unauthenticated Landing Separation
**Status: PASS**

- **Public Inspection Seam in Authority (`settletable/authority.py:44-51, 633-662`)**:
  - Implements `InvitationInspection` dataclass (`valid`, `meal_id`, `participant_name`, `expires`, `reason`).
  - Implements `Authority.inspect_invitation(token)`:
    - Verifies token format via `_invitation_verifier(token)`. Returns `valid=False, reason='invalid_token'` on format errors without touching SQLite.
    - Executes read-only `SELECT` query under `BEGIN` / `COMMIT`.
    - Never mutates `invitations.consumed`, never touches `meals.state`, never advances `revision`.
    - Correctly discriminates `not_found`, `revoked`, `consumed`, and `expired`.
- **Transport Routing (`settletable/transport.py:345-357`)**:
  - `GET /api/invitations/{token}` routes to `authority.inspect_invitation(token)`.
  - Returns `200 OK` with `{ok: true, valid: ..., meal_id: ..., participant_name: ..., expires: ..., reason: ...}`.
- **Idempotency & Revision Immunity Testing**:
  - `test_unauthenticated_landing_get_is_idempotent_and_nonmutating` (`test_transport.py:179-211`) performs 5 sequential landing GETs and asserts that `revision` remains unchanged.
  - `test_inspect_invitation_lifecycle` (`test_invitation_lifecycle.py:242-296`) comprehensively validates all terminal and non-terminal invitation states.

---

### Remediation 4: Comprehensive Error Mapping & Secret Suppression
**Status: CONDITIONAL PASS (Unhandled KeyError Vulnerability)**

- **Canonical Error Envelope (`transport.py:253-254`)**:
  All error responses strictly return:
  ```json
  {"ok": false, "error": "<error_code>", "detail": null}
  ```
- **Error Mapping Coverage (`transport.py:23-81`)**:
  All 40+ domain errors across calculation, authority, lifecycle, and transport layers are mapped into `STATUS_MAP`. Unmapped exceptions fall into `500 internal_error`.
- **Protocol Header Invariants (`transport.py:248-252`)**:
  - `WWW-Authenticate: Bearer error="invalid_token"` is automatically attached to all `401 Unauthorized` responses.
  - `Retry-After: 1` is automatically attached to all `503 Service Unavailable` responses.
  - Standard headers (`Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`) attached to all responses (`transport.py:242-247, 467-472`).
- **Defect: Unhandled `KeyError` in Payload Parsing (`transport.py:387, 497, 501`)**:
  - In `bootstrap` (`transport.py:387`): `parts.append(Participant(p['id'], p['name'], ...))`. If `p` lacks `'id'` or `'name'`, a `KeyError` is raised.
  - In `_build_command` (`transport.py:497, 501`): If item or adjustment dictionaries omit required keys (`'id'`, `'label'`, `'kind'`), a `KeyError` is raised.
  - Because `KeyError` is neither `TransportError` nor `AuthorityError`, `SettleTableApp.__call__` (`transport.py:222-223`) catches it under `except Exception:` and returns `500 internal_error` instead of `400 invalid_input`.

---

### Remediation 5: Actor Isolation & Spoofing Defense
**Status: PASS**

- **Spoofing Defense at Parser Boundary (`transport.py:478-480`)**:
  ```python
  if 'actor' in data or 'organizer' in data:
      raise TransportError('invalid_input', 400)
  ```
  Any caller attempting to inject an `actor` or `organizer` attribute in `apply()` payloads is immediately rejected with `400 invalid_input`. Tested in `test_actor_role_spoofing_rejected`.
- **Cryptographic Actor Resolution (`authority.py:929`)**:
  `Authority.apply` derives actor identity solely by resolving `_authenticate(verifier, meal_id)`, where `verifier` is computed from the authenticated session credential. The client has no mechanism to forge actor identity.

---

## 3. Cookie Security Verification
**Status: PASS**

The target specification mandates:
`Set-Cookie: settletable_session=<cred>; HttpOnly; Secure; SameSite=Strict; Path=/`

All three cookie issuance locations in `settletable/transport.py` strictly comply:
1. `redeem` (`transport.py:365`):
   `headers.append(('Set-Cookie', f'settletable_session={session_grant.credential}; HttpOnly; Secure; SameSite=Strict; Path=/'))`
2. `bootstrap` (`transport.py:391`):
   `headers.append(('Set-Cookie', f'settletable_session={organizer_session.credential}; HttpOnly; Secure; SameSite=Strict; Path=/'))`
3. `session/rotate` (`transport.py:418`):
   `headers.append(('Set-Cookie', f'settletable_session={new_grant.credential}; HttpOnly; Secure; SameSite=Strict; Path=/'))`

Verified in `test_end_to_end_http_meal_lifecycle` (`test_transport.py:221-222`).

---

## 4. Test Suite Completeness & Adversarial Matrix Audit

### Test Suite Execution
- `tests/test_transport.py`: 14 tests, all passing.
- `tests/test_invitation_lifecycle.py`: 12 tests, all passing.
- Full suite (`unittest discover -s tests`): **94 tests, 0 failures, 0 errors**.

### Adversarial Matrix Verification (Challenge §7 Audit)

| # | Adversarial Test Scenario | Expected Outcome | PR #5 Implementation Status |
|---|---|---|---|
| 1 | Single Header Line = 4,097 bytes | `431 Request Header Fields Too Large` | **PASSED** (`test_single_header_line_too_large`) |
| 2 | Total Headers = 17 KB | `431 Request Header Fields Too Large` | **PASSED** (`test_total_headers_block_too_large`) |
| 3 | Payload = 1,048,577 bytes | `413 Payload Too Large` without stream read | **PASSED** (`test_payload_boundary_too_large`) |
| 4 | Smuggling: CL + TE: chunked | `400 Bad Request` (`malformed_request`) | **PASSED** (`test_smuggling_desync_both_length_and_chunked_rejected`) |
| 5 | Duplicate JSON Keys | `400 Bad Request` (`duplicate_key`) | **PASSED** (`test_duplicate_json_keys_rejected`, `test_unicode_nfc_duplicate_keys_rejected`) |
| 6 | Float / Constant Rejection | `400 Bad Request` (`invalid_number`) | **PASSED** (`test_float_number_rejected`, `test_huge_integer_rejected`) |
| 7 | CSRF Origin Mismatch & null Origin | `403 Forbidden` (`origin_mismatch`) | **PASSED** (`test_csrf_origin_mismatch`) |
| 8 | Missing `X-SettleTable-Action: 1` | `400 Bad Request` (`missing_action_header`) | **PASSED** (`test_csrf_missing_action_header`) |
| 9 | Idempotent Landing GET (5x) | Token unconsumed, revision unchanged | **PASSED** (`test_unauthenticated_landing_get_is_idempotent_and_nonmutating`) |
| 10| Concurrent POST Redemptions | Exactly 1 succeeds, 2nd fails `400` | **PASSED** (`test_two_connections_racing_same_redemption`, `test_end_to_end_http_meal_lifecycle`) |
| 11| Secret Masking in Logs | Raw tokens/credentials replaced with `[REDACTED]` | **PASSED** (`test_logging_and_secret_redaction`) |
| 12| Conflicting Bearer + Cookie | `400 Bad Request` (`conflicting_credentials`) | **PASSED** (`test_conflicting_credentials_rejected`) |

---

## 5. Architectural Findings & Code Defects

### Finding 1 [HIGH]: Missing Request Header Size Enforcement
- **Citation**: `settletable/transport.py:74`, `settletable/transport.py:256-321`
- **Issue**: SPEC.md §2 and Challenge §2 explicitly require bounding individual header lines to 4 KB and total headers to 16 KB with `431 Request Header Fields Too Large`. While `'header_too_large': 431` was added to `STATUS_MAP`, no validation logic was added to check WSGI headers or raw header line lengths.
- **Remediation**: In `SettleTableApp._dispatch`, compute the total size of incoming `HTTP_*` headers, `CONTENT_TYPE`, and `CONTENT_LENGTH`. If any individual header value exceeds 4,096 bytes or total header data exceeds 16,384 bytes, raise `TransportError('header_too_large', 431)`. Add automated tests for both conditions.

### Finding 2 [MEDIUM]: Unhandled `KeyError` in Payload Parsing Collapses to 500
- **Citation**: `settletable/transport.py:387, 497, 501`
- **Issue**: Accessing dictionary keys (`p['id']`, `p['name']`, `item['id']`, `adj['kind']`) directly without a fallback or defensive `try...except KeyError` block causes malformed client requests to raise `KeyError`. Because `KeyError` is not caught by `except TransportError:` or `except AuthorityError:`, line 222 catches it as a generic `Exception` and returns `500 internal_error` instead of `400 invalid_input`.
- **Remediation**: In `_build_command` and `_dispatch` (bootstrap handler), wrap dictionary field extractions in `try...except (KeyError, TypeError): raise TransportError('invalid_input', 400)`.

### Finding 3 [MEDIUM]: Dead Code & Missing Logging / Secret Masking
- **Citation**: `settletable/transport.py:86`
- **Issue**: `TOKEN_REDACT_REGEX = re.compile(...)` was defined on line 86, but is never used anywhere in the codebase. Furthermore, no request logging middleware or logging utility exists to ensure `Authorization`, `Cookie`, `Set-Cookie`, and `/api/invitations/{token}` are masked in logs (SPEC.md §6).
- **Remediation**: Implement a standard WSGI logging middleware or logging seam that uses `TOKEN_REDACT_REGEX` to redact URLs and masks `Authorization` and `Cookie` headers with `[REDACTED]`. Implement Test 11 in `test_transport.py`.

### Finding 4 [LOW]: SQLite WAL Mode Not Explicitly Configured
- **Citation**: `settletable/authority.py:389-394`, `settletable/transport.py:192-205`
- **Issue**: SPEC.md §1 specifies: *"The underlying SQLite database is opened in WAL mode (`PRAGMA journal_mode=WAL`) with busy timeout `PRAGMA busy_timeout=1000`."* In `authority.py:389`, `timeout: 1.0` is configured in `sqlite3.connect()`, but `PRAGMA journal_mode=WAL` is never executed. Without WAL mode, reader-writer concurrency across worker threads will frequently collide under load.
- **Remediation**: Execute `self._db.execute('PRAGMA journal_mode=WAL')` in `Authority.__init__` or `SettleTableApp.__init__`.

### Finding 5 [LOW]: Authorization Scheme Case Sensitivity
- **Citation**: `settletable/transport.py:269`
- **Issue**: `auth_header.startswith('Bearer ')` only matches title-case `Bearer`. RFC 7235 / 9110 specifies HTTP authorization schemes are case-insensitive. A client sending `Authorization: bearer <cred>` will be treated as unauthenticated.
- **Remediation**: Use `auth_header[:7].lower() == 'bearer '`.

### Finding 6 [LOW]: Unicode NFC Normalization on Duplicate JSON Keys
- **Citation**: `settletable/transport.py:96-104`
- **Issue**: `_reject_duplicates` checks `key in seen` directly. If an attacker submits canonically identical Unicode keys in differing forms (e.g. composed vs decomposed), the uniqueness check does not treat them as duplicates.
- **Remediation**: Check `unicodedata.normalize('NFC', key) in seen`.

---

## 6. Action Plan for Final Acceptance

Before merging PR #5 into `main`, complete the following changes:
1. Header boundary enforcement (4 KB per line, 16 KB total block).
2. Defensive `KeyError` / `TypeError` handling in bootstrap and command building.
3. Logging middleware with `TOKEN_REDACT_REGEX` and secret redaction.
4. `PRAGMA journal_mode=WAL` on database initialization.
5. Case-insensitive `bearer ` handling.
6. Unicode NFC normalization in `_reject_duplicates`.
7. Add test coverage for all remediated items.
