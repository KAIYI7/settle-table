"""Isolated Docker End-to-End Backup and Restore Drill for SettleTable.

Performs a non-destructive verification drill using isolated Docker volumes
and synthetic meal/photo data. Guarantees that production/local project data
is never touched.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid


def run_cmd(cmd, desc=""):
    print(f"  * {desc} ... ", end="", flush=True)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"FAILED (code {res.returncode})")
        print(f"STDOUT:\n{res.stdout}")
        print(f"STDERR:\n{res.stderr}")
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    print("OK")
    return res.stdout


def main():
    drill_id = uuid.uuid4().hex[:8]
    src_volume = f"settletable_drill_src_{drill_id}"
    dest_volume = f"settletable_drill_dest_{drill_id}"
    host_backup_dir = tempfile.mkdtemp(prefix=f"settletable_drill_backups_{drill_id}_")

    image_tag = "settletable:latest"
    meal_id = f"drill-meal-{drill_id}"
    sample_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00"
        b"\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    expected_photo_sha = hashlib.sha256(sample_png).hexdigest()

    print(f"\n=======================================================")
    print(f" SettleTable -- Isolated Docker Backup/Restore Drill")
    print(f" Drill ID:     {drill_id}")
    print(f" Source Vol:   {src_volume}")
    print(f" Dest Vol:     {dest_volume}")
    print(f" Host Backups: {host_backup_dir}")
    print(f"=======================================================\n")

    try:
        # 1. Create isolated Docker volumes
        run_cmd(["docker", "volume", "create", src_volume], "Create isolated source volume")
        run_cmd(["docker", "volume", "create", dest_volume], "Create isolated destination volume")

        # 2. Seed synthetic meal and receipt photo in source volume
        seed_script = f"""
from pathlib import Path
from settletable.authority import Authority, Participant

db_path = Path('/data/settletable.sqlite')
storage_dir = Path('/data/receipt_photos')
storage_dir.mkdir(parents=True, exist_ok=True)

auth = Authority(db_path, storage_dir=storage_dir)
b_res = auth.bootstrap('{meal_id}', (
    Participant('org', 'Chef Organizer', organizer=True),
    Participant('diner1', 'Alice Diner'),
))

org_cred = next(s.credential for s in b_res.sessions if s.participant_id == 'org')
png_bytes = {sample_png!r}

meta = auth.store_receipt_photo(org_cred, '{meal_id}', png_bytes, 'image/png', 1, 1)
auth.close()

print("ORG_CRED:" + org_cred)
print("Seeding successful:", meta['filename'])
"""
        seed_out = run_cmd(
            ["docker", "run", "--rm", "-v", f"{src_volume}:/data", image_tag, "python", "-c", seed_script],
            "Seed synthetic meal and receipt photo into source volume",
        )
        org_cred = [line.split(":", 1)[1].strip() for line in seed_out.splitlines() if line.startswith("ORG_CRED:")][0]

        # 3. Execute the documented backup command using the source volume
        backup_cmd = [
            "docker", "run", "--rm",
            "-v", f"{src_volume}:/data",
            "-v", f"{host_backup_dir}:/backups",
            image_tag,
            "python", "tools/backup_restore.py", "backup",
            "--db", "/data/settletable.sqlite",
            "--photos", "/data/receipt_photos",
            "--out-dir", "/backups",
        ]
        backup_out = run_cmd(backup_cmd, "Execute documented backup command in Docker")

        # 4. Verify backup on host filesystem
        manifest_files = list(Path(host_backup_dir).glob("manifest_*.json"))
        if not manifest_files:
            raise RuntimeError(f"No manifest file generated in host backup dir: {host_backup_dir}")
        manifest_file = manifest_files[0]
        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        print(f"  * Backup verified on host: {manifest_file.name} (Photo count: {manifest_data['photo_count']})")
        assert manifest_data["photo_count"] == 1, f"Expected 1 photo, got {manifest_data['photo_count']}"

        # 5. Execute the documented restore command into the isolated destination volume
        # (Passes --skip-health-check and --skip-docker-check since this runs inside an ephemeral container)
        restore_cmd = [
            "docker", "run", "--rm",
            "-v", f"{dest_volume}:/data",
            "-v", f"{host_backup_dir}:/backups",
            image_tag,
            "python", "tools/backup_restore.py", "restore",
            "--manifest", f"/backups/{manifest_file.name}",
            "--dest-db", "/data/settletable.sqlite",
            "--dest-photos", "/data/receipt_photos",
            "--confirm-stopped",
            "--skip-health-check",
            "--skip-docker-check",
        ]
        restore_out = run_cmd(restore_cmd, "Execute documented restore command into destination volume")

        # 6. Verify restored database, receipt photo, and organizer authentication
        verify_script = f"""
import sqlite3, hashlib
from pathlib import Path
from settletable.authority import Authority

db_path = Path('/data/settletable.sqlite')
storage_dir = Path('/data/receipt_photos')

# Check SQLite integrity
conn = sqlite3.connect(db_path)
integrity = conn.execute("PRAGMA integrity_check;").fetchone()
conn.close()
assert integrity[0] == 'ok', f"Integrity check failed: {{integrity}}"

# Check meal and organizer authentication
auth = Authority(db_path, storage_dir=storage_dir)
snapshot = auth.snapshot('{org_cred}', '{meal_id}')
assert snapshot.meal_id == '{meal_id}'
assert len(snapshot.participants) == 2

# Authenticate organizer and verify receipt photo
part_id, is_org = auth.authenticate('{org_cred}', '{meal_id}')
assert is_org is True, "Organizer authentication failed"
photo_bytes, meta = auth.get_receipt_photo('{org_cred}', '{meal_id}')
actual_sha = hashlib.sha256(photo_bytes).hexdigest()
assert actual_sha == '{expected_photo_sha}', f"Photo hash mismatch: {{actual_sha}}"

auth.close()
print("Restored database integrity, meal snapshot, and receipt photo hash verified successfully!")
"""
        run_cmd(
            ["docker", "run", "--rm", "-v", f"{dest_volume}:/data", image_tag, "python", "-c", verify_script],
            "Verify restored volume integrity, photo hash, and organizer access",
        )

        # 7. Confirm that production volume 'settletable_data' is untouched
        print("  * Checking primary application volume protection ... ", end="", flush=True)
        # Verify settletable_data does not contain the drill meal id
        check_prod_script = f"""
from pathlib import Path
import sqlite3
prod_db = Path('/data/settletable.sqlite')
if prod_db.exists():
    conn = sqlite3.connect(prod_db)
    has_meal = conn.execute("SELECT 1 FROM meals WHERE id='{meal_id}';").fetchone()
    conn.close()
    assert not has_meal, "CRITICAL: Drill meal was written to primary volume!"
"""
        run_cmd(
            ["docker", "run", "--rm", "-v", "settletable_data:/data", image_tag, "python", "-c", check_prod_script],
            "Confirmed primary volume was not modified by the drill",
        )

        print(f"\n[DRILL SUCCESS] All isolated backup and restore operations verified successfully!")
        return 0

    finally:
        # Cleanup isolated resources
        print("\nCleaning up drill resources:")
        try:
            subprocess.run(["docker", "volume", "rm", "-f", src_volume], capture_output=True)
            print(f"  - Removed {src_volume}")
        except Exception:
            pass
        try:
            subprocess.run(["docker", "volume", "rm", "-f", dest_volume], capture_output=True)
            print(f"  - Removed {dest_volume}")
        except Exception:
            pass
        try:
            shutil.rmtree(host_backup_dir, ignore_errors=True)
            print(f"  - Removed {host_backup_dir}")
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
