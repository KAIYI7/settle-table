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


def _require(condition, code='invalid_input'):
    if not condition:
        raise AuthorityError(code)


def _id(value):
    _require(type(value) is str and 1 <= len(value) <= 64
             and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]*', value) is not None)


def _text(value, maximum):
    _require(type(value) is str and 1 <= len(value) <= maximum)
    _require(not any(unicodedata.category(c) in ('Cc', 'Cs') for c in value))


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


def _revision(value):
    _require(type(value) is int and 0 <= value < 9_223_372_036_854_775_807)


def _money(value, *, signed=False):
    if value is not None:
        _require(type(value) is int and abs(value) <= 1_000_000_000
                 and (signed or value >= 0))


def _rational(value):
    _require(type(value) in (int, Fraction))
    _require(0 < value <= 1_000_000 and value.numerator <= 1_000_000_000
             and value.denominator <= 1_000_000)
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
                               RevokeSession, RevokeMembership))
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
    if type(command) in (RevokeSession, RevokeMembership):
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
                          data['financial_revision'], claims, None, wire)


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
        value = self._clock()
        _require(type(value) in (int, float) and math.isfinite(value)
                 and abs(value) <= 1_000_000_000_000, 'storage_error')
        return value

    def _hook(self, stage):
        if self._failure_hook is not None:
            self._failure_hook(stage)

    def _rollback(self):
        try:
            if self._db is not None and self._db.in_transaction:
                self._db.execute('ROLLBACK')
        except Exception:
            # An unconfirmed transaction must never be reused after cleanup fails.
            self.close()

    def _storage_failure(self, error):
        self._rollback()
        code = 'busy' if getattr(error, 'sqlite_errorcode', None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) else 'storage_error'
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
        grants = tuple(SessionGrant(p.id, secrets.token_urlsafe(32)) for p in participants)
        state = {'revision': 0, 'financial_revision': 0, 'receipt': None,
                 'item_revisions': {}, 'claims': [], 'review': None,
                 'calculation': None, 'retired_ids': []}
        committed = False
        try:
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
            self._db.execute('COMMIT')
            committed = True
            self._hook('after_commit')
            return BootstrapResult(meal_id, grants)
        except AuthorityError:
            self._rollback()
            raise
        except sqlite3.Error as error:
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
            result = DraftSnapshot(meal_id, state['revision'], state['financial_revision'],
                                   _receipt_digest(state['receipt']), _decode_receipt(state['receipt']),
                                   tuple(ItemState(i, revision) for i, revision in sorted(state['item_revisions'].items())),
                                   _claims(state), None, None, False, self._issues(state),
                                   tuple(Participant(p[0], p[1], bool(p[2])) for p in people),
                                   tuple(p[0] for p in people if not p[3]))
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
        if data['kind'] in ('RevokeSession', 'RevokeMembership'):
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
            security = data['kind'] in ('RevokeSession', 'RevokeMembership')
            if not security:
                _require(state['calculation'] is None, 'finalized')
                _require(self._db.execute('SELECT COUNT(*) FROM commands WHERE meal_id=? AND security=0', (meal_id,)).fetchone()[0] < 10_000,
                         'resource_limit')
            if 'expected_revision' in data:
                _require(data['expected_revision'] == state['revision'], 'revision_conflict')
            if 'expected_financial_revision' in data:
                _require(data['expected_financial_revision'] == state['financial_revision'], 'financial_revision_conflict')
            if data['kind'] == 'ReplaceReceipt':
                changed = self._replace_receipt(state, data)
            elif data['kind'] == 'SetOwnQuantity':
                changed = self._set_own_quantity(state, actor, data)
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
                                  'changed_claims': [_claim_data(c) for c in changed], 'calculation': None})
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
            raise
        except sqlite3.Error as error:
            uncertain = committed or (commit_attempted and self._db is not None and not self._db.in_transaction)
            if uncertain:
                self._rollback()
                raise AuthorityError('commit_uncertain') from None
            self._storage_failure(error)
        except Exception:
            self._rollback()
            raise AuthorityError('commit_uncertain' if committed else 'storage_error') from None
