# SettleTable Deployment & Ingress Boundary Architecture

**Date:** 2026-10-20  
**Status:** Accepted Architecture Specification  
**Component:** `settletable.transport` & Deployment Boundary  

---

## 1. Overview & Two-Tier Security Boundary

SettleTable enforces a strict two-tier security boundary. Application-level Python/WSGI checks and ingress-level reverse proxy policies have distinct responsibilities:

```
[ Untrusted Client ]
         │
         │  (Raw TCP / TLS / HTTP Stream)
         ▼
┌────────────────────────────────────────────────────────┐
│ TIER 1: Ingress / Reverse Proxy (e.g. Nginx, Caddy)   │
│ - Raw wire buffer bounds (TCP stream protection)       │
│ - TLS termination & HSTS                               │
│ - Ingress request line & header buffer limits          │
│ - Route-level access controls (blocking /bootstrap)    │
└────────────────────────────────────────────────────────┘
         │
         │  (Local socket / Loopback HTTP / WSGI pipe)
         ▼
┌────────────────────────────────────────────────────────┐
│ TIER 2: SettleTable WSGI App (settletable.transport)   │
│ - Defense-in-depth on parsed WSGI environ              │
│ - Strict JSON grammar (no duplicates, no floats)       │
│ - CSRF mitigation (X-SettleTable-Action, Origin check) │
│ - Loopback proxy-header rejection                      │
│ - Credential segregation (HttpOnly cookies vs Bearer)  │
│ - Deterministic state machine & Authority transactions │
└────────────────────────────────────────────────────────┘
```

---

## 2. Ingress vs. WSGI Boundary Demarcation

### Why WSGI Header Checks Cannot Prove Raw-Wire Enforcement
In a standard WSGI environment, the WSGI server (Gunicorn, uWSGI, Waitress, wsgiref) or upstream reverse proxy reads and parses the raw TCP stream *before* populating the Python `environ` dictionary:
- If a malicious client sends 50 MB of raw header data across thousands of fragmented TCP packets (e.g., Slowloris), the WSGI server buffer may exhaust memory or stall *before* `SettleTableApp.__call__` is invoked.
- Application-level header limits in `SettleTableApp._dispatch` (single line $\le 4\text{ KB}$, total headers $\le 16\text{ KB}$) operate on already-parsed WSGI dictionary strings as **defense-in-depth**, not as a substitute for ingress TCP stream bounding.
- **Production Requirement:** An ingress reverse proxy MUST enforce stream buffer limits before requests reach the WSGI server.

---

## 3. Threat Model & Mitigations

### 3.1 Proxy-Mediated Loopback Bypass on `/bootstrap`
- **Threat:** SettleTable restricts meal bootstrap (`POST /api/meals/{meal_id}/bootstrap`) to loopback (`REMOTE_ADDR in ('127.0.0.1', '::1', 'localhost')`). When deployed behind a reverse proxy or tunnel running on the same host, the proxy connects to the WSGI backend over loopback. If the reverse proxy exposes `/api/meals/{meal_id}/bootstrap` to the public Internet, `REMOTE_ADDR` would appear as `127.0.0.1`, allowing unauthorized remote provisioning.
- **Application Mitigation:** `SettleTableApp` inspects incoming headers for proxy indicators (`X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `Forwarded`, `X-Real-IP`). If *any* proxy forwarding header is present on `/bootstrap`, the request is rejected with `403 Forbidden`.
- **Ingress Mitigation:** Reverse proxy configurations MUST explicitly block external access to `/api/meals/*/bootstrap` or restrict it to internal management IPs.

### 3.2 Credential Exposure at Provisioning
- **Threat:** If bootstrap returns session credentials for all predeclared diners in its HTTP response body, the entity bootstrapping the meal possesses raw bearer access for every diner, bypassing the invitation lifecycle and risking credential interception.
- **Application Mitigation:** `POST /api/meals/{meal_id}/bootstrap` returns credentials **strictly for the organizer**. Non-organizer diners are never assigned pre-minted credentials in HTTP responses; they MUST be enrolled via explicit invitations (`POST /api/meals/{meal_id}/invitations` -> `POST /api/meals/{meal_id}/invitations/{token}/redeem`).

### 3.3 Session Rotation & Cookie Credential Hygiene
- **Threat:** When a browser client authenticated via an `HttpOnly` cookie rotates its session, returning the new raw credential in the JSON response body exposes the token to JavaScript memory and DOM inspection, completely undermining `HttpOnly` protection against XSS exfiltration.
- **Application Mitigation:**
  - If a request is authenticated via cookie (`settletable_session`), the rotated credential is provided **strictly via the `Set-Cookie` header** (`HttpOnly; Secure; SameSite=Strict; Path=/`). The JSON response body contains `{"ok": true, "participant_id": "..."}` without the raw token.
  - Raw credentials in JSON are returned **only** when the caller authenticated programmatically via `Authorization: Bearer <cred>`.

---

## 4. Recommended Ingress Configuration (Nginx Reference)

```nginx
# Recommended Tier 1 Ingress Configuration for SettleTable
server {
    listen 443 ssl http2;
    server_name settletable.internal;

    # Wire limits (Raw TCP stream protection)
    client_max_body_size 1M;
    large_client_header_buffers 4 4k;
    client_header_timeout 10s;
    client_body_timeout 10s;

    # Block external access to bootstrap endpoint
    location ~* ^/api/meals/[^/]+/bootstrap$ {
        # Allow only administrative local subnet
        allow 127.0.0.1;
        allow ::1;
        deny all;

        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    # Public application traffic
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
