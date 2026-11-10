# SettleTable — Windows Host Operations & Disaster Recovery Runbook

**Document:** `docs/runbooks/windows_host_operations.md`  
**Target Environment:** Windows 10/11 Desktop / Laptop running Docker Desktop (WSL2 Backend)  
**Gateway:** Cloudflare Named Tunnel (`cloudflared`)  
**Persistent Storage:** Docker Named Volume `settletable_data` (`/data`)  

---

## 1. System Overview & Architecture

SettleTable is deployed as a single-instance containerized service on a self-hosted Windows machine. Ingress is routed through an outbound Cloudflare Named Tunnel, providing an enduring HTTPS endpoint (`https://settle.kybuilds.com`) without opening inbound router ports or configuring dynamic DNS.

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

### 1.1 Practical Deployment Lifecycle

To balance security, operational control, and low-maintenance availability, SettleTable follows a two-phase deployment lifecycle:

1. **Phase 1: First Real Dining Session (Supervised, On-Demand Activation)**:
   - For the inaugural meal with real invited friends and actual restaurant receipts, launch the stack explicitly before the dining event:
     ```powershell
     docker compose --profile with-cloudflared up -d
     ```
   - Supervise the session: monitor container logs (`docker compose logs -f`), observe RapidOCR processing on real physical receipts, and verify that invited diners join without issues.
   - At the conclusion of the meal, execute an explicit stopped backup to both local and off-host storage before shutting down or keeping the service active.
2. **Phase 2: Post-First-Meal Transition (Mostly-Available Operation with Auto-Restart)**:
   - Following successful initial validation, leave the stack running continuously with `restart: unless-stopped`.
   - Configure Docker Desktop to auto-start upon Windows login.
   - Host downtime (e.g., occasional computer reboots, sleep mode when laptop is unplugged, home router reconnects) is fully acceptable:
     - The SQLite WAL database guarantees zero transaction corruption across sudden power-off or reboots.
     - Session TTLs (7 days / 604,800 seconds) ensure active sessions remain valid across host downtime.
     - The Cloudflare connector automatically reconnects to Cloudflare edge nodes upon internet restoration without manual intervention.

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
- External diners accessing `https://settle.kybuilds.com` during an outage receive a standard Cloudflare error page (Error 502 Bad Gateway or Error 530 Origin DNS error).
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
# Note: In PowerShell, wrap variable names in braces before a colon (e.g. "${hostBackupDir}:/backups")
docker compose run --rm -v "${hostBackupDir}:/backups" settletable python tools/backup_restore.py backup --db /data/settletable.sqlite --photos /data/receipt_photos --out-dir /backups
if ($LASTEXITCODE -ne 0) { throw "Quiescent backup generation failed!" }
```
*(Note: `--storage-dir` and `--backup-dir` are accepted as aliases).*

#### 6.1.1 Offsite / Cloud-Synced Secondary Backup

To guarantee resilience against local SSD or workstation failure, pass `--copy-to` (or `--offsite-dir`) pointing to a secondary drive (e.g. secondary external drive, USB disk, or network share) or a cloud-synced folder (e.g. OneDrive, Google Drive, Dropbox):

```powershell
# Backup with automatic offsite mirror and hash verification:
docker compose run --rm -v "${hostBackupDir}:/backups" -v "${hostOffsiteDir}:/offsite" settletable python tools/backup_restore.py backup --db /data/settletable.sqlite --photos /data/receipt_photos --out-dir /backups --copy-to /offsite
if ($LASTEXITCODE -ne 0) { throw "Offsite backup failed!" }
```
The utility automatically:
1. Snapshots the database under a write quiescence lock (`BEGIN IMMEDIATE`).
2. Verifies and copies all referenced receipt photo assets.
3. Generates the checksummed `manifest_<timestamp>.json`.
4. Copies the database, photos, and manifest to the offsite directory.
5. Verifies that the offsite database and photos match the manifest SHA-256 hashes.

#### 6.1.2 Local Copy Completion vs Remote Cloud Synchronization

When using a cloud-synced directory (e.g. `<HOST_OFFSITE_DIR>` mapped to a Windows OneDrive or Google Drive folder):
- **Local write and verification**: The `backup_restore.py` CLI copies the snapshot files to the designated folder and verifies SHA-256 hashes against the local filesystem.
- **Asynchronous cloud sync**: Docker and Python complete their operations as soon as the files are written locally. However, actual durability against workstation loss depends on the host cloud sync client uploading the files to remote storage.
- **Verification action**: Always check the cloud sync client icon in the Windows notification area (system tray) to confirm synchronization is finished (e.g. status displays "Up to date" or green checkmark) before powering off or disconnecting the host machine.

#### 6.1.3 Data Confidentiality & Storage Protection

Real dining receipts, itemized participant selections, and financial settlements contain personal and financial information:
- **Host filesystem permissions**: Restrict NTFS permissions on `<HOST_BACKUP_DIR>` and `<HOST_OFFSITE_DIR>` so that only the operator's Windows account and Docker daemon service account have read/write access.
- **Drive encryption**: Enable Windows BitLocker Drive Encryption on the primary OS volume and any external backup drives to guard against physical device theft or loss.
- **Cloud storage security**: Ensure the destination cloud storage account (OneDrive, Google Drive, etc.) enforces multi-factor authentication (MFA/2FA) and that backup directories are never configured with public or anonymous sharing links.

#### 6.1.4 Pristine Database Initialization Before Baseline Backup

On a completely fresh persistent volume (such as `settletable_data` prior to the first dining event), the SQLite database file does not yet exist. Attempting to run `backup_restore.py backup` on an uninitialized volume will fail with `FileNotFoundError: Source database does not exist: /data/settletable.sqlite`.

To safely establish the initial schema and `.volume_identity` marker without opening public ingress or starting the web service:
```powershell
docker compose run --rm settletable python tools/bootstrap_meal.py init-db --db /data/settletable.sqlite
```
This initializes the database schema, enables WAL mode, and stamps the volume identity marker in isolation, allowing the baseline quiescent backup to succeed.

#### 6.1.5 Encrypted Cloud Mirroring with 7-Zip (Google Drive / Cloud Storage)

For real dining events, backups contain sensitive receipts, participant names, and settlement figures. To protect data privacy when mirroring to third-party cloud storage (such as Google Drive streamed virtual drive):

1. **Local Quiescence First**: SettleTable generates the snapshot and manifest on local NTFS storage first (`${hostBackupDir}`). Live SQLite WAL files are never synchronized directly to the cloud. Always verify the exit code:
   ```powershell
   docker compose run --rm -v "${hostBackupDir}:/backups" settletable python tools/backup_restore.py backup --db /data/settletable.sqlite --photos /data/receipt_photos --out-dir /backups
   if ($LASTEXITCODE -ne 0) { throw "Quiescent backup generation failed!" }
   ```
2. **Strict Single-Snapshot Scoping & Timestamp Extraction**: SettleTable's `backup_restore.py` generates its own UTC timestamp internally (`YYYYMMDD_HHMMSSZ`). Do not guess or generate a separate host timestamp. Obtain the exact snapshot timestamp directly from the generated manifest, and verify that the manifest, SQLite file, and receipt-photo directory strictly belong to that same snapshot before archiving:
   ```powershell
   # Preserve repository working directory and enter snapshot directory:
   Push-Location -LiteralPath "$hostBackupDir"
   try {
       # Extract the exact timestamp from the newly generated manifest:
       $manifestFile = (Get-ChildItem -Filter "manifest_*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1)
       if (-not $manifestFile) { throw "No backup manifest found in $hostBackupDir!" }
       if ($manifestFile.BaseName -match '^manifest_(.+)$') {
           $timestamp = $Matches[1]
       } else {
           throw "Manifest filename '$($manifestFile.Name)' does not match expected pattern 'manifest_<timestamp>.json'!"
       }

       # Verify tripartite snapshot integrity and manifest alignment before archiving:
       $manifestData = Get-Content $manifestFile.FullName -Raw | ConvertFrom-Json
       $expectedDb = "settletable_${timestamp}.sqlite"
       $expectedPhotos = "receipt_photos_${timestamp}"

       if ($manifestData.database.filename -ne $expectedDb -or -not (Test-Path -LiteralPath $expectedDb)) {
           throw "Snapshot database mismatch: expected '$expectedDb' on disk and in manifest!"
       }
       if ($manifestData.receipt_photos_dir -ne $expectedPhotos -or -not (Test-Path -LiteralPath $expectedPhotos)) {
           throw "Snapshot photos mismatch: expected '$expectedPhotos' on disk and in manifest!"
       }

       $archivePath = "${archiveDir}\settletable_backup_${timestamp}.7z"
       if (Test-Path -LiteralPath $archivePath) {
           throw "Target archive '$archivePath' already exists! Aborting to prevent overwrite."
       }

       # 3. Create encrypted archive with header encryption (file names, sizes, structure encrypted):
       # Note: The archive path MUST precede the input files in 7-Zip command syntax:
       & "<7Z_PATH>" a -t7z -mhe=on -p "$archivePath" "manifest_${timestamp}.json" "settletable_${timestamp}.sqlite" "receipt_photos_${timestamp}"
       if ($LASTEXITCODE -ne 0) { throw "7-Zip encrypted archive creation failed with exit code $LASTEXITCODE!" }

       # 4. Verify archive integrity:
       & "<7Z_PATH>" t -p "$archivePath"
       if ($LASTEXITCODE -ne 0) { throw "7-Zip archive integrity verification failed with exit code $LASTEXITCODE!" }
   } finally {
       Pop-Location
   }
   ```
   *Security Note on Passphrase*: Passing `-p` without an inline password instructs 7-Zip to securely prompt for the passphrase interactively on console (`Enter password (will not be echoed)`). The passphrase is never exposed in process arguments, logs, scripts, `.env`, or git history.
5. **Copy to Google Drive & Validate Hash**:
   The approved host Google Drive destination is `<GDRIVE_BACKUPS_DIR>` (located on the host at Google Drive `My Drive\SettleTable\backups`; strictly do not use `SettleTable_Backups`).
   The established local backup location is `.local\backups` within the repository root (do not create parallel backup directories).
   *Caution*: Never overwrite `settletable_backup_20261108_123746Z.7z` (the first real-meal backup).
   ```powershell
   # Ensure $gdriveBackupsDir is configured to your host's Google Drive 'My Drive\SettleTable\backups'
   if (-not $gdriveBackupsDir -or -not (Test-Path -LiteralPath $gdriveBackupsDir)) {
       throw "Approved Google Drive backup directory not accessible: $gdriveBackupsDir"
   }

   $sourceArchive = Join-Path $archiveDir "settletable_backup_${timestamp}.7z"
   $destArchive = Join-Path $gdriveBackupsDir "settletable_backup_${timestamp}.7z"

   # Safety check: prevent overwriting any existing backup (including inaugural real-meal archive):
   if (Test-Path -LiteralPath $destArchive) {
       throw "Destination archive already exists in Google Drive: $destArchive. Aborting to prevent overwrite."
   }

   # Copy using cmdlet error-handling (-ErrorAction Stop):
   Copy-Item -LiteralPath $sourceArchive -Destination $destArchive -ErrorAction Stop

   # Verify bit-for-bit SHA-256 match between local archive and Google Drive copy:
   $sourceHash = (Get-FileHash -LiteralPath $sourceArchive -Algorithm SHA256).Hash
   $destHash = (Get-FileHash -LiteralPath $destArchive -Algorithm SHA256).Hash
   if ($sourceHash -ne $destHash) {
       throw "SHA-256 verification failed between local archive ($sourceHash) and Google Drive copy ($destHash)!"
   }
   Write-Host "Archive copy verified matching SHA-256: $destHash" -ForegroundColor Green
   ```
6. **Distinguish Local Filesystem Copying from Verified Remote Cloud Upload**:
   - **Local Cache Copy (Virtual Mount Drive)**: `Copy-Item` copies the archive into the local DriveFS cache on Windows. Local readback or SHA-256 calculation confirms only that the file was written to the local cache. While in transit, DriveFS assigns a transient identifier (`local-*`), which is **not** evidence of cloud durability.
   - **Verified Remote Cloud Upload**: Durability in Google's cloud is confirmed only when:
     1. Google Drive for desktop finishes the upload and the taskbar notification area displays "Everything is up to date" (or DriveFS operations queue has 0 pending tasks).
     2. Google Drive replaces the transient `local-*` identifier with a permanent cloud resource ID in DriveFS metadata.
     3. The file is visible in the Google Drive web interface at `https://drive.google.com`.

### 6.2 Explicit Stopped-Container Backup (Recommended Gold Standard)

To guarantee 100% quiescence with zero in-flight uploads:

1. **Stop the Application**:
   ```powershell
   docker compose stop settletable
   ```
2. **Execute Backup**:
   ```powershell
   docker compose run --rm -v "${hostBackupDir}:/backups" settletable python tools/backup_restore.py backup --db /data/settletable.sqlite --photos /data/receipt_photos --out-dir /backups
   if ($LASTEXITCODE -ne 0) { throw "Stopped-container backup failed!" }
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
   docker compose run --rm -v "${hostBackupDir}:/backups" settletable python tools/backup_restore.py restore --manifest /backups/<MANIFEST_FILE_OR_DIR> --dest-db /data/settletable.sqlite --dest-photos /data/receipt_photos --confirm-stopped
   if ($LASTEXITCODE -ne 0) { throw "Restore verification failed!" }
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

#### 6.3.1 Restoring from an Encrypted Cloud Archive

If restoring from Google Drive or offsite encrypted cloud storage:
1. **Retrieve Cloud Archive**: Copy `settletable_backup_${timestamp}.7z` from `<GDRIVE_BACKUPS_DIR>` to a clean local staging directory: `$stagingDir`.
2. **Decrypt with 7-Zip**:
   ```powershell
   & "<7Z_PATH>" x -p "${stagingDir}\settletable_backup_${timestamp}.7z" -o"${decryptedDir}" -y
   if ($LASTEXITCODE -ne 0) { throw "7-Zip archive decryption failed!" }
   ```
   *(Enter your master passphrase when prompted; files are decrypted into `${decryptedDir}` with original directory structure).*
3. **Execute Verified Restore (with Proper PowerShell Bind-Mount Interpolation)**:
   > [!IMPORTANT]
   > In PowerShell, always wrap variable names in braces when immediately followed by a colon (e.g. `"${decryptedDir}:/backups"` rather than `"$decryptedDir:/backups"`) to prevent PowerShell from misinterpreting the colon as a drive-scope qualifier.
   ```powershell
   docker compose run --rm -v "${decryptedDir}:/backups" settletable python tools/backup_restore.py restore --manifest /backups/manifest_${timestamp}.json --dest-db /data/settletable.sqlite --dest-photos /data/receipt_photos --confirm-stopped
   if ($LASTEXITCODE -ne 0) { throw "Disaster recovery restore verification failed!" }
   ```
4. **Restart & Smoke Check**:
   ```powershell
   docker compose start settletable
   python tools/deployment_smoke_check.py --url http://127.0.0.1:8000
   ```

### 6.4 Storage Volume Isolation & Cross-Contamination Guard

SettleTable maintains strict physical volume isolation between synthetic test runs and real dining sessions:

- **`settletable_synthetic_data`**: Isolated volume used for automated test suites, CI drills, and synthetic rehearsals.
- **`settletable_data`**: Authoritative persistent volume reserved exclusively for real dining sessions and real receipts.

#### 6.4.1 In-Container Volume Identity Marker (`.volume_identity`)
To eliminate the risk of accidental volume selection (e.g. accidentally running a real dinner against the synthetic volume or running tests against the production volume):
- SettleTable writes a persistent marker `/data/.volume_identity` on initial startup recording the intended volume name.
- On subsequent startups, `settletable_app` compares `SETTLETABLE_DATA_VOLUME` against the on-disk marker.
- If a mismatch is detected, the container immediately aborts startup with a `RuntimeError` to prevent cross-volume contamination.

#### 6.4.2 Pre-Flight Volume Target Verification
Before starting containers or performing cutovers, always execute the volume verification tool:
```powershell
# Check current configuration in auto mode:
python tools/verify_volume_target.py

# Verify readiness for real-data production pilot:
python tools/verify_volume_target.py --mode real

# Verify readiness for synthetic rehearsal:
python tools/verify_volume_target.py --mode synthetic
```

#### 6.4.3 Protection Against Accidental Volume Deletion
- **NEVER** run `docker compose down -v` or `docker volume prune -f` in production. The `-v` flag instructs Docker to permanently delete persistent volumes.
- To safely stop the application without touching volumes, use `docker compose stop` or `docker compose down` (without `-v`).

### 6.5 Safe Production Application Image Rebuild & Schema Upgrade Procedure

When upgrading the production container to a newer reviewed checkpoint that includes schema migrations or code changes:

> [!IMPORTANT]
> **Controller Build Semantics**: `docker compose up -d settletable` and `.\tools\SettleTable-Control.ps1 start-local` reuse the locally tagged image `settletable:latest` and **do not automatically rebuild** when source files change. An explicit image rebuild is mandatory.

#### Step 1: Pre-Upgrade Quiescent Backup & Google Drive Durability

0. **Preserve and Verify Working Directory**:
   Ensure all operations originate from the SettleTable repository root:
   ```powershell
   $repoRoot = (Get-Location).Path
   if (-not (Test-Path -LiteralPath (Join-Path $repoRoot "tools\SettleTable-Control.cmd"))) {
       throw "Current working directory '$repoRoot' is not the SettleTable repository root!"
   }
   $hostBackupDir = Join-Path $repoRoot ".local\backups\pre_upgrade_snapshot"
   $archiveDir = Join-Path $repoRoot ".local\backups"
   if (-not (Test-Path -LiteralPath $hostBackupDir)) { New-Item -ItemType Directory -Path $hostBackupDir -Force }
   ```

1. **Stop Application Container**:
   Stop the application container to ensure complete quiescence:
   ```powershell
   .\tools\SettleTable-Control.ps1 stop-all
   # Or using the CMD launcher:
   # .\tools\SettleTable-Control.cmd stop-all
   ```

2. **Verify Production Volume Target**:
   ```powershell
   python tools/verify_volume_target.py --mode real
   if ($LASTEXITCODE -ne 0) { throw "Volume pre-flight check failed with exit code $LASTEXITCODE! Aborting upgrade." }
   ```

3. **Take Quiescent Backup of `settletable_data`**:
   ```powershell
   docker compose run --rm -v "${hostBackupDir}:/backups" settletable python tools/backup_restore.py backup --db /data/settletable.sqlite --photos /data/receipt_photos --out-dir /backups
   if ($LASTEXITCODE -ne 0) { throw "Pre-upgrade backup generation failed with exit code $LASTEXITCODE!" }
   ```

4. **Extract Manifest Timestamp, Verify Integrity, and Archive**:
   Preserve repository root and enter the snapshot folder temporarily using `Push-Location` / `Pop-Location`:
   ```powershell
   Push-Location -LiteralPath "$hostBackupDir"
   try {
       $manifestFile = (Get-ChildItem -Filter "manifest_*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1)
       if (-not $manifestFile) { throw "No backup manifest found in $hostBackupDir!" }
       if ($manifestFile.BaseName -match '^manifest_(.+)$') {
           $timestamp = $Matches[1]
       } else {
           throw "Manifest filename '$($manifestFile.Name)' does not match expected pattern!"
       }

       $manifestData = Get-Content $manifestFile.FullName -Raw | ConvertFrom-Json
       $expectedDb = "settletable_${timestamp}.sqlite"
       $expectedPhotos = "receipt_photos_${timestamp}"

       if ($manifestData.database.filename -ne $expectedDb -or -not (Test-Path -LiteralPath $expectedDb)) {
           throw "Snapshot database mismatch: expected '$expectedDb' on disk and in manifest!"
       }
       if ($manifestData.receipt_photos_dir -ne $expectedPhotos -or -not (Test-Path -LiteralPath $expectedPhotos)) {
           throw "Snapshot photos mismatch: expected '$expectedPhotos' on disk and in manifest!"
       }

       $archivePath = Join-Path $archiveDir "settletable_backup_${timestamp}.7z"
       if (Test-Path -LiteralPath $archivePath) {
           throw "Target archive '$archivePath' already exists! Aborting to prevent overwrite."
       }

       # Create 7-Zip encrypted archive:
       & "<7Z_PATH>" a -t7z -mhe=on -p "$archivePath" "manifest_${timestamp}.json" "settletable_${timestamp}.sqlite" "receipt_photos_${timestamp}"
       if ($LASTEXITCODE -ne 0) { throw "7-Zip encrypted archive creation failed with exit code $LASTEXITCODE!" }

       # Verify archive integrity:
       & "<7Z_PATH>" t -p "$archivePath"
       if ($LASTEXITCODE -ne 0) { throw "7-Zip archive integrity verification failed with exit code $LASTEXITCODE!" }
   } finally {
       Pop-Location
   }
   ```

5. **Copy to Google Drive & Validate Hash**:
   The approved host Google Drive destination is `<GDRIVE_BACKUPS_DIR>` (located on the host at Google Drive `My Drive\SettleTable\backups`; strictly do not use `SettleTable_Backups`).
   *Caution*: Never overwrite `settletable_backup_20261108_123746Z.7z` (the first real-meal backup).
   ```powershell
   if (-not $gdriveBackupsDir -or -not (Test-Path -LiteralPath $gdriveBackupsDir)) {
       throw "Approved Google Drive backup directory not accessible: $gdriveBackupsDir"
   }

   $sourceArchive = Join-Path $archiveDir "settletable_backup_${timestamp}.7z"
   $destArchive = Join-Path $gdriveBackupsDir "settletable_backup_${timestamp}.7z"

   # Safety check: prevent overwriting any existing backup:
   if (Test-Path -LiteralPath $destArchive) {
       throw "Destination archive already exists in Google Drive: $destArchive. Aborting to prevent overwrite."
   }

   # Copy using cmdlet error-handling (-ErrorAction Stop):
   Copy-Item -LiteralPath $sourceArchive -Destination $destArchive -ErrorAction Stop

   # Verify bit-for-bit SHA-256 match between local archive and Google Drive copy:
   $sourceHash = (Get-FileHash -LiteralPath $sourceArchive -Algorithm SHA256).Hash
   $destHash = (Get-FileHash -LiteralPath $destArchive -Algorithm SHA256).Hash
   if ($sourceHash -ne $destHash) {
       throw "SHA-256 verification failed between local archive ($sourceHash) and Google Drive copy ($destHash)!"
   }
   Write-Host "Archive copy verified matching SHA-256: $destHash" -ForegroundColor Green
   ```
   *Human Verification*: Confirm the Google Drive for desktop taskbar notification reports "Everything is up to date" (queue count 0), and a permanent cloud ID replaces the local ID.

#### Step 2: Preserve Working Image & Rebuild Application Image

Ensure execution from repository root:
```powershell
Set-Location -LiteralPath $repoRoot
```

1. **Tag previous working image as fallback**:
   ```powershell
   docker tag settletable:latest settletable:pre-pr65-safe
   if ($LASTEXITCODE -ne 0) { throw "Docker tag failed with exit code $LASTEXITCODE!" }
   ```
2. **Explicitly rebuild Docker application image**:
   ```powershell
   docker compose build settletable
   if ($LASTEXITCODE -ne 0) { throw "Docker image build failed with exit code $LASTEXITCODE!" }
   ```

#### Step 3: Local-Only Startup & Post-Migration Verification

Ensure execution from repository root:
```powershell
Set-Location -LiteralPath $repoRoot
```

1. **Start updated application locally** with Cloudflare strictly offline:
   ```powershell
   .\tools\SettleTable-Control.ps1 start-local
   # Or using the CMD launcher:
   # .\tools\SettleTable-Control.cmd start-local
   if ($LASTEXITCODE -ne 0) { throw "Local startup failed with exit code $LASTEXITCODE!" }
   ```
2. **Verify local health probe returns HTTP 200**:
   ```powershell
   curl.exe -i http://127.0.0.1:8000/healthz
   if ($LASTEXITCODE -ne 0) { throw "Health probe failed with exit code $LASTEXITCODE!" }
   ```
3. **Inspect container logs for clean database schema upgrade**:
   ```powershell
   docker compose logs --tail 30 settletable
   ```
4. **Safe, Read-Only Database & Asset Integrity Verification**:
   > [!IMPORTANT]
   > **Domain & Session Cookie Scope**: The organizer's session cookie was issued for domain `settle.kybuilds.com` with `Secure; HttpOnly; SameSite=Strict`. Standard desktop browsers will not transmit this cookie to `http://127.0.0.1:8000`, so visiting localhost in a browser will display the unauthenticated landing page. Do not assume the browser can access the historical meal simply because localhost health checks pass.
   >
   > Execute the following read-only Python verification script inside the container. It validates schema migration, meal state, finalized calculations, receipt photo SHA-256, and Notion export status directly against storage without exposing private diner names, receipt items, money values, or tokens in the console transcript:
   ```powershell
   docker compose exec settletable python -c @"
import hashlib, json, os, sqlite3

db = sqlite3.connect('/data/settletable.sqlite')

# 1. Verify schema columns
notion_cols = [r[1] for r in db.execute('PRAGMA table_info(notion_exports)').fetchall()]
photo_cols = [r[1] for r in db.execute('PRAGMA table_info(receipt_photos)').fetchall()]
assert 'public_url' in notion_cols, 'Missing public_url in notion_exports'
assert 'share_with_diners' in photo_cols, 'Missing share_with_diners in receipt_photos'

# 2. Verify meal and participants counts (privacy-safe: counts only)
meal_count = db.execute('SELECT COUNT(*) FROM meals').fetchone()[0]
part_row = db.execute('SELECT COUNT(*), SUM(organizer), SUM(active) FROM participants').fetchone()
assert meal_count >= 1, 'No meal found'
assert part_row[0] >= 1 and part_row[1] >= 1, 'Missing participants or organizer'

# 3. Verify finalized financial state and revision identifiers
meal_id, state_bytes = db.execute('SELECT id, state FROM meals LIMIT 1').fetchone()
state = json.loads(state_bytes)
assert state.get('calculation') is not None, 'Meal is not finalized'
assert state.get('finalized_revision') is not None, 'Missing finalized_revision'
assert len(state['calculation'].get('consumption', [])) > 0, 'No consumption records found'

# 4. Verify receipt photo file existence and SHA-256 integrity
photo_row = db.execute('SELECT filename, sha256, share_with_diners FROM receipt_photos WHERE meal_id = ?', (meal_id,)).fetchone()
if photo_row:
    fname, expected_hash, share_val = photo_row
    assert share_val == 0, f'Expected share_with_diners == 0 (default-disabled), got {share_val}'
    fpath = os.path.join('/data/receipt_photos', fname)
    assert os.path.isfile(fpath), f'Photo file missing at {fpath}'
    with open(fpath, 'rb') as f:
        actual_hash = hashlib.sha256(f.read()).hexdigest()
    assert actual_hash == expected_hash, 'Photo SHA-256 integrity mismatch'

# 5. Verify Notion export records and page associations
notion_row = db.execute('SELECT finalized_revision, status, page_id, public_url FROM notion_exports WHERE meal_id = ?', (meal_id,)).fetchone()
if notion_row:
    rev, status, page_id, pub_url = notion_row
    assert status == 'completed', f'Unexpected export status: {status}'
    assert len(page_id) > 0, 'Empty Notion page_id'
    assert rev == state['finalized_revision'], 'Notion export revision mismatch'

print('POST_MIGRATION_VERIFICATION: PASS')
print(f'  Meals: {meal_count}, Participants: {part_row[0]} (Organizers: {part_row[1]}, Active: {part_row[2]})')
print(f'  Finalized Revision: {state["finalized_revision"]}, Items: {len(state.get("items", []))}')
print(f'  Receipt Photo: Verified bit-for-bit (share_with_diners={photo_row[2] if photo_row else "N/A"})')
print(f'  Notion Export: Status={notion_row[1] if notion_row else "N/A"} (Revision={notion_row[0] if notion_row else "N/A"})')
print(f'  Schema Migration: public_url and share_with_diners verified present')
"@
   if ($LASTEXITCODE -ne 0) { throw "Post-migration data integrity verification failed with exit code $LASTEXITCODE!" }
   ```

5. **Authenticated Browser Verification Considerations**:
   If visual UI inspection in a browser is desired prior to reactivating the public tunnel:
   - **Do not bootstrap a new meal or issue new claim tokens** on the real production database. The historical meal is finalized; generating new bootstrap sessions risks state pollution.
   - **Do not open public ingress prematurely** (`start-public`).
   - If visual inspection is required, the operator can temporarily configure local loopback resolution (`127.0.0.1 settle.kybuilds.com` in Windows `hosts`) behind a local trusted HTTPS proxy terminating TLS for `settle.kybuilds.com`, allowing the browser to present the existing session cookie.
   - Otherwise, the programmatic post-migration verification above provides authoritative proof of data and schema integrity.

#### Step 4: Practical Rollback Procedure (If Verification Fails)
If container health check fails or post-migration verification is inconclusive:
1. Ensure operations execute from repository root:
   ```powershell
   Set-Location -LiteralPath $repoRoot
   ```
2. Stop the application container immediately:
   ```powershell
   .\tools\SettleTable-Control.ps1 stop-all
   ```
3. Restore the previous working Docker image:
   ```powershell
   docker tag settletable:pre-pr65-safe settletable:latest
   if ($LASTEXITCODE -ne 0) { throw "Docker tag rollback failed with exit code $LASTEXITCODE!" }
   ```
4. Restore database and receipt photos from the pre-upgrade verified snapshot:
   ```powershell
   docker compose run --rm -v "${hostBackupDir}:/backups" settletable python tools/backup_restore.py restore --manifest "/backups/manifest_${timestamp}.json" --dest-db /data/settletable.sqlite --dest-photos /data/receipt_photos --confirm-stopped
   if ($LASTEXITCODE -ne 0) { throw "Disaster recovery restore failed with exit code $LASTEXITCODE!" }
   ```
5. Start previous working image locally:
   ```powershell
   .\tools\SettleTable-Control.ps1 start-local
   if ($LASTEXITCODE -ne 0) { throw "Local startup failed with exit code $LASTEXITCODE!" }
   ```
6. Verify local health probe of restored state:
   ```powershell
   curl.exe -i http://127.0.0.1:8000/healthz
   if ($LASTEXITCODE -ne 0) { throw "Restored state health probe failed!" }
   ```

---

## 7. Emergency Troubleshooting & Operational Cheatsheet

| Task | Command | Expected Outcome |
|---|---|---|
| **Check container status** | `docker compose ps` | `settletable_app: Up (healthy)`; `settletable_tunnel: Up` |
| **Inspect application logs** | `docker compose logs -f settletable` | Gunicorn access & error logs (tokens redacted) |
| **Inspect tunnel logs** | `docker compose logs -f cloudflared` | Cloudflare connection registration logs |
| **Test local health** | `curl -i http://127.0.0.1:8000/healthz` | HTTP 200 `{"ok":true,"status":"healthy"}` |
| **Test public tunnel ingress** | `curl -i https://settle.kybuilds.com/healthz` | HTTP 200 `{"ok":true,"status":"healthy"}` |
| **Run deployment smoke check** | `python tools/deployment_smoke_check.py` | 13/13 smoke checks pass |
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
  python tools/deployment_smoke_check.py --url https://settle.kybuilds.com
  ```

---

## 9. Stage C1 Real-Meal Pilot Executable Checklist

Use this checklist during the first authorized invited-friends dining session:

### Pre-Flight (1–2 Days Before Gathering)
- [ ] 1. **Volume Pre-Flight Check**: Verify `.env` has `SETTLETABLE_DATA_VOLUME=settletable_data` and run `python tools/verify_volume_target.py --mode real`.
- [ ] 2. **Pristine Database Initialization (Fresh Volumes Only)**: On a brand-new volume prior to first meal creation, safely initialize the SQLite database schema and `.volume_identity` marker without opening public ingress:
  ```powershell
  docker compose run --rm settletable python tools/bootstrap_meal.py init-db --db /data/settletable.sqlite
  ```
- [ ] 3. **Pre-Pilot Clean Backup**: Run baseline quiescent backup to local and offsite storage:
  ```powershell
  docker compose run --rm -v "${hostBackupDir}:/backups" -v "${hostOffsiteDir}:/offsite" settletable python tools/backup_restore.py backup --db /data/settletable.sqlite --photos /data/receipt_photos --out-dir /backups --copy-to /offsite
  if ($LASTEXITCODE -ne 0) { throw "Baseline backup failed!" }
  ```
  *Confirm host cloud sync client (e.g. OneDrive / Google Drive system tray icon) reports sync status "Up to date" before proceeding.*
- [ ] 4. **Public Ingress Smoke Check**: Start the stack (`docker compose --profile with-cloudflared up -d`) and run `python tools/deployment_smoke_check.py --url https://settle.kybuilds.com` (13/13 passing). Stop the stack if not yet dining.

### Event Kickoff (At the Restaurant / Gathering)
- [ ] 5. **Activate Public Ingress**: On the Windows host, execute `docker compose --profile with-cloudflared up -d`. Confirm `docker compose ps` shows `settletable_app: Up (healthy)` and `settletable_tunnel: Up`.
- [ ] 6. **Provision Meal via Host CLI**:
  ```powershell
  docker compose exec settletable python tools/bootstrap_meal.py bootstrap --meal-id dinner-YYYYMMDD --organizer "HostName" --diners "Alice,Bob,Charlie"
  ```
- [ ] 7. **Organizer Browser Activation**:
  - Open the generated single-use Organizer Setup Link (`https://settle.kybuilds.com/#/claim-organizer/<token>`) in your mobile or desktop browser.
  - Confirm the organizer session cookie is acquired (`is_organizer: true`).
- [ ] 8. **Capture & Verify Real Receipt**:
  - Take a well-lit photo of the paper receipt and upload via the browser interface.
  - Verify RapidOCR extracted candidate items, amounts, Malaysian SST (6%/8%), and service charge.
  - Edit or confirm items in the receipt editor and tap **Confirm & Save**.
- [ ] 9. **Distribute Diner Invitation Links**:
  - Copy the generated fragment links (`https://settle.kybuilds.com/#/invite/<token>`) from the UI or bootstrap output.
  - Send individually to Alice, Bob, and Charlie via private WhatsApp / Telegram / Signal chat.
- [ ] 10. **Collaborative Allocation & Settlement**:
  - Friends open links on their mobile phones in Safari / Chrome (zero app download or Cloudflare Access login).
  - Diners select their consumed items or shares.
  - Review the real-time financial breakdown, multi-payer contributions, and suggested peer settlements.

### Post-Event Closure (End of Evening)
- [ ] 11. **Quiescent Backup & Encrypted Google Drive Cloud Mirror**:
  - *11a. Local Quiescent Snapshot*:
    ```powershell
    docker compose run --rm -v "${hostBackupDir}:/backups" settletable python tools/backup_restore.py backup --db /data/settletable.sqlite --photos /data/receipt_photos --out-dir /backups
    if ($LASTEXITCODE -ne 0) { throw "Quiescent backup generation failed!" }
    ```
  - *11b. Create Encrypted Archive (Single-Snapshot Scoped)*:
    Extract the snapshot timestamp `${timestamp}` directly from the generated manifest and archive strictly its corresponding verified files:
    ```powershell
    Push-Location -LiteralPath "$hostBackupDir"
    try {
        $manifestFile = (Get-ChildItem -Filter "manifest_*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1)
        if (-not $manifestFile -or -not ($manifestFile.BaseName -match '^manifest_(.+)$')) { throw "Valid backup manifest not found in $hostBackupDir!" }
        $timestamp = $Matches[1]
        $archivePath = "${archiveDir}\settletable_backup_${timestamp}.7z"
        if (Test-Path -LiteralPath $archivePath) { throw "Target archive '$archivePath' already exists! Aborting." }
        & "<7Z_PATH>" a -t7z -mhe=on -p "$archivePath" "manifest_${timestamp}.json" "settletable_${timestamp}.sqlite" "receipt_photos_${timestamp}"
        if ($LASTEXITCODE -ne 0) { throw "7-Zip encrypted archive creation failed with exit code $LASTEXITCODE!" }
        & "<7Z_PATH>" t -p "$archivePath"
        if ($LASTEXITCODE -ne 0) { throw "7-Zip archive integrity verification failed with exit code $LASTEXITCODE!" }
    } finally {
        Pop-Location
    }
    ```
    *(Type your strong master encryption passphrase when prompted; never write it to scripts or `.env`).*
  - *11c. Copy to Google Drive & Verify Cloud Durability*:
    ```powershell
    # Ensure $gdriveBackupsDir is configured to your host's Google Drive 'My Drive\SettleTable\backups'
    if (-not $gdriveBackupsDir -or -not (Test-Path -LiteralPath $gdriveBackupsDir)) { throw "Approved Google Drive directory not accessible: $gdriveBackupsDir" }
    $sourceArchive = Join-Path $archiveDir "settletable_backup_${timestamp}.7z"
    $destArchive = Join-Path $gdriveBackupsDir "settletable_backup_${timestamp}.7z"
    if (Test-Path -LiteralPath $destArchive) { throw "Destination archive already exists in Google Drive: $destArchive. Aborting to prevent overwrite." }
    Copy-Item -LiteralPath $sourceArchive -Destination $destArchive -ErrorAction Stop
    $sourceHash = (Get-FileHash -LiteralPath $sourceArchive -Algorithm SHA256).Hash
    $destHash = (Get-FileHash -LiteralPath $destArchive -Algorithm SHA256).Hash
    if ($sourceHash -ne $destHash) { throw "SHA-256 mismatch between local archive ($sourceHash) and Google Drive copy ($destHash)!" }
    Write-Host "Archive copy verified matching SHA-256: $destHash" -ForegroundColor Green
    ```
    *Important: Local copying to Google Drive writes to the local DriveFS cache (and receives a transient `local-*` identifier). Confirm verified remote cloud upload before powering off: the system tray icon displays "Everything is up to date" (queue count 0), and a permanent cloud ID replaces the local ID.*
- [ ] 12. **Lifecycle Decision**:
  - Either leave running for mostly-available post-dinner review (`restart: unless-stopped`), OR
  - Cleanly deactivate public ingress (`docker compose stop cloudflared`).
