"""Production WSGI application entrypoint for SettleTable.

Loads runtime configuration from environment variables and exposes
a standard WSGI application callable (`application` / `app`) for
production servers (Gunicorn, Waitress, uWSGI, etc.).
"""
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import uuid

from settletable.transport import SettleTableApp

logger = logging.getLogger("settletable.wsgi")


def check_volume_identity(db_path: Path, volume_env: str | None) -> None:
    """Verify or initialize volume identity marker to prevent cross-volume contamination."""
    if not volume_env:
        return
    data_dir = db_path.parent
    if not data_dir.exists():
        return

    marker_file = data_dir / ".volume_identity"

    # Detect existing dataset (database file or existing receipt photos)
    photos_dir = data_dir / "receipt_photos"
    has_existing_dataset = db_path.exists() or (
        photos_dir.exists() and any(photos_dir.iterdir())
    )

    if marker_file.exists():
        try:
            raw_text = marker_file.read_text(encoding="utf-8")
        except OSError as e:
            raise RuntimeError(
                f"CRITICAL: Volume identity marker at '{marker_file}' is unreadable ({e}). "
                f"Aborting startup to prevent accidental data corruption."
            ) from e

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"CRITICAL: Volume identity marker at '{marker_file}' is malformed JSON ({e}). "
                f"Aborting startup to prevent accidental data corruption."
            ) from e

        if not isinstance(data, dict) or not data.get("volume_name"):
            raise RuntimeError(
                f"CRITICAL: Volume identity marker at '{marker_file}' is missing 'volume_name'. "
                f"Aborting startup to prevent accidental data corruption."
            )

        recorded_volume = data["volume_name"]
        if recorded_volume != volume_env:
            raise RuntimeError(
                f"CRITICAL: Volume identity mismatch! Container configured with "
                f"SETTLETABLE_DATA_VOLUME='{volume_env}', but mounted storage directory '{data_dir}' "
                f"contains marker for '{recorded_volume}'. "
                f"Aborting startup to protect against cross-volume contamination."
            )
    else:
        # Marker does not exist
        if has_existing_dataset:
            raise RuntimeError(
                f"CRITICAL: Unmarked existing dataset detected at '{data_dir}' (database or photos exist, "
                f"but '.volume_identity' marker is missing). Aborting startup to protect unverified data."
            )

        # Genuinely fresh volume: initialize marker atomically
        tmp_marker = data_dir / f".volume_identity.tmp.{uuid.uuid4().hex[:8]}"
        try:
            marker_data = {
                "volume_name": volume_env,
                "initialized_at": datetime.now(timezone.utc).isoformat(),
            }
            tmp_marker.write_text(json.dumps(marker_data, indent=2), encoding="utf-8")
            tmp_marker.replace(marker_file)
            logger.info("Initialized volume identity marker for '%s' at %s", volume_env, marker_file)
        except OSError as e:
            if tmp_marker.exists():
                try:
                    tmp_marker.unlink()
                except OSError:
                    pass
            raise RuntimeError(
                f"CRITICAL: Failed to initialize volume identity marker on fresh volume '{data_dir}': {e}. "
                f"Aborting startup."
            ) from e


def create_app() -> SettleTableApp:
    """Create and configure a SettleTableApp instance from environment variables."""
    db_path = os.environ.get("SETTLETABLE_DB_PATH", ".local/settletable.sqlite")
    volume_env = os.environ.get("SETTLETABLE_DATA_VOLUME")
    if volume_env:
        check_volume_identity(Path(db_path), volume_env)

    storage_dir = os.environ.get("SETTLETABLE_STORAGE_DIR")
    server_origin = os.environ.get("SETTLETABLE_SERVER_ORIGIN", "http://localhost:8000").rstrip("/")

    allowed_hosts_str = os.environ.get(
        "SETTLETABLE_ALLOWED_HOSTS",
        "localhost:8000,127.0.0.1:8000,localhost,127.0.0.1"
    )
    allowed_hosts = [h.strip() for h in allowed_hosts_str.split(",") if h.strip()]

    allow_sync_export = os.environ.get("SETTLETABLE_ALLOW_SYNC_EXPORT", "0").lower() in ("1", "true", "yes")

    session_ttl = None
    session_ttl_str = os.environ.get("SETTLETABLE_SESSION_TTL")
    if session_ttl_str:
        try:
            val = int(session_ttl_str)
            if 1 <= val <= 2592000:
                session_ttl = val
        except ValueError:
            pass

    # Mock clients (strictly for testing and demonstration)
    notion_client = None
    if os.environ.get("SETTLETABLE_MOCK_NOTION") == "1":
        from settletable.notion import MockNotionClient
        notion_client = MockNotionClient()

    ocr_engine = None
    if os.environ.get("SETTLETABLE_MOCK_OCR") == "1":
        from settletable.ocr import MockOcrEngine
        ocr_engine = MockOcrEngine()

    return SettleTableApp(
        db_path=db_path,
        storage_dir=storage_dir,
        allowed_hosts=allowed_hosts,
        server_origin=server_origin,
        notion_client=notion_client,
        ocr_engine=ocr_engine,
        allow_sync_export=allow_sync_export,
        session_ttl=session_ttl,
    )


# Standard WSGI callables for production runners
application = create_app()
app = application

if __name__ == "__main__":
    from wsgiref.simple_server import make_server
    host = os.environ.get("SETTLETABLE_HOST", "127.0.0.1")
    port = int(os.environ.get("SETTLETABLE_PORT", "8000"))
    print(f"Starting SettleTable WSGI server on http://{host}:{port}")
    with make_server(host, port, app) as httpd:
        httpd.serve_forever()
