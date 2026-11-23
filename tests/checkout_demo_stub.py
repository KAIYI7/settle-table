"""In-process stub of the experimental bridge integration API (KP-SETTLETABLE-TNG-01 v2.1).

Test fixture only. It follows the design's wire contract and is not the bridge:
- PUT/GET /api/integrations/checkouts/{reference}, Bearer integration credential.
- PUT body exactly {"amountMinor": int, "currency": "MYR"}; reference lookup runs
  before the held-amount check; 201 create, 200 replay, 409 REFERENCE_CONFLICT,
  409 SAME_AMOUNT_HELD, 503 STORE_UNAVAILABLE.
- GET returns the 9-field allowlist or 404 {"error":"REFERENCE_NOT_FOUND"}.
- Every other route 404 {"error":"NOT_FOUND"}; errors are {"error": CODE}.
Control helpers mutate the store in-process (the organizer's bridge actions).

Observed-evidence mode (``observed_amount`` set) follows the KP-SETTLETABLE-TNG-02
v1.3 wire section that the G1 bridge implements: the PUT order for a new reference is
pinned amount (409 OBSERVED_AMOUNT_MISMATCH) -> single use (409
OBSERVED_CHECKOUT_SPENT) -> held amount; a replay of the bound reference still
returns 200 first; success bodies carry one extra key, evidenceMode
"OBSERVED_NOTIFICATION"; evidence is NOTIFICATION_UNVERIFIED. With
``observed_amount=None`` every synthetic byte is unchanged.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import threading
import uuid

PATH = re.compile(r'/api/integrations/checkouts/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})')
OPEN = {'AWAITING_PAYMENT', 'PAYMENT_DETECTED', 'AWAITING_VERIFICATION', 'AMBIGUOUS'}


class StubBridge:
    def __init__(self, token, control_nonce=None, observed_amount=None):
        self.token = token
        self.control_nonce = control_nonce
        self.observed_amount = observed_amount
        self.lock = threading.Lock()
        self.checkouts = {}        # reference -> allowlisted checkout dict
        self.other_holds = set()   # amounts held by non-integration checkouts
        self.calls = []            # (method, path, headers, body)
        self.fail = None           # None | 'store' | 'malformed' | 'drop' | (status, body)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), self._handler())
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self):
        return f'http://127.0.0.1:{self.server.server_port}'

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    # --- organizer/bridge-side control (synthetic evidence, review, expiry, loss) ---
    def transition(self, reference, status=None, evidence=None, review_expires_at=None, bump=1):
        with self.lock:
            checkout = self.checkouts[reference]
            if status is not None:
                checkout['status'] = status
            if evidence is not None:
                checkout['evidence'] = evidence
            if review_expires_at is not None:
                checkout['reviewExpiresAt'] = review_expires_at
            checkout['revision'] += bump
            return dict(checkout)

    def simulate_candidate(self, reference):
        return self.transition(reference, 'AWAITING_VERIFICATION', 'SYNTHETIC', '2026-11-17T04:30:00Z')

    def confirm(self, reference):
        if self.observed_amount is not None:
            return self.transition(reference, 'MANUALLY_CONFIRMED', 'NOTIFICATION_UNVERIFIED')
        return self.transition(reference, 'MANUALLY_CONFIRMED', 'SYNTHETIC')

    def observe_notification(self, reference, status='PAYMENT_DETECTED'):
        """Observed mode: a unique in-window wallet notification was matched (no text, no sender)."""
        return self.transition(reference, status, 'NOTIFICATION_UNVERIFIED', '2026-11-17T04:40:00Z')

    def ambiguous(self, reference):
        return self.transition(reference, 'AMBIGUOUS')

    def review_expire(self, reference):
        return self.transition(reference, 'REVIEW_EXPIRED')

    def synthetic_mode(self, reference=None):
        """Browser tests only: from now on answer as a synthetic-only bridge (no evidenceMode key)."""
        with self.lock:
            self.observed_amount = None
            return {'mode': 'synthetic'}

    def expire(self, reference):
        return self.transition(reference, 'EXPIRED')

    def lose_snapshot(self):
        with self.lock:
            self.checkouts.clear()

    def only(self):
        with self.lock:
            (reference, checkout), = self.checkouts.items()
            return reference, dict(checkout)

    # --- wire contract ---
    def _put(self, reference, raw):
        try:
            body = json.loads(raw, object_pairs_hook=_strict_pairs)
        except ValueError:
            return 400, {'error': 'INVALID_REQUEST'}
        if (type(body) is not dict or set(body) != {'amountMinor', 'currency'} or body['currency'] != 'MYR'
                or type(body['amountMinor']) is not int or not 1 <= body['amountMinor'] <= 1_000_000_000):
            return 400, {'error': 'INVALID_REQUEST'}
        amount = body['amountMinor']
        with self.lock:
            known = self.checkouts.get(reference)
            if known is not None:  # Lookup first: a replay is never blocked by its own hold.
                if known['amountMinor'] != amount:
                    return 409, {'error': 'REFERENCE_CONFLICT'}
                return 200, dict(known)
            if self.observed_amount is not None:
                if amount != self.observed_amount:
                    return 409, {'error': 'OBSERVED_AMOUNT_MISMATCH'}
                if self.checkouts:
                    return 409, {'error': 'OBSERVED_CHECKOUT_SPENT'}
            held = {c['amountMinor'] for c in self.checkouts.values() if c['status'] in OPEN} | self.other_holds
            if amount in held:
                return 409, {'error': 'SAME_AMOUNT_HELD'}
            checkout = {'reference': reference, 'checkoutId': str(uuid.uuid4()), 'amountMinor': amount,
                        'status': 'AWAITING_PAYMENT', 'evidence': 'NONE',
                        'createdAt': '2026-11-17T04:00:00.123456789Z', 'expiresAt': '2026-11-17T04:10:00.123456789Z',
                        'reviewExpiresAt': None, 'revision': 1}
            if self.observed_amount is not None:
                checkout['evidenceMode'] = 'OBSERVED_NOTIFICATION'
            self.checkouts[reference] = checkout
            return 201, dict(checkout)

    def _get(self, reference):
        with self.lock:
            known = self.checkouts.get(reference)
            return (200, dict(known)) if known is not None else (404, {'error': 'REFERENCE_NOT_FOUND'})

    def _handler(self):
        stub = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def _send(self, status, payload, content_type='application/json'):
                raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(raw)
                self.close_connection = True

            def _dispatch(self, method):
                raw = self.rfile.read(int(self.headers.get('Content-Length') or 0))
                if stub.control_nonce and self.path.startswith(f'/__control/{stub.control_nonce}/'):
                    return self._send(*stub._control(method, self.path, raw))
                stub.calls.append((method, self.path, dict(self.headers), raw))
                if method not in ('GET', 'PUT'):
                    return self._send(405, {'error': 'METHOD_INVALID'})
                match = PATH.fullmatch(self.path)
                if self.headers.get('Authorization') != 'Bearer ' + stub.token:
                    return self._send(401, {'error': 'UNAUTHORIZED'})
                if match is None:
                    return self._send(404, {'error': 'NOT_FOUND'})
                if method == 'PUT' and self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    return self._send(415, {'error': 'CONTENT_TYPE_INVALID'})
                failure = stub.fail
                if failure == 'drop':
                    self.close_connection = True
                    return
                if failure == 'store':
                    return self._send(503, {'error': 'STORE_UNAVAILABLE'})
                if failure == 'malformed':
                    return self._send(200, b'{"reference":"x"}')
                if isinstance(failure, tuple):
                    return self._send(*failure)
                status, payload = stub._put(match.group(1), raw) if method == 'PUT' else stub._get(match.group(1))
                return self._send(status, payload)

            def do_PUT(self):
                self._dispatch('PUT')

            def do_GET(self):
                self._dispatch('GET')

            def do_POST(self):
                self._dispatch('POST')

        return Handler

    def _control(self, method, path, raw):
        """Browser-test control channel; requires a per-run random nonce."""
        action = path.rsplit('/', 1)[-1]
        if action == 'state' and method == 'GET':
            with self.lock:
                return 200, {'checkouts': list(self.checkouts.values()),
                             'calls': [[m, p] for m, p, _, _ in self.calls]}
        if method != 'POST':
            return 405, {'error': 'METHOD_INVALID'}
        with self.lock:
            if not self.checkouts:
                return 409, {'error': 'NO_CHECKOUT'}
            reference = list(self.checkouts)[-1]  # The most recently created checkout.
        actions = {'candidate': self.simulate_candidate, 'confirm': self.confirm, 'expire': self.expire}
        if self.observed_amount is not None:
            actions = {'notification': self.observe_notification, 'confirm': self.confirm, 'expire': self.expire,
                       'ambiguous': self.ambiguous, 'review-expire': self.review_expire,
                       'synthetic-mode': self.synthetic_mode}
        if action not in actions:
            return 404, {'error': 'NOT_FOUND'}
        return 200, actions[action](reference)


def _strict_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('duplicate')
        out[key] = value
    return out
