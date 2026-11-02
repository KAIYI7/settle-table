"""Deterministic Malaysian dining receipt layout parser."""
import datetime
from fractions import Fraction
import re
import statistics

from .models import (
    CandidateAdjustment,
    CandidateItem,
    CandidateReceipt,
    OcrLine,
)

MONEY_PATTERN = re.compile(
    r"(?<![\w.])(?:[-+]|\((?=[^)]*?\d))?\s*(?:RM|MYR|\$)?\s*[-+]?\s*\d+[.,]\d{2}\)?(?!\d)",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b")
TIME_PATTERN = re.compile(r"\b([012]?\d:[0-5]\d(?::[0-5]\d)?)\b")


def parse_sen(raw: str) -> int:
    """Parse monetary string into integer sen without floating-point conversion."""
    clean = re.sub(r"\s+", "", raw).replace(",", ".")
    is_neg = "-" in clean or ("(" in clean and ")" in clean)
    clean = re.sub(r"[^\d.]", "", clean)
    parts = clean.split(".")
    if len(parts) != 2:
        raise ValueError(f"Ambiguous money string: {raw}")
    whole = int(parts[0])
    frac = int(parts[1].ljust(2, "0")[:2])
    return (-1 if is_neg else 1) * (whole * 100 + frac)


def clean_item_label(text: str) -> str:
    """Clean item text from leading/trailing quantities, currency markers, and modifier artifacts."""
    # Strip leading quantity if any: e.g. "1 ", "4x ", "2 × "
    text = re.sub(r"^\s*\d+(?:\.\d+)?\s*(?:[xX×*]\s*)?", "", text)
    # Strip trailing currency or price markers: RM, MYR, $, @, :, -
    text = re.sub(r"[\s:@-]+(?:RM|MYR|\$)?[\s:@-]*$", "", text, flags=re.IGNORECASE)
    # Strip trailing modifier quantities like 'x 1', '× 1', 'x1', '×1', 'x4', '×4'
    text = re.sub(r"[\s\-–—]+[xX×*]\s*\d+\s*$", "", text)
    text = re.sub(r"\s+[xX×*]\s*\d+\s*$", "", text)
    # Normalize internal hyphen to em-dash separator: e.g. "Item - Side Dish" -> "Item — Side Dish"
    text = re.sub(r"\s+[-–—]\s+", " — ", text)
    return text.strip()


def group_lines_into_rows(lines: list[OcrLine]) -> list[list[OcrLine]]:
    """Spatially cluster OCR line tokens into coherent horizontal rows."""
    if not lines:
        return []
    
    tokens = []
    for line in lines:
        xs = [pt[0] for pt in line.box]
        ys = [pt[1] for pt in line.box]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        height = max(1, max_y - min_y)
        mid_y = (min_y + max_y) / 2
        tokens.append({
            'line': line,
            'x': min_x,
            'y': mid_y,
            'min_y': min_y,
            'max_y': max_y,
            'height': height,
        })

    tokens.sort(key=lambda t: (t['y'], t['x']))
    grouped: list[list[dict]] = []
    for token in tokens:
        placed = False
        for group in grouped:
            r_min_y = min(t['min_y'] for t in group)
            r_max_y = max(t['max_y'] for t in group)
            r_mid_y = statistics.mean(t['y'] for t in group)
            overlap = min(token['max_y'], r_max_y) - max(token['min_y'], r_min_y)
            min_h = min(token['height'], min(t['height'] for t in group))
            if overlap >= min_h * 0.35 and abs(token['y'] - r_mid_y) <= min_h * 0.55:
                group.append(token)
                placed = True
                break
        if not placed:
            grouped.append([token])

    grouped.sort(key=lambda g: statistics.mean(t['y'] for t in g))
    result: list[list[OcrLine]] = []
    for group in grouped:
        group.sort(key=lambda t: t['x'])
        result.append([t['line'] for t in group])
    return result


def parse_malaysian_receipt(lines: list[OcrLine]) -> CandidateReceipt:
    """Parse OCR lines into a verified Malaysian dining CandidateReceipt."""
    rows = group_lines_into_rows(lines)
    text_rows = [" ".join(line.text for line in row) for row in rows]
    
    merchant: str | None = None
    date_val: str | None = None
    time_val: str | None = None

    # 1. Header parsing (Merchant, Date, Time)
    for row in text_rows:
        if not date_val:
            m_date = DATE_PATTERN.search(row)
            if m_date:
                raw_d = m_date.group(1).replace("/", "-")
                parts = raw_d.split("-")
                try:
                    if len(parts[0]) == 4:
                        # YYYY-MM-DD
                        d_obj = datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
                    else:
                        # DD-MM-YYYY
                        d_obj = datetime.date(int(parts[2]), int(parts[1]), int(parts[0]))
                    date_val = d_obj.isoformat()
                except ValueError:
                    pass

        if not time_val:
            m_time = TIME_PATTERN.search(row)
            if m_time:
                t_str = m_time.group(1)
                if t_str.count(":") == 1:
                    t_str += ":00"
                time_val = t_str

    # Extract merchant name from top lines
    merchant_parts: list[str] = []
    for row in text_rows[:8]:
        lbl = row.upper()
        if "SYNTHETIC" in lbl:
            continue
        if re.search(r"\b(?:COMPANY|REG|REGISTRATION|GST|SST|TAX|INVOICE|NO\.|JALAN|UNIT|TEL|FAX)\b|\d{5,}", lbl):
            if "SDN" in lbl and merchant_parts:
                merchant_parts.append(row)
            break
        if any(c.isalpha() for c in row):
            merchant_parts.append(row)
        if len(merchant_parts) >= 2:
            break
    if merchant_parts:
        merchant = " ".join(merchant_parts)

    # 2. Section scanning
    in_items = False
    past_items = False
    total_found = False
    tax_included = False
    printed_net_subtotal_sen: int | None = None
    printed_subtotal_sen: int | None = None
    tax_sen: int | None = None
    tax_kind = "SST"
    service_sen: int | None = None
    discount_sen: int | None = None
    rounding_sen: int | None = None
    total_candidates: list[tuple[int, int]] = []  # (priority, amount_sen)
    raw_items: list[dict] = []
    prefix_name: str | None = None

    for row in text_rows:
        lbl = row.upper().replace("T0TAL", "TOTAL")
        matches = list(MONEY_PATTERN.finditer(row))
        amounts: list[int] = []
        for m in matches:
            try:
                amounts.append(parse_sen(m.group(0)))
            except ValueError:
                pass

        # Check for tax inclusion notices
        if any(kw in lbl for kw in ("INCLUSIVE OF", "INCL SST", "INCL GST", "TAX INCL", "TAX INCLUSIVE")):
            tax_included = True

        # Ignore informational tax summary tables printed after grand total
        if re.search(r"\bTAX\s*SUMMARY\b", lbl):
            past_items = True
            total_found = True
            continue

        # Check for summary lines (must contain monetary amounts)
        summary_matched = False
        if amounts and (re.search(r"\b(?:SUB[-\s]*TOTAL|STTL|NET SALES|TOTAL SALES)\b", lbl) or re.search(r"\bTOTAL.*EXCLUD", lbl)):
            if printed_subtotal_sen is None or not total_found:
                printed_subtotal_sen = amounts[-1]
            summary_matched = True
            in_items = False
            past_items = True
        elif amounts and re.search(r"\b(?:ROUNDING|ROUND|ROUNDING ADJ)\b", lbl):
            if rounding_sen is None or not total_found:
                rounding_sen = amounts[-1]
            summary_matched = True
            in_items = False
            past_items = True
        elif amounts and re.search(r"\b(?:DISCOUNT|DISC|VOUCHER|REBATE|PROMO)\b", lbl):
            if discount_sen is None or not total_found:
                discount_sen = abs(amounts[-1])
            summary_matched = True
            in_items = False
            past_items = True
        elif amounts and re.search(r"\b(?:SERVICE\s*(?:CHARGE|CHG)|SVC\s*CHG)\b", lbl):
            if service_sen is None or not total_found:
                service_sen = amounts[-1]
            summary_matched = True
            in_items = False
            past_items = True
        elif amounts and re.search(r"\b(?:SST|GST|SERVICE TAX|SALES TAX|GOVT TAX)\b", lbl) and not re.search(r"\b(?:NO\.?|REG|INVOICE|SUMMARY|CODE|AMOUNT|TOTAL|TTL|ID)\b", lbl):
            if tax_sen is None or not total_found:
                tax_sen = amounts[-1]
                if "GST" in lbl:
                    tax_kind = "GST"
            summary_matched = True
            in_items = False
            past_items = True

        if summary_matched:
            continue

        # Check for final total
        if amounts and re.search(r"\b(?:TOTAL|^TTL\b|AMOUNT DUE|GRAND TOTAL)\b", lbl) and not re.search(r"\b(?:QTY|QUANTITY|SUBTOTAL|EXCLUD)\b", lbl):
            priority = 5 if "GRAND" in lbl else 3 if "INCLUS" in lbl else 2 if lbl.startswith("TTL") else 4
            total_candidates.append((priority, amounts[-1]))
            in_items = False
            past_items = True
            total_found = True
            continue

        if past_items:
            continue

        # Check for item table headers
        if not amounts and re.search(r"\b(?:DESCRIPT|ITEM|QTY.*UNIT|QTY.*TOTAL|PRODUCT)\b", lbl) and "TOTAL QTY" not in lbl:
            in_items = True
            prefix_name = None
            continue

        if not in_items:
            if amounts and not re.search(r"\b(?:DATE|TIME|TEL|FAX|TABLE|GUEST|CHECK|INV|CASHIER|ROUND|TAX|GST|SST|TOTAL|SUBTOTAL|SERVICE|SVC|DISCOUNT|VOUCHER|CASH|CHANGE|TIPS)\b", lbl):
                in_items = True
            else:
                continue

        # Item line extraction
        if amounts:
            before = row[:matches[0].start()].strip()
            # Match quantity: e.g. "2x", "2 x", "2 ×", "2", "1" at start or trailing before price
            q_match = re.match(r"^(\d+(?:\.\d+)?)\s*(?:[xX×*]\s*)?", before)
            quantity = (1, 1)
            item_text = before
            if q_match:
                matched_rest = before[q_match.end():].strip()
                if any(c.isalpha() for c in matched_rest):
                    try:
                        frac = Fraction(q_match.group(1)).limit_denominator(100)
                        quantity = (frac.numerator, frac.denominator)
                        item_text = matched_rest
                    except (ValueError, ZeroDivisionError):
                        quantity = (1, 1)
            if quantity == (1, 1):
                trailing_q = re.search(r"\b(\d+(?:\.\d+)?)\s*[xX×*]?$", before)
                if trailing_q:
                    potential_text = before[:trailing_q.start()].strip()
                    if potential_text and any(c.isalpha() for c in potential_text):
                        try:
                            frac = Fraction(trailing_q.group(1)).limit_denominator(100)
                            if frac > 0:
                                quantity = (frac.numerator, frac.denominator)
                                item_text = potential_text
                        except (ValueError, ZeroDivisionError):
                            pass
            
            clean_label = clean_item_label(item_text)
            if re.fullmatch(r"[A-Za-z]*\d+[A-Za-z]*", clean_label):
                clean_label = ""
            if clean_label:
                if prefix_name and raw_items:
                    raw_items[-1]["label"] += " " + prefix_name.strip()
                    prefix_name = None
                label = clean_label
            else:
                label = prefix_name or "Item"
                prefix_name = None
            unit_sen = amounts[-2] if len(amounts) > 1 else None
            line_sen = amounts[-1]
            raw_items.append({
                'label': label,
                'quantity': quantity,
                'unit_price_sen': unit_sen,
                'line_sen': line_sen,
            })
            prefix_name = None
        elif any(c.isalpha() for c in row):
            clean_sub = clean_item_label(row)
            if raw_items and in_items and not past_items:
                stripped = clean_sub.lstrip("-–— ")
                if clean_sub.startswith("-") or clean_sub.startswith("–") or clean_sub.startswith("—"):
                    raw_items[-1]["label"] += " — " + stripped
                elif not re.match(r"^\d+\b", clean_sub) and not re.search(r"\b(?:TABLE|GUEST|CHECK|INV|CASHIER|DATE|TIME|STAFF)\b", clean_sub.upper()):
                    raw_items[-1]["label"] += " " + stripped
                else:
                    prefix_name = row
            else:
                prefix_name = row

    # 3. Final Total Determination
    final_total_sen = max(total_candidates)[1] if total_candidates else None

    # 4. Malaysian Tax-Inclusive vs. Tax-Exclusive Resolution (The Wan Sheng Rule)
    computed_items_subtotal = sum(i['line_sen'] for i in raw_items)
    
    if tax_included:
        # Wan Sheng rule: subtotal_sen must match sum(line items).
        subtotal_sen = computed_items_subtotal
        if printed_subtotal_sen is not None and printed_subtotal_sen != computed_items_subtotal:
            printed_net_subtotal_sen = printed_subtotal_sen
        included_tax_sen = tax_sen
    else:
        subtotal_sen = printed_subtotal_sen if printed_subtotal_sen is not None else computed_items_subtotal
        included_tax_sen = None

    # 5. Build Candidate Items
    candidate_items: list[CandidateItem] = []
    item_ids: list[str] = []
    for idx, item in enumerate(raw_items, start=1):
        item_id = f"item-{idx}"
        item_ids.append(item_id)
        candidate_items.append(CandidateItem(
            id=item_id,
            label=item['label'],
            quantity=item['quantity'],
            unit_price_sen=item['unit_price_sen'],
            line_sen=item['line_sen'],
        ))

    # 6. Build Candidate Adjustments
    adjustments: list[CandidateAdjustment] = []
    all_item_ids = tuple(item_ids) if item_ids else None

    if not tax_included and tax_sen is not None and tax_sen > 0:
        adjustments.append(CandidateAdjustment(
            id="adj-tax-1",
            label=f"{tax_kind} Tax",
            kind="tax",
            amount_sen=tax_sen,
            eligible_item_ids=all_item_ids,
            rationale=f"Extracted {tax_kind} from receipt",
        ))

    if service_sen is not None and service_sen > 0:
        adjustments.append(CandidateAdjustment(
            id="adj-service-1",
            label="Service Charge",
            kind="service",
            amount_sen=service_sen,
            eligible_item_ids=all_item_ids,
            rationale="Extracted service charge from receipt",
            scope_mode='all_items',
        ))

    if discount_sen is not None and discount_sen > 0:
        adjustments.append(CandidateAdjustment(
            id="adj-discount-1",
            label="Discount",
            kind="discount",
            amount_sen=-abs(discount_sen),  # Strictly negative in SettleTable domain model
            eligible_item_ids=all_item_ids,
            rationale="Extracted discount from receipt",
        ))

    if rounding_sen is not None and rounding_sen != 0:
        adjustments.append(CandidateAdjustment(
            id="adj-rounding-1",
            label="Rounding Adjustment",
            kind="rounding",
            amount_sen=rounding_sen,
            eligible_item_ids=all_item_ids,
            rationale="Extracted BNM 5-sen rounding adjustment",
        ))

    # 7. Reconciliation & Issues Detection
    issues: list[str] = []
    
    # Validate BNM rounding range: strictly in {-2, -1, 0, +1, +2} sen
    if rounding_sen is not None and abs(rounding_sen) > 2:
        issues.append("invalid_rounding_adjustment")

    if not candidate_items:
        issues.append("missing_items")
    elif any(not item.label or item.label == "Item" for item in candidate_items):
        issues.append("unidentified_items")

    if final_total_sen is None:
        issues.append("missing_receipt_total")

    scores = [line.score for line in lines]
    mean_confidence = statistics.mean(scores) if scores else 0.0
    if mean_confidence < 0.85:
        issues.append("low_confidence")

    expected_total = subtotal_sen + sum(adj.amount_sen for adj in adjustments)
    discrepancy_sen = (final_total_sen - expected_total) if final_total_sen is not None else 0
    reconciled = (discrepancy_sen == 0 and final_total_sen is not None)

    if not reconciled and final_total_sen is not None:
        issues.append("candidate_receipt_mismatch")

    route = "human_verification" if not issues else "manual_correction"

    return CandidateReceipt(
        merchant=merchant,
        date=date_val,
        time=time_val,
        items=tuple(candidate_items),
        subtotal_sen=subtotal_sen,
        printed_net_subtotal_sen=printed_net_subtotal_sen,
        included_tax_sen=included_tax_sen,
        tax_sen=tax_sen,
        tax_kind=tax_kind,
        tax_included=tax_included,
        service_sen=service_sen,
        discount_sen=discount_sen,
        rounding_sen=rounding_sen,
        total_sen=final_total_sen,
        adjustments=tuple(adjustments),
        reconciled=reconciled,
        discrepancy_sen=discrepancy_sen,
        mean_confidence=mean_confidence,
        issues=tuple(sorted(set(issues))),
        route=route,
    )
