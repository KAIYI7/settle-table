"""SettleTable Hot Backup and Disaster Recovery Utility.

Performs live, crash-consistent backups of the SQLite database in WAL mode
using the official SQLite Online Backup API (`sqlite3.Connection.backup()`),
accompanied by atomic synchronization of receipt photo assets.
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


def hot_backup_database(src_db: Path, dest_db: Path) -> tuple[bool, str]:
    """Perform online SQLite backup while application is actively writing in WAL mode."""
    dest_db.parent.mkdir(parents=True, exist_ok=True)
    temp_dest = dest_db.with_suffix(".tmp")
    if temp_dest.exists():
        temp_dest.unlink()

    src_conn = None
    dest_conn = None
    try:
        src_conn = sqlite3.connect(f"file:{src_db.resolve()}?mode=ro", uri=True)
        dest_conn = sqlite3.connect(temp_dest)
        with dest_conn:
            src_conn.backup(dest_conn, pages=250)
        dest_conn.close()
        dest_conn = None

        # Verify integrity of the backup before finalizing
        check_conn = sqlite3.connect(temp_dest)
        cursor = check_conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        res = cursor.fetchone()
        check_conn.close()

        if not res or res[0] != "ok":
            if temp_dest.exists():
                temp_dest.unlink()
            return False, f"Integrity check failed: {res}"

        temp_dest.replace(dest_db)
        return True, "ok"
    except Exception as e:
        if temp_dest.exists():
            temp_dest.unlink()
        return False, str(e)
    finally:
        if src_conn:
            src_conn.close()
        if dest_conn:
            dest_conn.close()


def sync_receipt_photos(src_dir: Path, dest_dir: Path) -> dict[str, str]:
    """Copy receipt photo files to backup destination and return {filename: sha256}."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    photo_hashes = {}
    if not src_dir.exists():
        return photo_hashes

    for file_path in src_dir.iterdir():
        if file_path.is_file() and not file_path.name.endswith(".tmp"):
            dest_file = dest_dir / file_path.name
            shutil.copy2(file_path, dest_file)
            photo_hashes[file_path.name] = compute_sha256(dest_file)

    return photo_hashes


def backup_command(args):
    src_db = Path(args.db).resolve()
    if not src_db.exists():
        print(f"[ERROR] Source database not found: {src_db}", file=sys.stderr)
        sys.exit(1)

    src_photos = Path(args.photos).resolve() if args.photos else src_db.parent / "receipt_photos"
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    backup_db_file = out_dir / f"settletable_{timestamp}.sqlite"
    backup_photos_dir = out_dir / f"receipt_photos_{timestamp}"

    print(f"=== Starting SettleTable Hot Backup ===")
    print(f"Source DB:      {src_db}")
    print(f"Source Photos:  {src_photos}")
    print(f"Destination:    {out_dir}")

    # 1. Hot backup SQLite database
    print("\n[1/3] Performing SQLite online backup...")
    ok, msg = hot_backup_database(src_db, backup_db_file)
    if not ok:
        print(f"[ERROR] SQLite backup failed: {msg}", file=sys.stderr)
        sys.exit(1)
    db_sha = compute_sha256(backup_db_file)
    print(f"  [OK] Database backup created: {backup_db_file.name} (SHA-256: {db_sha[:16]}...)")

    # 2. Sync receipt photos
    print("\n[2/3] Synchronizing receipt photos...")
    photo_hashes = sync_receipt_photos(src_photos, backup_photos_dir)
    print(f"  [OK] Synchronized {len(photo_hashes)} receipt photo(s)")

    # 3. Create backup manifest
    print("\n[3/3] Generating manifest...")
    manifest = {
        "version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database": {
            "filename": backup_db_file.name,
            "sha256": db_sha,
            "size_bytes": backup_db_file.stat().st_size,
        },
        "receipt_photos_dir": backup_photos_dir.name,
        "photo_count": len(photo_hashes),
        "photos": photo_hashes,
    }
    manifest_path = out_dir / f"manifest_{timestamp}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"  [OK] Backup manifest written to {manifest_path.name}")
    print(f"\n[SUCCESS] Backup completed successfully at {manifest['created_at']}")


def restore_command(args):
    manifest_path = Path(args.manifest).resolve()
    if not manifest_path.exists():
        print(f"[ERROR] Manifest file not found: {manifest_path}", file=sys.stderr)
        sys.exit(1)

    manifest_dir = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    backup_db = manifest_dir / manifest["database"]["filename"]
    backup_photos = manifest_dir / manifest["receipt_photos_dir"]

    dest_db = Path(args.dest_db).resolve()
    dest_photos = Path(args.dest_photos).resolve() if args.dest_photos else dest_db.parent / "receipt_photos"

    print(f"=== Starting SettleTable Disaster Recovery Restore ===")
    print(f"Manifest:       {manifest_path}")
    print(f"Restore Target: {dest_db}")
    print(f"Photos Target:  {dest_photos}")

    # 1. Verify backup DB checksum and integrity
    print("\n[1/3] Verifying backup database integrity...")
    actual_db_sha = compute_sha256(backup_db)
    if actual_db_sha != manifest["database"]["sha256"]:
        print(f"[ERROR] Database checksum mismatch!", file=sys.stderr)
        sys.exit(1)

    check_conn = sqlite3.connect(backup_db)
    cursor = check_conn.cursor()
    cursor.execute("PRAGMA integrity_check;")
    res = cursor.fetchone()
    check_conn.close()
    if not res or res[0] != "ok":
        print(f"[ERROR] Backup database integrity check failed: {res}", file=sys.stderr)
        sys.exit(1)
    print("  [OK] Database checksum and PRAGMA integrity_check verified")

    # 2. Restore database
    print("\n[2/3] Restoring SQLite database...")
    dest_db.parent.mkdir(parents=True, exist_ok=True)
    # Remove existing WAL sidecars to prevent desynchronization
    for sidecar in (dest_db.with_suffix(".sqlite-wal"), dest_db.with_suffix(".sqlite-shm")):
        if sidecar.exists():
            sidecar.unlink()
    shutil.copy2(backup_db, dest_db)
    print(f"  [OK] Database restored to {dest_db}")

    # 3. Restore receipt photos
    print("\n[3/3] Restoring receipt photos...")
    dest_photos.mkdir(parents=True, exist_ok=True)
    restored_count = 0
    if backup_photos.exists():
        for p in backup_photos.iterdir():
            if p.is_file():
                shutil.copy2(p, dest_photos / p.name)
                restored_count += 1
    print(f"  [OK] Restored {restored_count} receipt photo file(s) to {dest_photos}")
    print(f"\n[SUCCESS] Restoration completed successfully.")


def main():
    parser = argparse.ArgumentParser(description="SettleTable Hot Backup and Disaster Recovery Utility")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Backup subcommand
    backup_parser = subparsers.add_parser("backup", help="Perform online hot backup of SQLite DB and receipt photos")
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
