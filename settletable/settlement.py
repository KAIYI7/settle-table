"""Pure domain logic for peer transfer suggestions, settlement tracking, and outstanding balances."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from settletable.funding import ParticipantNetBalance


@dataclass(frozen=True)
class SuggestedTransfer:
    sender_id: str
    receiver_id: str
    amount_sen: int


@dataclass(frozen=True)
class PeerTransferRecord:
    transfer_id: str
    command_id: str
    sender_id: str
    receiver_id: str
    amount_sen: int
    note: str | None
    created_at: float
    created_by: str
    status: str
    reversed_at: float | None = None
    reversed_by: str | None = None
    reversal_command_id: str | None = None
    reversal_reason: str | None = None


@dataclass(frozen=True)
class ParticipantOutstandingBalance:
    participant_id: str
    name: str
    is_active: bool
    base_net_balance_sen: int
    confirmed_sent_sen: int
    confirmed_received_sen: int
    outstanding_net_balance_sen: int


@dataclass(frozen=True)
class SettlementSnapshot:
    is_settled: bool
    outstanding_net_balances: tuple[ParticipantOutstandingBalance, ...]
    suggested_transfers: tuple[SuggestedTransfer, ...]
    transfers: tuple[PeerTransferRecord, ...]
    unfunded_blocker_sen: int


def derive_transfer_id(meal_id: str, command_id: str) -> str:
    """Deterministically derive a collision-resistant transfer ID from meal_id and command_id."""
    raw = f"{meal_id}:{command_id}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:16]
    return f"xfer-{digest}"


def compute_settlement(
    base_net_balances: tuple[ParticipantNetBalance, ...],
    transfers: tuple[PeerTransferRecord, ...],
    unfunded_sen: int,
) -> SettlementSnapshot:
    """Compute outstanding net balances and deterministic peer transfer suggestions.
    
    Invariant: sum(b.outstanding_net_balance_sen) == -unfunded_sen
    """
    confirmed_sent: dict[str, int] = {}
    confirmed_received: dict[str, int] = {}

    for t in transfers:
        if t.status == "confirmed":
            confirmed_sent[t.sender_id] = confirmed_sent.get(t.sender_id, 0) + t.amount_sen
            confirmed_received[t.receiver_id] = confirmed_received.get(t.receiver_id, 0) + t.amount_sen

    outstanding_list: list[ParticipantOutstandingBalance] = []
    for b in base_net_balances:
        p_id = b.participant_id
        sent = confirmed_sent.get(p_id, 0)
        recv = confirmed_received.get(p_id, 0)
        # Outstanding net balance:
        # Base net > 0 means participant fronted money (owed money). Receiving transfers reduces credit.
        # Base net < 0 means participant owes money. Sending transfers reduces debt (brings closer to 0).
        outstanding = b.net_sen + sent - recv
        outstanding_list.append(
            ParticipantOutstandingBalance(
                participant_id=p_id,
                name=b.participant_name,
                is_active=b.is_active,
                base_net_balance_sen=b.net_sen,
                confirmed_sent_sen=sent,
                confirmed_received_sen=recv,
                outstanding_net_balance_sen=outstanding,
            )
        )

    # Runtime assertion of mathematical cent conservation
    total_outstanding = sum(p.outstanding_net_balance_sen for p in outstanding_list)
    assert total_outstanding == -unfunded_sen, (
        f"Cent conservation violation in settlement: sum(outstanding)={total_outstanding} != -unfunded={-unfunded_sen}"
    )

    # Calculate deterministic suggested transfers
    # Debtors: outstanding < 0. Sorted descending by absolute debt, tie-break by participant_id.
    debtors: list[list[any]] = [
        [p.participant_id, -p.outstanding_net_balance_sen]
        for p in outstanding_list
        if p.outstanding_net_balance_sen < 0
    ]
    debtors.sort(key=lambda d: (-d[1], d[0]))

    # Creditors: outstanding > 0. Sorted descending by credit, tie-break by participant_id.
    creditors: list[list[any]] = [
        [p.participant_id, p.outstanding_net_balance_sen]
        for p in outstanding_list
        if p.outstanding_net_balance_sen > 0
    ]
    creditors.sort(key=lambda c: (-c[1], c[0]))

    suggested: list[SuggestedTransfer] = []
    d_idx = 0
    c_idx = 0

    while d_idx < len(debtors) and c_idx < len(creditors):
        d_pid, d_debt = debtors[d_idx]
        c_pid, c_credit = creditors[c_idx]

        xfer = min(d_debt, c_credit)
        if xfer > 0:
            suggested.append(
                SuggestedTransfer(sender_id=d_pid, receiver_id=c_pid, amount_sen=xfer)
            )
            debtors[d_idx][1] -= xfer
            creditors[c_idx][1] -= xfer

        if creditors[c_idx][1] == 0:
            c_idx += 1
        if debtors[d_idx][1] == 0:
            d_idx += 1

    is_settled = (unfunded_sen == 0) and all(
        p.outstanding_net_balance_sen == 0 for p in outstanding_list
    )

    return SettlementSnapshot(
        is_settled=is_settled,
        outstanding_net_balances=tuple(outstanding_list),
        suggested_transfers=tuple(suggested),
        transfers=transfers,
        unfunded_blocker_sen=unfunded_sen,
    )
