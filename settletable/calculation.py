"""Pure integer-sen calculation of supplied facts; does not authorize finalization."""
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import re


class CalculationError(ValueError):
    """Machine-readable rejection; path identifies the supplied invalid fact."""
    def __init__(self, code: str, path: str):
        self.code, self.path = code, path
        super().__init__(f"{code}: {path}")


def _money(value, path, signed=False):
    if type(value) is not int:
        raise CalculationError("money_type", path)
    if abs(value) > 1_000_000_000 or (value < 0 and not signed):
        raise CalculationError("money_bound", path)
    return value


def parse_money(text: str) -> int:
    """Parse bounded unsigned ASCII decimal MYR text exactly into integer sen."""
    if type(text) is not str:
        raise CalculationError("money_text_type", "money_text")
    if not 1 <= len(text) <= 16 or not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", text):
        raise CalculationError("money_text_format", "money_text")
    whole, _, fraction = text.partition(".")
    return _money(int(whole) * 100 + int(fraction.ljust(2, "0")), "money_text")


def _tuple(value, path, maximum, minimum=0):
    if type(value) is not tuple:
        raise CalculationError("tuple_required", path)
    if not minimum <= len(value) <= maximum:
        raise CalculationError("collection_bound", path)
    return value


def _id(value, path):
    if type(value) is not str or not 1 <= len(value) <= 64 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", value):
        raise CalculationError("invalid_id", path)
    return value


def _rational(value, path):
    if type(value) not in (int, Fraction):
        raise CalculationError("rational_type", path)
    if abs(value.numerator) > 1_000_000_000 or value.denominator > 1_000_000:
        raise CalculationError("rational_bound", path)
    if value < 0:
        raise CalculationError("negative_weight", path)
    return Fraction(value)


def _validate(meal):
    if type(meal) is not Meal:
        raise CalculationError("fact_type", "meal")
    participants = _tuple(meal.participants, "participants", 100, 1)
    seen = set()
    for person in participants:
        _id(person, "participants")
        if person in seen:
            raise CalculationError("duplicate_id", person)
        seen.add(person)
    _tuple(meal.items, "items", 500, 1)
    source_ids = set()
    for item in meal.items:
        if type(item) is not Item:
            raise CalculationError("fact_type", "items")
        _id(item.id, "item.id")
        if item.id in source_ids:
            raise CalculationError("duplicate_id", item.id)
        source_ids.add(item.id)
        _money(item.line_sen, item.id + ".line_sen")
        quantity = _rational(item.quantity, item.id + ".quantity")
        if not 0 < quantity <= 1_000_000:
            raise CalculationError("quantity_bound", item.id)
    return seen


@dataclass(frozen=True, slots=True)
class Share:
    participant_id: str
    value: int | Fraction


@dataclass(frozen=True, slots=True)
class Split:
    mode: str
    shares: tuple[Share, ...]


@dataclass(frozen=True, slots=True)
class Item:
    id: str
    line_sen: int
    split: Split
    quantity: int | Fraction = 1


@dataclass(frozen=True, slots=True)
class Adjustment:
    id: str
    kind: str
    amount_sen: int
    eligible_item_ids: tuple[str, ...] | None = None
    split: Split | None = None


@dataclass(frozen=True, slots=True)
class Meal:
    participants: tuple[str, ...]
    items: tuple[Item, ...]
    subtotal_sen: int
    total_sen: int
    adjustments: tuple[Adjustment, ...] = ()
    included_tax_sen: int = 0


@dataclass(frozen=True, slots=True)
class PersonAmount:
    participant_id: str
    sen: int


@dataclass(frozen=True, slots=True)
class SourceAllocation:
    source_id: str
    shares: tuple[PersonAmount, ...]


@dataclass(frozen=True, slots=True)
class Calculation:
    items: tuple[SourceAllocation, ...]
    adjustments: tuple[SourceAllocation, ...]
    consumption: tuple[PersonAmount, ...]


def _apportion(amount, weights, source_id):
    total = sum(weights.values())
    if not amount:
        return tuple(PersonAmount(p, 0) for p in sorted(weights))
    quotas = {p: Fraction(amount) * w / total for p, w in weights.items()}
    amounts = {p: q.numerator // q.denominator for p, q in quotas.items()}
    def order(p):
        wire = json.dumps(["tabwise-apportion-v1", source_id, p], separators=(",", ":"))
        return (-(quotas[p] - amounts[p]), hashlib.sha256(wire.encode("ascii")).digest(), p)
    for p in sorted(weights, key=order)[:amount - sum(amounts.values())]:
        amounts[p] += 1
    return tuple(PersonAmount(p, amounts[p]) for p in sorted(amounts))


def _split(split, amount, source_id, participants, quantity=None):
    if type(split) is not Split:
        raise CalculationError("fact_type", source_id + ".split")
    if type(split.mode) is not str or split.mode not in ("equal", "weights", "percent", "exact", "quantity"):
        raise CalculationError("split_mode", source_id)
    if split.mode == "quantity" and quantity is None:
        raise CalculationError("quantity_items_only", source_id)
    shares = _tuple(split.shares, source_id + ".shares", 100, 1)
    weights = {}
    for share in shares:
        if type(share) is not Share:
            raise CalculationError("fact_type", source_id + ".shares")
        person = _id(share.participant_id, source_id + ".participant_id")
        if person not in participants:
            raise CalculationError("foreign_participant", person)
        if person in weights:
            raise CalculationError("duplicate_participant", person)
        value = (_money(share.value, source_id + ".exact_sen") if split.mode == "exact"
                 else _rational(share.value, source_id + ".weight"))
        if split.mode == "equal" and value != 1:
            raise CalculationError("equal_weight", source_id)
        if split.mode == "quantity" and value == 0:
            raise CalculationError("quantity_bound", source_id)
        weights[person] = value
    total = sum(weights.values())
    if split.mode == "percent" and total != 100:
        raise CalculationError("percent_sum", source_id)
    if split.mode == "exact" and total != amount:
        raise CalculationError("exact_sum", source_id)
    if split.mode == "quantity" and total != quantity:
        raise CalculationError("quantity_sum", source_id)
    if amount and not total:
        raise CalculationError("zero_base", source_id)
    return _apportion(amount, weights, source_id)


def calculate(meal: Meal) -> Calculation:
    participants = _validate(meal)
    _money(meal.subtotal_sen, "subtotal_sen")
    _money(meal.total_sen, "total_sen")
    _money(meal.included_tax_sen, "included_tax_sen")
    _tuple(meal.adjustments, "adjustments", 100)
    item_subtotal = sum(item.line_sen for item in meal.items)
    if item_subtotal > 1_000_000_000:
        raise CalculationError("aggregate_bound", "item_subtotal")
    if item_subtotal != meal.subtotal_sen:
        raise CalculationError("subtotal_mismatch", "subtotal_sen")
    totals = dict.fromkeys(meal.participants, 0)
    allocations = []
    for item in sorted(meal.items, key=lambda item: item.id):
        _money(item.line_sen, item.id + ".line_sen")
        shares = _split(item.split, item.line_sen, item.id, participants, item.quantity)
        allocations.append(SourceAllocation(item.id, shares))
        for share in shares:
            totals[share.participant_id] += share.sen
    source_ids = {item.id for item in meal.items}
    by_item = {allocation.source_id: allocation.shares for allocation in allocations}
    changes = []
    for change in meal.adjustments:
        if type(change) is not Adjustment:
            raise CalculationError("fact_type", "adjustments")
        _id(change.id, "adjustment.id")
        if change.id in source_ids:
            raise CalculationError("duplicate_id", change.id)
        source_ids.add(change.id)
        _money(change.amount_sen, change.id + ".amount_sen", signed=True)
        if type(change.kind) is not str or change.kind not in ("tax", "service", "discount", "rounding"):
            raise CalculationError("adjustment_kind", change.id)
        if ((change.kind in ("tax", "service") and change.amount_sen < 0)
                or (change.kind == "discount" and change.amount_sen > 0)):
            raise CalculationError("adjustment_sign", change.id)
        if (change.eligible_item_ids is None) == (change.split is None):
            raise CalculationError("adjustment_scope_or_split", change.id)
        amount = abs(change.amount_sen)
        if change.eligible_item_ids is not None:
            scope = _tuple(change.eligible_item_ids, change.id + ".scope", 500, 1)
            seen, bases = set(), dict.fromkeys(participants, 0)
            for item_id in scope:
                _id(item_id, change.id + ".scope")
                if item_id in seen:
                    raise CalculationError("duplicate_scope", change.id)
                if item_id not in by_item:
                    raise CalculationError("foreign_item", change.id)
                seen.add(item_id)
                for share in by_item[item_id]:
                    bases[share.participant_id] += share.sen
            base = sum(bases.values())
            if change.kind == "discount" and amount > base:
                raise CalculationError("discount_over_base", change.id)
            if amount and not base:
                raise CalculationError("zero_base", change.id)
            shares = _apportion(amount, bases, change.id)
        else:
            if change.kind == "discount" and amount > meal.subtotal_sen:
                raise CalculationError("discount_over_base", change.id)
            shares = _split(change.split, amount, change.id, participants)
        signed = tuple(PersonAmount(p.participant_id, -p.sen if change.amount_sen < 0 else p.sen) for p in shares)
        changes.append(SourceAllocation(change.id, signed))
        for share in signed:
            totals[share.participant_id] += share.sen
    receipt_total = item_subtotal + sum(change.amount_sen for change in meal.adjustments)
    if not 0 <= receipt_total <= 1_000_000_000:
        raise CalculationError("aggregate_bound", "receipt_total")
    if receipt_total != meal.total_sen:
        raise CalculationError("receipt_total_mismatch", "total_sen")
    if any(amount < 0 for amount in totals.values()):
        raise CalculationError("negative_consumption", "consumption")
    if any(amount > 1_000_000_000 for amount in totals.values()):
        raise CalculationError("aggregate_bound", "consumption")
    if sum(totals.values()) != receipt_total:
        raise CalculationError("allocation_invariant", "consumption")
    return Calculation(tuple(allocations), tuple(sorted(changes, key=lambda c: c.source_id)),
                       tuple(PersonAmount(p, totals[p]) for p in sorted(totals)))
