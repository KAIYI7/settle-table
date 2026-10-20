"""Bounded same-origin transport adapter for SettleTable Authority.

Implements a defense-in-depth HTTP interface with strict wire boundary limits,
CSRF mitigation, host-only secure cookies, and unauthenticated landing separation.
"""
from dataclasses import asdict, is_dataclass
from fractions import Fraction
import http.cookies
import json
import re
import sqlite3
import threading
from urllib.parse import urlparse

from settletable.authority import (
    Authority, AuthorityError, Participant,
    ReplaceReceipt, SetOwnQuantity, ReviewReceipt, Finalize,
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
    # 431 Request Header Fields Too Large
    'header_too_large': 431,
    # 500 Internal Server Error
    'storage_error': 500,
    'internal_error': 500,
    # 503 Service Unavailable
    'commit_uncertain': 503,
    'busy': 503,
}

MAX_BODY_BYTES = 1_048_576  # 1 MB
MAX_JSON_DEPTH = 10
MAX_INT_DIGITS = 19
TOKEN_REDACT_REGEX = re.compile(r'(/api/(?:meals/[^/]+/)?invitations/)[A-Za-z0-9_-]{43}')


class TransportError(Exception):
    def __init__(self, code, status=None):
        super().__init__(code)
        self.code = code
        self.status = status or STATUS_MAP.get(code, 400)


def _reject_duplicates(pairs):
    seen = set()
    result = {}
    for key, val in pairs:
        if key in seen:
            raise TransportError('duplicate_key', 400)
        seen.add(key)
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
                 server_origin='http://localhost:8000', clock=None):
        self.db_path = str(db_path)
        self.allowed_hosts = set(allowed_hosts)
        self.server_origin = server_origin.rstrip('/')
        self.clock = clock
        self._local = threading.local()

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

    def _dispatch(self, environ):
        method = environ.get('REQUEST_METHOD', 'GET').upper()
        raw_path = environ.get('PATH_INFO', '/')
        path = raw_path.rstrip('/') or '/'

        # 1. Host header validation
        host = environ.get('HTTP_HOST', '')
        if self.allowed_hosts and host not in self.allowed_hosts:
            raise TransportError('invalid_host', 400)

        # 2. Extract credentials
        auth_header = environ.get('HTTP_AUTHORIZATION', '')
        bearer_cred = None
        if auth_header.startswith('Bearer '):
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
        if method == 'POST':
            cl = environ.get('CONTENT_LENGTH')
            if not cl:
                raise TransportError('missing_content_length', 411)
            try:
                length = int(cl)
            except ValueError:
                raise TransportError('malformed_request', 400)
            if length > MAX_BODY_BYTES:
                raise TransportError('payload_too_large', 413)

            wsgi_input = environ.get('wsgi.input')
            raw_body = wsgi_input.read(length) if wsgi_input else b''
            if len(raw_body) != length:
                raise TransportError('malformed_request', 400)
            body_data = parse_strict_json(raw_body) if raw_body else {}

        # 4. Route matching
        authority = self.get_authority()

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
            remote_addr = environ.get('REMOTE_ADDR', '')
            if remote_addr not in ('127.0.0.1', '::1', 'localhost', 'testclient'):
                raise TransportError('forbidden', 403)
            meal_id = m.group(1)
            raw_participants = body_data.get('participants')
            if not isinstance(raw_participants, list) or not raw_participants:
                raise TransportError('invalid_input', 400)
            parts = []
            for p in raw_participants:
                if not isinstance(p, dict):
                    raise TransportError('invalid_input', 400)
                parts.append(Participant(p['id'], p['name'], p.get('organizer', False)))
            b_res = authority.bootstrap(meal_id, tuple(parts))
            organizer_session = next(s for s, p in zip(b_res.sessions, parts) if p.organizer)
            headers = self._default_headers()
            headers.append(('Set-Cookie', f'settletable_session={organizer_session.credential}; HttpOnly; Secure; SameSite=Strict; Path=/'))
            out = {
                'ok': True,
                'meal_id': b_res.meal_id,
                'sessions': [{'participant_id': s.participant_id, 'credential': s.credential} for s in b_res.sessions],
            }
            return 201, headers, serialize_json(out)

        # Snapshot GET /api/meals/{meal_id}/snapshot
        m = re.fullmatch(r'/api/meals/([A-Za-z0-9_-]+)/snapshot', path)
        if m and method == 'GET':
            if not active_cred:
                raise TransportError('invalid_session', 401)
            meal_id = m.group(1)
            snapshot = authority.snapshot(active_cred, meal_id)
            out = asdict(snapshot)
            out['ok'] = True
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
                'credential': new_grant.credential,
            }
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
            adjustments = []
            for adj in raw_adjustments:
                adjustments.append(ReceiptAdjustment(
                    id=adj['id'],
                    label=adj['label'],
                    kind=adj['kind'],
                    amount_sen=adj.get('amount_sen'),
                    eligible_item_ids=tuple(adj.get('eligible_item_ids', ())),
                    rationale=adj.get('rationale', ''),
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
