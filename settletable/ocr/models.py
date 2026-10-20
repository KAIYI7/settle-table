"""Data models for SettleTable Bounded Local OCR Pipeline."""
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class OcrLine:
    """A recognized line of text with bounding box and confidence score."""
    text: str
    score: float
    box: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]

    def to_dict(self) -> dict[str, Any]:
        return {
            'text': self.text,
            'score': round(self.score, 4),
            'box': [list(pt) for pt in self.box],
        }


@dataclass(frozen=True)
class CandidateItem:
    """An extracted candidate receipt line item."""
    id: str
    label: str
    quantity: tuple[int, int]  # (numerator, denominator)
    unit_price_sen: int | None
    line_sen: int

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'label': self.label,
            'quantity': list(self.quantity),
            'unit_price_sen': self.unit_price_sen,
            'line_sen': self.line_sen,
        }


@dataclass(frozen=True)
class CandidateAdjustment:
    """An extracted candidate tax, service charge, discount, or rounding adjustment."""
    id: str
    label: str
    kind: str  # Strictly one of: 'tax', 'service', 'discount', 'rounding'
    amount_sen: int  # Positive for tax/service/round-up, negative for discount/round-down
    eligible_item_ids: tuple[str, ...] | None
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'label': self.label,
            'kind': self.kind,
            'amount_sen': self.amount_sen,
            'eligible_item_ids': list(self.eligible_item_ids) if self.eligible_item_ids is not None else None,
            'rationale': self.rationale,
        }


@dataclass(frozen=True)
class CandidateReceipt:
    """Full proposed receipt candidate extracted from a receipt image."""
    merchant: str | None
    date: str | None  # ISO YYYY-MM-DD
    time: str | None  # HH:MM:SS
    items: tuple[CandidateItem, ...]
    subtotal_sen: int | None
    printed_net_subtotal_sen: int | None
    included_tax_sen: int | None
    tax_sen: int | None
    tax_kind: str | None  # 'SST', 'GST', 'TAX'
    tax_included: bool
    service_sen: int | None
    discount_sen: int | None
    rounding_sen: int | None
    total_sen: int | None
    adjustments: tuple[CandidateAdjustment, ...]
    reconciled: bool
    discrepancy_sen: int
    mean_confidence: float
    issues: tuple[str, ...]
    route: str  # 'human_verification' or 'manual_correction'

    def to_dict(self) -> dict[str, Any]:
        return {
            'merchant': self.merchant,
            'date': self.date,
            'time': self.time,
            'items': [item.to_dict() for item in self.items],
            'subtotal_sen': self.subtotal_sen,
            'printed_net_subtotal_sen': self.printed_net_subtotal_sen,
            'included_tax_sen': self.included_tax_sen,
            'tax_sen': self.tax_sen,
            'tax_kind': self.tax_kind,
            'tax_included': self.tax_included,
            'service_sen': self.service_sen,
            'discount_sen': self.discount_sen,
            'rounding_sen': self.rounding_sen,
            'total_sen': self.total_sen,
            'adjustments': [adj.to_dict() for adj in self.adjustments],
            'reconciled': self.reconciled,
            'discrepancy_sen': self.discrepancy_sen,
            'mean_confidence': round(self.mean_confidence, 4),
            'issues': list(self.issues),
            'route': self.route,
        }
