# Bounded Same-Origin Transport Adapter Specification

**Status**: ACCEPTED / READY FOR IMPLEMENTATION  
**Component**: `settletable.transport`  
**Date**: 2026-10-20  
**Target Branch**: `feature/same-origin-transport`  
**Independent Challenge**: [research/phase-3/transport-adapter-challenge.md](../../research/phase-3/transport-adapter-challenge.md) (All findings incorporated)  

---

## 1. Overview and Architecture

The SettleTable local authority (`settletable.authority.Authority`) provides atomic SQLite persistence, deterministic apportion calculation (`settletable.calculation`), domain-separated credentials, and single-use invitation lifecycles.

This specification defines the **Bounded Same-Origin Transport Adapter**, a defense-in-depth HTTP adapter built on Python's standard library (`http.server` / WSGI) that exposes the authority over local HTTP.

### Threading & SQLite Connection Model
- `Authority` connections use `sqlite3.connect` and are strictly bound to their creating thread.
- The transport adapter manages `Authority` instances using a **Thread-Local Factory** (`threading.local()` or per-request connection).
- The underlying SQLite database is opened in WAL mode (`PRAGMA journal_mode=WAL`) with busy timeout `PRAGMA busy_timeout=1000`.

---

## 2. Wire Boundary & Parser Limits

All limits are enforced *before* memory allocation or JSON decoding:

| Parameter | Limit | Failure Response |
|---|---|---|
| Request Header Block Size | 16,384 bytes (16 KB total) | `431 Request Header Fields Too Large` (`header_too_large`) |
| Individual Header Line | 4,096 bytes (4 KB max) | `431 Request Header Fields Too Large` (`header_too_large`) |
| Request Body Size | 1,048,576 bytes (1 MB max) | `413 Payload Too Large` (`payload_too_large`) |
| Missing `Content-Length` on POST | Required if body present | `411 Length Required` (`missing_content_length`) |
| Desync / Smuggling Check | Both `Content-Length` & `Transfer-Encoding` | `400 Bad Request` (`malformed_request`) |
| Host Header Validation | Must match configured allowed host(s) | `400 Bad Request` (`invalid_host`) |
| Loopback Enforcement for Bootstrap | `remote_addr` must be loopback | `403 Forbidden` (`forbidden`) |
| JSON Nesting Depth | Maximum 10 levels | `400 Bad Request` (`malformed_json`) |
| Duplicate JSON Keys | Strict hook (`object_pairs_hook`) | `400 Bad Request` (`duplicate_key`) |
| Floating-Point / NaN / Inf | Strict float rejection (`parse_float`) | `400 Bad Request` (`invalid_number`) |
| Integer Digit Length | Max 19 digits (fits 64-bit signed int) | `400 Bad Request` (`invalid_number`) |
| Origin Check (mutating POST) | Must match configured server origin | `403 Forbidden` (`origin_mismatch`) |
| Action Header (mutating POST) | `X-SettleTable-Action: 1` required | `400 Bad Request` (`missing_action_header`) |

### Origin and CSRF Rules
1. **Browser Requests (Cookie-Authenticated or Unauthenticated POST)**:
   - Must supply matching `Origin` header.
   - `Origin: null` (sandboxed iframes, local files) is strictly rejected with `403 Forbidden` (`origin_mismatch`).
   - If `Origin` is absent on POST, `Referer` origin must match configured server origin; otherwise rejected with `403 Forbidden`.
   - Must supply `X-SettleTable-Action: 1`.
2. **Programmatic Requests (Bearer-Authenticated)**:
   - Requests bearing `Authorization: Bearer <cred>` and **no cookies** are exempt from `Origin` checking, but MUST still supply `X-SettleTable-Action: 1`.
3. **Conflicting Credentials**:
   - If both `Cookie: settletable_session=<credA>` and `Authorization: Bearer <credB>` are provided with differing credentials, reject immediately with `400 Bad Request` (`conflicting_credentials`). If identical, proceed.

---

## 3. Prerequisite: Read-Only Authority Inspection Method

To support non-mutating landing GETs without breaking transaction boundaries or reaching into private database state, `settletable.authority.Authority` must expose:

```python
@dataclass(frozen=True, slots=True)
class InvitationInspection:
    valid: bool
    meal_id: str | None = None
    participant_name: str | None = None
    expires: float | None = None
    reason: str | None = None  # 'expired', 'consumed', 'revoked', 'not_found', 'invalid_token'

def inspect_invitation(self, token: str) -> InvitationInspection:
    """Read-only inspection of an invitation token without mutating state or advancing revision."""
```

---

## 4. Endpoints & Route Mappings

All API responses return `Content-Type: application/json; charset=utf-8` and headers:
- `Cache-Control: no-store`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: no-referrer`

### 4.1 Provisioning & Session
- `POST /api/meals/{meal_id}/bootstrap`
  - Access: Local loopback only (`127.0.0.1` / `::1`), strictly rejecting proxy forwarding headers (`X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `Forwarded`, `X-Real-IP`).
  - Body: `{"participants": [{"id": "...", "name": "...", "organizer": true/false}, ...]}`
  - Action: Calls `Authority.bootstrap(meal_id, participants)`.
  - Credential Hygiene: Returns credentials **strictly for the organizer** (`sessions: [{"participant_id": "...", "credential": "..."}]`); never returns diner credentials. Diners must be enrolled via `issue_invitation`. Sets `Set-Cookie: settletable_session=<organizer_cred>; HttpOnly; Secure; SameSite=Strict; Path=/`.
- `POST /api/meals/{meal_id}/session/rotate`
  - Access: Authenticated diner session (via cookie or `Authorization: Bearer`).
  - Action: Calls `Authority.rotate_session(credential, meal_id)`.
  - Credential Hygiene: If authenticated via cookie, `credential` is omitted from the JSON response body and updated strictly via `Set-Cookie` (`HttpOnly`). If authenticated via `Authorization: Bearer`, `credential` is included in the JSON response body.
  - Returns: `200 OK` with `{"ok": true, "participant_id": "..."}`. If caller is organizer, returns `403 Forbidden` (`forbidden`).

### 4.2 Snapshot & Commands
- `GET /api/meals/{meal_id}/snapshot`
  - Access: Authenticated participant.
  - Action: Calls `Authority.snapshot(credential, meal_id)`.
  - Serialization: Serializes `DraftSnapshot` to JSON, mapping `Fraction` instances to `[numerator, denominator]`.
  - Returns: `200 OK` with JSON snapshot.
- `POST /api/meals/{meal_id}/apply`
  - Access: Authenticated participant.
  - Body: JSON command object (`ReplaceReceipt`, `SetOwnQuantity`, `ReviewReceipt`, `Finalize`, `RevokeInvitation`, `RevokeSession`, `RevokeMembership`).
  - Security Check: Rejects any request payload containing `actor` or `organizer` fields with `400 Bad Request` (`invalid_input`).
  - Action: Calls `Authority.apply(credential, meal_id, command)`.
  - Returns: `200 OK` with `AcceptedResult` JSON.

### 4.3 Invitations
- `POST /api/meals/{meal_id}/invitations`
  - Access: Authenticated organizer only.
  - Body: `{"participant_id": "...", "invite_ttl": 86400, "issue_id": "..." (optional)}`
  - Action: Calls `Authority.issue_invitation(organizer_cred, meal_id, participant_id, ...)`.
  - Returns: `201 Created` with `InvitationGrant` JSON.
- `GET /api/invitations/{token}`
  - Access: Public / unauthenticated.
  - **NON-MUTATING**: Calls `Authority.inspect_invitation(token)`. Never consumes the token or advances revision.
  - Returns: `200 OK` with `{"valid": true, "meal_id": "...", "participant_name": "...", "expires": ...}` or `{"valid": false, "reason": "..."}`.
- `POST /api/meals/{meal_id}/invitations/{token}/redeem`
  - Access: Public (bearer of valid invitation token).
  - Body: `{}` (empty object, requires `X-SettleTable-Action: 1`).
  - Action: Calls `Authority.redeem_invitation(token, meal_id)`.
  - Returns: `200 OK` with `SessionGrant` JSON; sets `Set-Cookie: settletable_session=<cred>; HttpOnly; Secure; SameSite=Strict; Path=/`.

---

## 5. Comprehensive Error Mapping

All error responses return:
```json
{
  "ok": false,
  "error": "error_code",
  "detail": null
}
```

| HTTP Status | Error Codes |
|---|---|
| **400 Bad Request** | `invalid_input`, `malformed_json`, `duplicate_key`, `invalid_number`, `missing_action_header`, `conflicting_credentials`, `malformed_request`, `invalid_host`, `invalid_command_kind`, `missing_receipt`, `missing_amount`, `subtotal_mismatch`, `receipt_total_mismatch`, `discount_over_base`, `zero_base`, `pending_claim`, `incomplete_quantity`, `quantity_capacity`, `claim_missing`, `unknown_item`, `review_required`, `calculation_rejected`, `unsupported_command`, `invalid_invitation` |
| **401 Unauthorized** | `invalid_session` *(Includes `WWW-Authenticate: Bearer error="invalid_token"` header)* |
| **403 Forbidden** | `forbidden`, `origin_mismatch` |
| **409 Conflict** | `command_conflict`, `revision_conflict`, `financial_revision_conflict`, `item_revision_conflict`, `receipt_digest_conflict`, `active_invitation_exists`, `already_revoked`, `finalized`, `claimed_item_deletion`, `retired_source`, `source_kind_conflict`, `meal_exists` |
| **411 Length Required** | `missing_content_length` |
| **413 Payload Too Large** | `payload_too_large` |
| **429 Too Many Requests** | `resource_limit` |
| **431 Request Header Fields Too Large** | `header_too_large` |
| **500 Internal Server Error** | `storage_error`, `internal_error` |
| **503 Service Unavailable** | `commit_uncertain`, `busy` *(Includes `Retry-After: 1` header)* |

---

## 6. Secret Redaction & Logging Invariants

1. **Access Log Redaction**: Request paths matching `/api/invitations/{token}` redact the token: `/api/invitations/[REDACTED]`.
2. **Header Redaction**: `Authorization`, `Cookie`, and `Set-Cookie` header values are masked with `[REDACTED]`.
3. **Body Redaction**: Response bodies for `/bootstrap`, `/session/rotate`, `/redeem`, and `/invitations` are never logged.
4. **Unhandled Exceptions**: Never expose tracebacks or internal paths to clients.
