# SettleTable — Cloudflare Named Tunnel Deployment Guide

This directory contains configuration templates and architectural guidance for deploying SettleTable behind a **Cloudflare Named Tunnel (`cloudflared`)** on a self-hosted Windows machine running Docker Desktop.

> [!IMPORTANT]
> **Stage B Offline Status**: No external tunnel is active, no credentials are created, and no domain is configured. These templates are offline references. Real external activation strictly requires explicit Product Owner authorization.

---

## 1. Architectural Strategy & Management Mode

Cloudflare Tunnels can be managed in two ways:

### Mode 1: Remotely Managed Tunnels (RECOMMENDED)

In a remotely managed tunnel, the tunnel, public hostnames, and ingress routing rules are defined in the **Cloudflare Zero Trust Dashboard** (under *Networks > Tunnels*). The local connector simply runs with an authentication token:

```sh
cloudflared tunnel --no-autoupdate run --token <TUNNEL_TOKEN>
```

**Why this is recommended for SettleTable:**
- **Zero local secrets in repo**: No credentials JSON file (`<UUID>.json`) or local certificate files to mount into containers or risk committing to Git. (Note: the `CLOUDFLARE_TUNNEL_TOKEN` stored in `.env` remains sensitive and must be protected on the local host with restricted file permissions).
- **Single source of truth**: Public hostnames (e.g. `settle.example.com`) and ingress targets are defined centrally on Cloudflare's edge.
- **Dynamic reconfiguration**: DNS routing and ingress targets can be updated in the dashboard without editing local files or restarting Docker containers.
- **Reproducible Docker Compose integration**: Pinned by version tag and multi-arch manifest list digest `cloudflare/cloudflared:2026.10.7@sha256:4955524aeaa379e154023d5a027c250f7b35041a2e7e950cf13f144bc9b9c5ba` covering both `linux/amd64` and `linux/arm64`. Pass `CLOUDFLARE_TUNNEL_TOKEN` in `.env` and start the connector container using `docker compose --profile with-cloudflared up -d`.

### Mode 2: Locally Managed Tunnels (ALTERNATIVE)

In a locally managed tunnel, routing is defined in a local YAML configuration file (`config.yml`), referencing a downloaded credentials JSON file:

- Configuration template: [`config.template.yml`](config.template.yml)
- Requires running CLI `cloudflared tunnel create <name>` and `cloudflared tunnel route dns <name> <hostname>`.
- In Docker Compose, the configuration and credentials files must be mounted into `/home/nonroot/.cloudflared/` inside the container.

*Drawbacks*: Introduces two competing sources of truth (local `config.yml` vs Cloudflare DNS), risks credentials file exposure on the host filesystem, and complicates container volume mounting on Windows.

---

## 2. Connector Topologies

### Topology A: Docker Compose Network (RECOMMENDED)

Both SettleTable and `cloudflared` run as container services on the same Docker bridge network (`tabwise_default`):

```
[ Internet / Diners ]
        │ HTTPS (443)
        ▼
[ Cloudflare Global Edge ]
        │ Encrypted Tunnel (Outbound QUIC/HTTP2)
        ▼
[ Host Windows Machine (Docker Desktop) ]
   └── Container: settletable_tunnel (cloudflared)
            │ Internal HTTP (8000)
            ▼
       Container: settletable_app (Gunicorn WSGI)
            └── SQLite WAL + Receipt Photos (/data)
```

- In the Cloudflare Zero Trust dashboard, set the ingress service URL to:  
  `http://settletable:8000`
- The `settletable_app` container port `8000` remains bound to `127.0.0.1:8000` on the Windows host exclusively for local operator health probes and administrative bootstrap CLI commands.
- External internet traffic never touches the host's physical network adapter directly; all traffic flows through the encrypted tunnel into Docker.

### Topology B: Native Windows Service (ALTERNATIVE)

If you prefer not to run `cloudflared` in Docker, `cloudflared.exe` can be installed directly on Windows and registered as a native Windows Service:

```powershell
# In an elevated PowerShell prompt:
cloudflared.exe service install <TUNNEL_TOKEN>
Start-Service cloudflared
```

- In this topology, set the ingress service URL to:  
  `http://127.0.0.1:8000`
- `settletable_app` must keep port `127.0.0.1:8000:8000` published so the Windows service can reach it.

---

## 3. Application Security & Invariants

When SettleTable is published via a Cloudflare Named Tunnel:

1. **Zero Cloudflare Access Friction**:
   - **Cloudflare Access MUST NOT be enabled.**
   - Diners join meals directly via standard mobile and desktop browsers without installing VPN clients, creating third-party accounts, or entering email OTP codes.
2. **Authoritative Application Security**:
   - SettleTable's built-in authorization model is authoritative:
     - Meals require unguessable 43-character invitation tokens or organizer join approvals.
     - Organizers claim sessions via secure single-use claim tokens.
     - Browser sessions are protected by `HttpOnly; SameSite=Strict; Path=/; Secure` cookies.
3. **Loopback Bootstrap Protection**:
   - `POST /api/meals/{meal_id}/bootstrap` enforces loopback access.
   - If ANY reverse proxy forwarding headers are detected (`CF-Connecting-IP`, `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `True-Client-IP`), the endpoint immediately aborts with `403 Forbidden`. External callers cannot create or bootstrap meals.
4. **Exact-Origin CSRF Protection & Host Enforcement**:
   - Mutating requests (`POST`, `DELETE`) require `X-SettleTable-Action: 1` and exact origin matching against `SETTLETABLE_SERVER_ORIGIN` (`https://settle.example.com`).
   - SettleTable enforces `SETTLETABLE_ALLOWED_HOSTS` inside Python WSGI as application defense-in-depth, rejecting foreign Host headers with HTTP 400 `invalid_host`. In live deployment, Cloudflare's edge catch-all 404 rule provides additional boundary defense.
5. **No Intermediate Caching**:
   - Dynamic API responses return `Cache-Control: no-store`.
   - Receipt photos return `Cache-Control: private, no-cache, no-store, must-revalidate`.
   - Responses are never cached on Cloudflare's shared edge network.

---

## 4. Configuration Steps (For Future Authorized Live Deployment)

When the Product Owner authorizes purchasing a domain and activating the pilot:

1. **Domain Setup**:
   - Purchase or assign a domain (e.g. `example.com`) and delegate nameservers to Cloudflare.
2. **Create Named Tunnel**:
   - In Cloudflare Zero Trust dashboard: **Networks > Tunnels > Add a tunnel**.
   - Select **Cloudflared**. Name the tunnel (e.g. `settletable-prod`).
3. **Configure Public Hostname**:
   - Subdomain: `settle`
   - Domain: `example.com` (FQDN: `settle.example.com`)
   - Service Type: `HTTP`
   - URL: `settletable:8000` (for Docker Compose Topology A)
4. **Set Environment Variables**:
   - Copy `deploy/env.template` to `.env`.
   - Set:
     ```env
     SETTLETABLE_SERVER_ORIGIN=https://settle.example.com
     SETTLETABLE_ALLOWED_HOSTS=settle.example.com,localhost:8000,127.0.0.1:8000,settletable:8000
     CLOUDFLARE_TUNNEL_TOKEN=<token_from_cloudflare_dashboard>
     ```
5. **Start Services**:
   ```sh
   docker compose --profile with-cloudflared up -d
   ```
6. **Verify Ingress**:
   - Run deployment smoke checks:
     ```sh
     python tools/deployment_smoke_check.py --url https://settle.example.com
     ```
