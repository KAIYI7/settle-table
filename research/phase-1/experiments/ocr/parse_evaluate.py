"""Disposable deterministic parser + development-set evaluation, NOT an app pipeline.

No network/model call. Parser never reads truth; evaluator does. Unknown amounts
are None, all recognized money is integer sen. Scores/latency are not money.
Freeze this script before the scored run; do not tune from resulting scores.
"""
import datetime
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parent
MONEY = re.compile(r"(?<![\d.])[-+]?\s*\d+[.,]\d{2}(?!\d)")
FIELDS = ["merchant", "date", "time", "subtotal_sen", "tax_sen", "service_sen",
          "discount_sen", "rounding_sen", "total_sen"]


def sen(raw):
    raw = re.sub(r"\s+", "", raw).replace(",", ".")
    if re.fullmatch(r"[-+]?\d+\.\d{2}", raw) is None:
        raise ValueError("ambiguous money")
    sign = -1 if raw.startswith("-") else 1
    whole, cents = raw.lstrip("+-").split(".")
    return sign * (int(whole) * 100 + int(cents))


def norm(raw):
    return re.sub(r"[^\w]", "", str(raw).upper(), flags=re.UNICODE)


def rows(lines):
    """Independent spatial grouping; text/geometry only, no receipt ground truth."""
    tokens = []
    for line in lines:
        xs = [point[0] for point in line["box"]]
        ys = [point[1] for point in line["box"]]
        tokens.append({"text": line["text"], "x": min(xs), "y": (min(ys)+max(ys))/2,
                       "height": max(ys)-min(ys), "score": line["score"]})
    if not tokens:
        return []
    threshold = max(4, statistics.median(t["height"] for t in tokens) * 0.55)
    grouped = []
    for token in sorted(tokens, key=lambda t: (t["y"], t["x"])):
        if grouped and abs(token["y"] - statistics.mean(t["y"] for t in grouped[-1])) <= threshold:
            grouped[-1].append(token)
        else:
            grouped.append([token])
    return [" ".join(t["text"] for t in sorted(row, key=lambda t: t["x"])) for row in grouped]


def parse(lines):
    text_rows = rows(lines)
    result = {field: None for field in FIELDS}
    result.update(items=[], issues=[], observed_rows=text_rows)
    date_pattern = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b")
    for row in text_rows:
        match = date_pattern.search(row)
        if match and result["date"] is None:
            try:
                result["date"] = datetime.datetime.strptime(match[1].replace("/", "-"), "%d-%m-%Y").date().isoformat()
            except ValueError:
                pass
        match = re.search(r"\b([012]?\d:[0-5]\d(?::[0-5]\d)?)\b", row)
        if match and result["time"] is None:
            result["time"] = match[1] + (":00" if match[1].count(":") == 1 else "")
    merchant_parts = []
    for row in text_rows[:8]:
        label = row.upper()
        if "SYNTHETIC" in label:
            continue
        if re.search(r"(?:COMPANY|REG|GST|TAX|INVOICE|NO\.|JALAN|UNIT|SDN|\d{3,})", label):
            if "SDN" in label and merchant_parts:
                merchant_parts.append(row)
            break
        if any(c.isalpha() for c in row):
            merchant_parts.append(row)
        if len(merchant_parts) >= 2:
            break
    if merchant_parts:
        result["merchant"] = " ".join(merchant_parts)

    in_items = False
    prefix = None
    final_candidates = []
    included = False
    for row in text_rows:
        label = row.upper().replace("T0TAL", "TOTAL")
        matches = list(MONEY.finditer(row))
        amounts = [sen(match[0]) for match in matches]
        if "INCLUS" in label or "INCLUDING GST" in label:
            included = True
        summary = None
        if re.search(r"SUB\s*TOTAL|STTL|NET SALES|EXCLUD", label):
            summary = "subtotal_sen"
        elif re.search(r"ROUND", label):
            summary = "rounding_sen"
        elif re.search(r"DISCOUNT|VOUCHER|REBAT", label):
            summary = "discount_sen"
        elif re.search(r"SERVICE\s*(?:CHARGE|CHG)|SVC\s*CHG", label):
            summary = "service_sen"
        elif re.search(r"\b(?:SST|GST|TAX)\b", label) and not re.search(r"NO\.?|REG|INVOICE|SUMMARY|CODE|AMOUNT", label):
            summary = "tax_sen"
        if summary and amounts:
            if result[summary] is None:
                result[summary] = abs(amounts[-1]) if summary == "discount_sen" else amounts[-1]
            in_items = False
            continue
        if amounts and re.search(r"TOTAL|^TTL\b|AMOUNT DUE", label) and not re.search(r"QTY|QUANTITY|SUBTOTAL", label):
            priority = 5 if "GRAND" in label else 3 if "INCLUS" in label else 2 if label.startswith("TTL") else 4
            final_candidates.append((priority, len(final_candidates), amounts[-1]))
            in_items = False
            continue
        if not amounts and re.search(r"DESCRIPT|PRODUCT CODE|QTY.*UNIT|QTY.*TOTAL", label) and "TOTAL QTY" not in label:
            in_items = True
            prefix = None
            continue
        if not in_items:
            continue
        if amounts:
            before = row[:matches[0].start()].strip()
            quantity_match = re.match(r"^(\d+(?:\.\d+)?)\s*(?:[xX]\s*)?", before)
            quantity = quantity_match[1] if quantity_match else None
            inline = before[quantity_match.end():].strip() if quantity_match else before
            if re.fullmatch(r"[A-Za-z]*\d+[A-Za-z]*", inline):
                inline = ""
            name = inline or prefix
            result["items"].append({"name": name, "quantity": quantity,
                                    "unit_price_sen": amounts[-2] if len(amounts)>1 else None,
                                    "line_total_sen": amounts[-1]})
            prefix = None
        elif any(c.isalpha() for c in row):
            if result["items"] and not result["items"][-1]["name"]:
                result["items"][-1]["name"] = row
            else:
                prefix = row
    if final_candidates:
        result["total_sen"] = max(final_candidates)[2]
    result["tax_included_candidate"] = included
    scores = [line["score"] for line in lines]
    result["mean_ocr_score"] = statistics.mean(scores) if scores else 0
    if not result["items"] or any(not item["name"] for item in result["items"]):
        result["issues"].append("missing_or_unidentified_items")
    if result["total_sen"] is None:
        result["issues"].append("missing_receipt_total")
    if result["date"] is None or result["merchant"] is None:
        result["issues"].append("missing_date_or_merchant")
    if result["mean_ocr_score"] < 0.90:
        result["issues"].append("low_mean_ocr_score")
    if result["total_sen"] is not None and result["items"]:
        base = sum(item["line_total_sen"] for item in result["items"])
        additional_tax = 0 if included else (result["tax_sen"] or 0)
        computed = base + additional_tax + (result["service_sen"] or 0) - (result["discount_sen"] or 0) + (result["rounding_sen"] or 0)
        result["computed_candidate_sen"] = computed
        result["discrepancy_sen"] = result["total_sen"] - computed
        if result["discrepancy_sen"]:
            result["issues"].append("candidate_receipt_mismatch")
    result["route"] = "manual_correction" if result["issues"] else "human_verification"
    return result


def matches(field, observed, expected):
    if field in ("merchant", "name"):
        return observed is not None and norm(observed) in [norm(x) for x in (expected if isinstance(expected,list) else [expected])]
    if field == "quantity":
        try:
            return observed is not None and Fraction(observed) == Fraction(expected)
        except (ValueError, ZeroDivisionError):
            return False
    return observed == expected


def main():
    truth = json.loads((ROOT / "data/truth.json").read_text(encoding="utf-8"))
    corpus = {entry["id"]: entry for entry in json.loads((ROOT / "data/corpus.json").read_text(encoding="utf-8"))}
    outputs = []
    summary = {"scope": "exploratory development corpus; no held-out accuracy estimate",
               "parser_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "matching": "strict normalized text; fixed positional item alignment; no fuzzy or oracle field recovery",
               "gate": "mean OCR score>=0.90, required header/item fields and exact candidate reconciliation; never skips human review",
               "cloud": "excluded by user; local gate routes weak results to manual correction",
               "engines": {}}
    for name in ("rapidocr", "paddleocr", "tesseract"):
        path = ROOT / "results" / (name + ".json")
        if not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        engine_summary = {"init_ms": raw["init_ms"], "groups": {}}
        for kind in ("real_historical_malaysian_dining", "synthetic_not_field_evidence"):
            counters = {field: {"correct":0,"labeled":0,"absent_correct":0,"absent_labeled":0} for field in FIELDS + ["name","quantity","unit_price_sen","line_total_sen"]}
            selected = [run for run in raw["runs"] if run["pass"] == 1 and corpus[Path(run["image"]).stem]["kind"] == kind]
            escalation = false_accept = 0
            latencies = []
            for run in selected:
                key = Path(run["image"]).stem
                expected = truth[key]
                observed = parse(run["lines"])
                all_correct = True
                for field in FIELDS:
                    if expected.get(field) is None:
                        # Null time/unit/quantity means unannotated; known absent charges have separate denominators.
                        if expected.get("presence",{}).get(field) == "absent_on_visual_inspection":
                            counters[field]["absent_labeled"] += 1
                            counters[field]["absent_correct"] += observed[field] is None
                        continue
                    correct = matches(field, observed[field], expected[field])
                    counters[field]["labeled"] += 1
                    counters[field]["correct"] += correct
                    all_correct &= correct
                for index, item in enumerate(expected["items"]):
                    actual = observed["items"][index] if index < len(observed["items"]) else {}
                    for field in ("name","quantity","unit_price_sen","line_total_sen"):
                        if item[field] is None:
                            continue
                        correct = matches(field, actual.get(field), item[field])
                        counters[field]["labeled"] += 1
                        counters[field]["correct"] += correct
                        all_correct &= correct
                if len(observed["items"]) != len(expected["items"]):
                    all_correct = False
                # Absent-field hallucinations also make a candidate unsafe.
                for field, presence in expected.get("presence",{}).items():
                    if presence == "absent_on_visual_inspection" and observed[field] is not None:
                        all_correct = False
                escalation += observed["route"] == "manual_correction"
                false_accept += observed["route"] == "human_verification" and not all_correct
                latencies.append(run["elapsed_ms"])
                outputs.append({"engine":name,"id":key,"kind":kind,"observed":observed,
                                "all_labeled_fields_exact":bool(all_correct),"expected_item_count":len(expected["items"])})
            engine_summary["groups"][kind] = {"images":len(selected),"field_metrics":counters,
               "warm_median_ms":statistics.median(latencies) if latencies else None,
               "warm_max_ms":max(latencies) if latencies else None,
               "gate_manual_count":escalation,"gate_unsafe_clean_candidates":false_accept}
        summary["engines"][name] = engine_summary
    (ROOT / "results/parsed.json").write_text(json.dumps(outputs,ensure_ascii=False,indent=2),encoding="utf-8")
    (ROOT / "results/metrics.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({name:{kind:{k:v for k,v in group.items() if k!='field_metrics'} for kind,group in engine['groups'].items()} for name,engine in summary['engines'].items()},indent=2))


if __name__ == "__main__":
    main()
