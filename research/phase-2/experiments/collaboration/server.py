"""DISPOSABLE localhost transport probe; synthetic bearer identities, no production auth.
Run: python research/phase-2/experiments/collaboration/server.py
Only 127.0.0.1:8766; in-memory state is discarded on exit. Never deploy this fixture.
"""
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import importlib.util
import json
from pathlib import Path
import threading
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
MODEL = HERE.parents[2] / "phase-1/experiments/collaboration/simulate.py"
spec = importlib.util.spec_from_file_location("phase1_disposable_model", MODEL)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
meal = module.Meal()
fixture_tokens = {"fixture-A": "A", "fixture-B": "B", "fixture-organizer": "organizer"}
barrier = threading.Barrier(2, timeout=60)
reports = []
arrivals = []
report_lock = threading.Lock()
authority_lock = threading.Lock()
receipt_total_sen = 1300  # Synthetic authoritative receipt; dish 1000 + tea 300.


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, status, value, html=False):
        body = value.encode() if html else json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8" if html else "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def actor(self):
        return fixture_tokens.get(self.headers.get("Authorization", "").removeprefix("Bearer "))

    def permitted(self):
        actor = self.actor()
        if actor not in meal.members:
            self.reply(403, {"error": "membership_revoked_or_unknown"})
            return None
        return actor

    def do_GET(self):
        path = urlparse(self.path)
        if path.path == "/":
            return self.reply(200, (HERE / "client.html").read_text(encoding="utf-8"), html=True)
        if path.path == "/results":
            return self.reply(200, self.results())
        if not self.permitted():
            return
        with meal.lock:
            if path.path == "/snapshot":
                return self.reply(200, meal.snapshot())
            if path.path == "/events":
                after = int(parse_qs(path.query).get("after", ["0"])[0])
                return self.reply(200, [deepcopy(e) for e in meal.events if e["sequence"] > after])
        self.reply(404, {"error": "not_found"})

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        except (ValueError, KeyError):
            return self.reply(400, {"error": "invalid_json"})
        # Evidence collection is fixture-only, intentionally independent of revoked meal access.
        if self.path == "/report":
            with report_lock:
                reports.append(body)
                data = self.results()
                (HERE / "results.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
            return self.reply(200, {"recorded": True})
        actor = self.permitted()
        if not actor:
            return
        if self.path == "/fixture-revoke":
            if actor != "organizer":
                return self.reply(403, {"error": "organizer_only_transition"})
            with meal.lock:
                meal.members.discard(body["person"])
            return self.reply(200, {"revoked": body["person"]})
        if self.path == "/op":
            if body.get("race"):
                arrivals.append({"actor": actor, "received_utc": datetime.now(timezone.utc).isoformat()})
                try:
                    barrier.wait()
                except threading.BrokenBarrierError:
                    return self.reply(408, {"error": "race_fixture_timed_out"})
            try:
                with authority_lock:
                    # New experiment gate: the Phase 1 simulation checked quantities/review,
                    # but did not check authoritative receipt-total reconciliation.
                    # Fixture has no fees/discounts; do not generalize this sum to production.
                    if (body["kind"] == "finalize" and actor == "organizer"
                            and body["expected"] == meal.revision and meal.reviewed
                            and sum(item["line_sen"] for item in meal.items.values()) != receipt_total_sen):
                        raise module.Rejected("receipt_total_mismatch")
                    result = meal.apply(actor, body["id"], body["kind"], body["expected"], body["payload"])
                return self.reply(200, result)
            except module.Rejected as error:
                return self.reply(409, {"error": str(error)})
        self.reply(404, {"error": "not_found"})

    def results(self):
        return {"scope": "DISPOSABLE real localhost HTTP and two browser-tab clients; NOT production authentication or Internet validation",
                "access_date": datetime.now(timezone.utc).isoformat(),
                "reports": deepcopy(reports), "race_request_arrivals": deepcopy(arrivals),
                "final_snapshot": meal.snapshot(), "money": "integer sen",
                "receipt_total_sen": receipt_total_sen,
                "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in [HERE / "server.py", HERE / "client.html", HERE / "run-browser.cjs", MODEL]},
                "limitations": ["Two tabs, not different physical devices or browser engines",
                                "HTTP polling/snapshot only; no SSE/WebSocket or Internet faults",
                                "In-memory lock, no database transaction or restart durability",
                                "Public synthetic fixture tokens and fixture revocation endpoint; never production auth",
                                "Browser A deliberately holds synthetic organizer token for organizer scenarios",
                                "No receipt images, external service, private data or paid calls"]}


if __name__ == "__main__":
    print("DISPOSABLE fixture: http://127.0.0.1:8766/?actor=A and ?actor=B", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8766), Handler).serve_forever()
