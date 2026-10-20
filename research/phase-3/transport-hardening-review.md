# Independent Security & Code Review: SettleTable Transport Hardening (PR #6)

**Target Repository**: `C:\LKY_Project\TabWise`  
**Target Branch**: `feature/transport-hardening` (Head Commit `7e77001`)  
**Components Reviewed**:
- Implementation: `settletable/transport.py`
- Tests: `tests/test_transport.py`
- Architecture Document: `docs/deployment-boundary.md`
- Specification: `.scratch/transport-adapter/SPEC.md`

**Reviewer**: Independent Security and Code Reviewer  
**Audit Recommendation**: **GO (PASS / APPROVED FOR MERGE)**

---

## 1. Executive Summary & Audit Gate Determination

PR #6 implements essential defensive hardening for `settletable.transport` across four key security boundaries identified during architecture reviews:
1. **Reverse Proxy Loopback Protection**: Prevents reverse proxies or tunnel backends from inadvertently exposing the unauthenticated loopback `/bootstrap` endpoint to external traffic.
2. **Credential Minimization at Provisioning**: Discards pre-minted diner credentials from the bootstrap HTTP response, ensuring only the organizer session is ever transmitted.
3. **Cookie-Context Credential Hygiene**: Prevents XSS token exfiltration by strictly omitting raw session credentials from the JSON response body during cookie-authenticated session rotations, while maintaining raw credential returns for programmatic Bearer token clients.
4. **Ingress vs. WSGI Boundary Demarcation**: Formally establishes the two-tier security model in `docs/deployment-boundary.md`, identifying why raw TCP stream bounds must reside in Tier 1 reverse proxies while WSGI provides Tier 2 application-level defense-in-depth.

All 104 unit, security, integration, and mathematical invariant tests across the entire test suite pass cleanly (`Ran 104 tests in 65.392s, OK`). No mathematical, financial, or state machine invariants were modified or disturbed.

### Gate Evaluation Summary

| # | Specific Audit Gate | Status | Key Implementation Citation | Key Test Citation |
|---|---|---|---|---|
| 1 | Reverse Proxy Loopback Protection | **PASS** | `settletable/transport.py:408-411` | `tests/test_transport.py:404-418` |
| 2 | Credential Minimization at Provisioning | **PASS** | `settletable/transport.py:429-440` | `tests/test_transport.py:419-434` |
| 3 | Cookie-Context Credential Hygiene | **PASS** | `settletable/transport.py:467-470` | `tests/test_transport.py:289-296, 435-460` |
| 4 | Ingress vs. WSGI Boundary Demarcation | **PASS** | `docs/deployment-boundary.md:9-49` | Reference Nginx config (`lines 72-103`) |
| 5 | Test Coverage & Invariant Integrity | **PASS** | 104 / 104 tests passing | `tests/test_transport.py`, `tests/test_calculation.py` |

**Final Recommendation**: **GO**. PR #6 meets all security criteria and is ready for production merge into `main`.

---

## 2. Detailed Audit Gate Findings

### Gate 1: Reverse Proxy Loopback Protection
- **Requirement**: Reject bootstrap requests containing proxy forwarding headers (`X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `Forwarded`, `X-Real-IP`) with `403 Forbidden`; prevent external attackers from spoofing loopback origin when behind an internal proxy or tunnel.
- **Implementation Citation**: `settletable/transport.py:405-415`
  ```python
  proxy_headers = ('HTTP_X_FORWARDED_FOR', 'HTTP_X_FORWARDED_HOST',
                   'HTTP_X_FORWARDED_PROTO', 'HTTP_FORWARDED', 'HTTP_X_REAL_IP')
  if any(h in environ for h in proxy_headers):
      raise TransportError('forbidden', 403)

  remote_addr = environ.get('REMOTE_ADDR', '')
  if remote_addr not in ('127.0.0.1', '::1', 'localhost', 'testclient'):
      raise TransportError('forbidden', 403)
  ```
- **Evaluation**:
  - In a standard deployment where an internal proxy (e.g. Nginx, Caddy, Cloudflare Tunnel, ngrok) forwards traffic to loopback `127.0.0.1:8000`, external requests forwarded by the proxy will have `REMOTE_ADDR == '127.0.0.1'`, which would normally pass a naïve loopback check.
  - The proxy header detection in lines 408–411 intercepts all five standard WSGI proxy headers (`HTTP_X_FORWARDED_FOR`, `HTTP_X_FORWARDED_HOST`, `HTTP_X_FORWARDED_PROTO`, `HTTP_FORWARDED`, `HTTP_X_REAL_IP`) and raises `TransportError('forbidden', 403)`.
  - If an external attacker attempts direct connection without proxy headers, line 414 rejects any `remote_addr` outside loopback with `403 Forbidden`.
  - Tested in `tests/test_transport.py:404-418` (`test_bootstrap_proxy_forwarding_headers_rejected`), validating that each individual proxy header results in `403 forbidden`.
- **Verdict**: **PASS**.

### Gate 2: Credential Minimization at Provisioning
- **Requirement**: Bootstrap must return ONLY the organizer's session in the JSON response; strictly prevent leaking credentials for non-organizer diners at bootstrap time.
- **Implementation Citation**: `settletable/transport.py:428-441`
  ```python
  b_res = authority.bootstrap(meal_id, tuple(parts))
  organizer_session = next(s for s, p in zip(b_res.sessions, parts) if p.organizer)
  headers = self._default_headers()
  headers.append(('Set-Cookie', f'settletable_session={organizer_session.credential}; HttpOnly; Secure; SameSite=Strict; Path=/'))
  out = {
      'ok': True,
      'meal_id': b_res.meal_id,
      'organizer_id': organizer_session.participant_id,
      'sessions': [{'participant_id': organizer_session.participant_id, 'credential': organizer_session.credential}],
  }
  return 201, headers, serialize_json(out)
  ```
- **Evaluation**:
  - `Authority.bootstrap` guarantees exactly one organizer exists (`authority.py:481`).
  - While `Authority.bootstrap` provisions the database state, `transport.py` filters `b_res.sessions` to isolate strictly the `organizer_session` (line 429).
  - Lines 438–440 serialize ONLY `organizer_id` and a single-item `sessions` list containing the organizer's credentials.
  - Non-organizer diners declared in `participants` have their pre-minted raw session credentials discarded from memory upon response serialization. They are never transmitted over HTTP, never written to cookies, and never leaked to the bootstrap caller.
  - Diners can only obtain active credentials through the single-use invitation token lifecycle (`issue_invitation` -> `redeem_invitation`).
  - In `authority.py:696-699`, redemption cleanly overwrites the dormant database session verifier using `ON CONFLICT(meal_id, participant_id) DO UPDATE SET verifier=?, expires=?, revoked=0`.
  - Tested in `tests/test_transport.py:419-434` (`test_bootstrap_never_leaks_all_participant_credentials`), verifying that `len(sessions) == 1`, organizer is returned, and neither `D1` nor `D2` are leaked.
- **Verdict**: **PASS**.

### Gate 3: Cookie-Context Credential Hygiene
- **Requirement**: `POST /api/meals/{meal_id}/session/rotate` must omit raw bearer credentials from the JSON response body when the caller authenticated via cookie; preserve raw credential return in JSON body strictly for programmatic clients authenticating via Bearer token.
- **Implementation Citation**: `settletable/transport.py:454-471`
  ```python
  new_grant = authority.rotate_session(active_cred, meal_id)
  headers = self._default_headers()
  headers.append(('Set-Cookie', f'settletable_session={new_grant.credential}; HttpOnly; Secure; SameSite=Strict; Path=/'))
  out = {
      'ok': True,
      'participant_id': new_grant.participant_id,
  }
  if bearer_cred and not used_cookie:
      out['credential'] = new_grant.credential
  return 200, headers, serialize_json(out)
  ```
- **Evaluation**:
  - When a user session originates from a browser via cookie, `used_cookie` is `True` (`transport.py:316`).
  - During rotation, line 469 checks `if bearer_cred and not used_cookie:`. Because `used_cookie` is `True`, `out['credential']` is NOT added to the JSON response dictionary.
  - The new token is delivered exclusively via the `Set-Cookie: settletable_session=<cred>; HttpOnly; Secure; SameSite=Strict; Path=/` response header (line 462). This ensures browser-side JavaScript and DOM scripts cannot read the session secret, preserving complete `HttpOnly` defense against XSS token exfiltration.
  - For headless/programmatic API clients authenticating via `Authorization: Bearer <cred>` without cookies, `bearer_cred and not used_cookie` evaluates to `True`, correctly returning `credential` in the JSON response body (line 470).
  - Tested in `tests/test_transport.py:285-296` (`test_end_to_end_http_meal_lifecycle`) for cookie isolation, and lines 435–460 (`test_session_rotation_bearer_returns_credential_in_json`) for programmatic Bearer preservation.
- **Verdict**: **PASS**.

### Gate 4: Ingress vs. WSGI Boundary Demarcation
- **Requirement**: `docs/deployment-boundary.md` must properly document the distinction between raw-wire ingress stream limits and application-level WSGI checks.
- **Evaluation of `docs/deployment-boundary.md`**:
  - **Two-Tier Architecture Model (`lines 9–37`)**: Correctly bifurcates security responsibilities into Tier 1 (Ingress Reverse Proxy / Nginx / Caddy) and Tier 2 (SettleTable WSGI Application).
  - **Demarcation Justification (`lines 41–49`)**: Thoroughly and accurately explains that WSGI servers (Gunicorn, uWSGI, Waitress, wsgiref) read and parse raw TCP streams into memory before calling the application (`SettleTableApp.__call__`). Consequently, application-level Python checks (e.g. 4 KB line limit, 16 KB total header limit) serve as defense-in-depth on parsed structures and cannot protect against slow stream attacks (Slowloris) or socket-level memory exhaustion.
  - **Threat Model & Mitigations (`lines 51–67`)**: Explicitly covers proxy-mediated loopback bypass, bootstrap credential exposure, and session rotation cookie hygiene.
  - **Production Reference Ingress Configuration (`lines 70–103`)**: Includes a production-ready Nginx configuration that implements wire-level stream bounds (`client_max_body_size 1M`, `large_client_header_buffers 4 4k`, `client_header_timeout 10s`, `client_body_timeout 10s`) and route-level access control on `^/api/meals/[^/]+/bootstrap$` (`allow 127.0.0.1; allow ::1; deny all;`).
- **Verdict**: **PASS**.

### Gate 5: Test Coverage & Invariant Integrity
- **Requirement**: Automated tests verifying each security boundary; financial and state invariants remain undisturbed.
- **Evaluation**:
  - **Dedicated Security Unit Tests**:
    - `test_bootstrap_proxy_forwarding_headers_rejected` (`test_transport.py:404-418`): Verified.
    - `test_bootstrap_never_leaks_all_participant_credentials` (`test_transport.py:419-434`): Verified.
    - `test_session_rotation_bearer_returns_credential_in_json` (`test_transport.py:435-460`): Verified.
    - Cookie rotation assertion in `test_end_to_end_http_meal_lifecycle` (`test_transport.py:289-296`): Verified.
    - Loopback direct IP enforcement `test_bootstrap_loopback_enforcement` (`test_transport.py:161-166`): Verified.
  - **Invariant Integrity**:
    - Ran full test suite across the repository: `Ran 104 tests in 65.392s, OK` (0 failures, 0 errors).
    - PR #6 modified zero lines of code in `settletable.authority` and `settletable.calculation`.
    - Cent/sen conservation, rational fraction apportionments, revision monotonicity, and database atomicity are completely unaffected.
- **Verdict**: **PASS**.

---

## 3. Final Recommendation & Sign-off

- **Audit Recommendation**: **GO (PASS / APPROVED FOR MERGE)**
- All five audit gates have been objectively verified against code, tests, architecture documents, and specifications.
- PR #6 is robust, well-tested, and secure.
