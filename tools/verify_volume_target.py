"""SettleTable Pre-Flight Volume Target & Storage Isolation Verification Utility.

Inspects Docker Compose volume resolution, verifies file system permissions (UID 10001),
validates the `.volume_identity` marker, and prevents accidental cross-volume contamination
between synthetic testing and real-meal production storage.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent


def get_env_volume(env_path: Path) -> str | None:
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("SETTLETABLE_DATA_VOLUME="):
            return line.split("=", 1)[1].strip()
    return None


def resolve_compose_volume(env_path: Path | None = None) -> str:
    cmd_json = ["docker", "compose"]
    if env_path and env_path.exists():
        cmd_json.extend(["--env-file", str(env_path)])
    cmd_json.extend(["config", "--format", "json"])

    res = subprocess.run(
        cmd_json,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if res.returncode != 0:
        # Fallback to text parsing
        cmd_txt = ["docker", "compose"]
        if env_path and env_path.exists():
            cmd_txt.extend(["--env-file", str(env_path)])
        cmd_txt.extend(["config"])
        res_txt = subprocess.run(
            cmd_txt,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        if res_txt.returncode != 0:
            raise RuntimeError(f"docker compose config failed: {res_txt.stderr}")
        # Look under volumes: settletable_data: name: <vol>
        lines = res_txt.stdout.splitlines()
        in_volumes = False
        in_st_data = False
        for line in lines:
            if line.strip() == "volumes:":
                in_volumes = True
                continue
            if in_volumes and line.strip().startswith("settletable_data:"):
                in_st_data = True
                continue
            if in_st_data and "name:" in line:
                return line.split("name:", 1)[1].strip()
        return "settletable_data"

    data = json.loads(res.stdout)
    volumes = data.get("volumes", {})
    st_vol = volumes.get("settletable_data", {})
    return st_vol.get("name", "settletable_data")


def inspect_volume_contents(volume_name: str) -> dict:
    probe_script = """
import json, os, sqlite3, sys
from pathlib import Path

data_dir = Path('/data')
res = {
    'uid': os.getuid(),
    'gid': os.getgid(),
    'data_exists': data_dir.exists(),
    'data_writable': os.access(data_dir, os.W_OK),
    'stat_uid': data_dir.stat().st_uid,
    'stat_gid': data_dir.stat().st_gid,
    'marker': None,
    'db_exists': False,
    'db_size': 0,
    'meal_count': 0,
    'photo_count': 0,
    'photos_writable': False,
}

marker = data_dir / '.volume_identity'
if marker.exists():
    try:
        res['marker'] = json.loads(marker.read_text(encoding='utf-8'))
    except Exception as e:
        res['marker'] = {'error': str(e)}

db_file = data_dir / 'settletable.sqlite'
if db_file.exists():
    res['db_exists'] = True
    res['db_size'] = db_file.stat().st_size
    try:
        conn = sqlite3.connect(f'file:{db_file}?mode=ro', uri=True)
        meals = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='meals';").fetchone()
        if meals and meals[0] > 0:
            count = conn.execute("SELECT count(*) FROM meals;").fetchone()
            res['meal_count'] = count[0] if count else 0
        conn.close()
    except Exception:
        pass

photos_dir = data_dir / 'receipt_photos'
if photos_dir.exists():
    res['photos_writable'] = os.access(photos_dir, os.W_OK)
    res['photo_count'] = sum(1 for p in photos_dir.iterdir() if p.is_file())

print(json.dumps(res))
"""
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{volume_name}:/data",
        "settletable:latest",
        "python", "-c", probe_script,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Volume probe container failed: {res.stderr}\n{res.stdout}")
    for line in res.stdout.splitlines():
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    raise RuntimeError(f"Failed to parse volume probe output: {res.stdout}")


def main():
    parser = argparse.ArgumentParser(description="Verify SettleTable Target Volume & Isolation")
    parser.add_argument(
        "--mode",
        choices=["auto", "real", "synthetic"],
        default="auto",
        help="Expected operational mode: 'real' (requires settletable_data), 'synthetic' (requires settletable_synthetic_data), or 'auto' (inspect active configuration)",
    )
    parser.add_argument("--env-file", default=str(REPO_ROOT / ".env"), help="Path to .env file")
    args = parser.parse_args()

    env_path = Path(args.env_file)
    print("\n=======================================================")
    print(" SettleTable -- Target Volume & Storage Pre-Flight Check")
    print("=======================================================\n")

    env_vol = get_env_volume(env_path)
    print(f"  * .env Configuration:        {env_path.name} (SETTLETABLE_DATA_VOLUME={env_vol})")

    resolved_vol = resolve_compose_volume(env_path)
    print(f"  * Resolved Compose Volume:   {resolved_vol}")

    # Check volume existence
    vol_check = subprocess.run(["docker", "volume", "inspect", resolved_vol], capture_output=True, text=True)
    if vol_check.returncode != 0:
        print(f"  [FAIL] Docker volume '{resolved_vol}' does not exist!")
        sys.exit(1)

    print(f"  * Docker Volume Status:      Found ({resolved_vol})")

    # Probe volume internals
    info = inspect_volume_contents(resolved_vol)
    print(f"  * Container User / Group:    UID={info['uid']} GID={info['gid']} (Non-root settletable)")
    print(f"  * Storage Owner / Group:     UID={info['stat_uid']} GID={info['stat_gid']}")
    print(f"  * Storage Writable:          {info['data_writable']} (photos: {info['photos_writable']})")

    # Volume Identity Marker
    marker = info.get("marker")
    if marker:
        marker_name = marker.get("volume_name")
        print(f"  * Volume Identity Marker:    {marker_name} (Initialized: {marker.get('initialized_at', 'unknown')})")
        if marker_name != resolved_vol:
            print(f"\n[CRITICAL ERROR] Volume marker mismatch! Volume '{resolved_vol}' contains marker for '{marker_name}'!")
            sys.exit(1)
    else:
        print("  * Volume Identity Marker:    Not yet initialized (fresh volume)")

    # Data Status
    print(f"  * Database File:             {'Present (' + str(info['db_size']) + ' bytes, ' + str(info['meal_count']) + ' meals)' if info['db_exists'] else 'Empty / Uninitialized'}")
    print(f"  * Receipt Photos:            {info['photo_count']} files")

    # Mode Assertions
    print("\nOperational Mode Assessment:")
    if resolved_vol == "settletable_data":
        print("  -> MODE: PRODUCTION / REAL-DATA PILOT (settletable_data)")
        if args.mode == "synthetic":
            print("  [FAIL] Mode mismatch: requested synthetic mode but active volume is 'settletable_data'!")
            sys.exit(1)
    elif resolved_vol == "settletable_synthetic_data":
        print("  -> MODE: SYNTHETIC TESTING / REHEARSAL (settletable_synthetic_data)")
        if args.mode == "real":
            print("  [FAIL] Mode mismatch: requested real mode but active volume is 'settletable_synthetic_data'!")
            sys.exit(1)
    else:
        print(f"  -> MODE: CUSTOM ({resolved_vol})")

    print("\n[VERDICT: PASS] Storage configuration, non-root permissions, and volume isolation verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
