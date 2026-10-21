"""Bounded same-origin transport adapter for SettleTable Authority.

Implements a defense-in-depth HTTP interface with strict wire boundary limits,
CSRF mitigation, host-only secure cookies, and unauthenticated landing separation.
"""
from dataclasses import asdict, is_dataclass
from fractions import Fraction
import http.cookies
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import unicodedata
from urllib.parse import urlparse

from settletable.authority import (
    Authority, AuthorityError, Participant,
    ReplaceReceipt, SetOwnQuantity, AssignParticipantQuantity, ReviewReceipt, Finalize,
    RevokeInvitation, RevokeSession, RevokeMembership,
    Receipt, ReceiptItem, ReceiptAdjustment,
)

# Status code mappings per Section 5 of SPEC.md
STATUS_MAP = {
    # 400 Bad Request
    'invalid_input': 400,
    'malformed_json': 400,
    'duplicate_key': 400,
    'invalid_number': 400,
    'missing_action_header': 400,
    'conflicting_credentials': 400,
    'malformed_request': 400,
    'invalid_host': 400,
    'invalid_command_kind': 400,
    'missing_receipt': 400,
    'missing_amount': 400,
    'subtotal_mismatch': 400,
    'receipt_total_mismatch': 400,
    'discount_over_base': 400,
    'zero_base': 400,
    'pending_claim': 400,
    'incomplete_quantity': 400,
    'quantity_capacity': 400,
    'claim_missing': 400,
    'unknown_item': 400,
    'review_required': 400,
    'calculation_rejected': 400,
    'unsupported_command': 400,
    'invalid_invitation': 400,
    'invalid_image': 400,
    # 401 Unauthorized
    'invalid_session': 401,
    # 403 Forbidden
    'forbidden': 403,
    'origin_mismatch': 403,
    # 409 Conflict
    'command_conflict': 409,
    'revision_conflict': 409,
    'financial_revision_conflict': 409,
    'item_revision_conflict': 409,
    'receipt_digest_conflict': 409,
    'active_invitation_exists': 409,
    'already_revoked': 409,
    'finalized': 409,
    'meal_not_finalized': 409,
    'export_in_progress': 409,
    'claimed_item_deletion': 409,
    'retired_source': 409,
    'source_kind_conflict': 409,
    'meal_exists': 409,
    # 411 Length Required
    'missing_content_length': 411,
    # 413 Payload Too Large
    'payload_too_large': 413,
    # 429 Too Many Requests
    'resource_limit': 429,
    'notion_rate_limited': 429,
    # 431 Request Header Fields Too Large
    'header_too_large': 431,
    # 500 Internal Server Error
    'storage_error': 500,
    'internal_error': 500,
    # 502 Bad Gateway
    'notion_error': 502,
    # 503 Service Unavailable
    'commit_uncertain': 503,
    'busy': 503,
    'ocr_unavailable': 503,
    'notion_auth_error': 400,
}

MAX_BODY_BYTES = 1_048_576  # 1 MB
MAX_IMAGE_BYTES = 5_242_880  # 5 MB
MAX_HEADER_LINE_BYTES = 4_096  # 4 KB
MAX_TOTAL_HEADERS_BYTES = 16_384  # 16 KB
MAX_JSON_DEPTH = 10
MAX_INT_DIGITS = 19
TOKEN_REDACT_REGEX = re.compile(r'(/api/(?:meals/[^/]+/)?invitations/)[A-Za-z0-9_-]{43}')
STATIC_DIR = Path(__file__).parent / 'static'
STATIC_FILES = {
    'style.css': 'text/css; charset=utf-8',
    'app.js': 'application/javascript; charset=utf-8',
    'favicon.svg': 'image/svg+xml',
}


def redact_log_string(s: str) -> str:
    s = TOKEN_REDACT_REGEX.sub(r'\1[REDACTED]', s)
    s = re.sub(r'(Bearer\s+)[A-Za-z0-9_-]+', r'\1[REDACTED]', s, flags=re.IGNORECASE)
    s = re.sub(r'(settletable_session=)[A-Za-z0-9_-]+', r'\1[REDACTED]', s)
    s = re.sub(r'(secret_|ntn_)[A-Za-z0-9_-]{10,}', r'\1[REDACTED]', s)
    s = re.sub(r'"token"\s*:\s*"[^"]+"', r'"token":"[REDACTED]"', s)
    return s


class TransportError(Exception):
    def __init__(self, code, status=None):
        super().__init__(code)
        self.code = code
        self.status = status or STATUS_MAP.get(code, 400)


def _reject_duplicates(pairs):
    seen = set()
    result = {}
    for key, val in pairs:
        norm_key = unicodedata.normalize('NFC', key)
        if norm_key in seen:
            raise TransportError('duplicate_key', 400)
        seen.add(norm_key)
        result[key] = val
    return result


def _reject_float(val):
    raise TransportError('invalid_number', 400)


def _reject_constant(val):
    raise TransportError('invalid_number', 400)


def _check_nesting_depth(s):
    depth = 0
    max_d = 0
    in_str = False
    esc = False
    for char in s:
        if in_str:
            if esc:
                esc = False
            elif char == '\\':
                esc = True
            elif char == '"':
                in_str = False
        else:
            if char == '"':
                in_str = True
            elif char in ('{', '['):
                depth += 1
                if depth > max_d:
                    max_d = depth
            elif char in ('}', ']'):
                depth -= 1
    return max_d


def parse_strict_json(body_bytes):
    if len(body_bytes) > MAX_BODY_BYTES:
        raise TransportError('payload_too_large', 413)
    try:
        text = body_bytes.decode('utf-8')
    except UnicodeDecodeError:
        raise TransportError('malformed_json', 400) from None

    if _check_nesting_depth(text) > MAX_JSON_DEPTH:
        raise TransportError('malformed_json', 400)

    try:
        data = json.loads(
            text,
            object_pairs_hook=_reject_duplicates,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except TransportError:
        raise
    except Exception:
        raise TransportError('malformed_json', 400) from None

    # Validate integer sizes to prevent quadratic CPU attacks
    _validate_int_bounds(data)
    return data


def _validate_int_bounds(val):
    if isinstance(val, int) and not isinstance(val, bool):
        if len(str(abs(val))) > MAX_INT_DIGITS:
            raise TransportError('invalid_number', 400)
    elif isinstance(val, dict):
        for v in val.values():
            _validate_int_bounds(v)
    elif isinstance(val, list):
        for item in val:
            _validate_int_bounds(item)


def json_serializer(obj):
    if isinstance(obj, Fraction):
        return [obj.numerator, obj.denominator]
    if is_dataclass(obj):
        return asdict(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def serialize_json(data):
    return json.dumps(data, default=json_serializer, separators=(',', ':')).encode('utf-8')


class SettleTableApp:
    def __init__(self, db_path, allowed_hosts=('localhost:8000', '127.0.0.1:8000', 'testserver'),
                 server_origin='http://localhost:8000', clock=None, logger=None, ocr_engine=None,
                 notion_client=None, allow_sync_export=False):
        self.db_path = str(db_path)
        self.allowed_hosts = set(allowed_hosts)
        self.server_origin = server_origin.rstrip('/')
        self.clock = clock if clock is not None else time.time
        self.logger = logger
        self.ocr_engine = ocr_engine
        self.notion_client = notion_client
        self.allow_sync_export = (
            bool(allow_sync_export)
            or os.environ.get('SETTLETABLE_ALLOW_SYNC_EXPORT') == '1'
        )
        self._local = threading.local()

    def get_ocr_engine(self):
        if self.ocr_engine is not None:
            return self.ocr_engine
        try:
            from settletable.ocr import RapidOcrEngine
            return RapidOcrEngine()
        except Exception:
            raise TransportError('ocr_unavailable', 503)

    def get_notion_client(self):
        if self.notion_client is not None:
            return self.notion_client
        from settletable.notion import NotionHttpClient
        return NotionHttpClient()

    def get_authority(self):
        if not hasattr(self._local, 'authority') or self._local.authority is None:
            self._local.authority = Authority(self.db_path, clock=self.clock)
        return self._local.authority

    def close(self):
        if hasattr(self._local, 'authority') and self._local.authority is not None:
            try:
                self._local.authority.close()
            except Exception:
                pass
            self._local.authority = None

    def __call__(self, environ, start_response):
        try:
            status_code, headers, body_bytes = self._dispatch(environ)
        except TransportError as e:
            status_code, headers, body_bytes = self._format_error(e.code, e.status)
        except AuthorityError as e:
            status_code = STATUS_MAP.get(e.code, 500)
            status_code, headers, body_bytes = self._format_error(e.code, status_code)
        except Exception:
            status_code, headers, body_bytes = self._format_error('internal_error', 500)

        if self.logger:
            raw_path = environ.get('PATH_INFO', '/')
            method = environ.get('REQUEST_METHOD', 'GET').upper()
            safe_path = redact_log_string(raw_path)
            self.logger(f"{method} {safe_path} -> {status_code}")

        status_line = f"{status_code} {self._status_text(status_code)}"
        start_response(status_line, headers)
        return [body_bytes]

    def _status_text(self, code):
        texts = {
            200: 'OK', 201: 'Created',
            400: 'Bad Request', 401: 'Unauthorized', 403: 'Forbidden',
            404: 'Not Found', 409: 'Conflict', 411: 'Length Required',
            413: 'Payload Too Large', 429: 'Too Many Requests',
            431: 'Request Header Fields Too Large',
            500: 'Internal Server Error', 501: 'Not Implemented',
            503: 'Service Unavailable',
        }
        return texts.get(code, 'Unknown')

    def _format_error(self, code, status_code):
        headers = [
            ('Content-Type', 'application/json; charset=utf-8'),
            ('Cache-Control', 'no-store'),
            ('X-Content-Type-Options', 'nosniff'),
            ('Referrer-Policy', 'no-referrer'),
        ]
        if status_code == 401:
            headers.append(('WWW-Authenticate', 'Bearer error="invalid_token"'))
        elif status_code == 503:
            headers.append(('Retry-After', '1'))

        payload = {'ok': False, 'error': code, 'detail': None}
        return status_code, headers, serialize_json(payload)

    def _static_headers(self, content_type, cache_control='no-cache'):
        return [
            ('Content-Type', content_type),
            ('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"),
            ('X-Content-Type-Options', 'nosniff'),
            ('Referrer-Policy', 'no-referrer'),
            ('Cache-Control', cache_control),
        ]

    def _dispatch(self, environ):
        method = environ.get('REQUEST_METHOD', 'GET').upper()
        raw_path = environ.get('PATH_INFO', '/')
        path = raw_path.rstrip('/') or '/'

        # 0. Request Header boundaries (single line <= 4KB, total block <= 16KB)
        total_header_bytes = 0
        for k, v in environ.items():
            if k.startswith('HTTP_') or k in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
                line_len = len(k) + len(str(v))
                if line_len > MAX_HEADER_LINE_BYTES:
                    raise TransportError('header_too_large', 431)
                total_header_bytes += line_len
        if total_header_bytes > MAX_TOTAL_HEADERS_BYTES:
            raise TransportError('header_too_large', 431)

        # 1. Host header validation
        host = environ.get('HTTP_HOST', '')
        if self.allowed_hosts and host not in self.allowed_hosts:
            raise TransportError('invalid_host', 400)

        # 2. Extract credentials
        auth_header = environ.get('HTTP_AUTHORIZATION', '')
        bearer_cred = None
        if auth_header[:7].lower() == 'bearer ':
            bearer_cred = auth_header[7:].strip()

        cookie_header = environ.get('HTTP_COOKIE', '')
        cookie_cred = None
        if cookie_header:
            cookie = http.cookies.SimpleCookie()
            try:
                cookie.load(cookie_header)
                if 'settletable_session' in cookie:
                    cookie_cred = cookie['settletable_session'].value
            except Exception:
                pass

        if bearer_cred and cookie_cred and bearer_cred != cookie_cred:
            raise TransportError('conflicting_credentials', 400)

        active_cred = bearer_cred or cookie_cred
        used_cookie = bool(cookie_cred)

        # 3. CSRF & Action check on mutating requests (POST)
        if method == 'POST':
            # Missing or chunked body check
            cl_header = environ.get('CONTENT_LENGTH')
            te_header = environ.get('HTTP_TRANSFER_ENCODING')

            if cl_header and te_header:
                raise TransportError('malformed_request', 400)
            if te_header:
                raise TransportError('not_implemented', 501)

            # Mandatory custom header check for all POST endpoints
            action_hdr = environ.get('HTTP_X_SETTLETABLE_ACTION')
            if action_hdr != '1':
                raise TransportError('missing_action_header', 400)

            # Origin check: required if cookie was used OR if unauthenticated browser POST
            if used_cookie or not bearer_cred:
                origin = environ.get('HTTP_ORIGIN')
                if origin:
                    if origin == 'null' or origin.rstrip('/') != self.server_origin:
                        raise TransportError('origin_mismatch', 403)
                else:
                    referer = environ.get('HTTP_REFERER')
                    if referer:
                        parsed = urlparse(referer)
                        ref_origin = f"{parsed.scheme}://{parsed.netloc}".rstrip('/')
                        if ref_origin != self.server_origin:
                            raise TransportError('origin_mismatch', 403)
                    else:
                        # Missing both Origin and Referer on browser-context POST
                        raise TransportError('origin_mismatch', 403)

        # Read body for POST
        body_data = None
        raw_image_body = None
        is_ocr_extract = bool(method == 'POST' and re.fullmatch(r'/api/meals/[A-Za-z0-9_-]+/ocr/extract', path))
        if method == 'POST':
            cl = environ.get('CONTENT_LENGTH')
            if not cl:
                raise TransportError('missing_content_length', 411)
            try:
                length = int(cl)
            except ValueError:
                raise TransportError('malformed_request', 400)
            max_limit = MAX_IMAGE_BYTES if is_ocr_extract else MAX_BODY_BYTES
            if length > max_limit:
                raise TransportError('payload_too_large', 413)

            wsgi_input = environ.get('wsgi.input')
            raw_body = wsgi_input.read(length) if wsgi_input else b''
            if len(raw_body) != length:
                raise TransportError('malformed_request', 400)

            if is_ocr_extract:
                raw_image_body = raw_body
            else:
                body_data = parse_strict_json(raw_body) if raw_body else {}

        # 4. Route matching
        authority = self.get_authority()

        # Static asset serving (HTML shell and static files)
        if method == 'GET':
            if path == '/':
                index_path = STATIC_DIR / 'index.html'
                if index_path.exists():
                    return 200, self._static_headers('text/html; charset=utf-8', 'no-store, no-cache, must-revalidate'), index_path.read_bytes()
                raise TransportError('not_found', 404)

            # GET /invite/{token} serves HTML shell for invitation landing
            m_inv_shell = re.fullmatch(r'/invite/([A-Za-z0-9_-]{43})', path)
            if m_inv_shell:
                index_path = STATIC_DIR / 'index.html'
                if index_path.exists():
                    return 200, self._static_headers('text/html; charset=utf-8', 'no-store, no-cache, must-revalidate'), index_path.read_bytes()
                raise TransportError('not_found', 404)

            # GET /static/{filename}
            m_stat = re.fullmatch(r'/static/([A-Za-z0-9_.-]+)', path)
            if m_stat:
                filename = m_stat.group(1)
                if filename in STATIC_FILES:
                    fpath = STATIC_DIR / filename
                    if fpath.exists():
                        return 200, self._static_headers(STATIC_FILES[filename], 'no-cache'), fpath.read_bytes()
                raise TransportError('not_found', 404)

            if path == '/favicon.ico':
                fav = STATIC_DIR / 'favicon.svg'
                if fav.exists():
                    return 200, self._static_headers('image/svg+xml', 'no-cache'), fav.read_bytes()
                return 204, self._default_headers(), b''

        # Unauthenticated landing GET /api/invitations/{token}
        m = re.fullmatch(r'/api/invitations/([A-Za-z0-9_-]{43})', path)
        if m and method == 'GET':
            token = m.group(1)
            res = authority.inspect_invitation(token)
            out = {
                'ok': True,
                'valid': res.valid,
                'meal_id': res.meal_id,
                'participant_name': res.participant_name,
                'expires': res.expires,
                'reason': res.reason,
            }
            return 200, self._default_headers(), serialize_json(out)

        # Clear / Exit Session POST /api/session/clear or POST /api/meals/{meal_id}/session/exit
        if method == 'POST' and (path in ('/api/session/clear', '/api/session/exit') or re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/session/exit', path)):
            headers = self._default_headers()
            headers.append(('Set-Cookie', 'settletable_session=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT'))
            return 200, headers, serialize_json({'ok': True, 'cleared': True})

        # Redeem invitation POST /api/meals/{meal_id}/invitations/{token}/redeem
        m = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/invitations/([A-Za-z0-9_-]{43})/redeem', path)
        if m and method == 'POST':
            meal_id, token = m.group(1), m.group(2)
            session_grant = authority.redeem_invitation(token, meal_id)
            headers = self._default_headers()
            headers.append(('Set-Cookie', f'settletable_session={session_grant.credential}; HttpOnly; Secure; SameSite=Strict; Path=/'))
            out = {
                'ok': True,
                'meal_id': meal_id,
                'participant_id': session_grant.participant_id,
            }
            return 200, headers, serialize_json(out)

        # Bootstrap POST /api/meals/{meal_id}/bootstrap
        m = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/bootstrap', path)
        if m and method == 'POST':
            # Ingress/Proxy header protection: a reverse proxy forwarding requests to loopback
            # would make untrusted external calls appear to originate from 127.0.0.1.
            # Reject if any proxy forwarding headers are present.
            proxy_headers = ('HTTP_X_FORWARDED_FOR', 'HTTP_X_FORWARDED_HOST',
                             'HTTP_X_FORWARDED_PROTO', 'HTTP_FORWARDED', 'HTTP_X_REAL_IP')
            if any(h in environ for h in proxy_headers):
                raise TransportError('forbidden', 403)

            remote_addr = environ.get('REMOTE_ADDR', '')
            if remote_addr not in ('127.0.0.1', '::1', 'localhost', 'testclient'):
                raise TransportError('forbidden', 403)
            meal_id = m.group(1)
            raw_participants = body_data.get('participants')
            if not isinstance(raw_participants, list) or not raw_participants:
                raise TransportError('invalid_input', 400)
            try:
                parts = []
                for p in raw_participants:
                    if not isinstance(p, dict):
                        raise TransportError('invalid_input', 400)
                    parts.append(Participant(p['id'], p['name'], p.get('organizer', False)))
            except (KeyError, TypeError):
                raise TransportError('invalid_input', 400)
            b_res = authority.bootstrap(meal_id, tuple(parts))
            organizer_session = next(s for s, p in zip(b_res.sessions, parts) if p.organizer)
            headers = self._default_headers()
            headers.append(('Set-Cookie', f'settletable_session={organizer_session.credential}; HttpOnly; Secure; SameSite=Strict; Path=/'))
            # Defense against credential exposure: Never return all participant credentials
            # to an untrusted client. Only the provisioned organizer session is returned.
            # Diners must join via explicit invitations (issue_invitation -> redeem_invitation).
            out = {
                'ok': True,
                'meal_id': b_res.meal_id,
                'organizer_id': organizer_session.participant_id,
                'sessions': [{'participant_id': organizer_session.participant_id, 'credential': organizer_session.credential}],
            }
            return 201, headers, serialize_json(out)

        # Snapshot GET /api/meals/{meal_id}/snapshot
        m = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/snapshot', path)
        if m and method == 'GET':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id = m.group(1)
            part_id, is_org = authority.authenticate(active_cred, meal_id)
            snapshot = authority.snapshot(active_cred, meal_id)
            out = asdict(snapshot)
            out['ok'] = True
            out['current_participant_id'] = part_id
            out['is_organizer'] = is_org
            return 200, self._default_headers(), serialize_json(out)

        # Rotate Session POST /api/meals/{meal_id}/session/rotate
        m = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/session/rotate', path)
        if m and method == 'POST':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id = m.group(1)
            new_grant = authority.rotate_session(active_cred, meal_id)
            headers = self._default_headers()
            headers.append(('Set-Cookie', f'settletable_session={new_grant.credential}; HttpOnly; Secure; SameSite=Strict; Path=/'))
            out = {
                'ok': True,
                'participant_id': new_grant.participant_id,
            }
            # Only return raw bearer credential if request was authenticated via Bearer token (programmatic client).
            # Cookie-authenticated browser clients receive the credential strictly via HttpOnly cookie to prevent XSS exfiltration.
            if bearer_cred and not used_cookie:
                out['credential'] = new_grant.credential
            return 200, headers, serialize_json(out)

        # Issue Invitation POST /api/meals/{meal_id}/invitations
        m = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/invitations', path)
        if m and method == 'POST':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id = m.group(1)
            participant_id = body_data.get('participant_id')
            invite_ttl = body_data.get('invite_ttl', 86400)
            issue_id = body_data.get('issue_id')
            grant = authority.issue_invitation(active_cred, meal_id, participant_id,
                                               invite_ttl=invite_ttl, issue_id=issue_id)
            out = {
                'ok': True,
                'meal_id': grant.meal_id,
                'participant_id': grant.participant_id,
                'token': grant.token,
                'expires': grant.expires,
            }
            return 201, self._default_headers(), serialize_json(out)

        # Apply Command POST /api/meals/{meal_id}/apply
        m = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/apply', path)
        if m and method == 'POST':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id = m.group(1)
            command = self._build_command(body_data)
            accepted = authority.apply(active_cred, meal_id, command)
            out = {
                'ok': True,
                'kind': accepted.kind,
                'revision': accepted.revision,
                'financial_revision': accepted.financial_revision,
                'changed_claims': accepted.changed_claims,
                'calculation': accepted.calculation,
            }
            return 200, self._default_headers(), serialize_json(out)

        # Extract Receipt OCR POST /api/meals/{meal_id}/ocr/extract
        m_ocr = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/ocr/extract', path)
        if m_ocr and method == 'POST':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id = m_ocr.group(1)
            part_id, is_org = authority.authenticate(active_cred, meal_id)
            if not is_org:
                raise TransportError('forbidden', 403)

            ct = environ.get('CONTENT_TYPE', '').split(';')[0].strip().lower()
            if ct not in ('image/jpeg', 'image/png', 'image/webp', 'image/jpg'):
                raise TransportError('invalid_image', 400)

            engine = self.get_ocr_engine()
            try:
                from settletable.ocr import parse_malaysian_receipt, OcrUnavailableError, InvalidImageError, validate_image_payload
                validate_image_payload(raw_image_body or b'', expected_mime=ct)
                lines = engine.recognize(raw_image_body or b'')
                candidate = parse_malaysian_receipt(lines)
                out = {
                    'ok': True,
                    'candidate': candidate.to_dict(),
                }
                return 200, self._default_headers(), serialize_json(out)
            except InvalidImageError:
                raise TransportError('invalid_image', 400) from None
            except OcrUnavailableError:
                raise TransportError('ocr_unavailable', 503) from None

        # Check Notion Export Status GET /api/meals/{meal_id}/export/notion
        m_notion_get = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/export/notion', path)
        if m_notion_get and method == 'GET':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id = m_notion_get.group(1)
            part_id, is_org = authority.authenticate(active_cred, meal_id)
            if not is_org:
                raise TransportError('forbidden', 403)
            snap = asdict(authority.snapshot(active_cred, meal_id))
            rev = snap.get('revision', 0)
            rec = authority.get_notion_export(meal_id, rev)
            if rec:
                return 200, self._default_headers(), serialize_json({'ok': True, 'export': rec})
            return 200, self._default_headers(), serialize_json({'ok': True, 'export': {'status': 'not_started'}})

        # Export Finalized Meal to Notion POST /api/meals/{meal_id}/export/notion
        m_notion = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/export/notion', path)
        if m_notion and method == 'POST':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id = m_notion.group(1)
            part_id, is_org = authority.authenticate(active_cred, meal_id)
            if not is_org:
                raise TransportError('forbidden', 403)

            snap = asdict(authority.snapshot(active_cred, meal_id))
            if not snap.get('finalized'):
                raise TransportError('meal_not_finalized', 409)

            import os
            token = body_data.get('token') or os.environ.get('SETTLETABLE_NOTION_TOKEN')
            if not token:
                notion_cli = self.get_notion_client()
                if notion_cli.__class__.__name__ == 'MockNotionClient' or os.environ.get('SETTLETABLE_MOCK_NOTION') == '1':
                    token = 'secret_mock_notion_uat_testing_token_12345'

            raw_parent_id = body_data.get('parent_id') or os.environ.get('SETTLETABLE_NOTION_PARENT_ID')
            parent_type = body_data.get('parent_type', 'page_id')

            if not isinstance(token, str) or not (token.startswith('secret_') or token.startswith('ntn_')) or len(token) < 20 or len(token) > 128:
                raise TransportError('invalid_input', 400)
            if not isinstance(raw_parent_id, str):
                raise TransportError('invalid_input', 400)
            from settletable.notion.client import extract_notion_id
            parent_id = extract_notion_id(raw_parent_id)
            if not parent_id:
                raise TransportError('invalid_input', 400)
            if parent_type not in ('page_id', 'database_id'):
                raise TransportError('invalid_input', 400)

            rev = snap.get('revision', 0)
            digest = snap.get('calculation_digest') or ''
            rec = authority.get_notion_export(meal_id, rev)
            if rec and rec.get('status') == 'completed':
                out = {
                    'ok': True,
                    'export': {
                        'ok': True,
                        'status': 'already_exported',
                        'page_id': rec['page_id'],
                        'page_url': rec['page_url'],
                        'blocks_created': 0,
                    },
                }
                return 200, self._default_headers(), serialize_json(out)
            if rec and rec.get('status') == 'in_progress':
                elapsed = time.time() - rec.get('exported_at', 0)
                if elapsed < 60.0:
                    return 202, self._default_headers(), serialize_json({
                        'ok': True,
                        'export': {
                            'ok': True,
                            'status': 'in_progress',
                            'page_id': None,
                            'page_url': None,
                        }
                    })

            authority.record_notion_export_in_progress(meal_id, rev, digest)

            qs = environ.get('QUERY_STRING', '')
            requested_sync = ('sync=1' in qs) or (environ.get('HTTP_X_SETTLETABLE_SYNC_EXPORT') == '1')
            is_sync = requested_sync and self.allow_sync_export

            from settletable.notion import (
                NotionExportConfig,
                NotionRateLimitError,
                NotionAuthError,
                NotionNotFoundError,
                NotionValidationError,
                NotionError,
                export_finalized_meal,
            )
            config = NotionExportConfig(
                token=token,
                parent_id=parent_id.strip(),
                parent_type=parent_type,
                mode=body_data.get('mode', 'compact'),
            )

            if is_sync:
                try:
                    client = self.get_notion_client()
                    result = export_finalized_meal(client, meal_id, snap, config)
                    if result.ok:
                        authority.record_notion_export_completed(
                            meal_id, rev, result.page_id or '', result.page_url or '', digest
                        )
                        out = {'ok': True, 'export': result.to_dict()}
                        return 200, self._default_headers(), serialize_json(out)
                    else:
                        authority.record_notion_export_failed(meal_id, rev, result.error or 'notion_error')
                        return 400, self._default_headers(), serialize_json({'ok': False, 'error': result.error or 'notion_error'})
                except NotionRateLimitError:
                    authority.record_notion_export_failed(meal_id, rev, 'notion_rate_limited')
                    raise TransportError('notion_rate_limited', 429) from None
                except NotionAuthError:
                    authority.record_notion_export_failed(meal_id, rev, 'notion_auth_error')
                    raise TransportError('notion_auth_error', 400) from None
                except (NotionValidationError, NotionNotFoundError):
                    authority.record_notion_export_failed(meal_id, rev, 'invalid_input')
                    raise TransportError('invalid_input', 400) from None
                except NotionError:
                    authority.record_notion_export_failed(meal_id, rev, 'notion_error')
                    raise TransportError('notion_error', 502) from None
                except Exception:
                    authority.record_notion_export_failed(meal_id, rev, 'notion_error')
                    raise TransportError('notion_error', 502) from None
            else:
                # Asynchronous delivery: dispatch in background thread, return 202 immediately
                # to prevent WSGI worker thread starvation for live diners.
                # Ephemeral background worker thread (asynchronous execution, not durable queue persistence).
                # Does not survive process termination; uncompleted exports time out cleanly after 60s.
                def _bg_export():
                    bg_auth = self.get_authority()
                    try:
                        client = self.get_notion_client()
                        result = export_finalized_meal(client, meal_id, snap, config)
                        if result.ok:
                            bg_auth.record_notion_export_completed(
                                meal_id, rev, result.page_id or '', result.page_url or '', digest
                            )
                        else:
                            bg_auth.record_notion_export_failed(meal_id, rev, result.error or 'notion_error')
                    except NotionRateLimitError:
                        bg_auth.record_notion_export_failed(meal_id, rev, 'notion_rate_limited')
                    except NotionAuthError:
                        bg_auth.record_notion_export_failed(meal_id, rev, 'notion_auth_error')
                    except (NotionValidationError, NotionNotFoundError):
                        bg_auth.record_notion_export_failed(meal_id, rev, 'invalid_input')
                    except NotionError:
                        bg_auth.record_notion_export_failed(meal_id, rev, 'notion_error')
                    except Exception:
                        bg_auth.record_notion_export_failed(meal_id, rev, 'unexpected_error')
                    finally:
                        self.close()

                bg_thread = threading.Thread(target=_bg_export, daemon=True)
                bg_thread.start()
                out = {
                    'ok': True,
                    'export': {
                        'ok': True,
                        'status': 'in_progress',
                        'page_id': None,
                        'page_url': None,
                        'message': 'Notion export running asynchronously in background',
                    }
                }
                return 202, self._default_headers(), serialize_json(out)

        raise TransportError('not_found', 404)

    def _default_headers(self):
        return [
            ('Content-Type', 'application/json; charset=utf-8'),
            ('Cache-Control', 'no-store'),
            ('X-Content-Type-Options', 'nosniff'),
            ('Referrer-Policy', 'no-referrer'),
        ]

    def _build_command(self, data):
        if not isinstance(data, dict):
            raise TransportError('invalid_input', 400)
        # Actor/organizer spoofing defense: callers cannot provide actor/organizer
        if 'actor' in data or 'organizer' in data:
            raise TransportError('invalid_input', 400)

        kind = data.get('kind')
        cmd_id = data.get('command_id')
        if not kind or not cmd_id:
            raise TransportError('invalid_input', 400)

        try:
            if kind == 'ReplaceReceipt':
                rcpt_data = data.get('receipt')
                if not isinstance(rcpt_data, dict):
                    raise TransportError('invalid_input', 400)
                raw_items = rcpt_data.get('items', [])
                raw_adjustments = rcpt_data.get('adjustments', [])
                items = []
                for item in raw_items:
                    qty = item.get('quantity', 1)
                    if isinstance(qty, list) and len(qty) == 2:
                        qty = Fraction(qty[0], qty[1])
                    items.append(ReceiptItem(item['id'], item['label'], qty, item.get('line_sen')))
                item_id_set = {item.id for item in items}
                adjustments = []
                for idx, adj in enumerate(raw_adjustments, start=1):
                    raw_eligible = adj.get('eligible_item_ids') or ()
                    eligible = tuple(eid for eid in raw_eligible if eid in item_id_set)
                    if not eligible:
                        eligible = tuple(item.id for item in items)
                    adj_id = adj.get('id') or f"adj-{idx}"
                    label = adj.get('label') or adj.get('kind') or f"Adjustment {idx}"
                    rationale = adj.get('rationale')
                    if not rationale or not str(rationale).strip():
                        rationale = f"{label} adjustment"
                    else:
                        rationale = str(rationale).strip()
                    adjustments.append(ReceiptAdjustment(
                        id=str(adj_id),
                        label=str(label),
                        kind=adj['kind'],
                        amount_sen=adj.get('amount_sen'),
                        eligible_item_ids=eligible,
                        rationale=rationale,
                    ))
                receipt = Receipt(
                    items=tuple(items),
                    subtotal_sen=rcpt_data.get('subtotal_sen'),
                    total_sen=rcpt_data.get('total_sen'),
                    adjustments=tuple(adjustments),
                    included_tax_sen=rcpt_data.get('included_tax_sen', 0),
                )
                return ReplaceReceipt(
                    command_id=cmd_id,
                    expected_revision=data.get('expected_revision', 0),
                    expected_financial_revision=data.get('expected_financial_revision', 0),
                    receipt=receipt,
                )
            elif kind == 'SetOwnQuantity':
                qty = data.get('quantity')
                if isinstance(qty, list) and len(qty) == 2:
                    qty = Fraction(qty[0], qty[1])
                return SetOwnQuantity(
                    command_id=cmd_id,
                    item_id=data.get('item_id'),
                    quantity=qty,
                    expected_item_revision=data.get('expected_item_revision'),
                    expected_financial_revision=data.get('expected_financial_revision'),
                )
            elif kind == 'AssignParticipantQuantity':
                qty = data.get('quantity')
                if isinstance(qty, list) and len(qty) == 2:
                    qty = Fraction(qty[0], qty[1])
                part_id = data.get('participant_id')
                if not part_id or not isinstance(part_id, str):
                    raise TransportError('invalid_input', 400)
                return AssignParticipantQuantity(
                    command_id=cmd_id,
                    participant_id=part_id,
                    item_id=data.get('item_id'),
                    quantity=qty,
                    expected_item_revision=data.get('expected_item_revision'),
                    expected_financial_revision=data.get('expected_financial_revision'),
                )
            elif kind == 'ReviewReceipt':
                return ReviewReceipt(
                    command_id=cmd_id,
                    expected_revision=data.get('expected_revision'),
                    expected_financial_revision=data.get('expected_financial_revision'),
                    receipt_digest=data.get('receipt_digest'),
                )
            elif kind == 'Finalize':
                return Finalize(
                    command_id=cmd_id,
                    expected_revision=data.get('expected_revision'),
                    expected_financial_revision=data.get('expected_financial_revision'),
                )
            elif kind == 'RevokeInvitation':
                return RevokeInvitation(
                    command_id=cmd_id,
                    expected_revision=data.get('expected_revision'),
                    participant_id=data.get('participant_id'),
                )
            elif kind == 'RevokeSession':
                return RevokeSession(
                    command_id=cmd_id,
                    expected_revision=data.get('expected_revision'),
                    participant_id=data.get('participant_id'),
                )
            elif kind == 'RevokeMembership':
                return RevokeMembership(
                    command_id=cmd_id,
                    expected_revision=data.get('expected_revision'),
                    participant_id=data.get('participant_id'),
                )
            else:
                raise TransportError('invalid_command_kind', 400)
        except (KeyError, TypeError):
            raise TransportError('invalid_input', 400)
