"""Production WSGI application entrypoint for SettleTable.

Loads runtime configuration from environment variables and exposes
a standard WSGI application callable (`application` / `app`) for
production servers (Gunicorn, Waitress, uWSGI, etc.).
"""
import os
from pathlib import Path

from settletable.transport import SettleTableApp


def create_app() -> SettleTableApp:
    """Create and configure a SettleTableApp instance from environment variables."""
    db_path = os.environ.get("SETTLETABLE_DB_PATH", ".local/settletable.sqlite")
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
