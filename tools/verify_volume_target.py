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
else:
    res['photos_writable'] = res['data_writable']

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


def validate_configuration(env_vol: str | None, resolved_vol: str, mode: str) -> None:
    """Validate environment consistency and operational mode assertions."""
    # 1. Check configuration consistency if .env specifies a volume
    if env_vol and env_vol != resolved_vol:
        raise ValueError(
            f"Configuration conflict: .env specifies SETTLETABLE_DATA_VOLUME='{env_vol}', "
            f"but Docker Compose resolved '{resolved_vol}'!"
        )

    # 2. Enforce mode assertions strictly (fail closed)
    if mode == "real":
        if resolved_vol != "settletable_data":
            raise ValueError(
                f"Mode mismatch: mode 'real' strictly requires volume 'settletable_data', "
                f"but resolved volume is '{resolved_vol}'!"
            )
    elif mode == "synthetic":
        if resolved_vol != "settletable_synthetic_data":
            raise ValueError(
                f"Mode mismatch: mode 'synthetic' strictly requires volume 'settletable_synthetic_data', "
                f"but resolved volume is '{resolved_vol}'!"
            )
    elif mode == "auto":
        if resolved_vol not in ("settletable_data", "settletable_synthetic_data"):
            raise ValueError(
                f"Unexpected volume '{resolved_vol}'. SettleTable strictly requires "
                f"'settletable_data' or 'settletable_synthetic_data'!"
            )


def validate_storage_permissions(info: dict) -> None:
    """Enforce non-root ownership and storage writability invariants."""
    if info.get("uid") != 10001 or info.get("gid") != 10001:
        raise PermissionError(
            f"Container user mismatch: expected UID=10001 GID=10001 (settletable), "
            f"got UID={info.get('uid')} GID={info.get('gid')}!"
        )
    if info.get("stat_uid") != 10001 or info.get("stat_gid") != 10001:
        raise PermissionError(
            f"Storage directory ownership mismatch: volume '/data' is owned by "
            f"UID={info.get('stat_uid')} GID={info.get('stat_gid')}, but must be owned by UID=10001 GID=10001!"
        )
    if not info.get("data_writable"):
        raise PermissionError("Storage directory '/data' is not writable by non-root user (UID 10001)!")
    if not info.get("photos_writable"):
        raise PermissionError("Receipt photos directory '/data/receipt_photos' is not writable by non-root user (UID 10001)!")


def validate_marker_integrity(resolved_vol: str, info: dict) -> None:
    """Validate volume identity marker integrity against resolved volume."""
    marker = info.get("marker")
    if marker:
        if isinstance(marker, dict) and "error" in marker:
            raise RuntimeError(f"Corrupt or unreadable volume marker on '{resolved_vol}': {marker['error']}")
        marker_name = marker.get("volume_name") if isinstance(marker, dict) else None
        if not marker_name:
            raise RuntimeError(f"Invalid volume marker on '{resolved_vol}': missing 'volume_name'")
        if marker_name != resolved_vol:
            raise RuntimeError(
                f"CRITICAL: Volume marker mismatch! Volume '{resolved_vol}' contains marker for '{marker_name}'!"
            )
    elif info.get("db_exists") or info.get("photo_count", 0) > 0:
        raise RuntimeError(
            f"CRITICAL: Unmarked existing dataset detected on volume '{resolved_vol}' (database or photos exist without .volume_identity marker)!"
        )


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

    # 1. Enforce mode and configuration consistency
    try:
        validate_configuration(env_vol, resolved_vol, args.mode)
    except ValueError as e:
        print(f"\n  [FAIL] {e}")
        sys.exit(1)

    # 2. Check volume existence in Docker daemon
    vol_check = subprocess.run(["docker", "volume", "inspect", resolved_vol], capture_output=True, text=True)
    if vol_check.returncode != 0:
        print(f"  [FAIL] Docker volume '{resolved_vol}' does not exist!")
        sys.exit(1)

    print(f"  * Docker Volume Status:      Found ({resolved_vol})")

    # 3. Probe volume internals (read-only, non-mutating)
    info = inspect_volume_contents(resolved_vol)
    print(f"  * Container User / Group:    UID={info['uid']} GID={info['gid']} (Non-root settletable)")
    print(f"  * Storage Owner / Group:     UID={info['stat_uid']} GID={info['stat_gid']}")
    print(f"  * Storage Writable:          {info['data_writable']} (photos: {info['photos_writable']})")

    # 4. Enforce non-root ownership and writability invariants
    try:
        validate_storage_permissions(info)
    except PermissionError as e:
        print(f"\n  [FAIL] {e}")
        sys.exit(1)

    # 5. Enforce volume marker integrity
    marker = info.get("marker")
    if marker and isinstance(marker, dict) and marker.get("volume_name"):
        print(f"  * Volume Identity Marker:    {marker['volume_name']} (Initialized: {marker.get('initialized_at', 'unknown')})")
    else:
        print("  * Volume Identity Marker:    Not yet initialized (fresh volume)")

    try:
        validate_marker_integrity(resolved_vol, info)
    except RuntimeError as e:
        print(f"\n  [FAIL] {e}")
        sys.exit(1)

    # 6. Report Data Status
    print(f"  * Database File:             {'Present (' + str(info['db_size']) + ' bytes, ' + str(info['meal_count']) + ' meals)' if info['db_exists'] else 'Empty / Uninitialized'}")
    print(f"  * Receipt Photos:            {info['photo_count']} files")

    # Mode Assessment Display
    print("\nOperational Mode Assessment:")
    if resolved_vol == "settletable_data":
        print("  -> MODE: PRODUCTION / REAL-DATA PILOT (settletable_data)")
    elif resolved_vol == "settletable_synthetic_data":
        print("  -> MODE: SYNTHETIC TESTING / REHEARSAL (settletable_synthetic_data)")

    print("\n[VERDICT: PASS] Storage configuration, non-root permissions, and volume isolation verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
