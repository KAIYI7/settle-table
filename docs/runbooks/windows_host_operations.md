# SettleTable — Windows Host Operations & Disaster Recovery Runbook

**Document:** `docs/runbooks/windows_host_operations.md`  
**Target Environment:** Windows 10/11 Desktop / Laptop running Docker Desktop (WSL2 Backend)  
**Gateway:** Cloudflare Named Tunnel (`cloudflared`)  
**Persistent Storage:** Docker Named Volume `settletable_data` (`/data`)  

---

## 1. System Overview & Architecture

SettleTable is deployed as a single-instance containerized service on a self-hosted Windows machine. Ingress is routed through an outbound Cloudflare Named Tunnel, providing an enduring HTTPS endpoint (`https://settle.example.com`) without opening inbound router ports or configuring dynamic DNS.

```
┌────────────────────────────────────────────────────────┐
│               Public Internet / Diners                 │
└──────────────────────────┬─────────────────────────────┘
                           │ HTTPS (443)
                           ▼
┌────────────────────────────────────────────────────────┐
│              Cloudflare Global Edge                    │
└──────────────────────────┬─────────────────────────────┘
                           │ Encrypted Tunnel (Outbound)
                           ▼
┌────────────────────────────────────────────────────────┐
│           Windows Host (Docker Desktop / WSL2)         │
│                                                        │
│  ┌──────────────────────┐    ┌──────────────────────┐  │
│  │  settletable_tunnel  │───>│   settletable_app    │  │
│  │    (cloudflared)     │    │   (Gunicorn WSGI)    │  │
│  └──────────────────────┘    └──────────┬───────────┘  │
│                                         │              │
│                              Persistent Volume /data   │
│                              - settletable.sqlite (WAL)│
│                              - receipt_photos/         │
└────────────────────────────────────────────────────────┘
```

---

## 2. Windows Power & Sleep Management

Because SettleTable runs on a Windows workstation, power management settings must prevent the computer from sleeping during planned dining sessions.

### 2.1 Preventing Sleep During Events

1. **Windows Settings Configuration**:
   - Open **Settings > System > Power & battery > Screen and sleep**.
   - Under **When plugged in, put my device to sleep after**, select **Never**.
   - You may keep display turn-off enabled (e.g. 10 minutes) without affecting Docker or tunnel execution.
2. **Command-Line Sleep Override (Temporary)**:
   - To disable sleep during an active dinner, run an elevated PowerShell or Command Prompt:
     ```cmd
     powercfg /change standby-timeout-ac 0
     ```
   - To restore normal sleep timeout afterward (e.g. 30 minutes):
     ```cmd
     powercfg /change standby-timeout-ac 30
     ```
3. **Microsoft PowerToys Awake**:
   - If installed, right-click the PowerToys Awake tray icon and select **Keep awake indefinitely** or **Keep awake until expiration**.

---

## 3. Docker Desktop Configuration & Lifecycle

### 3.1 Recommended Docker Desktop Settings

1. **Auto-Start on Login**:
   - Open Docker Desktop **Settings > General**.
   - Check **Start Docker Desktop when you log in**.
2. **WSL2 Resource Allocation (`.wslconfig`)**:
   - Sizing should be treated as an adjustable recommendation tailored to the physical host's RAM:
     - For workstations with 16 GB+ RAM, allocating 4 GB and 2 vCPUs provides generous headroom for RapidOCR CPU inference and Gunicorn worker threads.
     - For laptops or machines with 8 GB RAM, 2 GB to 3 GB with swap is sufficient.
   - To configure, create or edit `%USERPROFILE%\.wslconfig` in Windows:
     ```ini
     [wsl2]
     memory=4GB
     processors=2
     swap=2GB
     ```
   - Run `wsl --shutdown` in PowerShell to apply changes.
3. **Container Restart Policy**:
   - The `docker-compose.yml` file configures `restart: unless-stopped` for all services.
   - When Docker Desktop starts upon login, the `settletable_app` container (and `settletable_tunnel` if enabled) starts automatically.

---

## 4. Reboots, Power Loss & Recovery

### 4.1 Crash-Consistency Guarantees

- **SQLite WAL Mode**:
  - The database runs with `PRAGMA journal_mode=WAL` and `busy_timeout=1000`.
  - Uncommitted transactions are automatically rolled back.
  - Committed transactions preserved in the WAL file (`settletable.sqlite-wal`) are safely replayed into the main database by SQLite on next connection opening.
- **Receipt Photos**:
  - Receipt photos are written to `/data/receipt_photos/` and flushed to disk before metadata is committed.
  - Corrupted or partial writes are detected via SHA-256 validation.

### 4.2 Post-Reboot Verification

After Windows restarts and you log in:
1. Allow Docker Desktop 30–60 seconds to initialize WSL2 and start containers.
2. Open PowerShell and verify container status:
   ```powershell
   docker compose ps
   ```
   Expected status:
   - `settletable_app`: `Up (healthy)` (monitored via built-in `HEALTHCHECK` probe against `/healthz`).
   - `settletable_tunnel`: `Up` (running as a daemon; the distroless `cloudflared` image has no health check probe defined).
3. Check the application health probe locally:
   ```powershell
   curl http://127.0.0.1:8000/healthz
   ```
   Expected response: `{"ok":true,"status":"healthy"}`.

---

## 5. Internet Outages & Tunnel Reconnection

### 5.1 Residential Internet Disconnections

- If WAN connectivity drops, `settletable_app` continues running locally without disruption.
- The `cloudflared` tunnel connector detects the connection drop and attempts reconnection with exponential backoff (starting at 1s, doubling up to 300s).
- External diners accessing `https://settle.example.com` during an outage receive a standard Cloudflare error page (Error 502 Bad Gateway or Error 530 Origin DNS error).
- Once residential internet restores:
  - `cloudflared` automatically reconnects to the nearest Cloudflare edge point.
  - Diners refreshing their browsers immediately resume dining collaboration.
  - Active sessions, participants, and allocations remain fully intact.
- No manual restart commands are required.

---

## 6. Consistent Backup & Verified Restore Protocol

To ensure disaster recovery and prevent data loss, follow this procedure for backups and restorations.

### 6.1 Online Quiescent Backup (Application Running)

SettleTable's backup tool acquires an internal write lock (`BEGIN IMMEDIATE`), snapshots the database via `sqlite3.backup()`, verifies photo SHA-256 hashes against database records, and generates a SHA-256 checksummed manifest (note: checksummed for data integrity, not cryptographically signed).

Run from the repository root:
```powershell
# Using a disposable container mounting the persistent volume and host backup directory:
docker compose run --rm -v "<HOST_BACKUP_DIR>:/backups" settletable python tools/backup_restore.py backup --db /data/settletable.sqlite --photos /data/receipt_photos --out-dir /backups
```
*(Note: `--storage-dir` and `--backup-dir` are accepted as aliases).*

### 6.2 Explicit Stopped-Container Backup (Recommended Gold Standard)

To guarantee 100% quiescence with zero in-flight uploads:

1. **Stop the Application**:
   ```powershell
   docker compose stop settletable
   ```
2. **Execute Backup**:
   ```powershell
   docker compose run --rm -v "<HOST_BACKUP_DIR>:/backups" settletable python tools/backup_restore.py backup --db /data/settletable.sqlite --photos /data/receipt_photos --out-dir /backups
   ```
3. **Restart the Application**:
   ```powershell
   docker compose start settletable
   ```

### 6.3 Verified Disaster Recovery / Restore Procedure

> [!CAUTION]
> **Safety Contract**: Restore requires an explicitly stopped application container. The restoration tool enforces `--confirm-stopped`, probes the local `/healthz` endpoint, inspects the Docker daemon, and tests SQLite exclusive locking before proceeding. Never attempt to bypass these safety checks.

1. **Stop the Application Container**:
   ```powershell
   docker compose stop settletable
   ```
2. **Confirm Application is Stopped**:
   ```powershell
   docker compose ps
   ```
   Ensure `settletable_app` is `Exited`.
3. **Execute Verified Staged Restore**:
   ```powershell
   docker compose run --rm -v "<HOST_BACKUP_DIR>:/backups" settletable python tools/backup_restore.py restore --manifest /backups/<MANIFEST_FILE_OR_DIR> --dest-db /data/settletable.sqlite --dest-photos /data/receipt_photos --confirm-stopped
   ```
   *(Note: `--manifest` accepts either the direct manifest JSON file path e.g. `/backups/manifest_20261106_070457Z.json` or the backup directory containing it).*

   *What happens during verified restore:*
   - **Pre-flight verification**: Checks manifest checksums, database `PRAGMA integrity_check;`, and photo SHA-256 hashes before touching live files.
   - **Isolated staging**: Stages files into `/data/.restore_staging_{uuid}`.
   - **Pre-restore archive**: Moves current dataset and WAL files into `/data/.pre_restore_archive_{uuid}`.
   - **Controlled cutover**: Moves staged files into production locations and re-verifies integrity.
   - **Automated rollback**: If cutover verification fails for any reason, the previous dataset is automatically restored from the pre-restore archive without data destruction.
4. **Restart the Application**:
   ```powershell
   docker compose start settletable
   ```
5. **Run Deployment Smoke Checks**:
   ```powershell
   python tools/deployment_smoke_check.py --url http://127.0.0.1:8000
   ```

---

## 7. Emergency Troubleshooting & Operational Cheatsheet

| Task | Command | Expected Outcome |
|---|---|---|
| **Check container status** | `docker compose ps` | `settletable_app: Up (healthy)`; `settletable_tunnel: Up` |
| **Inspect application logs** | `docker compose logs -f settletable` | Gunicorn access & error logs (tokens redacted) |
| **Inspect tunnel logs** | `docker compose logs -f cloudflared` | Cloudflare connection registration logs |
| **Test local health** | `curl -i http://127.0.0.1:8000/healthz` | HTTP 200 `{"ok":true,"status":"healthy"}` |
| **Test public tunnel ingress** | `curl -i https://settle.example.com/healthz` | HTTP 200 `{"ok":true,"status":"healthy"}` |
| **Run deployment smoke check** | `python tools/deployment_smoke_check.py` | 11/11 smoke checks pass |
| **Administrative bootstrap meal** | `docker compose exec settletable python tools/bootstrap_meal.py bootstrap --meal-id <id>` | Prints single-use organizer setup link |
| **Emergency organizer recovery** | `docker compose exec settletable python tools/bootstrap_meal.py recover --meal-id <id>` | Prints fresh organizer recovery link |
| **Restart application service** | `docker compose restart settletable` | Service restarts cleanly |
| **Restart tunnel service** | `docker compose restart cloudflared` | Tunnel reconnects to edge |

---

## 8. Connector Token Security & Pre-Activation Verification

### 8.1 Tunnel Token Confidentiality
The `CLOUDFLARE_TUNNEL_TOKEN` stored in `.env` grants authoritative ingress routing to your Cloudflare Tunnel:
- Restrict read permissions on `.env` in Windows (Right-click `.env` > Properties > Security > ensure only your user account has Read/Write permissions).
- `.env` is listed in `.gitignore` and must never be committed to source control.

### 8.2 Pre-Activation Verification Scope
- **Docker Compose validation** (`docker compose config`): Confirms service syntax, volume declarations, and local port bindings, but does **not** test remote Cloudflare network connectivity.
- **Application Host Header Filtering**: SettleTable enforces `SETTLETABLE_ALLOWED_HOSTS` inside Python WSGI as defense-in-depth. In live deployment, Cloudflare's edge catch-all 404 rule provides additional boundary protection.
- Before inviting diners to a live dining event, always execute the deployment smoke test against the live public domain:
  ```powershell
  python tools/deployment_smoke_check.py --url https://settle.example.com
  ```
