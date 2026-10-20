"""Durable local draft acceptance. Not an Internet authentication endpoint."""
from dataclasses import dataclass, field
from fractions import Fraction
import hashlib
import json
import math
import re
import secrets
import sqlite3
import time
import unicodedata

from . import calculation as calc


class AuthorityError(ValueError):
    """Safe public failure. Never includes credentials, commands or SQL."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class Participant:
    id: str
    name: str
    organizer: bool = False


@dataclass(frozen=True, slots=True)
class SessionGrant:
    participant_id: str
    credential: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class InvitationGrant:
    meal_id: str
    participant_id: str
    token: str = field(repr=False)
    expires: float | int


@dataclass(frozen=True, slots=True)
class InvitationInspection:
    valid: bool
    meal_id: str | None = None
    participant_name: str | None = None
    expires: float | int | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class InvitationRecord:
    participant_id: str
    created_at: float | int
    expires: float | int
    consumed: bool
    revoked: bool
    issue_id: str


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    meal_id: str
    sessions: tuple[SessionGrant, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class ReceiptItem:
    id: str
    label: str
    quantity: int | Fraction = 1
    line_sen: int | None = None


@dataclass(frozen=True, slots=True)
class ReceiptAdjustment:
    id: str
    label: str
    kind: str
    amount_sen: int | None
    eligible_item_ids: tuple[str, ...]
    rationale: str


@dataclass(frozen=True, slots=True)
class Receipt:
    items: tuple[ReceiptItem, ...] = ()
    subtotal_sen: int | None = None
    total_sen: int | None = None
    adjustments: tuple[ReceiptAdjustment, ...] = ()
    included_tax_sen: int | None = 0


@dataclass(frozen=True, slots=True)
class ReplaceReceipt:
    command_id: str
    expected_revision: int
    expected_financial_revision: int
    receipt: Receipt


@dataclass(frozen=True, slots=True)
class SetOwnQuantity:
    command_id: str
    item_id: str
    quantity: int | Fraction | None
    expected_item_revision: int
    expected_financial_revision: int


@dataclass(frozen=True, slots=True)
class ReviewReceipt:
    command_id: str
    expected_revision: int
    expected_financial_revision: int
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class Finalize:
    command_id: str
    expected_revision: int
    expected_financial_revision: int


@dataclass(frozen=True, slots=True)
class RevokeSession:
    command_id: str
    expected_revision: int
    participant_id: str


@dataclass(frozen=True, slots=True)
class RevokeMembership:
    command_id: str
    expected_revision: int
    participant_id: str


@dataclass(frozen=True, slots=True)
class RevokeInvitation:
    command_id: str
    expected_revision: int
    participant_id: str


@dataclass(frozen=True, slots=True)
class Claim:
    item_id: str
    participant_id: str
    quantity: Fraction
    financial_revision: int
    status: str


@dataclass(frozen=True, slots=True)
class ItemState:
    item_id: str
    item_revision: int


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    participant_id: str
    financial_revision: int
    receipt_digest: str
    command_id: str


@dataclass(frozen=True, slots=True)
class AcceptedResult:
    command_id: str
    kind: str
    revision: int
    financial_revision: int
    changed_claims: tuple[Claim, ...]
    calculation: calc.Calculation | None
    canonical_bytes: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class DraftSnapshot:
    meal_id: str
    revision: int
    financial_revision: int
    receipt_digest: str | None
    receipt: Receipt | None
    items: tuple[ItemState, ...]
    claims: tuple[Claim, ...]
    review: ReviewRecord | None
    calculation: calc.Calculation | None
    finalized: bool
    issues: tuple[str, ...]
    participants: tuple[Participant, ...]
    inactive_participant_ids: tuple[str, ...]
    invitations: tuple[InvitationRecord, ...] = ()


def _require(condition, code='invalid_input'):
    if not condition:
        raise AuthorityError(code)


def _id(value):
    _require(type(value) is str and 1 <= len(value) <= 64
             and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]*', value) is not None)


def _text(value, maximum):
    _require(type(value) is str and 1 <= len(value) <= maximum)
    _require(not any(unicodedata.category(c) in ('Cc', 'Cs') for c in value))
    _require(any(not c.isspace() and unicodedata.category(c) != 'Cf' for c in value))


def _tuple(value, maximum, minimum=0):
    _require(type(value) is tuple and minimum <= len(value) <= maximum)


def _wire(value):
    data = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('ascii')
    _require(len(data) <= 1_048_576, 'resource_limit')
    return data


def _verifier(credential):
    _require(type(credential) is str and len(credential) == 43
             and re.fullmatch(r'[A-Za-z0-9_-]{43}', credential) is not None,
             'invalid_session')
    return hashlib.sha256(b'settletable-local-session-v1\0' + credential.encode('ascii')).digest()


def _invitation_verifier(token):
    _require(type(token) is str and len(token) == 43
             and re.fullmatch(r'[A-Za-z0-9_-]{43}', token) is not None,
             'invalid_invitation')
    return hashlib.sha256(b'settletable-invitation-v1\0' + token.encode('ascii')).digest()


def _revision(value):
    _require(type(value) is int and 0 <= value < 9_223_372_036_854_775_807)


def _money(value, *, signed=False):
    if value is not None:
        _require(type(value) is int and abs(value) <= 1_000_000_000
                 and (signed or value >= 0))


def _rational(value):
    _require(type(value) in (int, Fraction))
    _require(0 < value.numerator <= 1_000_000_000 and value.denominator <= 1_000_000)
    _require(value <= 1_000_000)
    return [value.numerator, value.denominator]


def _receipt_data(receipt):
    _require(type(receipt) is Receipt)
    _tuple(receipt.items, 500)
    _tuple(receipt.adjustments, 100)
    for amount in (receipt.subtotal_sen, receipt.total_sen, receipt.included_tax_sen):
        _money(amount)
    ids, items = set(), []
    for item in receipt.items:
        _require(type(item) is ReceiptItem)
        _id(item.id)
        _require(item.id not in ids)
        ids.add(item.id)
        _text(item.label, 160)
        quantity = _rational(item.quantity)
        _money(item.line_sen)
        items.append({'id': item.id, 'label': item.label, 'quantity': quantity, 'line_sen': item.line_sen})
    _require(sum(i.line_sen or 0 for i in receipt.items) <= 1_000_000_000)
    changes = []
    for change in receipt.adjustments:
        _require(type(change) is ReceiptAdjustment)
        _id(change.id)
        _require(change.id not in ids)
        ids.add(change.id)
        _text(change.label, 160)
        _text(change.rationale, 500)
        _require(type(change.kind) is str and change.kind in ('tax', 'service', 'discount', 'rounding'))
        _money(change.amount_sen, signed=True)
        if change.amount_sen is not None:
            _require(not (change.kind in ('tax', 'service') and change.amount_sen < 0)
                     and not (change.kind == 'discount' and change.amount_sen > 0))
        _tuple(change.eligible_item_ids, 500, 1)
        scope = set()
        for item_id in change.eligible_item_ids:
            _id(item_id)
            _require(item_id in {i.id for i in receipt.items} and item_id not in scope)
            scope.add(item_id)
        changes.append({'id': change.id, 'label': change.label, 'kind': change.kind,
                        'amount_sen': change.amount_sen, 'eligible_item_ids': sorted(scope),
                        'rationale': change.rationale})
    return {'items': sorted(items, key=lambda i: i['id']), 'subtotal_sen': receipt.subtotal_sen,
            'total_sen': receipt.total_sen, 'adjustments': sorted(changes, key=lambda a: a['id']),
            'included_tax_sen': receipt.included_tax_sen}


def _decode_receipt(data):
    if data is None:
        return None
    return Receipt(tuple(ReceiptItem(i['id'], i['label'], Fraction(*i['quantity']), i['line_sen'])
                         for i in data['items']), data['subtotal_sen'], data['total_sen'],
                   tuple(ReceiptAdjustment(a['id'], a['label'], a['kind'], a['amount_sen'],
                                           tuple(a['eligible_item_ids']), a['rationale'])
                         for a in data['adjustments']), data['included_tax_sen'])


def _receipt_digest(receipt):
    return None if receipt is None else hashlib.sha256(b'settletable-receipt-v1\0' + _wire(receipt)).hexdigest()


def _command_data(command):
    _require(type(command) in (ReplaceReceipt, SetOwnQuantity, ReviewReceipt, Finalize,
                               RevokeSession, RevokeMembership, RevokeInvitation))
    _id(command.command_id)
    data = {'contract': 'settletable-command-v1', 'kind': type(command).__name__, 'command_id': command.command_id}
    if type(command) is SetOwnQuantity:
        _id(command.item_id)
        _revision(command.expected_item_revision)
        data.update(item_id=command.item_id, quantity=None if command.quantity is None else _rational(command.quantity),
                    expected_item_revision=command.expected_item_revision)
    else:
        _revision(command.expected_revision)
        data['expected_revision'] = command.expected_revision
    if type(command) in (ReplaceReceipt, SetOwnQuantity, ReviewReceipt, Finalize):
        _revision(command.expected_financial_revision)
        data['expected_financial_revision'] = command.expected_financial_revision
    if type(command) is ReplaceReceipt:
        data['receipt'] = _receipt_data(command.receipt)
    if type(command) is ReviewReceipt:
        _require(type(command.receipt_digest) is str and re.fullmatch(r'[0-9a-f]{64}', command.receipt_digest))
        data['receipt_digest'] = command.receipt_digest
    if type(command) in (RevokeSession, RevokeMembership, RevokeInvitation):
        _id(command.participant_id)
        data['participant_id'] = command.participant_id
    return data


def _claims(state):
    return tuple(Claim(c['item_id'], c['participant_id'], Fraction(*c['quantity']),
                       c['financial_revision'], 'confirmed' if c['financial_revision'] == state['financial_revision'] else 'pending')
                 for c in sorted(state['claims'], key=lambda c: (c['item_id'], c['participant_id'])))


def _decode_result(wire):
    data = json.loads(wire)
    claims = tuple(Claim(c['item_id'], c['participant_id'], Fraction(*c['quantity']),
                         c['financial_revision'], c['status']) for c in data['changed_claims'])
    return AcceptedResult(data['command_id'], data['kind'], data['revision'],
                          data['financial_revision'], claims, _decode_calculation(data['calculation']), wire)


def _calculation_data(result):
    def amounts(rows):
        return [{'participant_id': p.participant_id, 'sen': p.sen} for p in rows]
    def sources(rows):
        return [{'source_id': source.source_id, 'shares': amounts(source.shares)} for source in rows]
    return {'items': sources(result.items), 'adjustments': sources(result.adjustments),
            'consumption': amounts(result.consumption)}


def _decode_calculation(data):
    if data is None:
        return None
    def amounts(rows):
        return tuple(calc.PersonAmount(p['participant_id'], p['sen']) for p in rows)
    def sources(rows):
        return tuple(calc.SourceAllocation(s['source_id'], amounts(s['shares'])) for s in rows)
    return calc.Calculation(sources(data['items']), sources(data['adjustments']), amounts(data['consumption']))


def _claim_data(claim):
    return {'item_id': claim.item_id, 'participant_id': claim.participant_id,
            'quantity': [claim.quantity.numerator, claim.quantity.denominator],
            'financial_revision': claim.financial_revision, 'status': claim.status}


class Authority:
    """One SQLite connection; each instance may be used by its owning thread."""
    def __init__(self, path, *, clock=time.time, failure_hook=None):
        self._clock, self._failure_hook = clock, failure_hook
        self._db = None
        try:
            options = {'isolation_level': None, 'timeout': 1.0}
            if hasattr(sqlite3, 'LEGACY_TRANSACTION_CONTROL'):
                options['autocommit'] = sqlite3.LEGACY_TRANSACTION_CONTROL
            self._db = sqlite3.connect(path, **options)
            self._db.execute('PRAGMA foreign_keys=ON')
            self._db.execute('PRAGMA journal_mode=WAL')
            self._db.execute('PRAGMA busy_timeout=1000')
            self._db.executescript('''
                CREATE TABLE IF NOT EXISTS meals (
                    id TEXT PRIMARY KEY, state BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS participants (
                    meal_id TEXT NOT NULL REFERENCES meals(id), id TEXT NOT NULL,
                    name TEXT NOT NULL, organizer INTEGER NOT NULL, active INTEGER NOT NULL,
                    PRIMARY KEY(meal_id,id));
                CREATE TABLE IF NOT EXISTS sessions (
                    verifier BLOB PRIMARY KEY, meal_id TEXT NOT NULL, participant_id TEXT NOT NULL,
                    expires REAL NOT NULL, revoked INTEGER NOT NULL,
                    UNIQUE(meal_id,participant_id),
                    FOREIGN KEY(meal_id,participant_id) REFERENCES participants(meal_id,id));
                CREATE TABLE IF NOT EXISTS commands (
                    meal_id TEXT NOT NULL, participant_id TEXT NOT NULL, command_id TEXT NOT NULL,
                    body BLOB NOT NULL, digest BLOB NOT NULL, result BLOB NOT NULL,
                    security INTEGER NOT NULL,
                    PRIMARY KEY(meal_id,participant_id,command_id),
                    FOREIGN KEY(meal_id,participant_id) REFERENCES participants(meal_id,id));
                CREATE TABLE IF NOT EXISTS invitations (
                    verifier BLOB PRIMARY KEY, meal_id TEXT NOT NULL, participant_id TEXT NOT NULL,
                    issuer_id TEXT NOT NULL, issue_id TEXT NOT NULL, created_at REAL NOT NULL,
                    expires REAL NOT NULL, consumed INTEGER NOT NULL DEFAULT 0,
                    revoked INTEGER NOT NULL DEFAULT 0, generation INTEGER NOT NULL,
                    UNIQUE(meal_id,issue_id),
                    FOREIGN KEY(meal_id,participant_id) REFERENCES participants(meal_id,id),
                    FOREIGN KEY(meal_id,issuer_id) REFERENCES participants(meal_id,id));
                CREATE TABLE IF NOT EXISTS participant_lifecycle (
                    meal_id TEXT NOT NULL, participant_id TEXT NOT NULL,
                    generation INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY(meal_id,participant_id),
                    FOREIGN KEY(meal_id,participant_id) REFERENCES participants(meal_id,id));
            ''')
        except sqlite3.Error:
            self.close()
            raise AuthorityError('storage_error') from None

    def close(self):
        if self._db is not None:
            connection, self._db = self._db, None
            try:
                connection.close()
            except Exception:
                pass

    def _now(self):
        try:
            value = self._clock()
        except Exception:
            raise AuthorityError('storage_error') from None
        _require(type(value) in (int, float) and math.isfinite(value)
                 and abs(value) <= 1_000_000_000_000, 'storage_error')
        return value

    def _hook(self, stage):
        if self._failure_hook is not None:
            try:
                self._failure_hook(stage)
            except Exception:
                # Dependency failures must not impersonate domain rejections.
                raise RuntimeError('dependency_failure') from None

    def _rollback(self):
        try:
            if self._db is not None and self._db.in_transaction:
                self._db.execute('ROLLBACK')
        except Exception:
            # An unconfirmed transaction must never be reused after cleanup fails.
            self.close()

    def _storage_failure(self, error):
        self._rollback()
        sqlite_code = getattr(error, 'sqlite_errorcode', 0)
        code = 'busy' if type(sqlite_code) is int and sqlite_code & 255 in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) else 'storage_error'
        raise AuthorityError(code) from None

    def bootstrap(self, meal_id, participants, *, session_ttl=3600):
        _id(meal_id)
        _tuple(participants, 100, 1)
        seen = set()
        for person in participants:
            _require(type(person) is Participant)
            _id(person.id)
            _text(person.name, 80)
            _require(type(person.organizer) is bool and person.id not in seen)
            seen.add(person.id)
        _require(sum(p.organizer for p in participants) == 1)
        _require(type(session_ttl) is int and 1 <= session_ttl <= 86400)
        state = {'revision': 0, 'financial_revision': 0, 'receipt': None,
                 'item_revisions': {}, 'claims': [], 'review': None,
                 'calculation': None, 'retired_ids': []}
        committed = False
        commit_attempted = False
        try:
            grants = tuple(SessionGrant(p.id, secrets.token_urlsafe(32)) for p in participants)
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN IMMEDIATE')
            _require(self._db.execute('SELECT 1 FROM meals WHERE id=?', (meal_id,)).fetchone() is None, 'meal_exists')
            self._db.execute('INSERT INTO meals VALUES (?,?)', (meal_id, _wire(state)))
            expires = self._now() + session_ttl
            for person, grant in zip(participants, grants):
                self._db.execute('INSERT INTO participants VALUES (?,?,?,?,1)',
                                 (meal_id, person.id, person.name, int(person.organizer)))
                self._db.execute('INSERT INTO sessions VALUES (?,?,?,?,0)',
                                 (_verifier(grant.credential), meal_id, person.id, expires))
            self._hook('after_state')
            self._hook('before_commit')
            commit_attempted = True
            self._db.execute('COMMIT')
            committed = True
            self._hook('after_commit')
            return BootstrapResult(meal_id, grants)
        except AuthorityError:
            self._rollback()
            if committed:
                raise AuthorityError('commit_uncertain') from None
            raise
        except sqlite3.Error as error:
            try:
                transaction_open = self._db is not None and self._db.in_transaction
            except Exception:
                transaction_open = None
            if committed or (commit_attempted and transaction_open is not True):
                self._rollback()
                raise AuthorityError('commit_uncertain') from None
            self._storage_failure(error)
        except Exception:
            self._rollback()
            raise AuthorityError('commit_uncertain' if committed else 'storage_error') from None

    def _authenticate(self, verifier, meal_id):
        row = self._db.execute('''SELECT p.id,p.organizer FROM sessions s
            JOIN participants p ON p.meal_id=s.meal_id AND p.id=s.participant_id
            WHERE s.verifier=? AND s.meal_id=? AND s.revoked=0 AND p.active=1 AND s.expires>?''',
            (verifier, meal_id, self._now())).fetchone()
        _require(row is not None, 'invalid_session')
        return row

    def snapshot(self, credential, meal_id):
        verifier = _verifier(credential)
        _id(meal_id)
        try:
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN')
            self._authenticate(verifier, meal_id)
            state = json.loads(self._db.execute('SELECT state FROM meals WHERE id=?', (meal_id,)).fetchone()[0])
            people = self._db.execute('SELECT id,name,organizer,active FROM participants WHERE meal_id=? ORDER BY id', (meal_id,)).fetchall()
            inv_rows = self._db.execute('''SELECT participant_id,created_at,expires,consumed,revoked,issue_id
                FROM invitations WHERE meal_id=? ORDER BY participant_id,created_at,issue_id''', (meal_id,)).fetchall()
            invitations = tuple(InvitationRecord(r[0], r[1], r[2], bool(r[3]), bool(r[4]), r[5]) for r in inv_rows)
            result = DraftSnapshot(meal_id, state['revision'], state['financial_revision'],
                                   _receipt_digest(state['receipt']), _decode_receipt(state['receipt']),
                                   tuple(ItemState(i, revision) for i, revision in sorted(state['item_revisions'].items())),
                                   _claims(state), None if state['review'] is None else ReviewRecord(**state['review']),
                                   _decode_calculation(state['calculation']), state['calculation'] is not None,
                                   self._issues(state),
                                   tuple(Participant(p[0], p[1], bool(p[2])) for p in people),
                                   tuple(p[0] for p in people if not p[3]),
                                   invitations)
            self._db.execute('COMMIT')
            return result
        except AuthorityError:
            self._rollback()
            raise
        except sqlite3.Error as error:
            self._storage_failure(error)
        except Exception:
            self._rollback()
            raise AuthorityError('storage_error') from None

    def issue_invitation(self, organizer_credential, meal_id, participant_id, *, invite_ttl=86400, issue_id=None):
        verifier = _verifier(organizer_credential)
        _id(meal_id)
        _id(participant_id)
        _require(type(invite_ttl) is int and 1 <= invite_ttl <= 604800)
        if issue_id is not None:
            _id(issue_id)
        committed = False
        commit_attempted = False
        try:
            if issue_id is None:
                issue_id = f'inv-{secrets.token_urlsafe(16)}'
            token = secrets.token_urlsafe(32)
            inv_verifier = _invitation_verifier(token)
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN IMMEDIATE')
            actor, organizer = self._authenticate(verifier, meal_id)
            _require(bool(organizer), 'forbidden')
            existing_issue = self._db.execute('SELECT 1 FROM invitations WHERE meal_id=? AND issue_id=?',
                                              (meal_id, issue_id)).fetchone()
            _require(existing_issue is None, 'command_conflict')
            target = self._db.execute('SELECT organizer,active FROM participants WHERE meal_id=? AND id=?',
                                      (meal_id, participant_id)).fetchone()
            _require(target is not None and not target[0] and target[1] == 1, 'forbidden')
            now = self._now()
            expires = now + invite_ttl
            gen_row = self._db.execute('SELECT generation FROM participant_lifecycle WHERE meal_id=? AND participant_id=?',
                                       (meal_id, participant_id)).fetchone()
            current_gen = 1 if gen_row is None else gen_row[0]
            _require(current_gen < 64, 'resource_limit')
            active_inv = self._db.execute('''SELECT 1 FROM invitations
                WHERE meal_id=? AND participant_id=? AND revoked=0 AND consumed=0 AND expires>?''',
                (meal_id, participant_id, now)).fetchone()
            _require(active_inv is None, 'active_invitation_exists')
            next_gen = current_gen + 1
            self._db.execute('''INSERT INTO participant_lifecycle (meal_id,participant_id,generation)
                VALUES (?,?,?) ON CONFLICT(meal_id,participant_id) DO UPDATE SET generation=?''',
                (meal_id, participant_id, next_gen, next_gen))
            self._db.execute('''INSERT INTO invitations (verifier,meal_id,participant_id,issuer_id,issue_id,created_at,expires,consumed,revoked,generation)
                VALUES (?,?,?,?,?,?,?,0,0,?)''',
                (inv_verifier, meal_id, participant_id, actor, issue_id, now, expires, next_gen))
            state = json.loads(self._db.execute('SELECT state FROM meals WHERE id=?', (meal_id,)).fetchone()[0])
            state['revision'] += 1
            _revision(state['revision'])
            self._db.execute('UPDATE meals SET state=? WHERE id=?', (_wire(state), meal_id))
            self._hook('before_commit')
            commit_attempted = True
            self._db.execute('COMMIT')
            committed = True
            self._hook('after_commit')
            return InvitationGrant(meal_id, participant_id, token, expires)
        except AuthorityError:
            self._rollback()
            if committed:
                raise AuthorityError('commit_uncertain') from None
            raise
        except sqlite3.Error as error:
            try:
                transaction_open = self._db is not None and self._db.in_transaction
            except Exception:
                transaction_open = None
            uncertain = committed or (commit_attempted and transaction_open is not True)
            if uncertain:
                self._rollback()
                raise AuthorityError('commit_uncertain') from None
            self._storage_failure(error)
        except Exception:
            self._rollback()
            raise AuthorityError('commit_uncertain' if committed else 'storage_error') from None

    def inspect_invitation(self, token):
        try:
            inv_verifier = _invitation_verifier(token)
        except AuthorityError:
            return InvitationInspection(valid=False, reason='invalid_token')

        try:
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN')
            now = self._now()
            row = self._db.execute('''
                SELECT i.meal_id, i.participant_id, i.expires, i.consumed, i.revoked, p.name, p.active
                FROM invitations i
                JOIN participants p ON p.meal_id = i.meal_id AND p.id = i.participant_id
                WHERE i.verifier = ?
            ''', (inv_verifier,)).fetchone()
            self._db.execute('COMMIT')
            if row is None:
                return InvitationInspection(valid=False, reason='not_found')
            meal_id, part_id, expires, consumed, revoked, name, active = row
            if not active or revoked:
                return InvitationInspection(valid=False, meal_id=meal_id, participant_name=name, expires=expires, reason='revoked')
            if consumed:
                return InvitationInspection(valid=False, meal_id=meal_id, participant_name=name, expires=expires, reason='consumed')
            if expires <= now:
                return InvitationInspection(valid=False, meal_id=meal_id, participant_name=name, expires=expires, reason='expired')
            return InvitationInspection(valid=True, meal_id=meal_id, participant_name=name, expires=expires)
        except Exception:
            self._rollback()
            raise AuthorityError('storage_error') from None

    def redeem_invitation(self, invitation_token, meal_id, *, session_ttl=3600):
        inv_verifier = _invitation_verifier(invitation_token)
        _id(meal_id)
        _require(type(session_ttl) is int and 1 <= session_ttl <= 86400)
        committed = False
        commit_attempted = False
        try:
            credential = secrets.token_urlsafe(32)
            sess_verifier = _verifier(credential)
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN IMMEDIATE')
            now = self._now()
            row = self._db.execute('''SELECT participant_id,expires,consumed,revoked
                FROM invitations WHERE verifier=? AND meal_id=?''',
                (inv_verifier, meal_id)).fetchone()
            _require(row is not None and row[1] > now and row[2] == 0 and row[3] == 0, 'invalid_invitation')
            participant_id = row[0]
            target = self._db.execute('SELECT organizer,active FROM participants WHERE meal_id=? AND id=?',
                                      (meal_id, participant_id)).fetchone()
            _require(target is not None and not target[0] and target[1] == 1, 'invalid_invitation')
            gen_row = self._db.execute('SELECT generation FROM participant_lifecycle WHERE meal_id=? AND participant_id=?',
                                       (meal_id, participant_id)).fetchone()
            current_gen = 1 if gen_row is None else gen_row[0]
            _require(current_gen < 64, 'resource_limit')
            next_gen = current_gen + 1
            self._db.execute('''INSERT INTO participant_lifecycle (meal_id,participant_id,generation)
                VALUES (?,?,?) ON CONFLICT(meal_id,participant_id) DO UPDATE SET generation=?''',
                (meal_id, participant_id, next_gen, next_gen))
            self._db.execute('UPDATE invitations SET consumed=1 WHERE verifier=?', (inv_verifier,))
            sess_expires = now + session_ttl
            self._db.execute('''INSERT INTO sessions (verifier,meal_id,participant_id,expires,revoked)
                VALUES (?,?,?,?,0)
                ON CONFLICT(meal_id,participant_id) DO UPDATE SET verifier=?,expires=?,revoked=0''',
                (sess_verifier, meal_id, participant_id, sess_expires, sess_verifier, sess_expires))
            state = json.loads(self._db.execute('SELECT state FROM meals WHERE id=?', (meal_id,)).fetchone()[0])
            state['revision'] += 1
            _revision(state['revision'])
            self._db.execute('UPDATE meals SET state=? WHERE id=?', (_wire(state), meal_id))
            self._hook('before_commit')
            commit_attempted = True
            self._db.execute('COMMIT')
            committed = True
            self._hook('after_commit')
            return SessionGrant(participant_id, credential)
        except AuthorityError:
            self._rollback()
            if committed:
                raise AuthorityError('commit_uncertain') from None
            raise
        except sqlite3.Error as error:
            try:
                transaction_open = self._db is not None and self._db.in_transaction
            except Exception:
                transaction_open = None
            uncertain = committed or (commit_attempted and transaction_open is not True)
            if uncertain:
                self._rollback()
                raise AuthorityError('commit_uncertain') from None
            self._storage_failure(error)
        except Exception:
            self._rollback()
            raise AuthorityError('commit_uncertain' if committed else 'storage_error') from None

    def rotate_session(self, credential, meal_id, *, session_ttl=3600):
        verifier = _verifier(credential)
        _id(meal_id)
        _require(type(session_ttl) is int and 1 <= session_ttl <= 86400)
        committed = False
        commit_attempted = False
        try:
            new_credential = secrets.token_urlsafe(32)
            new_verifier = _verifier(new_credential)
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN IMMEDIATE')
            actor, organizer = self._authenticate(verifier, meal_id)
            _require(not organizer, 'forbidden')
            gen_row = self._db.execute('SELECT generation FROM participant_lifecycle WHERE meal_id=? AND participant_id=?',
                                       (meal_id, actor)).fetchone()
            current_gen = 1 if gen_row is None else gen_row[0]
            _require(current_gen < 64, 'resource_limit')
            next_gen = current_gen + 1
            self._db.execute('''INSERT INTO participant_lifecycle (meal_id,participant_id,generation)
                VALUES (?,?,?) ON CONFLICT(meal_id,participant_id) DO UPDATE SET generation=?''',
                (meal_id, actor, next_gen, next_gen))
            now = self._now()
            sess_expires = now + session_ttl
            self._db.execute('UPDATE sessions SET verifier=?,expires=?,revoked=0 WHERE meal_id=? AND participant_id=?',
                             (new_verifier, sess_expires, meal_id, actor))
            self._hook('before_commit')
            commit_attempted = True
            self._db.execute('COMMIT')
            committed = True
            self._hook('after_commit')
            return SessionGrant(actor, new_credential)
        except AuthorityError:
            self._rollback()
            if committed:
                raise AuthorityError('commit_uncertain') from None
            raise
        except sqlite3.Error as error:
            try:
                transaction_open = self._db is not None and self._db.in_transaction
            except Exception:
                transaction_open = None
            uncertain = committed or (commit_attempted and transaction_open is not True)
            if uncertain:
                self._rollback()
                raise AuthorityError('commit_uncertain') from None
            self._storage_failure(error)
        except Exception:
            self._rollback()
            raise AuthorityError('commit_uncertain' if committed else 'storage_error') from None

    @staticmethod
    def _receipt_issues(state):
        receipt = state['receipt']
        if receipt is None or not receipt['items']:
            return ('missing_receipt',)
        values = [receipt['subtotal_sen'], receipt['total_sen'], receipt['included_tax_sen']]
        values += [i['line_sen'] for i in receipt['items']]
        values += [a['amount_sen'] for a in receipt['adjustments']]
        if None in values:
            return ('missing_amount',)
        subtotal = sum(i['line_sen'] for i in receipt['items'])
        issues = []
        if subtotal != receipt['subtotal_sen']:
            issues.append('subtotal_mismatch')
        if subtotal + sum(a['amount_sen'] for a in receipt['adjustments']) != receipt['total_sen']:
            issues.append('receipt_total_mismatch')
        for change in receipt['adjustments']:
            base = sum(i['line_sen'] for i in receipt['items'] if i['id'] in change['eligible_item_ids'])
            if change['kind'] == 'discount' and -change['amount_sen'] > base:
                issues.append('discount_over_base')
            if change['amount_sen'] and not base:
                issues.append('zero_base')
        return tuple(sorted(set(issues)))

    @classmethod
    def _issues(cls, state):
        issues = list(cls._receipt_issues(state))
        if any(c['financial_revision'] != state['financial_revision'] for c in state['claims']):
            issues.append('pending_claim')
        if state['receipt'] is not None:
            for item in state['receipt']['items']:
                quantity = sum((Fraction(*c['quantity']) for c in state['claims']
                                if c['item_id'] == item['id'] and c['financial_revision'] == state['financial_revision']), Fraction())
                if quantity != Fraction(*item['quantity']):
                    issues.append('incomplete_quantity')
        return tuple(sorted(set(issues)))

    def _permission(self, actor, organizer, meal_id, data):
        if data['kind'] != 'SetOwnQuantity':
            _require(bool(organizer), 'forbidden')
        if data['kind'] in ('RevokeSession', 'RevokeMembership', 'RevokeInvitation'):
            target = self._db.execute('SELECT organizer FROM participants WHERE meal_id=? AND id=?',
                                      (meal_id, data['participant_id'])).fetchone()
            _require(target is not None and not target[0] and data['participant_id'] != actor, 'forbidden')

    def _replace_receipt(self, state, data):
        old = state['receipt']
        olditems = {} if old is None else {i['id']: i for i in old['items']}
        newitems = {i['id']: i for i in data['receipt']['items']}
        oldsources = set() if old is None else {i['id'] for i in old['items'] + old['adjustments']}
        newsources = {i['id'] for i in data['receipt']['items'] + data['receipt']['adjustments']}
        _require(not newsources.intersection(state['retired_ids']), 'retired_source')
        _require(not (set(olditems) & (newsources - set(newitems))), 'source_kind_conflict')
        _require(not ((oldsources - set(olditems)) & set(newitems)), 'source_kind_conflict')
        removed = set(olditems) - set(newitems)
        _require(not any(c['item_id'] in removed for c in state['claims']), 'claimed_item_deletion')
        state['retired_ids'] = sorted(set(state['retired_ids']) | (oldsources - newsources))
        revisions = {}
        for item_id, item in newitems.items():
            previous = state['item_revisions'].get(item_id, 0)
            revisions[item_id] = previous + int(olditems.get(item_id) != item)
            _revision(revisions[item_id])
        state['item_revisions'] = revisions
        state['receipt'] = data['receipt']
        state['financial_revision'] += 1
        _revision(state['financial_revision'])
        state['review'] = None
        return _claims(state)

    def _set_own_quantity(self, state, actor, data):
        item_id = data['item_id']
        _require(item_id in state['item_revisions'], 'unknown_item')
        _require(data['expected_item_revision'] == state['item_revisions'][item_id], 'item_revision_conflict')
        previous = [c for c in state['claims'] if c['item_id'] == item_id and c['participant_id'] == actor]
        quantity = data['quantity']
        if quantity is None:
            _require(bool(previous), 'claim_missing')
            state['claims'].remove(previous[0])
        else:
            current = sum((Fraction(*c['quantity']) for c in state['claims']
                           if c['item_id'] == item_id and c['participant_id'] != actor
                           and c['financial_revision'] == state['financial_revision']), Fraction())
            item = next(i for i in state['receipt']['items'] if i['id'] == item_id)
            _require(current + Fraction(*quantity) <= Fraction(*item['quantity']), 'quantity_capacity')
            if previous:
                state['claims'].remove(previous[0])
            state['claims'].append({'item_id': item_id, 'participant_id': actor,
                                    'quantity': quantity, 'financial_revision': state['financial_revision']})
        state['item_revisions'][item_id] += 1
        _revision(state['item_revisions'][item_id])
        return tuple(c for c in _claims(state) if c.item_id == item_id and c.participant_id == actor)

    def _review_receipt(self, state, actor, data):
        _require(data['receipt_digest'] == _receipt_digest(state['receipt']), 'receipt_digest_conflict')
        issues = self._receipt_issues(state)
        _require(not issues, issues[0] if issues else 'receipt_issue')
        state['review'] = {'participant_id': actor, 'financial_revision': state['financial_revision'],
                           'receipt_digest': data['receipt_digest'], 'command_id': data['command_id']}

    def _finalize(self, state, meal_id):
        review = state['review']
        _require(review is not None and review['financial_revision'] == state['financial_revision']
                 and review['receipt_digest'] == _receipt_digest(state['receipt']), 'review_required')
        issues = self._issues(state)
        _require(not issues, issues[0] if issues else 'draft_incomplete')
        receipt = state['receipt']
        people = tuple(p[0] for p in self._db.execute('SELECT id FROM participants WHERE meal_id=? ORDER BY id', (meal_id,)))
        items = tuple(calc.Item(i['id'], i['line_sen'],
                                calc.Split('quantity', tuple(calc.Share(c.participant_id, c.quantity)
                                     for c in _claims(state) if c.item_id == i['id'])),
                                Fraction(*i['quantity'])) for i in receipt['items'])
        adjustments = tuple(calc.Adjustment(a['id'], a['kind'], a['amount_sen'],
                                            tuple(a['eligible_item_ids'])) for a in receipt['adjustments'])
        try:
            result = calc.calculate(calc.Meal(people, items, receipt['subtotal_sen'], receipt['total_sen'],
                                               adjustments, receipt['included_tax_sen']))
        except calc.CalculationError:
            raise AuthorityError('calculation_rejected') from None
        state['calculation'] = _calculation_data(result)

    def _revoke(self, meal_id, data):
        now = self._now()
        if data['kind'] == 'RevokeSession':
            sess_up = self._db.execute('UPDATE sessions SET revoked=1 WHERE meal_id=? AND participant_id=? AND revoked=0',
                                       (meal_id, data['participant_id'])).rowcount
            inv_up = self._db.execute('UPDATE invitations SET revoked=1 WHERE meal_id=? AND participant_id=? AND revoked=0 AND consumed=0 AND expires>?',
                                      (meal_id, data['participant_id'], now)).rowcount
            _require(sess_up + inv_up > 0, 'already_revoked')
        elif data['kind'] == 'RevokeMembership':
            part_up = self._db.execute('UPDATE participants SET active=0 WHERE meal_id=? AND id=? AND active=1',
                                       (meal_id, data['participant_id'])).rowcount
            self._db.execute('UPDATE sessions SET revoked=1 WHERE meal_id=? AND participant_id=? AND revoked=0',
                             (meal_id, data['participant_id']))
            self._db.execute('UPDATE invitations SET revoked=1 WHERE meal_id=? AND participant_id=? AND revoked=0 AND consumed=0 AND expires>?',
                             (meal_id, data['participant_id'], now))
            _require(part_up == 1, 'already_revoked')
        elif data['kind'] == 'RevokeInvitation':
            inv_up = self._db.execute('UPDATE invitations SET revoked=1 WHERE meal_id=? AND participant_id=? AND revoked=0 AND consumed=0 AND expires>?',
                                      (meal_id, data['participant_id'], now)).rowcount
            _require(inv_up > 0, 'already_revoked')

    def apply(self, credential, meal_id, command):
        verifier = _verifier(credential)
        _id(meal_id)
        data = _command_data(command)
        body = _wire(data)
        digest = hashlib.sha256(b'settletable-command-digest-v1\0' + body).digest()
        committed = False
        commit_attempted = False
        try:
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN IMMEDIATE')
            actor, organizer = self._authenticate(verifier, meal_id)
            self._permission(actor, organizer, meal_id, data)
            saved = self._db.execute('SELECT body,digest,result FROM commands WHERE meal_id=? AND participant_id=? AND command_id=?',
                                     (meal_id, actor, command.command_id)).fetchone()
            if saved is not None:
                _require(saved[0] == body and saved[1] == digest, 'command_conflict')
                result = _decode_result(saved[2])
                self._db.execute('COMMIT')
                return result
            state = json.loads(self._db.execute('SELECT state FROM meals WHERE id=?', (meal_id,)).fetchone()[0])
            security = data['kind'] in ('RevokeSession', 'RevokeMembership', 'RevokeInvitation')
            if not security:
                _require(state['calculation'] is None, 'finalized')
                _require(self._db.execute('SELECT COUNT(*) FROM commands WHERE meal_id=? AND security=0', (meal_id,)).fetchone()[0] < 10_000,
                         'resource_limit')
            else:
                _require(self._db.execute('SELECT COUNT(*) FROM commands WHERE meal_id=? AND security=1', (meal_id,)).fetchone()[0] < 15_000,
                         'resource_limit')
            if 'expected_revision' in data:
                _require(data['expected_revision'] == state['revision'], 'revision_conflict')
            if 'expected_financial_revision' in data:
                _require(data['expected_financial_revision'] == state['financial_revision'], 'financial_revision_conflict')
            if data['kind'] == 'ReplaceReceipt':
                changed = self._replace_receipt(state, data)
            elif data['kind'] == 'SetOwnQuantity':
                changed = self._set_own_quantity(state, actor, data)
            elif data['kind'] == 'ReviewReceipt':
                self._review_receipt(state, actor, data)
                changed = ()
            elif data['kind'] == 'Finalize':
                self._finalize(state, meal_id)
                changed = ()
            elif security:
                self._revoke(meal_id, data)
                changed = ()
            else:
                raise AuthorityError('unsupported_command')
            state['revision'] += 1
            _revision(state['revision'])
            state_bytes = _wire(state)
            _require(security or len(state_bytes) <= 900_000, 'resource_limit')
            self._db.execute('UPDATE meals SET state=? WHERE id=?', (state_bytes, meal_id))
            self._hook('after_state')
            result_bytes = _wire({'command_id': command.command_id, 'kind': data['kind'],
                                  'revision': state['revision'], 'financial_revision': state['financial_revision'],
                                  'changed_claims': [_claim_data(c) for c in changed],
                                  'calculation': state['calculation'] if data['kind'] == 'Finalize' else None})
            self._db.execute('INSERT INTO commands VALUES (?,?,?,?,?,?,?)',
                             (meal_id, actor, command.command_id, body, digest, result_bytes, int(security)))
            self._hook('after_result')
            self._hook('before_commit')
            commit_attempted = True
            self._db.execute('COMMIT')
            committed = True
            self._hook('after_commit')
            return _decode_result(result_bytes)
        except AuthorityError:
            self._rollback()
            if committed:
                raise AuthorityError('commit_uncertain') from None
            raise
        except sqlite3.Error as error:
            try:
                transaction_open = self._db is not None and self._db.in_transaction
            except Exception:
                transaction_open = None
            uncertain = committed or (commit_attempted and transaction_open is not True)
            if uncertain:
                self._rollback()
                raise AuthorityError('commit_uncertain') from None
            self._storage_failure(error)
        except Exception:
            self._rollback()
            raise AuthorityError('commit_uncertain' if committed else 'storage_error') from None
