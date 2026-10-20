"""Local development and demonstration runner for SettleTable."""
import argparse
from pathlib import Path
import sys
from wsgiref.simple_server import make_server

# Ensure package root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from settletable.transport import SettleTableApp


def main():
    parser = argparse.ArgumentParser(description="Run SettleTable local demo server")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--db", default=".local/demo.sqlite", help="SQLite database path")
    args = parser.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    origin = f"http://{args.host}:{args.port}"
    app = SettleTableApp(db_path, server_origin=origin)

    print("=" * 60)
    print(" SettleTable - Local Browser MVP Demo Server")
    print("=" * 60)
    print(f" URL:         {origin}")
    print(f" Database:    {db_path.resolve()}")
    print(" Architecture: Zero-dependency WSGI + SQLite WAL + Vanilla ES2022")
    print("=" * 60)
    print(" Press Ctrl+C to stop.\n")

    with make_server(args.host, args.port, app) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down demo server.")
        finally:
            app.close()


if __name__ == "__main__":
    main()
