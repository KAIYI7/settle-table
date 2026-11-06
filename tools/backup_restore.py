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
import sys

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


def check_database_unlocked(db_path: Path):
    """Verify that no active process holds a write lock on the target database."""
    if not db_path.exists():
        return
    test_conn = None
    try:
        test_conn = sqlite3.connect(db_path, timeout=0.1)
        test_conn.execute("PRAGMA busy_timeout=100;")
        test_conn.execute("BEGIN IMMEDIATE;")
        test_conn.execute("ROLLBACK;")
    except sqlite3.OperationalError as e:
        raise RuntimeError(
            f"Target database '{db_path.name}' is currently locked by a running process: {e}. "
            "Stop the application container before restoring to prevent database corruption."
        ) from None
    finally:
        if test_conn:
            try:
                test_conn.close()
            except Exception:
                pass


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


def perform_verified_restore(manifest_path: Path, dest_db: Path, dest_photos: Path) -> dict:
    """Restore database and receipt photos with strict cross-verification and process locking checks."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    manifest_dir = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    backup_db = manifest_dir / manifest["database"]["filename"]
    if not backup_db.exists():
        raise FileNotFoundError(f"Backup database file not found: {backup_db}")

    backup_photos_dir = manifest_dir / manifest["receipt_photos_dir"]

    # 1. Active process lock defense: refuse to restore if destination DB is in use
    check_database_unlocked(dest_db)

    # 2. Verify backup database file integrity & checksum
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

    # 3. Verify photo files in backup against manifest
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

    # 4. Verify backup database photo records match manifest
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
    db_conn.close()

    # 5. Restore SQLite database (clear WAL sidecars first to prevent corruption)
    dest_db.parent.mkdir(parents=True, exist_ok=True)
    for sidecar in (dest_db.with_suffix(".sqlite-wal"), dest_db.with_suffix(".sqlite-shm")):
        if sidecar.exists():
            sidecar.unlink()
    shutil.copy2(backup_db, dest_db)

    # Verify restored database integrity on destination disk
    dest_check = sqlite3.connect(dest_db)
    dest_res = dest_check.execute("PRAGMA integrity_check;").fetchone()
    dest_check.close()
    if not dest_res or dest_res[0] != "ok":
        raise RuntimeError(f"Restored database failed integrity check: {dest_res}")

    # 6. Restore receipt photos
    dest_photos.mkdir(parents=True, exist_ok=True)
    restored_count = 0
    if backup_photos_dir.exists():
        for p in backup_photos_dir.iterdir():
            if p.is_file():
                dest_file = dest_photos / p.name
                shutil.copy2(p, dest_file)
                restored_count += 1

    return {
        "status": "ok",
        "restored_db": str(dest_db),
        "db_sha256": actual_db_sha,
        "restored_photos_count": restored_count,
        "restored_photos_dir": str(dest_photos),
    }


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

    try:
        res = perform_verified_restore(manifest_path, dest_db, dest_photos)
        print("\n[OK] Database and receipt photos verified and restored.")
        print(f"  Restored DB:      {res['restored_db']} (SHA-256: {res['db_sha256'][:16]}...)")
        print(f"  Restored Photos:  {res['restored_photos_count']} files in {res['restored_photos_dir']}")
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

    args = parser.parse_args()
    if args.command == "backup":
        backup_command(args)
    elif args.command == "restore":
        restore_command(args)


if __name__ == "__main__":
    main()
