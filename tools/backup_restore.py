"""SettleTable Quiescent Backup and Disaster Recovery Utility.

Performs provably consistent, quiescent snapshots of the SQLite database in WAL mode
with synchronized verification of receipt photo assets, and verified restoration
with active process lock detection and cross-manifest checksum validation.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
import uuid

# Ensure repository root is in path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def compute_sha256(filepath: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def check_restore_safety(
    db_path: Path,
    *,
    confirm_stopped: bool = False,
    check_url: str | None = "http://127.0.0.1:8000/healthz",
    check_docker: bool = True,
):
    """Enforce the restore safety contract.

    Restoring a database over an active, running application can cause split-brain
    WAL desynchronization or file locking errors. Because an idle SQLite connection
    in WAL mode does not hold an active writer lock, testing SQLite locks alone
    CANNOT prove that the application process or container is inactive.

    The primary safety invariant is an explicitly stopped application container.
    This check verifies:
    1. The operator provided explicit confirmation that the application is stopped (--confirm-stopped).
    2. Probing the local application health endpoint (if accessible) confirms no server is actively listening.
    3. Docker CLI inspection (if available) confirms the SettleTable container is not running.
    4. SQLite exclusive locking confirms no transaction or lock is currently active on disk.
    """
    if not confirm_stopped:
        raise RuntimeError(
            "Restoration safety violation: SettleTable must be stopped prior to restoring data.\n"
            "Stop the application container ('docker compose down' or 'docker stop settletable_app')\n"
            "and pass '--confirm-stopped' to proceed."
        )

    # 1. Probe local health endpoint if configured
    if check_url:
        try:
            req = urllib.request.Request(check_url, headers={"User-Agent": "settletable-restore-check"})
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                if resp.status == 200:
                    raise RuntimeError(
                        f"Active application detected: server responded with HTTP 200 at '{check_url}'.\n"
                        "Restoration aborted. Stop the application container before restoring."
                    )
        except urllib.error.URLError:
            pass
        except TimeoutError:
            pass
        except OSError:
            pass

    # 2. Check Docker container status if docker command is available
    if check_docker and shutil.which("docker"):
        try:
            res = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", "settletable_app"],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            if res.returncode == 0 and res.stdout.strip() == "true":
                raise RuntimeError(
                    "Docker container 'settletable_app' is currently running.\n"
                    "Restoration aborted. Run 'docker stop settletable_app' or 'docker compose down' before restoring."
                )
        except (subprocess.TimeoutExpired, OSError):
            pass

    # 3. Check SQLite database lock if file exists on disk
    if db_path.exists():
        test_conn = None
        try:
            test_conn = sqlite3.connect(db_path, timeout=0.1)
            test_conn.execute("PRAGMA busy_timeout=100;")
            test_conn.execute("PRAGMA locking_mode=EXCLUSIVE;")
            test_conn.execute("BEGIN EXCLUSIVE;")
            test_conn.execute("ROLLBACK;")
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                raise RuntimeError(
                    f"Target database '{db_path.name}' is currently locked by a running process: {e}.\n"
                    "Stop the application container before restoring to prevent database corruption."
                ) from None
        except sqlite3.DatabaseError:
            pass  # File is not a valid SQLite database or is empty; not locked by SQLite engine
        finally:
            if test_conn:
                try:
                    test_conn.close()
                except Exception:
                    pass


# Alias for backwards compatibility
check_database_unlocked = check_restore_safety


def perform_quiescent_backup(src_db: Path, src_photos: Path, out_dir: Path) -> Path:
    """Perform a quiescent snapshot while holding an immediate write transaction lock.

    Holding BEGIN IMMEDIATE ensures no concurrent transactions commit or insert/delete
    receipt photos while the database pages and photo assets are being copied.
    """
    if not src_db.exists():
        raise FileNotFoundError(f"Source database not found: {src_db}")

    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    backup_db_file = out_dir / f"settletable_{timestamp}.sqlite"
    backup_photos_dir = out_dir / f"receipt_photos_{timestamp}"
    temp_db_file = backup_db_file.with_suffix(".tmp")
    if temp_db_file.exists():
        temp_db_file.unlink()

    backup_photos_dir.mkdir(parents=True, exist_ok=True)
    photo_manifest = {}
    lock_conn = None
    ro_conn = None
    dest_conn = None

    try:
        # 1. Acquire write lock on source database to quiesce all writes/commits
        lock_conn = sqlite3.connect(src_db, timeout=5.0)
        lock_conn.execute("PRAGMA busy_timeout=5000;")
        lock_conn.execute("BEGIN IMMEDIATE;")

        # 2. Open read-only connection to read consistent snapshot and perform backup
        ro_conn = sqlite3.connect(f"file:{src_db.resolve()}?mode=ro", uri=True)

        # 3. Query all active receipt photos recorded in the database
        has_table = ro_conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='receipt_photos';"
        ).fetchone()

        db_photos = []
        if has_table:
            db_photos = ro_conn.execute(
                "SELECT meal_id, filename, sha256, byte_size FROM receipt_photos ORDER BY filename;"
            ).fetchall()

        # 4. Verify and copy every referenced photo file while holding the write lock
        for meal_id, filename, expected_sha, expected_size in db_photos:
            photo_path = src_photos / filename
            if not photo_path.exists() or not photo_path.is_file():
                raise FileNotFoundError(
                    f"Receipt photo '{filename}' recorded in database for meal '{meal_id}' is missing from disk: {photo_path}"
                )
            actual_size = photo_path.stat().st_size
            actual_sha = compute_sha256(photo_path)
            if actual_size != expected_size or actual_sha != expected_sha:
                raise ValueError(
                    f"Receipt photo '{filename}' checksum mismatch (expected SHA {expected_sha}, got {actual_sha})"
                )

            dest_photo = backup_photos_dir / filename
            shutil.copy2(photo_path, dest_photo)
            photo_manifest[filename] = {
                "meal_id": meal_id,
                "sha256": actual_sha,
                "size_bytes": actual_size,
            }

        # 5. Backup SQLite database pages from read-only connection to destination
        dest_conn = sqlite3.connect(temp_db_file)
        with dest_conn:
            ro_conn.backup(dest_conn, pages=250)
        dest_conn.close()
        dest_conn = None

        ro_conn.close()
        ro_conn = None

        # 6. Release the write lock
        lock_conn.execute("ROLLBACK;")
        lock_conn.close()
        lock_conn = None

        # 7. Run integrity check on the temporary snapshot
        check_conn = sqlite3.connect(temp_db_file)
        res = check_conn.execute("PRAGMA integrity_check;").fetchone()
        check_conn.close()
        if not res or res[0] != "ok":
            raise RuntimeError(f"Backup database failed PRAGMA integrity_check: {res}")

        # Promote temporary snapshot
        temp_db_file.replace(backup_db_file)
        db_sha = compute_sha256(backup_db_file)

        # Write manifest
        manifest = {
            "version": "1.1",
            "type": "settletable-quiescent-backup",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database": {
                "filename": backup_db_file.name,
                "sha256": db_sha,
                "size_bytes": backup_db_file.stat().st_size,
            },
            "receipt_photos_dir": backup_photos_dir.name,
            "photo_count": len(photo_manifest),
            "photos": photo_manifest,
        }
        manifest_path = out_dir / f"manifest_{timestamp}.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest_path

    except Exception:
        if temp_db_file.exists():
            try:
                temp_db_file.unlink()
            except OSError:
                pass
        if backup_db_file.exists():
            try:
                backup_db_file.unlink()
            except OSError:
                pass
        if backup_photos_dir.exists():
            try:
                shutil.rmtree(backup_photos_dir)
            except OSError:
                pass
        raise
    finally:
        if dest_conn:
            try:
                dest_conn.close()
            except Exception:
                pass
        if ro_conn:
            try:
                ro_conn.close()
            except Exception:
                pass
        if lock_conn:
            try:
                lock_conn.execute("ROLLBACK;")
            except Exception:
                pass
            try:
                lock_conn.close()
            except Exception:
                pass


def perform_verified_restore(
    manifest_path: Path,
    dest_db: Path,
    dest_photos: Path,
    *,
    confirm_stopped: bool = False,
    check_url: str | None = "http://127.0.0.1:8000/healthz",
    check_docker: bool = True,
    keep_backup: bool = True,
) -> dict:
    """Restore database and receipt photos using a verified staged cutover.

    Guarantees:
    - Pre-flight validation checks manifest, backup database integrity, photo checksums,
      and lack of extraneous files before touching the destination.
    - Staged preparation happens in an isolated staging directory on the destination volume.
    - Previous destination data is safely archived before cutover.
    - Post-cutover destination integrity is verified; if validation fails, destination
      is automatically rolled back from the archive.
    - Old destination receipt photos not in the backup are cleanly archived and do not
      pollute the restored state.

    Filesystem Multi-Path Atomicity Note:
    Individual file rename/replace (os.replace) is atomic within the same filesystem volume.
    However, replacing both a database file and an entire photo directory across multiple
    filesystem paths cannot be fully atomic across crashes without filesystem-level transactions.
    SettleTable mitigates this by staging all files first and verifying post-cutover integrity
    with automated rollback.
    """
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    manifest_dir = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    backup_db = manifest_dir / manifest["database"]["filename"]
    if not backup_db.exists():
        raise FileNotFoundError(f"Backup database file not found: {backup_db}")

    backup_photos_dir = manifest_dir / manifest["receipt_photos_dir"]

    # 1. Enforce restore safety contract
    check_restore_safety(
        dest_db,
        confirm_stopped=confirm_stopped,
        check_url=check_url,
        check_docker=check_docker,
    )

    # 2. Pre-flight verification of backup database
    actual_db_sha = compute_sha256(backup_db)
    if actual_db_sha != manifest["database"]["sha256"]:
        raise ValueError(
            f"Backup database checksum mismatch: expected {manifest['database']['sha256']}, got {actual_db_sha}"
        )

    check_conn = sqlite3.connect(backup_db)
    res = check_conn.execute("PRAGMA integrity_check;").fetchone()
    check_conn.close()
    if not res or res[0] != "ok":
        raise RuntimeError(f"Backup database PRAGMA integrity_check failed: {res}")

    # 3. Pre-flight verification of backup photos
    raw_photos = manifest.get("photos", {})
    verified_photos = {}
    for filename, meta in raw_photos.items():
        photo_file = backup_photos_dir / filename
        if not photo_file.exists():
            raise FileNotFoundError(f"Backup receipt photo missing: {photo_file}")
        actual_photo_sha = compute_sha256(photo_file)
        expected_sha = meta["sha256"] if isinstance(meta, dict) else meta
        if actual_photo_sha != expected_sha:
            raise ValueError(f"Receipt photo '{filename}' checksum mismatch in backup!")
        verified_photos[filename] = actual_photo_sha

    # Verify no extraneous files exist in backup photos directory
    if backup_photos_dir.exists():
        for p in backup_photos_dir.iterdir():
            if p.is_file() and p.name not in verified_photos:
                raise ValueError(
                    f"Extraneous receipt photo '{p.name}' in backup directory is not recorded in manifest!"
                )

    # Cross-verify database photo table against manifest
    db_conn = sqlite3.connect(backup_db)
    has_photo_table = db_conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='receipt_photos';"
    ).fetchone()
    if has_photo_table:
        db_rows = db_conn.execute("SELECT filename, sha256 FROM receipt_photos;").fetchall()
        for fn, db_sha in db_rows:
            if fn not in verified_photos or verified_photos[fn] != db_sha:
                db_conn.close()
                raise ValueError(f"Database photo record '{fn}' does not match backup photos on disk!")
        if len(db_rows) != len(verified_photos):
            db_conn.close()
            raise ValueError("Count of photo records in database does not match manifest photos!")
    db_conn.close()

    # 4. Prepare staged restore in an isolated temporary staging directory on the destination volume
    dest_db.parent.mkdir(parents=True, exist_ok=True)
    dest_photos.parent.mkdir(parents=True, exist_ok=True)

    restore_id = uuid.uuid4().hex[:8]
    staging_dir = dest_db.parent / f".restore_staging_{restore_id}"
    staging_dir.mkdir(parents=True, exist_ok=True)
    staged_db = staging_dir / dest_db.name
    staged_photos = staging_dir / dest_photos.name
    staged_photos.mkdir(parents=True, exist_ok=True)

    archive_dir = dest_db.parent / f".pre_restore_archive_{restore_id}"

    try:
        # Copy to staging
        shutil.copy2(backup_db, staged_db)
        for fn in verified_photos:
            shutil.copy2(backup_photos_dir / fn, staged_photos / fn)

        # Re-verify staged database
        staged_db_sha = compute_sha256(staged_db)
        if staged_db_sha != actual_db_sha:
            raise RuntimeError("Staged database checksum failed verification!")
        staged_check = sqlite3.connect(staged_db)
        staged_res = staged_check.execute("PRAGMA integrity_check;").fetchone()
        staged_check.close()
        if not staged_res or staged_res[0] != "ok":
            raise RuntimeError(f"Staged database failed integrity check: {staged_res}")

        # Re-verify staged photos
        for fn, exp_sha in verified_photos.items():
            sp = staged_photos / fn
            if not sp.exists() or compute_sha256(sp) != exp_sha:
                raise RuntimeError(f"Staged photo '{fn}' failed verification!")

        # 5. Quarantine previous destination data (to allow rollback if cutover fails)
        archive_dir.mkdir(parents=True, exist_ok=True)
        archived_db = False
        archived_photos = False

        if dest_db.exists():
            shutil.move(str(dest_db), str(archive_dir / dest_db.name))
            archived_db = True
        # Clean any stale WAL sidecars
        for sidecar in (dest_db.with_suffix(".sqlite-wal"), dest_db.with_suffix(".sqlite-shm")):
            if sidecar.exists():
                shutil.move(str(sidecar), str(archive_dir / sidecar.name))

        if dest_photos.exists():
            shutil.move(str(dest_photos), str(archive_dir / dest_photos.name))
            archived_photos = True

        # 6. Controlled Cutover
        try:
            # Move staged DB to dest_db
            shutil.move(str(staged_db), str(dest_db))
            # Move staged photos to dest_photos
            shutil.move(str(staged_photos), str(dest_photos))

            # 7. Post-cutover validation at final destination
            if not dest_db.exists() or compute_sha256(dest_db) != actual_db_sha:
                raise RuntimeError("Post-cutover destination database checksum mismatch!")
            dest_conn = sqlite3.connect(dest_db)
            dest_res = dest_conn.execute("PRAGMA integrity_check;").fetchone()
            dest_conn.close()
            if not dest_res or dest_res[0] != "ok":
                raise RuntimeError(f"Post-cutover database failed integrity check: {dest_res}")

            for fn, exp_sha in verified_photos.items():
                dp = dest_photos / fn
                if not dp.exists() or compute_sha256(dp) != exp_sha:
                    raise RuntimeError(f"Post-cutover photo '{fn}' missing or corrupted!")

            dest_photo_count = sum(1 for p in dest_photos.iterdir() if p.is_file())
            if dest_photo_count != len(verified_photos):
                raise RuntimeError(
                    f"Post-cutover photo count mismatch: expected {len(verified_photos)}, found {dest_photo_count}"
                )

        except Exception as cutover_err:
            # Automated Rollback to previous destination state!
            if dest_db.exists():
                try: dest_db.unlink()
                except OSError: pass
            if dest_photos.exists():
                try: shutil.rmtree(dest_photos)
                except OSError: pass

            if archived_db and (archive_dir / dest_db.name).exists():
                shutil.move(str(archive_dir / dest_db.name), str(dest_db))
            for sidecar in (dest_db.with_suffix(".sqlite-wal"), dest_db.with_suffix(".sqlite-shm")):
                archived_sc = archive_dir / sidecar.name
                if archived_sc.exists():
                    shutil.move(str(archived_sc), str(sidecar))
            if archived_photos and (archive_dir / dest_photos.name).exists():
                shutil.move(str(archive_dir / dest_photos.name), str(dest_photos))

            raise RuntimeError(
                f"Cutover failed: {cutover_err}. Destination rolled back to previous dataset."
            ) from cutover_err

        # Cutover succeeded: handle archive directory
        archived_backup_path = None
        if archived_db or archived_photos:
            if keep_backup:
                archived_backup_path = dest_db.parent / f"{dest_db.stem}.pre_restore_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%SZ')}.bak"
                if archive_dir.exists():
                    shutil.move(str(archive_dir), str(archived_backup_path))
            else:
                shutil.rmtree(archive_dir, ignore_errors=True)

        return {
            "status": "ok",
            "restored_db": str(dest_db),
            "db_sha256": actual_db_sha,
            "restored_photos_count": len(verified_photos),
            "restored_photos_dir": str(dest_photos),
            "previous_dataset_archive": str(archived_backup_path) if archived_backup_path else None,
        }

    finally:
        # Clean up staging directory
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)


def backup_command(args):
    src_db = Path(args.db).resolve()
    src_photos = Path(args.photos).resolve() if args.photos else src_db.parent / "receipt_photos"
    out_dir = Path(args.out_dir).resolve()

    print("=== Starting SettleTable Quiescent Backup ===")
    print(f"Source DB:      {src_db}")
    print(f"Source Photos:  {src_photos}")
    print(f"Destination:    {out_dir}")

    try:
        manifest_path = perform_quiescent_backup(src_db, src_photos, out_dir)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        print("\n[OK] Quiescent database and photo snapshot completed.")
        print(f"  Manifest:     {manifest_path.name}")
        print(f"  DB SHA-256:   {manifest['database']['sha256'][:16]}...")
        print(f"  Photo Count:  {manifest['photo_count']}")
        print(f"\n[SUCCESS] Backup completed successfully at {manifest['created_at']}")
    except Exception as e:
        print(f"\n[ERROR] Backup failed: {e}", file=sys.stderr)
        sys.exit(1)


def restore_command(args):
    manifest_path = Path(args.manifest).resolve()
    dest_db = Path(args.dest_db).resolve()
    dest_photos = Path(args.dest_photos).resolve() if args.dest_photos else dest_db.parent / "receipt_photos"

    print("=== Starting SettleTable Disaster Recovery Restore ===")
    print(f"Manifest:       {manifest_path}")
    print(f"Restore Target: {dest_db}")
    print(f"Photos Target:  {dest_photos}")

    check_url = None if args.skip_health_check else args.check_url

    try:
        res = perform_verified_restore(
            manifest_path,
            dest_db,
            dest_photos,
            confirm_stopped=args.confirm_stopped,
            check_url=check_url,
            check_docker=not args.skip_docker_check,
            keep_backup=not args.no_backup,
        )
        print("\n[OK] Database and receipt photos verified and restored.")
        print(f"  Restored DB:      {res['restored_db']} (SHA-256: {res['db_sha256'][:16]}...)")
        print(f"  Restored Photos:  {res['restored_photos_count']} files in {res['restored_photos_dir']}")
        if res.get("previous_dataset_archive"):
            print(f"  Previous Archive: {res['previous_dataset_archive']}")
        print("\n[SUCCESS] Restoration completed successfully.")
    except Exception as e:
        print(f"\n[ERROR] Restoration failed: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="SettleTable Quiescent Backup and Disaster Recovery Utility")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Backup subcommand
    backup_parser = subparsers.add_parser("backup", help="Perform quiescent snapshot of SQLite DB and receipt photos")
    backup_parser.add_argument("--db", default=".local/settletable.sqlite", help="Path to active SQLite database")
    backup_parser.add_argument("--photos", default=None, help="Path to receipt photos directory (default: <db_dir>/receipt_photos)")
    backup_parser.add_argument("--out-dir", default=".local/backups", help="Directory where backup will be stored")

    # Restore subcommand
    restore_parser = subparsers.add_parser("restore", help="Restore database and receipt photos from backup manifest")
    restore_parser.add_argument("--manifest", required=True, help="Path to backup manifest.json")
    restore_parser.add_argument("--dest-db", default=".local/settletable.sqlite", help="Destination path for restored database")
    restore_parser.add_argument("--dest-photos", default=None, help="Destination directory for receipt photos")
    restore_parser.add_argument("--confirm-stopped", action="store_true",
                                help="Confirm that the SettleTable application container has been stopped before restoring")
    restore_parser.add_argument("--check-url", default="http://127.0.0.1:8000/healthz",
                                help="Health URL to check for active application (default: http://127.0.0.1:8000/healthz)")
    restore_parser.add_argument("--skip-health-check", action="store_true",
                                help="Skip probing the local application health endpoint")
    restore_parser.add_argument("--skip-docker-check", action="store_true",
                                help="Skip checking docker container status")
    restore_parser.add_argument("--no-backup", action="store_true",
                                help="Do not retain a backup copy of previous destination data")

    args = parser.parse_args()
    if args.command == "backup":
        backup_command(args)
    elif args.command == "restore":
        restore_command(args)


if __name__ == "__main__":
    main()
