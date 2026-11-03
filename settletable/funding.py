"""Domain models and pure calculations for restaurant bill funding and net balances."""
from dataclasses import dataclass
import hashlib
from typing import Sequence


VALID_PAYMENT_METHODS = ('cash', 'card', 'ewallet', 'bank_transfer', 'other')
VALID_CONTRIBUTION_STATUSES = ('active', 'reversed')


@dataclass(frozen=True, slots=True)
class PayerContributionRecord:
    contribution_id: str
    command_id: str
    participant_id: str
    participant_name: str
    amount_sen: int
    payment_method: str | None
    created_at: float
    created_by: str
    status: str
    reversed_at: float | None = None
    reversed_by: str | None = None
    reversal_command_id: str | None = None
    reversal_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ParticipantNetBalance:
    participant_id: str
    participant_name: str
    is_active: bool
    contributed_sen: int
    consumption_sen: int
    net_sen: int


@dataclass(frozen=True, slots=True)
class FundingSnapshot:
    total_contributed_sen: int
    unfunded_sen: int
    receipt_total_sen: int
    status: str  # 'not_funded' | 'partially_funded' | 'fully_funded'
    net_balances: tuple[ParticipantNetBalance, ...]


def derive_contribution_id(meal_id: str, command_id: str) -> str:
    """Deterministically derive a collision-resistant contribution ID from meal and command IDs."""
    digest = hashlib.sha256(f"{meal_id}:{command_id}".encode("ascii")).hexdigest()
    return f"contrib-{digest[:16]}"


def compute_funding_status(receipt_total_sen: int, total_contributed_sen: int) -> str:
    """Classify the funding status of a meal.

    Zero-total meals are fully funded immediately.
    """
    if total_contributed_sen >= receipt_total_sen:
        return 'fully_funded'
    if total_contributed_sen == 0 and receipt_total_sen > 0:
        return 'not_funded'
    return 'partially_funded'


def compute_net_balances(
    consumption_records: Sequence[tuple[str, int]],  # (participant_id, consumption_sen)
    participant_names: dict[str, str],               # participant_id -> name
    active_participants: set[str],                   # set of currently active participant IDs
    active_contributions: Sequence[PayerContributionRecord],
    receipt_total_sen: int,
) -> tuple[FundingSnapshot, tuple[ParticipantNetBalance, ...]]:
    """Compute base net balances and funding snapshot with exact cent conservation.

    Base Net Balance = Contributed - Consumption Liability.
    Sum of Base Net Balances == Total Contributed - Receipt Total == -Unfunded Amount.
    """
    # Sum active contributions per participant
    contributed_by_person: dict[str, int] = {p_id: 0 for p_id, _ in consumption_records}
    for contrib in active_contributions:
        if contrib.status == 'active':
            contributed_by_person[contrib.participant_id] = (
                contributed_by_person.get(contrib.participant_id, 0) + contrib.amount_sen
            )

    total_contributed = sum(
        c.amount_sen for c in active_contributions if c.status == 'active'
    )
    unfunded_sen = max(0, receipt_total_sen - total_contributed)
    status = compute_funding_status(receipt_total_sen, total_contributed)

    # Build deterministically ordered net balances (sorted by participant_id ASC)
    balances: list[ParticipantNetBalance] = []
    for participant_id, consumption_sen in sorted(consumption_records, key=lambda r: r[0]):
        contributed = contributed_by_person.get(participant_id, 0)
        net_sen = contributed - consumption_sen
        name = participant_names.get(participant_id, participant_id)
        is_active = participant_id in active_participants
        balances.append(
            ParticipantNetBalance(
                participant_id=participant_id,
                participant_name=name,
                is_active=is_active,
                contributed_sen=contributed,
                consumption_sen=consumption_sen,
                net_sen=net_sen,
            )
        )

    # Cent conservation invariant verification
    total_net = sum(b.net_sen for b in balances)
    expected_net = total_contributed - receipt_total_sen
    if total_net != expected_net:
        raise ValueError(
            f"Cent conservation invariant violated: sum(net)={total_net} != {expected_net}"
        )

    snapshot = FundingSnapshot(
        total_contributed_sen=total_contributed,
        unfunded_sen=unfunded_sen,
        receipt_total_sen=receipt_total_sen,
        status=status,
        net_balances=tuple(balances),
    )
    return snapshot, tuple(balances)
