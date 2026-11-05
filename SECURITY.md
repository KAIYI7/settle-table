# Security Policy & Architecture Boundaries

## 1. Reporting a Vulnerability

Security and privacy are core architectural priorities of SettleTable. If you discover a vulnerability, security flaw, or potential credential leak:

- **Do NOT** open a public GitHub issue.
- Please report vulnerabilities privately by emailing the repository owner directly or via GitHub Private Vulnerability Reporting.
- Include a detailed description of the vulnerability, reproduction steps or curl commands, and affected environment.
- We will acknowledge receipt within 48 hours and coordinate a fix and advisory.

---

## 2. Threat Model & Two-Tier Ingress Architecture

SettleTable enforces a strict two-tier security boundary between the untrusted public Internet and the authoritative core application:

```
[ Untrusted Client ]
         │
         │  (Raw TCP / TLS / HTTP Stream)
         ▼
┌────────────────────────────────────────────────────────┐
│ TIER 1: Ingress / Reverse Proxy (e.g. Caddy, Nginx)   │
│ - Raw wire buffer bounds (Slowloris stream defense)    │
│ - TLS termination & HSTS                               │
│ - Ingress request line & header buffer limits          │
│ - Route-level access controls: BLOCK /bootstrap        │
└────────────────────────────────────────────────────────┘
         │
         │  (Local socket / Loopback HTTP / WSGI pipe)
         ▼
┌────────────────────────────────────────────────────────┐
│ TIER 2: SettleTable WSGI App (settletable.transport)   │
│ - Defense-in-depth on parsed WSGI environ              │
│ - Strict JSON grammar (no duplicates, no floats)       │
│ - CSRF mitigation (X-SettleTable-Action, Origin check) │
│ - Loopback proxy-header rejection on /bootstrap        │
│ - Credential segregation (HttpOnly cookies vs Bearer)  │
│ - Deterministic state machine & SQLite WAL authority   │
└────────────────────────────────────────────────────────┘
```

### 2.1 Defense-in-Depth Invariants

1. **Exact-Origin CSRF Mitigation**:
   All state-mutating requests (`POST`, `DELETE`) require the custom header `X-SettleTable-Action: 1`. In browser contexts, the `Origin` (or `Referer`) header must match `server_origin` exactly. Sandboxed iframes (`Origin: null`) and cross-site requests are rejected with HTTP 403.

2. **Loopback-Only Meal Provisioning**:
   `POST /api/meals/{meal_id}/bootstrap` is strictly restricted to local loopback calls (`127.0.0.1`, `::1`). If **any** proxy forwarding headers (`X-Forwarded-For`, `X-Forwarded-Proto`, etc.) are detected, the request is immediately rejected with HTTP 403 Forbidden. External clients cannot provision arbitrary meal rooms over the Internet.

3. **Credential Segregation & XSS Immunity**:
   Browser sessions are stored exclusively in `HttpOnly; Secure; SameSite=Strict; Path=/` cookies (`settletable_session`). When an organizer or diner rotates or renews their session, the credential is provided strictly via the `Set-Cookie` header and **never** returned in JSON response bodies to prevent JavaScript DOM exfiltration.

4. **Zero-Float Financial Math**:
   All monetary amounts are represented as exact integers in minor units (Malaysian `sen`). Fractional item portions use rational fractions (numerator/denominator). Floating-point parsing is rejected at the JSON parser level (`parse_float` raises an error).

5. **Log Redaction**:
   All session tokens, invitation tokens, join tokens, Bearer headers, and Notion API secrets are automatically scrubbed by `redact_log_string` before being written to standard output or server logs.

6. **Air-Gapped Local OCR**:
   Optical character recognition runs strictly on the host server CPU using RapidOCR with ONNX Runtime. SettleTable makes **zero** third-party cloud vision API calls, and uploaded receipt images never leave the host server.

---

## 3. Operational Requirements for Hosted Deployments

To maintain these security guarantees in a hosted environment:
- **Always deploy behind Tier 1**: Never expose the raw Python WSGI server or port 8000 directly to the public Internet without an ingress reverse proxy (Caddy or Nginx).
- **Configure Public Origin**: Explicitly set `SETTLETABLE_SERVER_ORIGIN` and `SETTLETABLE_ALLOWED_HOSTS` to your public HTTPS domain in the production environment.
- **Maintain Ingress Block on Bootstrap**: Ensure your reverse proxy configuration explicitly blocks external traffic to `/api/meals/*/bootstrap`.
