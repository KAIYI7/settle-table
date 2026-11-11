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
    parser.add_argument("--mock-notion", action="store_true", help="Use deterministic mock Notion client for testing/demo")
    parser.add_argument("--mock-ocr", action="store_true", help="Use deterministic mock OCR engine for testing/demo")
    args = parser.parse_args()

    import os
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    origin = f"http://{args.host}:{args.port}"
    allowed_hosts = {f"{args.host}:{args.port}", f"localhost:{args.port}", args.host, "localhost"}

    notion_client = None
    if args.mock_notion or os.environ.get("SETTLETABLE_MOCK_NOTION") == "1":
        from settletable.notion import MockNotionClient
        notion_client = MockNotionClient()
        os.environ.setdefault("SETTLETABLE_NOTION_TOKEN", "secret_mock_notion_uat_testing_token_12345")

    ocr_engine = None
    if args.mock_ocr or os.environ.get("SETTLETABLE_MOCK_OCR") == "1":
        import json
        from settletable.ocr import MockOcrEngine, OcrLine
        fixtures_path = REPO_ROOT / "tests" / "fixtures" / "ocr" / "tokens.json"
        fixtures = {}
        if fixtures_path.exists():
            with open(fixtures_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, lines_raw in data.items():
                fixtures[k] = [
                    OcrLine(text=l["text"], score=l["score"], box=tuple(tuple(pt) for pt in l["box"]))
                    for l in lines_raw
                ]
        default_lines = [
            OcrLine("RESTORAN WAN SHENG", 0.98, ((10, 10), (100, 10), (100, 30), (10, 30))),
            OcrLine("NO. 12 JALAN PUDU", 0.96, ((10, 35), (100, 35), (100, 50), (10, 50))),
            OcrLine("1 CHICKEN RICE 12.00", 0.95, ((10, 55), (100, 55), (100, 75), (10, 75))),
            OcrLine("1 ICE LEMON TEA 3.20", 0.94, ((10, 80), (100, 80), (100, 100), (10, 100))),
            OcrLine("SUBTOTAL 15.20", 0.96, ((10, 110), (100, 110), (100, 130), (10, 130))),
            OcrLine("SERVICE CHARGE 1.52", 0.95, ((10, 140), (100, 140), (100, 160), (10, 160))),
            OcrLine("ROUNDING -0.02", 0.93, ((10, 170), (100, 170), (100, 190), (10, 190))),
            OcrLine("TOTAL 16.70", 0.98, ((10, 200), (100, 200), (100, 220), (10, 220))),
        ]
        ocr_engine = MockOcrEngine(fixtures=fixtures, default_lines=default_lines)

    from settletable.public_creation import PublicCreationConfig, PublicCreationGate
    pub_cfg = PublicCreationConfig.from_env(origin)
    pub_cfg.enabled = True
    pub_cfg.rate_limit_burst = 50
    pub_cfg.rate_limit_hourly = 200
    pub_cfg.rate_limit_daily = 500
    pub_gate = PublicCreationGate(pub_cfg)

    app = SettleTableApp(
        db_path,
        server_origin=origin,
        allowed_hosts=allowed_hosts,
        notion_client=notion_client,
        ocr_engine=ocr_engine,
        public_creation_gate=pub_gate,
    )

    print("=" * 60)
    print(" SettleTable - Local Browser MVP Demo Server")
    print("=" * 60)
    print(f" URL:         {origin}")
    print(f" Database:    {db_path.resolve()}")
    print(" Architecture: Zero-dependency WSGI + SQLite WAL + Vanilla ES2022")
    print("=" * 60)
    print(" Press Ctrl+C to stop.\n")

    try:
        with make_server(args.host, args.port, app) as httpd:
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\nShutting down demo server.")
            finally:
                app.close()
    except (PermissionError, OSError) as e:
        print(f"\n[ERROR] Unable to bind to {args.host}:{args.port} ({e}).")
        print(f"Port {args.port} is already in use by another application on your system.")
        print("Please choose an available port, for example:")
        print("    python tools/run_demo.py --port 8000 --mock-ocr --mock-notion")
        print("    python tools/run_demo.py --port 8095 --mock-ocr --mock-notion\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
