"""Durable local draft acceptance. Not an Internet authentication endpoint."""
from dataclasses import dataclass, field
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import secrets
import sqlite3
import time
import unicodedata

from . import calculation as calc
from .funding import (
    FundingSnapshot,
    ParticipantNetBalance,
    PayerContributionRecord,
    compute_net_balances,
    derive_contribution_id,
)
from .settlement import (
    ParticipantOutstandingBalance,
    PeerTransferRecord,
    SettlementSnapshot,
    SuggestedTransfer,
    compute_settlement,
    derive_transfer_id,
)


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
class JoinRequestRecord:
    id: str
    participant_id: str
    display_name: str
    status: str
    created_at: float | int
    expires: float | int


@dataclass(frozen=True, slots=True)
class OrganizerClaimGrant:
    meal_id: str
    token: str = field(repr=False)
    expires: float | int
    issue_id: str


@dataclass(frozen=True, slots=True)
class OrganizerClaimInspection:
    valid: bool
    meal_id: str | None = None
    organizer_id: str | None = None
    organizer_name: str | None = None
    expires: float | int | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    meal_id: str
    sessions: tuple[SessionGrant, ...] = field(repr=False)
    organizer_claim: OrganizerClaimGrant | None = None


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
    scope_mode: str | None = None


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
class AssignParticipantQuantity:
    command_id: str
    participant_id: str
    item_id: str
    quantity: int | Fraction | None
    expected_item_revision: int
    expected_financial_revision: int


@dataclass(frozen=True, slots=True)
class AllocationSpec:
    participant_id: str
    quantity: int | Fraction


@dataclass(frozen=True, slots=True)
class SetItemAllocations:
    command_id: str
    item_id: str
    allocations: tuple[AllocationSpec, ...]
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
class RecordContribution:
    command_id: str
    expected_revision: int
    participant_id: str
    amount_sen: int
    payment_method: str | None = None


@dataclass(frozen=True, slots=True)
class ReverseContribution:
    command_id: str
    expected_revision: int
    contribution_id: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class RecordTransfer:
    command_id: str
    expected_revision: int
    sender_id: str
    receiver_id: str
    amount_sen: int
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ReverseTransfer:
    command_id: str
    expected_revision: int
    transfer_id: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class Claim:
    item_id: str
    participant_id: str
    quantity: Fraction
    financial_revision: int
    status: str
    assigned_by: str | None = None


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
    contribution_id: str | None = None
    transfer_id: str | None = None


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
    join_requests: tuple[JoinRequestRecord, ...] = ()
    has_receipt_photo: bool = False
    receipt_photo: dict | None = None
    finalized_revision: int | None = None
    funding: FundingSnapshot | None = None
    contributions: tuple[PayerContributionRecord, ...] = ()
    transfers: tuple[PeerTransferRecord, ...] = ()
    settlement: SettlementSnapshot | None = None


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


def _join_claim_verifier(token):
    _require(type(token) is str and len(token) == 43
             and re.fullmatch(r'[A-Za-z0-9_-]{43}', token) is not None,
             'invalid_token')
    return hashlib.sha256(b'settletable-join-claim-v1\0' + token.encode('ascii')).digest()


def _organizer_claim_verifier(token):
    _require(type(token) is str and len(token) == 43
             and re.fullmatch(r'[A-Za-z0-9_-]{43}', token) is not None,
             'invalid_organizer_claim')
    return hashlib.sha256(b'settletable-organizer-claim-v1\0' + token.encode('ascii')).digest()


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
        _require(change.scope_mode in (None, 'all_items', 'fixed_items'))
        _tuple(change.eligible_item_ids, 500, 1)
        scope = set()
        for item_id in change.eligible_item_ids:
            _id(item_id)
            _require(item_id in {i.id for i in receipt.items} and item_id not in scope)
            scope.add(item_id)
        if change.scope_mode == 'all_items':
            _require(scope == {i.id for i in receipt.items})
        entry = {'id': change.id, 'label': change.label, 'kind': change.kind,
                 'amount_sen': change.amount_sen, 'eligible_item_ids': sorted(scope),
                 'rationale': change.rationale}
        if change.scope_mode is not None:
            entry['scope_mode'] = change.scope_mode
        changes.append(entry)
    return {'items': sorted(items, key=lambda i: i['id']), 'subtotal_sen': receipt.subtotal_sen,
            'total_sen': receipt.total_sen, 'adjustments': sorted(changes, key=lambda a: a['id']),
            'included_tax_sen': receipt.included_tax_sen}


def _decode_receipt(data):
    if data is None:
        return None
    return Receipt(tuple(ReceiptItem(i['id'], i['label'], Fraction(*i['quantity']), i['line_sen'])
                         for i in data['items']), data['subtotal_sen'], data['total_sen'],
                   tuple(ReceiptAdjustment(a['id'], a['label'], a['kind'], a['amount_sen'],
                                           tuple(a['eligible_item_ids']), a['rationale'], a.get('scope_mode'))
                         for a in data['adjustments']), data['included_tax_sen'])


def _receipt_digest(receipt):
    return None if receipt is None else hashlib.sha256(b'settletable-receipt-v1\0' + _wire(receipt)).hexdigest()


def _command_data(command):
    _require(type(command) in (ReplaceReceipt, SetOwnQuantity, AssignParticipantQuantity, SetItemAllocations, ReviewReceipt, Finalize,
                               RevokeSession, RevokeMembership, RevokeInvitation,
                               RecordContribution, ReverseContribution,
                               RecordTransfer, ReverseTransfer))
    _id(command.command_id)
    data = {'contract': 'settletable-command-v1', 'kind': type(command).__name__, 'command_id': command.command_id}
    if type(command) is SetOwnQuantity:
        _id(command.item_id)
        _revision(command.expected_item_revision)
        data.update(item_id=command.item_id, quantity=None if command.quantity is None else _rational(command.quantity),
                    expected_item_revision=command.expected_item_revision)
    elif type(command) is AssignParticipantQuantity:
        _id(command.participant_id)
        _id(command.item_id)
        _revision(command.expected_item_revision)
        data.update(participant_id=command.participant_id, item_id=command.item_id,
                    quantity=None if command.quantity is None else _rational(command.quantity),
                    expected_item_revision=command.expected_item_revision)
    elif type(command) is SetItemAllocations:
        _id(command.item_id)
        _revision(command.expected_item_revision)
        _require(isinstance(command.allocations, (tuple, list)))
        _require(len(command.allocations) <= 500)
        alloc_data = []
        for a in command.allocations:
            if isinstance(a, AllocationSpec):
                pid = a.participant_id
                qty = a.quantity
            elif isinstance(a, (tuple, list)) and len(a) == 2:
                pid, qty = a
            elif isinstance(a, dict) and 'participant_id' in a and 'quantity' in a:
                pid, qty = a['participant_id'], a['quantity']
            else:
                _require(False, 'invalid_input')
            _id(pid)
            alloc_data.append({'participant_id': pid, 'quantity': _rational(qty)})
        data.update(item_id=command.item_id,
                    allocations=alloc_data,
                    expected_item_revision=command.expected_item_revision)
    elif type(command) is RecordContribution:
        _revision(command.expected_revision)
        data['expected_revision'] = command.expected_revision
        _id(command.participant_id)
        _money(command.amount_sen)
        _require(1 <= command.amount_sen <= 1_000_000_000, 'invalid_input')
        method = command.payment_method
        if method is not None:
            _require(method in ('cash', 'card', 'ewallet', 'bank_transfer', 'other'), 'invalid_input')
        data.update(participant_id=command.participant_id, amount_sen=command.amount_sen,
                    payment_method=method)
    elif type(command) is ReverseContribution:
        _revision(command.expected_revision)
        data['expected_revision'] = command.expected_revision
        _id(command.contribution_id)
        reason = command.reason
        if reason is not None:
            _text(reason, 200)
        data.update(contribution_id=command.contribution_id, reason=reason)
    elif type(command) is RecordTransfer:
        _revision(command.expected_revision)
        data['expected_revision'] = command.expected_revision
        _id(command.sender_id)
        _id(command.receiver_id)
        _require(command.sender_id != command.receiver_id, 'self_transfer_prohibited')
        _money(command.amount_sen)
        _require(1 <= command.amount_sen <= 1_000_000_000, 'invalid_input')
        note = command.note
        if note is not None:
            _text(note, 200)
        data.update(sender_id=command.sender_id, receiver_id=command.receiver_id,
                    amount_sen=command.amount_sen, note=note)
    elif type(command) is ReverseTransfer:
        _revision(command.expected_revision)
        data['expected_revision'] = command.expected_revision
        _id(command.transfer_id)
        reason = command.reason
        if reason is not None:
            _text(reason, 200)
        data.update(transfer_id=command.transfer_id, reason=reason)
    else:
        _revision(command.expected_revision)
        data['expected_revision'] = command.expected_revision
    if type(command) in (ReplaceReceipt, SetOwnQuantity, AssignParticipantQuantity, SetItemAllocations, ReviewReceipt, Finalize):
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
                       c['financial_revision'], 'confirmed' if c['financial_revision'] == state['financial_revision'] else 'pending',
                       c.get('assigned_by'))
                 for c in sorted(state['claims'], key=lambda c: (c['item_id'], c['participant_id'])))


def _decode_result(wire):
    data = json.loads(wire)
    claims = tuple(Claim(c['item_id'], c['participant_id'], Fraction(*c['quantity']),
                         c['financial_revision'], c['status'], c.get('assigned_by')) for c in data['changed_claims'])
    return AcceptedResult(data['command_id'], data['kind'], data['revision'],
                          data['financial_revision'], claims, _decode_calculation(data['calculation']), wire,
                          data.get('contribution_id'),
                          data.get('transfer_id'))


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
    data = {'item_id': claim.item_id, 'participant_id': claim.participant_id,
            'quantity': [claim.quantity.numerator, claim.quantity.denominator],
            'financial_revision': claim.financial_revision, 'status': claim.status}
    if claim.assigned_by is not None:
        data['assigned_by'] = claim.assigned_by
    return data


class Authority:
    """One SQLite connection; each instance may be used by its owning thread."""
    def __init__(self, path, *, clock=time.time, failure_hook=None, storage_dir=None):
        self._clock = clock if clock is not None else time.time
        self._failure_hook = failure_hook
        self._db = None
        self._temp_storage_dir = None
        if storage_dir is not None:
            self.storage_dir = Path(storage_dir)
        elif str(path) == ':memory:':
            import tempfile
            self._temp_storage_dir = tempfile.TemporaryDirectory()
            self.storage_dir = Path(self._temp_storage_dir.name)
        else:
            self.storage_dir = Path(path).parent / 'receipt_photos'
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
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
                CREATE TABLE IF NOT EXISTS notion_exports (
                    meal_id TEXT NOT NULL REFERENCES meals(id),
                    finalized_revision INTEGER NOT NULL,
                    page_id TEXT NOT NULL,
                    page_url TEXT NOT NULL,
                    exported_at REAL NOT NULL,
                    export_digest TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'completed',
                    PRIMARY KEY(meal_id, finalized_revision));
                CREATE TABLE IF NOT EXISTS receipt_photos (
                    meal_id TEXT PRIMARY KEY REFERENCES meals(id) ON DELETE CASCADE,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    byte_size INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    uploaded_at REAL NOT NULL,
                    uploaded_by TEXT NOT NULL,
                    FOREIGN KEY(meal_id, uploaded_by) REFERENCES participants(meal_id, id));
                CREATE TABLE IF NOT EXISTS join_requests (
                    id TEXT PRIMARY KEY,
                    meal_id TEXT NOT NULL,
                    participant_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    verifier BLOB NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires REAL NOT NULL,
                    FOREIGN KEY(meal_id,participant_id) REFERENCES participants(meal_id,id),
                    FOREIGN KEY(meal_id) REFERENCES meals(id) ON DELETE CASCADE);
                CREATE INDEX IF NOT EXISTS idx_join_requests_meal_status ON join_requests (meal_id, status);
                CREATE TABLE IF NOT EXISTS organizer_claims (
                    verifier BLOB PRIMARY KEY,
                    meal_id TEXT NOT NULL,
                    issuer_id TEXT NOT NULL,
                    issue_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires REAL NOT NULL,
                    consumed INTEGER NOT NULL DEFAULT 0,
                    revoked INTEGER NOT NULL DEFAULT 0,
                    generation INTEGER NOT NULL,
                    UNIQUE(meal_id, issue_id),
                    FOREIGN KEY(meal_id) REFERENCES meals(id) ON DELETE CASCADE);
                CREATE INDEX IF NOT EXISTS idx_organizer_claims_meal_status ON organizer_claims (meal_id, consumed, revoked);
                CREATE TABLE IF NOT EXISTS payment_simulations (
                    integration_id TEXT NOT NULL, meal_id TEXT NOT NULL,
                    finalize_actor_id TEXT NOT NULL, finalize_command_id TEXT NOT NULL,
                    participant_id TEXT NOT NULL, purpose_version TEXT NOT NULL,
                    client_reference TEXT NOT NULL, basis BLOB NOT NULL,
                    payment_id TEXT, payment_version INTEGER, payment_status TEXT,
                    payment_updated_at TEXT, observed_at REAL,
                    outcome TEXT NOT NULL, retry_after INTEGER,
                    PRIMARY KEY(integration_id,meal_id,finalize_actor_id,finalize_command_id,participant_id,purpose_version),
                    UNIQUE(integration_id,client_reference),
                    FOREIGN KEY(meal_id,participant_id) REFERENCES participants(meal_id,id));
                CREATE TABLE IF NOT EXISTS payer_contributions (
                    meal_id TEXT NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
                    contribution_id TEXT NOT NULL,
                    command_id TEXT NOT NULL,
                    participant_id TEXT NOT NULL,
                    amount_sen INTEGER NOT NULL CHECK (amount_sen >= 1 AND amount_sen <= 1000000000),
                    payment_method TEXT CHECK (payment_method IN ('cash', 'card', 'ewallet', 'bank_transfer', 'other') OR payment_method IS NULL),
                    created_at REAL NOT NULL,
                    created_by TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'reversed')),
                    reversed_at REAL,
                    reversed_by TEXT,
                    reversal_command_id TEXT,
                    reversal_reason TEXT,
                    PRIMARY KEY(meal_id, contribution_id),
                    UNIQUE(meal_id, command_id),
                    FOREIGN KEY(meal_id, participant_id) REFERENCES participants(meal_id, id),
                    FOREIGN KEY(meal_id, created_by) REFERENCES participants(meal_id, id),
                    FOREIGN KEY(meal_id, reversed_by) REFERENCES participants(meal_id, id));
                CREATE INDEX IF NOT EXISTS idx_payer_contributions_status ON payer_contributions(meal_id, status);
                CREATE TRIGGER IF NOT EXISTS prevent_payer_contributions_delete
                BEFORE DELETE ON payer_contributions
                BEGIN
                    SELECT RAISE(FAIL, 'payer_contributions rows cannot be deleted');
                END;
                CREATE TRIGGER IF NOT EXISTS prevent_payer_contributions_tamper
                BEFORE UPDATE ON payer_contributions
                FOR EACH ROW
                BEGIN
                    SELECT CASE
                        WHEN OLD.status != 'active' THEN
                            RAISE(FAIL, 'cannot modify inactive contribution')
                        WHEN NEW.status != 'reversed' THEN
                            RAISE(FAIL, 'invalid status transition')
                        WHEN NEW.meal_id != OLD.meal_id OR NEW.contribution_id != OLD.contribution_id
                          OR NEW.command_id != OLD.command_id OR NEW.participant_id != OLD.participant_id
                          OR NEW.amount_sen != OLD.amount_sen OR NEW.created_at != OLD.created_at
                          OR NEW.created_by != OLD.created_by OR (NEW.payment_method IS NOT OLD.payment_method) THEN
                            RAISE(FAIL, 'immutable contribution columns cannot be modified')
                    END;
                END;
                CREATE TABLE IF NOT EXISTS peer_transfers (
                    meal_id TEXT NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
                    transfer_id TEXT NOT NULL,
                    command_id TEXT NOT NULL,
                    sender_id TEXT NOT NULL,
                    receiver_id TEXT NOT NULL,
                    amount_sen INTEGER NOT NULL CHECK (amount_sen >= 1 AND amount_sen <= 1000000000),
                    note TEXT,
                    created_at REAL NOT NULL,
                    created_by TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'reversed')),
                    reversed_at REAL,
                    reversed_by TEXT,
                    reversal_command_id TEXT,
                    reversal_reason TEXT,
                    PRIMARY KEY(meal_id, transfer_id),
                    UNIQUE(meal_id, command_id),
                    CHECK(sender_id != receiver_id),
                    FOREIGN KEY(meal_id, sender_id) REFERENCES participants(meal_id, id),
                    FOREIGN KEY(meal_id, receiver_id) REFERENCES participants(meal_id, id),
                    FOREIGN KEY(meal_id, created_by) REFERENCES participants(meal_id, id),
                    FOREIGN KEY(meal_id, reversed_by) REFERENCES participants(meal_id, id));
                CREATE INDEX IF NOT EXISTS idx_peer_transfers_status ON peer_transfers(meal_id, status);
                CREATE TRIGGER IF NOT EXISTS prevent_peer_transfers_delete
                BEFORE DELETE ON peer_transfers
                BEGIN
                    SELECT RAISE(FAIL, 'peer_transfers rows cannot be deleted');
                END;
                CREATE TRIGGER IF NOT EXISTS prevent_peer_transfers_tamper
                BEFORE UPDATE ON peer_transfers
                FOR EACH ROW
                BEGIN
                    SELECT CASE
                        WHEN OLD.status != 'confirmed' THEN
                            RAISE(FAIL, 'cannot modify inactive transfer')
                        WHEN NEW.status != 'reversed' THEN
                            RAISE(FAIL, 'invalid status transition')
                        WHEN NEW.meal_id != OLD.meal_id OR NEW.transfer_id != OLD.transfer_id
                          OR NEW.command_id != OLD.command_id OR NEW.sender_id != OLD.sender_id
                          OR NEW.receiver_id != OLD.receiver_id OR NEW.amount_sen != OLD.amount_sen
                          OR NEW.created_at != OLD.created_at OR NEW.created_by != OLD.created_by
                          OR (NEW.note IS NOT OLD.note) THEN
                            RAISE(FAIL, 'immutable transfer columns cannot be modified')
                    END;
                END;
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
        if getattr(self, '_temp_storage_dir', None) is not None:
            try:
                self._temp_storage_dir.cleanup()
            except Exception:
                pass
            self._temp_storage_dir = None

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

    def _issue_organizer_claim_in_tx(self, meal_id, organizer_id, *, claim_ttl=604800, issue_id=None, issuer_id=None):
        if issue_id is None:
            issue_id = f'claim-{secrets.token_urlsafe(16)}'
        token = secrets.token_urlsafe(32)
        claim_verifier = _organizer_claim_verifier(token)
        now = self._now()
        expires = now + claim_ttl
        actor = issuer_id or organizer_id

        # Invalidate prior active unconsumed claims for this meal
        self._db.execute(
            'UPDATE organizer_claims SET revoked=1 WHERE meal_id=? AND consumed=0 AND revoked=0 AND expires>?',
            (meal_id, now)
        )

        self._db.execute(
            '''INSERT INTO organizer_claims (verifier, meal_id, issuer_id, issue_id, created_at, expires, consumed, revoked, generation)
               VALUES (?, ?, ?, ?, ?, ?, 0, 0, 1)''',
            (claim_verifier, meal_id, actor, issue_id, now, expires)
        )
        return OrganizerClaimGrant(meal_id, token, expires, issue_id)

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
        _require(type(session_ttl) is int and 1 <= session_ttl <= 2592000)
        state = {'revision': 0, 'financial_revision': 0, 'receipt': None,
                 'item_revisions': {}, 'claims': [], 'review': None,
                 'calculation': None, 'retired_ids': [], 'finalized_revision': None}
        committed = False
        commit_attempted = False
        try:
            grants = tuple(SessionGrant(p.id, secrets.token_urlsafe(32)) for p in participants)
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN IMMEDIATE')
            _require(self._db.execute('SELECT 1 FROM meals WHERE id=?', (meal_id,)).fetchone() is None, 'meal_exists')
            self._db.execute('INSERT INTO meals VALUES (?,?)', (meal_id, _wire(state)))
            expires = self._now() + session_ttl
            org_person = next(p for p in participants if p.organizer)
            for person, grant in zip(participants, grants):
                self._db.execute('INSERT INTO participants VALUES (?,?,?,?,1)',
                                 (meal_id, person.id, person.name, int(person.organizer)))
                self._db.execute('INSERT INTO sessions VALUES (?,?,?,?,0)',
                                 (_verifier(grant.credential), meal_id, person.id, expires))
            org_claim = self._issue_organizer_claim_in_tx(meal_id, org_person.id, claim_ttl=session_ttl)
            self._hook('after_state')
            self._hook('before_commit')
            commit_attempted = True
            self._db.execute('COMMIT')
            committed = True
            self._hook('after_commit')
            return BootstrapResult(meal_id, grants, org_claim)
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
            auth_user, is_organizer = self._authenticate(verifier, meal_id)
            state = json.loads(self._db.execute('SELECT state FROM meals WHERE id=?', (meal_id,)).fetchone()[0])
            people = self._db.execute('SELECT id,name,organizer,active FROM participants WHERE meal_id=? ORDER BY id', (meal_id,)).fetchall()
            inv_rows = self._db.execute('''SELECT participant_id,created_at,expires,consumed,revoked,issue_id
                FROM invitations WHERE meal_id=? ORDER BY participant_id,created_at,issue_id''', (meal_id,)).fetchall()
            invitations = tuple(InvitationRecord(r[0], r[1], r[2], bool(r[3]), bool(r[4]), r[5]) for r in inv_rows)
            join_requests = ()
            if is_organizer:
                now = self._now()
                jr_rows = self._db.execute('''SELECT id,participant_id,display_name,status,created_at,expires
                    FROM join_requests WHERE meal_id=? AND expires>? AND status IN ('pending', 'approved')
                    ORDER BY created_at DESC''', (meal_id, now)).fetchall()
                join_requests = tuple(JoinRequestRecord(r[0], r[1], r[2], r[3], r[4], r[5]) for r in jr_rows)
            photo_row = self._db.execute(
                'SELECT filename, content_type, byte_size, width, height, uploaded_at FROM receipt_photos WHERE meal_id=?',
                (meal_id,)
            ).fetchone()
            has_receipt_photo = False
            receipt_photo = None
            if photo_row:
                photo_path = (self.storage_dir / photo_row[0]).resolve()
                if photo_path.is_relative_to(self.storage_dir.resolve()) and photo_path.is_file():
                    has_receipt_photo = True
                    receipt_photo = {
                        'filename': photo_row[0],
                        'content_type': photo_row[1],
                        'byte_size': photo_row[2],
                        'width': photo_row[3],
                        'height': photo_row[4],
                        'uploaded_at': photo_row[5],
                    }
            finalized_revision = state.get('finalized_revision')
            if finalized_revision is None and state['calculation'] is not None:
                finalized_revision = state['revision']
            contributions = ()
            funding = None
            transfers = ()
            settlement = None
            if state['calculation'] is not None:
                contrib_rows = self._db.execute('''
                    SELECT contribution_id, command_id, participant_id, amount_sen, payment_method,
                           created_at, created_by, status, reversed_at, reversed_by,
                           reversal_command_id, reversal_reason
                    FROM payer_contributions
                    WHERE meal_id=?
                    ORDER BY created_at ASC, contribution_id ASC
                ''', (meal_id,)).fetchall()
                part_names = {p[0]: p[1] for p in people}
                active_set = {p[0] for p in people if p[3]}
                contrib_records = tuple(
                    PayerContributionRecord(
                        contribution_id=r[0],
                        command_id=r[1],
                        participant_id=r[2],
                        participant_name=part_names.get(r[2], r[2]),
                        amount_sen=r[3],
                        payment_method=r[4],
                        created_at=r[5],
                        created_by=r[6],
                        status=r[7],
                        reversed_at=r[8],
                        reversed_by=r[9],
                        reversal_command_id=r[10],
                        reversal_reason=r[11],
                    ) for r in contrib_rows
                )
                contributions = contrib_records
                calc_consumption = [(p['participant_id'], p['sen']) for p in state['calculation']['consumption']]
                receipt_total = state['receipt']['total_sen']
                funding, net_balances = compute_net_balances(
                    consumption_records=calc_consumption,
                    participant_names=part_names,
                    active_participants=active_set,
                    active_contributions=contrib_records,
                    receipt_total_sen=receipt_total,
                )
                xfer_rows = self._db.execute('''
                    SELECT transfer_id, command_id, sender_id, receiver_id, amount_sen,
                           note, created_at, created_by, status, reversed_at, reversed_by,
                           reversal_command_id, reversal_reason
                    FROM peer_transfers
                    WHERE meal_id=?
                    ORDER BY created_at ASC, transfer_id ASC
                ''', (meal_id,)).fetchall()
                transfers = tuple(
                    PeerTransferRecord(
                        transfer_id=r[0], command_id=r[1], sender_id=r[2], receiver_id=r[3],
                        amount_sen=r[4], note=r[5], created_at=r[6], created_by=r[7], status=r[8],
                        reversed_at=r[9], reversed_by=r[10], reversal_command_id=r[11], reversal_reason=r[12],
                    ) for r in xfer_rows
                )
                settlement = compute_settlement(
                    base_net_balances=net_balances,
                    transfers=transfers,
                    unfunded_sen=funding.unfunded_sen,
                )
            result = DraftSnapshot(meal_id, state['revision'], state['financial_revision'],
                                   _receipt_digest(state['receipt']), _decode_receipt(state['receipt']),
                                   tuple(ItemState(i, revision) for i, revision in sorted(state['item_revisions'].items())),
                                   _claims(state), None if state['review'] is None else ReviewRecord(**state['review']),
                                   _decode_calculation(state['calculation']), state['calculation'] is not None,
                                   self._issues(state),
                                   tuple(Participant(p[0], p[1], bool(p[2])) for p in people),
                                   tuple(p[0] for p in people if not p[3]),
                                   invitations,
                                   join_requests,
                                   has_receipt_photo,
                                   receipt_photo,
                                   finalized_revision,
                                   funding,
                                   contributions,
                                   transfers,
                                   settlement)
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
        _require(type(invite_ttl) is int and 1 <= invite_ttl <= 2592000)
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

    def issue_organizer_claim(self, meal_id, *, claim_ttl=604800, issue_id=None):
        """Host/Administrative issuance of an organizer claim link without requiring existing session."""
        _id(meal_id)
        _require(type(claim_ttl) is int and 1 <= claim_ttl <= 2592000)
        if issue_id is not None:
            _id(issue_id)
        try:
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN IMMEDIATE')
            meal_row = self._db.execute('SELECT 1 FROM meals WHERE id=?', (meal_id,)).fetchone()
            _require(meal_row is not None, 'meal_not_found')
            org_row = self._db.execute(
                'SELECT id FROM participants WHERE meal_id=? AND organizer=1 AND active=1',
                (meal_id,)
            ).fetchone()
            _require(org_row is not None, 'organizer_not_found')
            grant = self._issue_organizer_claim_in_tx(meal_id, org_row[0], claim_ttl=claim_ttl, issue_id=issue_id)
            self._db.execute('COMMIT')
            return grant
        except AuthorityError:
            self._rollback()
            raise
        except sqlite3.Error as error:
            self._storage_failure(error)
        except Exception:
            self._rollback()
            raise AuthorityError('storage_error') from None

    def issue_organizer_recovery(self, organizer_credential, meal_id, *, claim_ttl=604800, issue_id=None):
        """Active organizer generates a backup recovery link for themselves."""
        verifier = _verifier(organizer_credential)
        _id(meal_id)
        _require(type(claim_ttl) is int and 1 <= claim_ttl <= 2592000)
        if issue_id is not None:
            _id(issue_id)
        try:
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN IMMEDIATE')
            actor, is_organizer = self._authenticate(verifier, meal_id)
            _require(bool(is_organizer), 'forbidden')
            grant = self._issue_organizer_claim_in_tx(meal_id, actor, claim_ttl=claim_ttl, issue_id=issue_id, issuer_id=actor)
            self._db.execute('COMMIT')
            return grant
        except AuthorityError:
            self._rollback()
            raise
        except sqlite3.Error as error:
            self._storage_failure(error)
        except Exception:
            self._rollback()
            raise AuthorityError('storage_error') from None

    def inspect_organizer_claim(self, token):
        try:
            claim_verifier = _organizer_claim_verifier(token)
        except AuthorityError:
            return OrganizerClaimInspection(valid=False, reason='invalid_token')

        try:
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN')
            now = self._now()
            row = self._db.execute('''
                SELECT c.meal_id, c.expires, c.consumed, c.revoked, p.id, p.name, p.active
                FROM organizer_claims c
                JOIN participants p ON p.meal_id = c.meal_id AND p.organizer = 1
                WHERE c.verifier = ?
            ''', (claim_verifier,)).fetchone()
            self._db.execute('COMMIT')
            if row is None:
                return OrganizerClaimInspection(valid=False, reason='not_found')
            meal_id, expires, consumed, revoked, org_id, org_name, active = row
            if not active or revoked:
                return OrganizerClaimInspection(valid=False, meal_id=meal_id, organizer_id=org_id, organizer_name=org_name, expires=expires, reason='revoked')
            if consumed:
                return OrganizerClaimInspection(valid=False, meal_id=meal_id, organizer_id=org_id, organizer_name=org_name, expires=expires, reason='consumed')
            if expires <= now:
                return OrganizerClaimInspection(valid=False, meal_id=meal_id, organizer_id=org_id, organizer_name=org_name, expires=expires, reason='expired')
            return OrganizerClaimInspection(valid=True, meal_id=meal_id, organizer_id=org_id, organizer_name=org_name, expires=expires)
        except Exception:
            self._rollback()
            raise AuthorityError('storage_error') from None

    def claim_organizer_session(self, claim_token, meal_id, *, session_ttl=3600):
        claim_verifier = _organizer_claim_verifier(claim_token)
        _id(meal_id)
        _require(type(session_ttl) is int and 1 <= session_ttl <= 2592000)
        committed = False
        commit_attempted = False
        try:
            credential = secrets.token_urlsafe(32)
            sess_verifier = _verifier(credential)
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN IMMEDIATE')
            now = self._now()
            row = self._db.execute('''
                SELECT expires, consumed, revoked
                FROM organizer_claims
                WHERE verifier = ? AND meal_id = ?
            ''', (claim_verifier, meal_id)).fetchone()
            _require(row is not None, 'invalid_organizer_claim')
            expires, consumed, revoked = row
            _require(revoked == 0, 'organizer_claim_revoked')
            _require(consumed == 0, 'organizer_claim_consumed')
            _require(expires > now, 'organizer_claim_expired')

            org_row = self._db.execute(
                'SELECT id, active FROM participants WHERE meal_id=? AND organizer=1',
                (meal_id,)
            ).fetchone()
            _require(org_row is not None and org_row[1] == 1, 'organizer_not_found')
            organizer_id = org_row[0]

            # Mark claim consumed
            self._db.execute('UPDATE organizer_claims SET consumed=1 WHERE verifier=?', (claim_verifier,))

            # Issue or refresh organizer session
            sess_expires = now + session_ttl
            self._db.execute('''
                INSERT INTO sessions (verifier, meal_id, participant_id, expires, revoked)
                VALUES (?, ?, ?, ?, 0)
                ON CONFLICT(meal_id, participant_id) DO UPDATE SET verifier=?, expires=?, revoked=0
            ''', (sess_verifier, meal_id, organizer_id, sess_expires, sess_verifier, sess_expires))

            # Bump meal revision
            state = json.loads(self._db.execute('SELECT state FROM meals WHERE id=?', (meal_id,)).fetchone()[0])
            state['revision'] += 1
            _revision(state['revision'])
            self._db.execute('UPDATE meals SET state=? WHERE id=?', (_wire(state), meal_id))

            self._hook('before_commit')
            commit_attempted = True
            self._db.execute('COMMIT')
            committed = True
            self._hook('after_commit')
            return SessionGrant(organizer_id, credential)
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

    def _finalized_allocation(self, credential, meal_id, participant_id, *, initiate=False):
        """Authorized accepted-Finalize seam. Caller owns a short SQLite transaction.

        Never derives identity from the mutable snapshot revision or recalculates money.
        The simulation helper uses this connection so authorization and intent commit
        share one consistent authority snapshot.
        """
        _id(meal_id)
        _id(participant_id)
        actor, organizer = self._authenticate(_verifier(credential), meal_id)
        _require(bool(organizer) if initiate else bool(organizer) or actor == participant_id, 'forbidden')
        target = self._db.execute('SELECT active FROM participants WHERE meal_id=? AND id=?',
                                  (meal_id, participant_id)).fetchone()
        _require(target is not None, 'participant_not_found')
        _require(target[0] == 1, 'participant_inactive')
        state = json.loads(self._db.execute('SELECT state FROM meals WHERE id=?', (meal_id,)).fetchone()[0])
        _require(state['calculation'] is not None, 'meal_not_finalized')
        finalizations = []
        for final_actor, command_id, body, digest, result in self._db.execute(
                'SELECT participant_id,command_id,body,digest,result FROM commands WHERE meal_id=? AND security=0', (meal_id,)):
            command = json.loads(body)
            accepted = json.loads(result)
            if command.get('kind') == 'Finalize' or accepted.get('kind') == 'Finalize':
                _require(command.get('kind') == accepted.get('kind') == 'Finalize', 'invalid_finalization_basis')
                _require(_wire(command) == body and _wire(accepted) == result
                         and digest == hashlib.sha256(b'settletable-command-digest-v1\0' + body).digest(),
                         'invalid_finalization_basis')
                _id(final_actor)
                _id(command_id)
                _require(command.get('command_id') == accepted.get('command_id') == command_id,
                         'invalid_finalization_basis')
                revision, financial_revision = accepted.get('revision'), accepted.get('financial_revision')
                _require(type(revision) is int and 1 <= revision <= state['revision']
                         and type(financial_revision) is int and financial_revision == state['financial_revision']
                         and command.get('expected_revision') == revision - 1
                         and command.get('expected_financial_revision') == financial_revision
                         and accepted.get('calculation') == state['calculation'], 'invalid_finalization_basis')
                finalizations.append((final_actor, command_id, accepted, result))
        _require(len(finalizations) == 1, 'invalid_finalization_basis')
        final_actor, command_id, accepted, result = finalizations[0]
        rows = accepted['calculation'].get('consumption')
        _require(type(rows) is list and 1 <= len(rows) <= 100, 'invalid_finalization_basis')
        seen, amount = set(), None
        for row in rows:
            _require(type(row) is dict and set(row) == {'participant_id', 'sen'}, 'invalid_finalization_basis')
            _id(row['participant_id'])
            _require(row['participant_id'] not in seen and type(row['sen']) is int
                     and 0 <= row['sen'] <= 1_000_000_000, 'invalid_finalization_basis')
            seen.add(row['participant_id'])
            if row['participant_id'] == participant_id:
                amount = row['sen']
        _require(amount is not None, 'invalid_finalization_basis')
        return {'meal_id': meal_id, 'finalize_actor_id': final_actor, 'finalize_command_id': command_id,
                'participant_id': participant_id, 'revision': accepted['revision'],
                'financial_revision': accepted['financial_revision'],
                'result_digest': hashlib.sha256(result).hexdigest(), 'amountCents': amount, 'currency': 'MYR'}

    def finalized_allocation(self, credential, meal_id, participant_id):
        """Read the authorized immutable basis without changing accepted command bytes."""
        try:
            self._db.execute('BEGIN')
            basis = self._finalized_allocation(credential, meal_id, participant_id)
            self._db.execute('COMMIT')
            return basis
        except AuthorityError:
            self._rollback()
            raise
        except sqlite3.Error as error:
            self._storage_failure(error)
        except Exception:
            self._rollback()
            raise AuthorityError('invalid_finalization_basis') from None

    def payment_simulation(self, credential, meal_id, participant_id, config, *, create=False):
        from .payment_simulation import simulation_intent
        return simulation_intent(self, credential, meal_id, participant_id, config, create=create)

    def observe_payment_simulation(self, credential, meal_id, participant_id, config, observation):
        from .payment_simulation import store_observation
        return store_observation(self, credential, meal_id, participant_id, config, observation)

    def authenticate(self, credential, meal_id):
        verifier = _verifier(credential)
        _id(meal_id)
        try:
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN')
            row = self._authenticate(verifier, meal_id)
            self._db.execute('COMMIT')
            return row[0], bool(row[1])
        except AuthorityError:
            self._rollback()
            raise
        except Exception:
            self._rollback()
            raise AuthorityError('storage_error') from None

    def redeem_invitation(self, invitation_token, meal_id, *, session_ttl=3600):
        inv_verifier = _invitation_verifier(invitation_token)
        _id(meal_id)
        _require(type(session_ttl) is int and 1 <= session_ttl <= 2592000)
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
        _require(type(session_ttl) is int and 1 <= session_ttl <= 2592000)
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

    def create_join_request(self, meal_id, display_name, *, ttl=900):
        _id(meal_id)
        _text(display_name, 64)
        _require(type(ttl) is int and 60 <= ttl <= 86400, 'invalid_input')
        cleaned = display_name.strip()
        _require(len(cleaned) > 0, 'invalid_input')
        try:
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN IMMEDIATE')
            meal_row = self._db.execute('SELECT 1 FROM meals WHERE id=?', (meal_id,)).fetchone()
            _require(meal_row is not None, 'meal_not_found')

            now = self._now()
            # Bounded resource defense against table flooding
            active_count = self._db.execute('''SELECT COUNT(*) FROM join_requests
                WHERE meal_id=? AND status='pending' AND expires>?''', (meal_id, now)).fetchone()[0]
            _require(active_count < 20, 'resource_limit')
            total_count = self._db.execute('SELECT COUNT(*) FROM join_requests WHERE meal_id=?', (meal_id,)).fetchone()[0]
            _require(total_count < 100, 'resource_limit')

            # Anti-enumeration defense: all invalid targets (non-existent, organizer, inactive, ambiguous)
            # return the exact same generic AuthorityError('invalid_join_target') to prevent enumeration.
            parts = self._db.execute('SELECT id, name, organizer, active FROM participants WHERE meal_id=?', (meal_id,)).fetchall()
            matching = [p for p in parts if p[1].strip().lower() == cleaned.lower()]
            _require(len(matching) == 1, 'invalid_join_target')
            target_id, target_name, is_organizer, is_active = matching[0]
            _require(not is_organizer and is_active == 1, 'invalid_join_target')

            # DoS defense: An attacker cannot repeatedly submit requests to invalidate pending requests.
            # If an active pending request already exists for this participant, reject duplicate creation.
            existing_pending = self._db.execute('''SELECT 1 FROM join_requests
                WHERE meal_id=? AND participant_id=? AND status='pending' AND expires>?''',
                (meal_id, target_id, now)).fetchone()
            _require(existing_pending is None, 'active_join_request_exists')

            token = secrets.token_urlsafe(32)
            verifier = _join_claim_verifier(token)
            req_id = f'req-{secrets.token_urlsafe(16)}'
            expires = now + ttl
            self._db.execute('''INSERT INTO join_requests (id, meal_id, participant_id, display_name, verifier, status, created_at, expires)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)''',
                (req_id, meal_id, target_id, target_name, verifier, now, expires))
            # Note: We deliberately DO NOT increment state['revision'] on unauthenticated join requests.
            # Unauthenticated submissions do not alter meal state, draft receipt, or claims.
            # Bumping meal revision on unauthenticated requests would allow external callers to cause
            # revision_conflict on active diners and the organizer.
            self._db.execute('COMMIT')
            return req_id, token, target_id, target_name
        except AuthorityError:
            self._rollback()
            raise
        except sqlite3.Error as error:
            self._storage_failure(error)
        except Exception:
            self._rollback()
            raise AuthorityError('storage_error') from None

    def list_join_requests(self, organizer_credential, meal_id):
        verifier = _verifier(organizer_credential)
        _id(meal_id)
        try:
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN')
            row = self._authenticate(verifier, meal_id)
            _require(bool(row[1]), 'forbidden')
            now = self._now()
            rows = self._db.execute('''SELECT id, participant_id, display_name, status, created_at, expires
                FROM join_requests WHERE meal_id=? AND expires>? AND status IN ('pending', 'approved')
                ORDER BY created_at DESC''', (meal_id, now)).fetchall()
            result = tuple(JoinRequestRecord(r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows)
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

    def review_join_request(self, organizer_credential, meal_id, request_id, action):
        verifier = _verifier(organizer_credential)
        _id(meal_id)
        _id(request_id)
        _require(action in ('approve', 'reject'), 'invalid_input')
        try:
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN IMMEDIATE')
            row = self._authenticate(verifier, meal_id)
            _require(bool(row[1]), 'forbidden')
            now = self._now()
            req = self._db.execute('''SELECT participant_id, status, expires
                FROM join_requests WHERE id=? AND meal_id=?''',
                (request_id, meal_id)).fetchone()
            _require(req is not None, 'join_request_not_found')
            part_id, status, expires = req
            _require(expires > now, 'join_request_expired')
            _require(status == 'pending', 'join_request_conflict')

            if action == 'approve':
                target = self._db.execute('SELECT organizer, active FROM participants WHERE meal_id=? AND id=?',
                                          (meal_id, part_id)).fetchone()
                _require(target is not None and not target[0] and target[1] == 1, 'participant_inactive')
                new_status = 'approved'
            else:
                new_status = 'rejected'

            up = self._db.execute('''UPDATE join_requests SET status=? WHERE id=? AND status='pending' ''',
                                  (new_status, request_id)).rowcount
            _require(up == 1, 'join_request_conflict')
            state = json.loads(self._db.execute('SELECT state FROM meals WHERE id=?', (meal_id,)).fetchone()[0])
            state['revision'] += 1
            _revision(state['revision'])
            self._db.execute('UPDATE meals SET state=? WHERE id=?', (_wire(state), meal_id))
            self._db.execute('COMMIT')
            return new_status
        except AuthorityError:
            self._rollback()
            raise
        except sqlite3.Error as error:
            self._storage_failure(error)
        except Exception:
            self._rollback()
            raise AuthorityError('storage_error') from None

    def inspect_join_request(self, meal_id, request_id, claim_token):
        _id(meal_id)
        _id(request_id)
        verifier = _join_claim_verifier(claim_token)
        try:
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN')
            now = self._now()
            row = self._db.execute('''SELECT participant_id, display_name, status, expires
                FROM join_requests WHERE id=? AND meal_id=? AND verifier=?''',
                (request_id, meal_id, verifier)).fetchone()
            _require(row is not None, 'invalid_join_request')
            part_id, name, status, expires = row
            if expires <= now and status == 'pending':
                status = 'expired'
            self._db.execute('COMMIT')
            return {
                'request_id': request_id,
                'participant_id': part_id,
                'display_name': name,
                'status': status
            }
        except AuthorityError:
            self._rollback()
            raise
        except sqlite3.Error as error:
            self._storage_failure(error)
        except Exception:
            self._rollback()
            raise AuthorityError('storage_error') from None

    def claim_join_request(self, meal_id, request_id, claim_token, *, session_ttl=3600):
        _id(meal_id)
        _id(request_id)
        _require(type(session_ttl) is int and 1 <= session_ttl <= 2592000)
        verifier = _join_claim_verifier(claim_token)
        committed = False
        commit_attempted = False
        try:
            credential = secrets.token_urlsafe(32)
            sess_verifier = _verifier(credential)
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN IMMEDIATE')
            now = self._now()
            row = self._db.execute('''SELECT participant_id, status, expires
                FROM join_requests WHERE id=? AND meal_id=? AND verifier=?''',
                (request_id, meal_id, verifier)).fetchone()
            _require(row is not None and row[1] == 'approved' and row[2] > now, 'invalid_join_request')
            participant_id = row[0]

            target = self._db.execute('SELECT organizer, active FROM participants WHERE meal_id=? AND id=?',
                                      (meal_id, participant_id)).fetchone()
            _require(target is not None and not target[0] and target[1] == 1, 'invalid_join_request')

            gen_row = self._db.execute('SELECT generation FROM participant_lifecycle WHERE meal_id=? AND participant_id=?',
                                       (meal_id, participant_id)).fetchone()
            current_gen = 1 if gen_row is None else gen_row[0]
            _require(current_gen < 64, 'resource_limit')
            next_gen = current_gen + 1
            self._db.execute('''INSERT INTO participant_lifecycle (meal_id,participant_id,generation)
                VALUES (?,?,?) ON CONFLICT(meal_id,participant_id) DO UPDATE SET generation=?''',
                (meal_id, participant_id, next_gen, next_gen))

            self._db.execute('''UPDATE join_requests SET status='consumed' WHERE id=?''', (request_id,))

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
                if item['line_sen'] == 0:
                    continue
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

    def _replace_receipt(self, state, data, omitted_scope_ids=()):
        old = state['receipt']
        old_adjustments = {} if old is None else {a['id']: a for a in old['adjustments']}
        for adjustment in data['receipt']['adjustments']:
            previous = old_adjustments.get(adjustment['id'])
            if previous and adjustment['id'] in omitted_scope_ids:
                _require(previous['eligible_item_ids'] == adjustment['eligible_item_ids'])
            if previous and previous.get('scope_mode') == 'all_items':
                _require(adjustment.get('scope_mode') in ('all_items', 'fixed_items'))
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
        item = next(i for i in state['receipt']['items'] if i['id'] == item_id)
        _require(item['line_sen'] > 0, 'complimentary_item')
        previous = [c for c in state['claims'] if c['item_id'] == item_id and c['participant_id'] == actor]
        quantity = data['quantity']
        if quantity is None:
            _require(bool(previous), 'claim_missing')
            state['claims'].remove(previous[0])
        else:
            current = sum((Fraction(*c['quantity']) for c in state['claims']
                           if c['item_id'] == item_id and c['participant_id'] != actor
                           and c['financial_revision'] == state['financial_revision']), Fraction())
            _require(current + Fraction(*quantity) <= Fraction(*item['quantity']), 'quantity_capacity')
            if previous:
                state['claims'].remove(previous[0])
            state['claims'].append({'item_id': item_id, 'participant_id': actor,
                                    'quantity': quantity, 'financial_revision': state['financial_revision']})
        state['item_revisions'][item_id] += 1
        _revision(state['item_revisions'][item_id])
        return tuple(c for c in _claims(state) if c.item_id == item_id and c.participant_id == actor)

    def _assign_participant_quantity(self, meal_id, state, actor, data):
        target_id = data['participant_id']
        target = self._db.execute('SELECT active FROM participants WHERE meal_id=? AND id=?',
                                  (meal_id, target_id)).fetchone()
        _require(target is not None and target[0] == 1, 'forbidden')
        item_id = data['item_id']
        _require(item_id in state['item_revisions'], 'unknown_item')
        _require(data['expected_item_revision'] == state['item_revisions'][item_id], 'item_revision_conflict')
        item = next(i for i in state['receipt']['items'] if i['id'] == item_id)
        _require(item['line_sen'] > 0, 'complimentary_item')
        previous = [c for c in state['claims'] if c['item_id'] == item_id and c['participant_id'] == target_id]
        quantity = data['quantity']
        if quantity is None:
            _require(bool(previous), 'claim_missing')
            state['claims'].remove(previous[0])
        else:
            current = sum((Fraction(*c['quantity']) for c in state['claims']
                           if c['item_id'] == item_id and c['participant_id'] != target_id
                           and c['financial_revision'] == state['financial_revision']), Fraction())
            _require(current + Fraction(*quantity) <= Fraction(*item['quantity']), 'quantity_capacity')
            if previous:
                state['claims'].remove(previous[0])
            claim_entry = {'item_id': item_id, 'participant_id': target_id,
                           'quantity': quantity, 'financial_revision': state['financial_revision'],
                           'assigned_by': actor}
            state['claims'].append(claim_entry)
        state['item_revisions'][item_id] += 1
        _revision(state['item_revisions'][item_id])
        return tuple(c for c in _claims(state) if c.item_id == item_id and c.participant_id == target_id)

    def _set_item_allocations(self, meal_id, state, actor, data):
        item_id = data['item_id']
        _require(item_id in state['item_revisions'], 'unknown_item')
        _require(data['expected_item_revision'] == state['item_revisions'][item_id], 'item_revision_conflict')
        _require(state['receipt'] is not None, 'unknown_item')
        item = next((i for i in state['receipt']['items'] if i['id'] == item_id), None)
        _require(item is not None, 'unknown_item')
        _require(item['line_sen'] > 0, 'complimentary_item')
        allocations = data['allocations']
        part_ids = [a['participant_id'] for a in allocations]
        _require(len(part_ids) == len(set(part_ids)), 'invalid_input')
        for pid in part_ids:
            target = self._db.execute('SELECT active FROM participants WHERE meal_id=? AND id=?',
                                      (meal_id, pid)).fetchone()
            _require(target is not None and target[0] == 1, 'forbidden')
        requested_total = sum((Fraction(*a['quantity']) for a in allocations), Fraction())
        _require(requested_total <= Fraction(*item['quantity']), 'quantity_capacity')
        previous_claims = {c['participant_id']: c for c in state['claims'] if c['item_id'] == item_id}
        state['claims'] = [c for c in state['claims'] if c['item_id'] != item_id]
        for a in allocations:
            pid = a['participant_id']
            qty = a['quantity']
            prev = previous_claims.get(pid)
            if prev is not None and prev['quantity'] == qty and prev['financial_revision'] == state['financial_revision']:
                assigned_by = prev.get('assigned_by')
            else:
                assigned_by = actor
            state['claims'].append({
                'item_id': item_id,
                'participant_id': pid,
                'quantity': qty,
                'financial_revision': state['financial_revision'],
                'assigned_by': assigned_by,
            })
        state['item_revisions'][item_id] += 1
        _revision(state['item_revisions'][item_id])
        return tuple(c for c in _claims(state) if c.item_id == item_id)

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
        state['finalized_revision'] = state['revision'] + 1

    def _revoke(self, meal_id, data):
        now = self._now()
        if data['kind'] == 'RevokeSession':
            sess_up = self._db.execute('UPDATE sessions SET revoked=1 WHERE meal_id=? AND participant_id=? AND revoked=0',
                                       (meal_id, data['participant_id'])).rowcount
            inv_up = self._db.execute('UPDATE invitations SET revoked=1 WHERE meal_id=? AND participant_id=? AND revoked=0 AND consumed=0 AND expires>?',
                                      (meal_id, data['participant_id'], now)).rowcount
            self._db.execute('''UPDATE join_requests SET status='rejected' WHERE meal_id=? AND participant_id=? AND status IN ('pending', 'approved')''',
                             (meal_id, data['participant_id']))
            _require(sess_up + inv_up > 0, 'already_revoked')
        elif data['kind'] == 'RevokeMembership':
            part_up = self._db.execute('UPDATE participants SET active=0 WHERE meal_id=? AND id=? AND active=1',
                                       (meal_id, data['participant_id'])).rowcount
            self._db.execute('UPDATE sessions SET revoked=1 WHERE meal_id=? AND participant_id=? AND revoked=0',
                             (meal_id, data['participant_id']))
            self._db.execute('UPDATE invitations SET revoked=1 WHERE meal_id=? AND participant_id=? AND revoked=0 AND consumed=0 AND expires>?',
                             (meal_id, data['participant_id'], now))
            self._db.execute('''UPDATE join_requests SET status='rejected' WHERE meal_id=? AND participant_id=? AND status IN ('pending', 'approved')''',
                             (meal_id, data['participant_id']))
            _require(part_up == 1, 'already_revoked')
        elif data['kind'] == 'RevokeInvitation':
            inv_up = self._db.execute('UPDATE invitations SET revoked=1 WHERE meal_id=? AND participant_id=? AND revoked=0 AND consumed=0 AND expires>?',
                                      (meal_id, data['participant_id'], now)).rowcount
            _require(inv_up > 0, 'already_revoked')

    def _record_contribution(self, meal_id, state, actor, command_id, data):
        _require(state['calculation'] is not None, 'not_finalized')
        participant_id = data['participant_id']
        amount_sen = data['amount_sen']
        payment_method = data.get('payment_method')
        calc_data = state['calculation']
        consumption_participants = {p['participant_id'] for p in calc_data['consumption']}
        _require(participant_id in consumption_participants, 'invalid_participant')
        row = self._db.execute("SELECT COALESCE(SUM(amount_sen), 0) FROM payer_contributions WHERE meal_id=? AND status='active'",
                               (meal_id,)).fetchone()
        active_sum = row[0] if row else 0
        receipt_total = state['receipt']['total_sen']
        _require(active_sum + amount_sen <= receipt_total, 'overpayment_prohibited')
        contribution_id = derive_contribution_id(meal_id, command_id)
        now = self._now()
        self._db.execute('''
            INSERT INTO payer_contributions (
                meal_id, contribution_id, command_id, participant_id, amount_sen,
                payment_method, created_at, created_by, status
            ) VALUES (?,?,?,?,?,?,?,?,'active')
        ''', (meal_id, contribution_id, command_id, participant_id, amount_sen, payment_method, now, actor))
        return contribution_id

    def _reverse_contribution(self, meal_id, state, actor, command_id, data):
        _require(state['calculation'] is not None, 'not_finalized')
        contribution_id = data['contribution_id']
        reason = data.get('reason')
        row = self._db.execute('SELECT status, participant_id, amount_sen FROM payer_contributions WHERE meal_id=? AND contribution_id=?',
                               (meal_id, contribution_id)).fetchone()
        _require(row is not None, 'contribution_not_found')
        _require(row[0] == 'active', 'invalid_contribution_status')
        participant_id = row[1]
        amount_sen = row[2]

        active_contrib_row = self._db.execute(
            "SELECT COALESCE(SUM(amount_sen), 0) FROM payer_contributions WHERE meal_id=? AND participant_id=? AND status='active'",
            (meal_id, participant_id)).fetchone()
        current_active = active_contrib_row[0] if active_contrib_row else 0
        new_active = current_active - amount_sen

        transfers_row = self._db.execute(
            "SELECT COALESCE(SUM(amount_sen), 0) FROM peer_transfers WHERE meal_id=? AND receiver_id=? AND status='confirmed'",
            (meal_id, participant_id)).fetchone()
        confirmed_received = transfers_row[0] if transfers_row else 0

        _require(new_active >= confirmed_received, 'active_peer_transfers_exist')

        now = self._now()
        self._db.execute('''
            UPDATE payer_contributions
            SET status='reversed', reversed_at=?, reversed_by=?, reversal_command_id=?, reversal_reason=?
            WHERE meal_id=? AND contribution_id=?
        ''', (now, actor, command_id, reason, meal_id, contribution_id))

    def _record_transfer(self, meal_id, state, actor, command_id, data):
        _require(state['calculation'] is not None, 'not_finalized')
        sender_id = data['sender_id']
        receiver_id = data['receiver_id']
        amount_sen = data['amount_sen']
        note = data.get('note')

        _require(sender_id != receiver_id, 'self_transfer_prohibited')
        people_ids = {p[0] for p in self._db.execute('SELECT id FROM participants WHERE meal_id=?', (meal_id,)).fetchall()}
        _require(sender_id in people_ids and receiver_id in people_ids, 'invalid_participant')
        _require(1 <= amount_sen <= 1_000_000_000, 'invalid_input')

        people = self._db.execute('SELECT id, name, organizer, active FROM participants WHERE meal_id=?', (meal_id,)).fetchall()
        part_names = {p[0]: p[1] for p in people}
        active_set = {p[0] for p in people if p[3]}

        contrib_rows = self._db.execute('''
            SELECT contribution_id, command_id, participant_id, amount_sen, payment_method,
                   created_at, created_by, status, reversed_at, reversed_by,
                   reversal_command_id, reversal_reason
            FROM payer_contributions
            WHERE meal_id=?
            ORDER BY created_at ASC, contribution_id ASC
        ''', (meal_id,)).fetchall()
        contrib_records = tuple(
            PayerContributionRecord(
                contribution_id=r[0], command_id=r[1], participant_id=r[2],
                participant_name=part_names.get(r[2], r[2]), amount_sen=r[3],
                payment_method=r[4], created_at=r[5], created_by=r[6], status=r[7],
                reversed_at=r[8], reversed_by=r[9], reversal_command_id=r[10], reversal_reason=r[11],
            ) for r in contrib_rows
        )
        calc_consumption = [(p['participant_id'], p['sen']) for p in state['calculation']['consumption']]
        receipt_total = state['receipt']['total_sen']
        funding, net_balances = compute_net_balances(
            consumption_records=calc_consumption,
            participant_names=part_names,
            active_participants=active_set,
            active_contributions=contrib_records,
            receipt_total_sen=receipt_total,
        )

        xfer_rows = self._db.execute('''
            SELECT transfer_id, command_id, sender_id, receiver_id, amount_sen,
                   note, created_at, created_by, status, reversed_at, reversed_by,
                   reversal_command_id, reversal_reason
            FROM peer_transfers
            WHERE meal_id=?
            ORDER BY created_at ASC, transfer_id ASC
        ''', (meal_id,)).fetchall()
        transfers = tuple(
            PeerTransferRecord(
                transfer_id=r[0], command_id=r[1], sender_id=r[2], receiver_id=r[3],
                amount_sen=r[4], note=r[5], created_at=r[6], created_by=r[7], status=r[8],
                reversed_at=r[9], reversed_by=r[10], reversal_command_id=r[11], reversal_reason=r[12],
            ) for r in xfer_rows
        )
        settlement = compute_settlement(
            base_net_balances=net_balances,
            transfers=transfers,
            unfunded_sen=funding.unfunded_sen,
        )

        bal_map = {b.participant_id: b.outstanding_net_balance_sen for b in settlement.outstanding_net_balances}
        sender_bal = bal_map.get(sender_id, 0)
        receiver_bal = bal_map.get(receiver_id, 0)

        _require(sender_bal < 0, 'not_a_debtor')
        _require(receiver_bal > 0, 'not_a_creditor')

        sender_debt = -sender_bal
        receiver_credit = receiver_bal
        max_allowed = min(sender_debt, receiver_credit)
        _require(amount_sen <= max_allowed, 'over_settlement_prohibited')

        transfer_id = derive_transfer_id(meal_id, command_id)
        now = self._now()
        self._db.execute('''
            INSERT INTO peer_transfers (
                meal_id, transfer_id, command_id, sender_id, receiver_id, amount_sen,
                note, created_at, created_by, status
            ) VALUES (?,?,?,?,?,?,?,?,?,'confirmed')
        ''', (meal_id, transfer_id, command_id, sender_id, receiver_id, amount_sen, note, now, actor))
        return transfer_id

    def _reverse_transfer(self, meal_id, state, actor, command_id, data):
        _require(state['calculation'] is not None, 'not_finalized')
        transfer_id = data['transfer_id']
        reason = data.get('reason')
        row = self._db.execute('SELECT status FROM peer_transfers WHERE meal_id=? AND transfer_id=?',
                               (meal_id, transfer_id)).fetchone()
        _require(row is not None, 'transfer_not_found')
        _require(row[0] == 'confirmed', 'invalid_transfer_status')
        now = self._now()
        self._db.execute('''
            UPDATE peer_transfers
            SET status='reversed', reversed_at=?, reversed_by=?, reversal_command_id=?, reversal_reason=?
            WHERE meal_id=? AND transfer_id=?
        ''', (now, actor, command_id, reason, meal_id, transfer_id))

    def apply(self, credential, meal_id, command, *, replay_only=False, omitted_scope_ids=()):
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
            _require(not replay_only)
            state = json.loads(self._db.execute('SELECT state FROM meals WHERE id=?', (meal_id,)).fetchone()[0])
            security = data['kind'] in ('RevokeSession', 'RevokeMembership', 'RevokeInvitation')
            post_finalization = data['kind'] in ('RecordContribution', 'ReverseContribution', 'RecordTransfer', 'ReverseTransfer')
            if security:
                _require(self._db.execute('SELECT COUNT(*) FROM commands WHERE meal_id=? AND security=1', (meal_id,)).fetchone()[0] < 15_000,
                         'resource_limit')
            else:
                _require(self._db.execute('SELECT COUNT(*) FROM commands WHERE meal_id=? AND security=0', (meal_id,)).fetchone()[0] < 10_000,
                         'resource_limit')
            if post_finalization:
                _require(state['calculation'] is not None, 'not_finalized')
                if state.get('finalized_revision') is None:
                    state['finalized_revision'] = state['revision']
            elif not security:
                _require(state['calculation'] is None, 'finalized')
            if 'expected_revision' in data:
                _require(data['expected_revision'] == state['revision'], 'revision_conflict')
            if 'expected_financial_revision' in data:
                _require(data['expected_financial_revision'] == state['financial_revision'], 'financial_revision_conflict')
            contrib_id = None
            transfer_id = None
            if data['kind'] == 'ReplaceReceipt':
                changed = self._replace_receipt(state, data, omitted_scope_ids)
            elif data['kind'] == 'SetOwnQuantity':
                changed = self._set_own_quantity(state, actor, data)
            elif data['kind'] == 'AssignParticipantQuantity':
                changed = self._assign_participant_quantity(meal_id, state, actor, data)
            elif data['kind'] == 'SetItemAllocations':
                changed = self._set_item_allocations(meal_id, state, actor, data)
            elif data['kind'] == 'ReviewReceipt':
                self._review_receipt(state, actor, data)
                changed = ()
            elif data['kind'] == 'Finalize':
                self._finalize(state, meal_id)
                changed = ()
            elif data['kind'] == 'RecordContribution':
                contrib_id = self._record_contribution(meal_id, state, actor, command.command_id, data)
                changed = ()
            elif data['kind'] == 'ReverseContribution':
                self._reverse_contribution(meal_id, state, actor, command.command_id, data)
                changed = ()
            elif data['kind'] == 'RecordTransfer':
                transfer_id = self._record_transfer(meal_id, state, actor, command.command_id, data)
                changed = ()
            elif data['kind'] == 'ReverseTransfer':
                self._reverse_transfer(meal_id, state, actor, command.command_id, data)
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
            result_dict = {'command_id': command.command_id, 'kind': data['kind'],
                           'revision': state['revision'], 'financial_revision': state['financial_revision'],
                           'changed_claims': [_claim_data(c) for c in changed],
                           'calculation': state['calculation'] if data['kind'] == 'Finalize' else None}
            if contrib_id is not None:
                result_dict['contribution_id'] = contrib_id
            if transfer_id is not None:
                result_dict['transfer_id'] = transfer_id
            result_bytes = _wire(result_dict)
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

    def get_notion_export(self, meal_id, finalized_revision):
        try:
            row = self._db.execute(
                'SELECT page_id, page_url, exported_at, export_digest, status '
                'FROM notion_exports WHERE meal_id = ? AND finalized_revision = ?',
                (meal_id, finalized_revision),
            ).fetchone()
            if not row:
                return None
            status = row[4]
            digest = row[3]
            if status == 'in_progress' and (self._now() - row[2]) > 60.0:
                status = 'failed'
                digest = 'timeout'
            return {
                'page_id': row[0],
                'page_url': row[1],
                'exported_at': row[2],
                'export_digest': digest,
                'status': status,
            }
        except sqlite3.Error as err:
            self._storage_failure(err)

    def record_notion_export_in_progress(self, meal_id, finalized_revision, export_digest):
        try:
            self._db.execute('BEGIN IMMEDIATE')
            now = self._now()
            self._db.execute(
                'INSERT INTO notion_exports (meal_id, finalized_revision, page_id, page_url, exported_at, export_digest, status) '
                'VALUES (?, ?, ?, ?, ?, ?, ?) '
                'ON CONFLICT(meal_id, finalized_revision) DO UPDATE SET '
                'status = excluded.status, exported_at = excluded.exported_at, export_digest = excluded.export_digest',
                (meal_id, finalized_revision, '', '', now, export_digest, 'in_progress'),
            )
            self._db.execute('COMMIT')
        except sqlite3.Error as err:
            self._rollback()
            self._storage_failure(err)

    def record_notion_export_failed(self, meal_id, finalized_revision, error_code):
        try:
            self._db.execute('BEGIN IMMEDIATE')
            now = self._now()
            self._db.execute(
                'INSERT INTO notion_exports (meal_id, finalized_revision, page_id, page_url, exported_at, export_digest, status) '
                'VALUES (?, ?, ?, ?, ?, ?, ?) '
                'ON CONFLICT(meal_id, finalized_revision) DO UPDATE SET '
                'status = excluded.status, exported_at = excluded.exported_at, export_digest = excluded.export_digest',
                (meal_id, finalized_revision, '', '', now, str(error_code)[:128], 'failed'),
            )
            self._db.execute('COMMIT')
        except sqlite3.Error as err:
            self._rollback()
            self._storage_failure(err)

    def record_notion_export_completed(self, meal_id, finalized_revision, page_id, page_url, export_digest):
        try:
            self._db.execute('BEGIN IMMEDIATE')
            now = self._now()
            self._db.execute(
                'INSERT INTO notion_exports (meal_id, finalized_revision, page_id, page_url, exported_at, export_digest, status) '
                'VALUES (?, ?, ?, ?, ?, ?, ?) '
                'ON CONFLICT(meal_id, finalized_revision) DO UPDATE SET '
                'page_id = excluded.page_id, page_url = excluded.page_url, '
                'exported_at = excluded.exported_at, export_digest = excluded.export_digest, status = excluded.status',
                (meal_id, finalized_revision, page_id, page_url, now, export_digest, 'completed'),
            )
            self._db.execute('COMMIT')
        except sqlite3.Error as err:
            self._rollback()
            self._storage_failure(err)

    def clear_notion_export(self, meal_id, finalized_revision):
        try:
            self._db.execute('BEGIN IMMEDIATE')
            self._db.execute(
                'DELETE FROM notion_exports WHERE meal_id = ? AND finalized_revision = ? AND status = ?',
                (meal_id, finalized_revision, 'in_progress'),
            )
            self._db.execute('COMMIT')
        except sqlite3.Error as err:
            self._rollback()
            self._storage_failure(err)

    def store_receipt_photo(self, organizer_credential, meal_id, image_bytes, content_type, width, height):
        verifier = _verifier(organizer_credential)
        _id(meal_id)
        _require(type(image_bytes) is bytes and 1 <= len(image_bytes) <= 5_242_880, 'invalid_image')
        _require(content_type in ('image/jpeg', 'image/png', 'image/webp', 'image/jpg'), 'invalid_image')
        _require(type(width) is int and 1 <= width <= 4096, 'invalid_image')
        _require(type(height) is int and 1 <= height <= 4096, 'invalid_image')
        _require(width * height <= 16_777_216, 'invalid_image')

        ext_map = {'image/jpeg': 'jpg', 'image/jpg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}
        ext = ext_map.get(content_type, 'jpg')
        normalized_mime = 'image/jpeg' if content_type == 'image/jpg' else content_type
        safe_meal_id = re.sub(r'[^A-Za-z0-9_-]', '_', meal_id)
        sha = hashlib.sha256(image_bytes).hexdigest()
        filename = f"{safe_meal_id}_{sha[:16]}.{ext}"
        tmp_filename = f"{safe_meal_id}_{sha[:16]}_{secrets.token_hex(4)}.tmp"
        tmp_path = self.storage_dir / tmp_filename
        dest_path = self.storage_dir / filename

        old_filename = None
        new_file_created = False
        try:
            _require(self._db is not None, 'storage_error')
            tmp_path.write_bytes(image_bytes)

            self._db.execute('BEGIN IMMEDIATE')
            actor, is_organizer = self._authenticate(verifier, meal_id)
            _require(is_organizer, 'forbidden')

            state_row = self._db.execute('SELECT state FROM meals WHERE id=?', (meal_id,)).fetchone()
            _require(state_row is not None, 'meal_not_found')
            state = json.loads(state_row[0])
            _require(state.get('calculation') is None, 'finalized')

            existing_row = self._db.execute('SELECT filename FROM receipt_photos WHERE meal_id=?', (meal_id,)).fetchone()
            if existing_row:
                old_filename = existing_row[0]

            now = self._now()

            # Atomically move staging file into destination BEFORE committing database metadata
            tmp_path.replace(dest_path)
            new_file_created = True

            self._db.execute('''
                INSERT INTO receipt_photos (meal_id, filename, content_type, byte_size, sha256, width, height, uploaded_at, uploaded_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(meal_id) DO UPDATE SET
                    filename=excluded.filename,
                    content_type=excluded.content_type,
                    byte_size=excluded.byte_size,
                    sha256=excluded.sha256,
                    width=excluded.width,
                    height=excluded.height,
                    uploaded_at=excluded.uploaded_at,
                    uploaded_by=excluded.uploaded_by
            ''', (meal_id, filename, normalized_mime, len(image_bytes), sha, width, height, now, actor))

            self._db.execute('COMMIT')

            if old_filename and old_filename != filename:
                old_path = (self.storage_dir / old_filename).resolve()
                if old_path.is_relative_to(self.storage_dir.resolve()) and old_path.exists():
                    try:
                        old_path.unlink()
                    except OSError:
                        pass

            return {
                'meal_id': meal_id,
                'filename': filename,
                'content_type': normalized_mime,
                'byte_size': len(image_bytes),
                'sha256': sha,
                'width': width,
                'height': height,
                'uploaded_at': now,
                'uploaded_by': actor,
            }
        except AuthorityError:
            self._rollback()
            if new_file_created and dest_path.exists() and dest_path != (self.storage_dir / (old_filename or '')):
                try:
                    dest_path.unlink()
                except OSError:
                    pass
            raise
        except sqlite3.Error as error:
            if new_file_created and dest_path.exists() and dest_path != (self.storage_dir / (old_filename or '')):
                try:
                    dest_path.unlink()
                except OSError:
                    pass
            self._storage_failure(error)
        except Exception:
            self._rollback()
            if new_file_created and dest_path.exists() and dest_path != (self.storage_dir / (old_filename or '')):
                try:
                    dest_path.unlink()
                except OSError:
                    pass
            raise AuthorityError('storage_error') from None
        finally:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass

    def get_receipt_photo(self, credential, meal_id):
        verifier = _verifier(credential)
        _id(meal_id)
        try:
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN')
            actor, is_organizer = self._authenticate(verifier, meal_id)
            _require(is_organizer, 'forbidden')

            row = self._db.execute(
                'SELECT filename, content_type, byte_size, sha256, width, height, uploaded_at, uploaded_by FROM receipt_photos WHERE meal_id=?',
                (meal_id,)
            ).fetchone()
            _require(row is not None, 'photo_not_found')
            filename, content_type, byte_size, sha256, width, height, uploaded_at, uploaded_by = row
            target_path = (self.storage_dir / filename).resolve()
            _require(target_path.is_relative_to(self.storage_dir.resolve()), 'forbidden')
            _require(target_path.is_file(), 'photo_not_found')
            data = target_path.read_bytes()
            _require(len(data) == byte_size and hashlib.sha256(data).hexdigest() == sha256, 'photo_corrupted')
            self._db.execute('COMMIT')
            meta = {
                'meal_id': meal_id,
                'filename': filename,
                'content_type': content_type,
                'byte_size': byte_size,
                'sha256': sha256,
                'width': width,
                'height': height,
                'uploaded_at': uploaded_at,
                'uploaded_by': uploaded_by,
            }
            return data, meta
        except AuthorityError:
            self._rollback()
            raise
        except sqlite3.Error as error:
            self._storage_failure(error)
        except Exception:
            self._rollback()
            raise AuthorityError('storage_error') from None

    def delete_receipt_photo(self, organizer_credential, meal_id):
        verifier = _verifier(organizer_credential)
        _id(meal_id)
        old_filename = None
        try:
            _require(self._db is not None, 'storage_error')
            self._db.execute('BEGIN IMMEDIATE')
            actor, is_organizer = self._authenticate(verifier, meal_id)
            _require(is_organizer, 'forbidden')

            state_row = self._db.execute('SELECT state FROM meals WHERE id=?', (meal_id,)).fetchone()
            _require(state_row is not None, 'meal_not_found')
            state = json.loads(state_row[0])
            _require(state.get('calculation') is None, 'finalized')

            existing_row = self._db.execute('SELECT filename FROM receipt_photos WHERE meal_id=?', (meal_id,)).fetchone()
            if existing_row:
                old_filename = existing_row[0]
                self._db.execute('DELETE FROM receipt_photos WHERE meal_id=?', (meal_id,))

            self._db.execute('COMMIT')

            if old_filename:
                old_path = (self.storage_dir / old_filename).resolve()
                if old_path.is_relative_to(self.storage_dir.resolve()) and old_path.exists():
                    try:
                        old_path.unlink()
                    except OSError:
                        pass
        except AuthorityError:
            self._rollback()
            raise
        except sqlite3.Error as error:
            self._storage_failure(error)
        except Exception:
            self._rollback()
            raise AuthorityError('storage_error') from None
