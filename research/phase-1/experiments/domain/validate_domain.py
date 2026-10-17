"""Disposable Phase-1 experiment; not an application module or production test suite.

Standard library only. Money is integer sen; all weights/quantities are Fraction.
Run: python validate_domain.py --output results.json --seed 20261016 --trials 3000
"""

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import random
import re
import sys


class Rejected(ValueError):
    pass


def integer(value):
    if type(value) is not int:
        raise Rejected("money_must_be_integer_sen")
    return value


def person_id(value):
    if type(value) is not str or not value.strip():
        raise Rejected("invalid_participant_id")
    return value


def money_map(values, allow_negative=False):
    for person, amount in values.items():
        person_id(person)
        integer(amount)
        if not allow_negative and amount < 0:
            raise Rejected("negative_amount_requires_explicit_mode")
    return values


def parse_sen(text):
    if type(text) is not str or re.fullmatch(r"-?[0-9]+(?:\.[0-9]{1,2})?", text) is None:
        raise Rejected("ambiguous_money_string")
    sign = -1 if text.startswith("-") else 1
    whole, _, fraction = text.lstrip("-").partition(".")
    return sign * (int(whole) * 100 + int(fraction.ljust(2, "0") or "0"))


def rational(value):
    if type(value) not in (str, int, Fraction):
        raise Rejected("weight_must_be_exact")
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise Rejected("invalid_rational") from error


def weights_from(pairs):
    weights = {}
    for person, value in pairs:
        person_id(person)
        if person in weights:
            raise Rejected("duplicate_person")
        weight = rational(value)
        if weight < 0:
            raise Rejected("negative_weight")
        weights[person] = weight
    return weights


def apportion(amount, pairs, component_id):
    """Pure experimental interface: signed sen + exact weights -> conserved sen.

    Stable component/person hashes break ties; zero-weight people cannot get residue.
    Negative amounts negate allocation of the absolute amount. No I/O, globals or RNG.
    """
    integer(amount)
    weights = weights_from(pairs)
    total_weight = sum(weights.values(), Fraction(0))
    if not total_weight:
        if amount:
            raise Rejected("zero_eligible_base")
        return {person: 0 for person in weights}
    magnitude = abs(amount)
    quotas = {person: Fraction(magnitude) * weight / total_weight
              for person, weight in weights.items()}
    amounts = {person: quota.numerator // quota.denominator
               for person, quota in quotas.items()}
    remaining = magnitude - sum(amounts.values())
    eligible = [person for person, weight in weights.items() if weight]
    eligible.sort(key=lambda person: (
        -(quotas[person] - amounts[person]),
        hashlib.sha256((component_id + "\0" + person).encode()).digest(), person))
    for person in eligible[:remaining]:
        amounts[person] += 1
    sign = -1 if amount < 0 else 1
    return {person: sign * value for person, value in amounts.items()}


def exact_split(amount, pairs):
    values = {}
    for person, value in pairs:
        person_id(person)
        if person in values:
            raise Rejected("duplicate_person")
        integer(value)
        if value < 0:
            raise Rejected("negative_consumption")
        values[person] = value
    if sum(values.values()) != integer(amount):
        raise Rejected("exact_sum_mismatch")
    return values


def percent_split(amount, pairs, component_id):
    weights = weights_from(pairs)
    if sum(weights.values(), Fraction(0)) != 100:
        raise Rejected("percentage_must_total_100")
    return apportion(amount, list(weights.items()), component_id)


def quantity_split(amount, quantity, pairs, component_id):
    quantity = rational(quantity)
    weights = weights_from(pairs)
    if quantity <= 0 or sum(weights.values(), Fraction(0)) != quantity:
        raise Rejected("quantity_sum_mismatch")
    return apportion(amount, list(weights.items()), component_id)


def sum_components(people, components):
    if len(people) != len(set(people)):
        raise Rejected("duplicate_person")
    for person in people:
        person_id(person)
    totals = {person: 0 for person in people}
    for component in components:
        for person, amount in component.items():
            if person not in totals:
                raise Rejected("unknown_participant")
            totals[person] += integer(amount)
    return totals


def scoped_adjustment(amount, item_ids, items, component_id, permit_credit=False):
    integer(amount)
    if len(item_ids) != len(set(item_ids)):
        raise Rejected("duplicate_scope_item")
    if any(item_id not in items for item_id in item_ids):
        raise Rejected("unknown_scope_item")
    base = {}
    for item_id in item_ids:
        money_map(items[item_id])
        for person, cost in items[item_id].items():
            base[person] = base.get(person, 0) + cost
    if any(value < 0 for value in base.values()):
        raise Rejected("negative_eligible_base")
    if not permit_credit and amount < 0 and -amount > sum(base.values()):
        raise Rejected("discount_exceeds_eligible_base")
    return apportion(amount, list(base.items()), component_id)


def review_gate(items, canonical_item_subtotal, added_components, receipt_total, unresolved=(), refund_mode=False):
    integer(canonical_item_subtotal)
    integer(receipt_total)
    if not refund_mode and (canonical_item_subtotal < 0 or receipt_total < 0):
        raise Rejected("negative_amount_requires_explicit_mode")
    for item in items:
        money_map(item, allow_negative=refund_mode)
    for component in added_components:
        money_map(component, allow_negative=True)
    if unresolved:
        raise Rejected("review_incomplete")
    item_sum = sum(sum(item.values()) for item in items)
    if item_sum != canonical_item_subtotal:
        raise Rejected("subtotal_mismatch")
    if item_sum + sum(sum(component.values()) for component in added_components) != receipt_total:
        raise Rejected("receipt_total_mismatch")
    return True


def draft_reconciliation(receipt_total, assigned, unassigned):
    integer(receipt_total)
    integer(assigned)
    integer(unassigned)
    if min(receipt_total, assigned, unassigned) < 0:
        raise Rejected("negative_amount_requires_explicit_mode")
    discrepancy = receipt_total - assigned - unassigned
    return {"receipt_total_sen": receipt_total, "assigned_sen": assigned,
            "unassigned_sen": unassigned, "diagnostic_discrepancy_sen": discrepancy,
            "arithmetic_reconciled": unassigned == 0 and discrepancy == 0}


def balances(owed, payments, transfers=(), refund_mode=False):
    money_map(owed, allow_negative=refund_mode)
    money_map(payments, allow_negative=refund_mode)
    if any(person not in owed for person in payments):
        raise Rejected("unknown_payer")
    if sum(owed.values()) != sum(payments.values()):
        raise Rejected("funding_mismatch")
    result = {person: payments.get(person, 0) - cost for person, cost in owed.items()}
    seen = {}
    for transfer in transfers:
        transfer_id, sender, receiver, amount, state = transfer
        if type(transfer_id) is not str or not transfer_id.strip():
            raise Rejected("invalid_transfer_id")
        person_id(sender)
        person_id(receiver)
        integer(amount)
        if sender not in result or receiver not in result:
            raise Rejected("unknown_settlement_person")
        if amount <= 0 or sender == receiver:
            raise Rejected("invalid_transfer")
        if transfer_id in seen:
            if seen[transfer_id] != transfer:
                raise Rejected("conflicting_transfer_id")
            continue
        seen[transfer_id] = transfer
        if state not in ("suggested", "pending", "confirmed", "void"):
            raise Rejected("invalid_transfer_state")
        if state == "confirmed":
            result[sender] += amount
            result[receiver] -= amount
    return result


def suggestions(net):
    money_map(net, allow_negative=True)
    if sum(net.values()) != 0:
        raise Rejected("nonzero_group_balance")
    working = dict(net)
    result = []
    for debtor in sorted(working):
        if working[debtor] >= 0:
            continue
        for creditor in sorted(working):
            if working[creditor] <= 0:
                continue
            amount = min(-working[debtor], working[creditor])
            working[debtor] += amount
            working[creditor] -= amount
            result.append(("suggestion-" + str(len(result)), debtor, creditor, amount, "suggested"))
            if working[debtor] == 0:
                break
    assert not any(working.values())
    return result


def simulate_confirmation(transfers):
    """Explicit experiment action, never an assertion that real money moved."""
    assert all(transfer[4] == "suggested" for transfer in transfers)
    return [(*transfer[:4], "confirmed") for transfer in transfers]


def remove_membership(person, allocation, payments, transfers):
    person_id(person)
    money_map(allocation, allow_negative=True)
    money_map(payments, allow_negative=True)
    if allocation.get(person, 0) or payments.get(person, 0) or any(
            person in transfer[1:3] for transfer in transfers):
        raise Rejected("retain_person_with_history")
    return True


def run(seed, trials):
    cases = []

    def record(name, evidence, inputs, result):
        cases.append({"name": name, "classification": evidence,
                      "inputs": inputs, "result": result, "status": "PASS"})

    def reject(name, reason, action, inputs):
        try:
            action()
        except Rejected as error:
            assert str(error) == reason, (name, str(error), reason)
            record(name, "experiment_expected_rejection", inputs, {"reason": str(error)})
        else:
            raise AssertionError((name, "expected rejection"))

    assert [parse_sen(value) for value in ("12.50", "0.01", "-0.01", "2")] == [1250, 1, -1, 200]
    record("exact_decimal_to_sen", "experiment", {"decimal_strings": ["12.50", "0.01", "-0.01", "2"]}, [1250, 1, -1, 200])
    reject("fractional_sen_input", "ambiguous_money_string", lambda: parse_sen("1.005"), {"amount": "1.005"})
    reject("ambiguous_money_separator", "ambiguous_money_string", lambda: parse_sen("1,234.56"), {"amount": "1,234.56"})

    split = apportion(1000, [(p, 1) for p in "ABC"], "shared-dish")
    assert sorted(split.values()) == [333, 333, 334]
    record("equal_shared_dish", "experiment", {"sen": 1000, "weights": [1, 1, 1]}, split)

    split = apportion(1000, [("A", "1/2"), ("B", "1/3"), ("C", "1/6")], "custom")
    assert split == {"A": 500, "B": 333, "C": 167}
    record("custom_rational_weights", "experiment", {"sen": 1000, "weights": ["1/2", "1/3", "1/6"]}, split)

    split = quantity_split(2500, "5/2", [("A", 1), ("B", "3/2")], "quantity")
    assert split == {"A": 1000, "B": 1500}
    record("fractional_quantity", "experiment", {"sen": 2500, "quantity": "5/2", "claims": ["1", "3/2"]}, split)

    split = percent_split(10000, [("A", "33.33"), ("B", "33.33"), ("C", "33.34")], "percent")
    assert split == {"A": 3333, "B": 3333, "C": 3334}
    record("percent_exact_decimal", "experiment", {"sen": 10000, "percent": ["33.33", "33.33", "33.34"]}, split)

    split = exact_split(1000, [("A", 1), ("B", 999)])
    record("exact_sen", "experiment", {"sen": 1000, "claims": {"A": 1, "B": 999}}, split)
    reject("exact_mismatch", "exact_sum_mismatch", lambda: exact_split(1000, [("A", 333), ("B", 666)]), {"sen": 1000, "claims": [333, 666]})
    reject("percent_mismatch", "percentage_must_total_100", lambda: percent_split(1000, [("A", "33.33"), ("B", "66.66")], "bad"), {"percent": ["33.33", "66.66"]})
    reject("quantity_unassigned", "quantity_sum_mismatch", lambda: quantity_split(1000, 3, [("A", 1), ("B", 1)], "bad"), {"quantity": 3, "claimed": 2})
    reject("negative_weight", "negative_weight", lambda: apportion(100, [("A", -1)], "bad"), {"weight": -1})
    reject("noninteger_money", "money_must_be_integer_sen", lambda: apportion(Fraction(1, 2), [("A", 1)], "bad"), {"money": "1/2 sen"})
    reject("duplicate_participant", "duplicate_person", lambda: apportion(100, [("A", 1), ("A", 1)], "bad"), {"participants": ["A", "A"]})
    reject("zero_base_nonzero_charge", "zero_eligible_base", lambda: apportion(100, [("A", 0)], "bad"), {"sen": 100, "base": 0})
    assert apportion(0, [("A", 0)], "zero") == {"A": 0}
    record("zero_base_zero_charge", "experiment", {"sen": 0, "base": 0}, {"A": 0})

    items = {"foodA": {"A": 1000}, "foodB": {"B": 2000}, "drink": {"C": 1000}}
    tax = scoped_adjustment(180, ["foodA", "foodB"], items, "sst")
    assert tax == {"A": 60, "B": 120}
    record("scoped_printed_sst", "experiment_policy_variant", {"items": items, "eligible": ["foodA", "foodB"], "printed_sst_sen": 180}, tax)
    service = scoped_adjustment(300, ["foodA", "foodB"], items, "service")
    assert service == {"A": 100, "B": 200}
    record("service_excludes_drink", "experiment_policy_variant", {"items": items, "eligible": ["foodA", "foodB"], "printed_service_sen": 300}, service)
    discount = scoped_adjustment(-500, ["foodB"], items, "discount")
    assert discount == {"B": -500}
    record("item_discount_follows_consumers", "experiment_policy_variant", {"eligible": ["foodB"], "discount_sen": -500}, discount)
    reject("voucher_exceeds_base", "discount_exceeds_eligible_base", lambda: scoped_adjustment(-1001, ["foodA"], items, "bad"), {"base_sen": 1000, "discount_sen": -1001})
    allowed_credit = scoped_adjustment(-1001, ["foodA"], items, "explicit-credit", permit_credit=True)
    assert sum_components("A", [items["foodA"], allowed_credit]) == {"A": -1}
    record("discount_credit_policy_alternative", "experiment_policy_variant", {
        "base_sen": 1000, "discount_sen": -1001, "explicit_permit_credit": True}, {
        "adjustment_sen": allowed_credit, "resulting_consumption_sen": {"A": -1}})
    reject("invalid_eligibility", "unknown_scope_item", lambda: scoped_adjustment(10, ["missing"], items, "bad"), {"eligible": ["missing"]})

    tax_included = {"item_total_sen": 1060, "included_sst_memo_sen": 60, "added_sst_sen": 0, "receipt_total_sen": 1060}
    assert review_gate([{"A": 1060}], 1060, [], 1060)
    record("included_sst_not_double_added", "experiment_policy_variant", tax_included, {"A": 1060})
    reject("included_sst_double_count", "receipt_total_mismatch", lambda: review_gate([{"A": 1060}], 1060, [{"A": 60}], 1060), tax_included)
    # Visually reviewed historical Malaysian receipt: quantity/unit/line columns
    # and exclusive/inclusive totals coexist. Do not assume every printed
    # intermediate subtotal is on the same basis as the gross item lines.
    historical_items = [{"A": 280, "B": 280}, {"A": 20, "B": 20}]
    assert review_gate(historical_items, 600, [], 600)
    assert 2 * 280 == 560 and 2 * 20 == 40 and 566 + 34 == 600
    record("real_2018_wan_sheng_inclusive_gst", "experiment_real_receipt_arithmetic", {
        "image_id": "X51008030563", "date_printed": "02-04-2018",
        "image_sha256": "4ebb8257cd1bc9dafb5b40d8c48e8318260ce08fa19cb68dbd86499182412e7c",
        "milo": {"quantity": "2", "unit_sen": 280, "line_sen": 560},
        "takeaway": {"quantity": "2", "unit_sen": 20, "line_sen": 40},
        "printed_total_excluding_gst_sen": 566, "included_gst_sen": 34,
        "printed_total_inclusive_gst_sen": 600, "receipt_total_sen": 600}, {
        "canonical_gross_item_subtotal_sen": 600, "printed_net_subtotal_sen": 566,
        "additional_tax_sen": 0, "illustrative_equal_consumption_sen": {"A": 300, "B": 300},
        "not_a_current_sst_rate_claim": True})
    reject("real_receipt_wrong_subtotal_basis", "subtotal_mismatch", lambda: review_gate(historical_items, 566, [], 600), {
        "gross_item_sum_sen": 600, "wrongly_used_printed_net_subtotal_sen": 566})
    reject("real_receipt_quantity_double_count", "subtotal_mismatch", lambda: review_gate([{"A": 1120}, {"A": 80}], 600, [], 600), {
        "line_totals_sen": [560, 40], "wrongly_multiplied_by_quantity": 2})

    original = {"food": {"A": 2000, "B": 3000, "C": 5000}}
    merchant_discount = scoped_adjustment(-1000, ["food"], original, "merchant-voucher")
    discounted = sum_components("ABC", [original["food"], merchant_discount])
    assert discounted == {"A": 1800, "B": 2700, "C": 4500}
    tender_balances = balances(original["food"], {"A": 1000, "B": 9000})
    record("voucher_discount_vs_tender", "experiment_policy_comparison", {"items": original, "voucher_sen": 1000}, {
        "merchant_discount": {"consumption_sen": discounted, "receipt_total_sen": 9000},
        "prepaid_tender": {"consumption_sen": original["food"], "receipt_total_sen": 10000,
                           "payments_sen": {"A_voucher_owner": 1000, "B_cash": 9000}, "net_sen": tender_balances}})

    base = {"food": {"A": 1000, "B": 2000}}
    reduction = scoped_adjustment(-600, ["food"], base, "voucher")
    before = scoped_adjustment(300, ["food"], base, "service")
    # Printed fixed 300 is conserved even if the reviewed proportional base changes.
    after_items = {"food": sum_components("AB", [base["food"], reduction])}
    after = scoped_adjustment(300, ["food"], after_items, "service")
    assert before == after == {"A": 100, "B": 200}
    record("fixed_charge_vs_rate_order", "experiment_policy_comparison", {"base_sen": 3000, "discount_sen": -600,
           "printed_service_sen": 300, "illustrative_rate": "1/10"}, {
           "printed_fixed_service_allocation": before, "rate_before_discount_sen": 300,
           "rate_after_discount_sen": 240, "difference_sen": 60})
    targeted_discount = scoped_adjustment(-500, ["foodA"], items, "targeted-voucher")
    pre_discount_service = scoped_adjustment(300, ["foodA", "foodB"], items, "target-service")
    changed_base = {**items, "foodA": sum_components("A", [items["foodA"], targeted_discount])}
    post_discount_service = scoped_adjustment(300, ["foodA", "foodB"], changed_base, "target-service")
    assert pre_discount_service == {"A": 100, "B": 200}
    assert post_discount_service == {"A": 60, "B": 240}
    record("targeted_discount_changes_charge_base", "experiment_policy_comparison", {
        "food_sen": {"A": 1000, "B": 2000}, "A_discount_sen": -500, "fixed_service_sen": 300}, {
        "before_discount_base": pre_discount_service, "after_discount_base": post_discount_service})

    round_positive = apportion(2, [(p, 1) for p in "ABC"], "printed-rounding")
    round_negative = apportion(-2, [(p, 1) for p in "ABC"], "printed-rounding")
    assert sum(round_positive.values()) == 2 and round_negative == {p: -v for p, v in round_positive.items()}
    record("printed_rounding_signed_component", "experiment", {"positive_sen": 2, "negative_sen": -2}, {"positive": round_positive, "negative": round_negative})
    reject("receipt_mismatch_gate", "receipt_total_mismatch", lambda: review_gate([{"A": 1000}], 1000, [{"A": 60}], 1061), {"computed_sen": 1060, "receipt_sen": 1061})
    reject("subtotal_mismatch_gate", "subtotal_mismatch", lambda: review_gate([{"A": 1000}], 999, [], 1000), {"item_sum_sen": 1000, "reviewed_canonical_item_subtotal_sen": 999})
    draft = draft_reconciliation(1060, 600, 400)
    assert draft["diagnostic_discrepancy_sen"] == 60 and not draft["arithmetic_reconciled"]
    assert draft["receipt_total_sen"] == sum(draft[field] for field in (
        "assigned_sen", "unassigned_sen", "diagnostic_discrepancy_sen"))
    record("draft_assigned_unassigned_discrepancy", "experiment", {
        "receipt_total_sen": 1060, "assigned_sen": 600, "unassigned_sen": 400}, draft)
    complete_draft = draft_reconciliation(1060, 1060, 0)
    assert complete_draft["arithmetic_reconciled"]
    record("arithmetic_gate_requires_zero_unassigned_and_discrepancy", "experiment", {
        "receipt_total_sen": 1060, "assigned_sen": 1060, "unassigned_sen": 0}, complete_draft)
    reject("unit_vs_line_ambiguity_gate", "review_incomplete", lambda: review_gate([{"A": 700}], 700, [], 700, ["unit_or_line_unknown"]), {"quantity": "2", "printed_price_sen": 700, "alternatives_line_sen": [700, 1400]})
    record("unit_rounding_not_forced", "experiment_policy_variant", {"quantity": "3", "unit_sen": 333, "printed_line_sen": 1000}, {
        "unit_product_sen": 999, "canonical_reviewed_line_sen": 1000,
        "allocation_sen": apportion(1000, [(p, 1) for p in "ABC"], "rounded-unit-line")})

    owed = {"A": 2120, "B": 3180, "C": 5300}
    payments = {"A": 7000, "B": 3600}
    net = balances(owed, payments)
    assert net == {"A": 4880, "B": 420, "C": -5300}
    record("multiple_payers", "experiment", {"owed_sen": owed, "payments_sen": payments}, net)
    partial = ("t1", "C", "A", 2000, "confirmed")
    partial_net = balances(owed, payments, [partial])
    assert partial_net == {"A": 2880, "B": 420, "C": -3300}
    record("partial_settlement", "experiment", {"transfer": partial}, partial_net)
    proposed = suggestions(partial_net)
    assert balances(owed, payments, [partial] + proposed) == partial_net
    record("suggestions_have_no_confirmed_accounting_effect", "experiment", {"suggested": proposed}, partial_net)
    full = [partial] + simulate_confirmation(proposed)
    assert not any(balances(owed, payments, full).values())
    record("complete_settlement", "experiment", {"transfers": full}, balances(owed, payments, full))
    assert balances(owed, payments, [partial, partial]) == partial_net
    record("repeat_confirmation_idempotent", "experiment", {"transfers": [partial, partial]}, partial_net)
    reject("conflicting_transfer_identity", "conflicting_transfer_id", lambda: balances(owed, payments, [partial, ("t1", "C", "A", 2001, "confirmed")]), {"same_id_amounts_sen": [2000, 2001]})
    assert balances(owed, payments, [("pending", "C", "A", 2000, "pending")]) == net
    record("pending_transfer_no_accounting_effect", "experiment", {"amount_sen": 2000, "state": "pending"}, net)
    reject("unfunded_meal", "funding_mismatch", lambda: balances(owed, {"A": 7000}), {"owed_sen": 10600, "paid_sen": 7000})
    for name, action in (
        ("noninteger_consumption", lambda: balances({"A": Fraction(1, 2)}, {"A": Fraction(1, 2)})),
        ("boolean_payment", lambda: balances({"A": 1}, {"A": True})),
        ("boolean_item_review", lambda: review_gate([{"A": True}], 1, [], 1)),
        ("noninteger_adjustment_review", lambda: review_gate([{"A": 1}], 1, [{"A": Fraction(1, 2)}], 1)),
        ("noninteger_receipt_total", lambda: review_gate([{"A": 1}], 1, [], Fraction(1))),
        ("noninteger_scope_base", lambda: scoped_adjustment(1, ["food"], {"food": {"A": True}}, "bad")),
        ("boolean_suggestion_net", lambda: suggestions({"A": True, "B": -1})),
        ("noninteger_draft", lambda: draft_reconciliation(1, Fraction(1), 0)),
    ):
        reject(name, "money_must_be_integer_sen", action, {"malformed_money": name})
    reject("negative_restaurant_payment", "negative_amount_requires_explicit_mode", lambda: balances({"A": 100, "B": 0}, {"A": -1, "B": 101}), {"payments_sen": {"A": -1, "B": 101}})
    reject("unknown_restaurant_payer", "unknown_payer", lambda: balances({"A": 100}, {"X": 100}), {"payer": "X"})
    reject("invalid_participant_identity", "invalid_participant_id", lambda: apportion(100, [("", 1)], "bad"), {"person": ""})
    refund_net = balances({"A": -100, "B": 0}, {"B": -100}, refund_mode=True)
    assert refund_net == {"A": 100, "B": -100}
    record("explicit_refund_mode_arithmetic_only", "experiment_policy_variant", {
        "consumption_sen": {"A": -100, "B": 0}, "restaurant_refund_sen": {"B": -100}, "refund_mode": True}, refund_net)

    revised_owed = {"A": 2220, "B": 3080, "C": 5300}
    revised_net = balances(revised_owed, payments, full)
    assert revised_net == {"A": -100, "B": 100, "C": 0}
    record("correction_after_settled_preserves_transfers", "experiment_policy_variant", {
        "old_owed_sen": owed, "revised_owed_sen": revised_owed, "historical_transfers": full}, {
        "reopened_net_sen": revised_net, "new_suggestions": suggestions(revised_net)})
    reversal = ("reverse-t1", "A", "C", 2000, "confirmed")
    reversed_net = balances(owed, payments, full + [reversal])
    assert reversed_net == {"A": 2000, "B": 0, "C": -2000}
    record("mistaken_transfer_reversed_without_deletion", "experiment_policy_variant", {
        "original_transfer": partial, "compensating_transfer": reversal}, reversed_net)
    overpaid = balances({"A": 0, "B": 100}, {"A": 100}, [("overpaid", "B", "A", 101, "confirmed")])
    assert overpaid == {"A": -1, "B": 1}
    record("overpayment_requires_reverse_debt_or_policy", "experiment_policy_variant", {
        "owed_sen": {"A": 0, "B": 100}, "payments_sen": {"A": 100}, "B_to_A_sen": 101}, overpaid)

    joined = {**owed, "D": 0}
    assert balances(joined, payments, full) == {"A": 0, "B": 0, "C": 0, "D": 0}
    record("join_does_not_reallocate_history", "experiment_policy_variant", {"joining_person": "D", "historical_claim_sen": 0}, balances(joined, payments, full))
    reject("leave_with_consumption", "retain_person_with_history", lambda: remove_membership("C", owed, payments, full), {"person": "C", "owed_sen": 5300, "now_settled": True})
    reject("leave_with_payment_only", "retain_person_with_history", lambda: remove_membership("A", {"A": 0}, {"A": 100}, []), {"person": "A", "payment_sen": 100})
    assert remove_membership("D", joined, payments, full)
    record("unused_joiner_can_leave", "experiment_policy_variant", {"person": "D", "history": []}, {"allowed": True})

    zero = {"free": {"A": 0, "B": 0}}
    reject("fully_discounted_charge_requires_explicit_policy", "zero_eligible_base", lambda: scoped_adjustment(100, ["free"], zero, "fee"), {"charge_sen": 100, "remaining_base_sen": 0})
    explicit = apportion(100, [("A", 1), ("B", 1)], "explicit-fee-choice")
    assert explicit == {"A": 50, "B": 50}
    record("explicit_equal_zero_base_override", "experiment_policy_variant", {"charge_sen": 100, "human_selected_weights": {"A": 1, "B": 1}}, explicit)

    # Hamilton allocation conserves money but is not monotonic per person.
    paradox_weights = list(zip("ABCDEF", [1500, 1500, 900, 500, 500, 200]))
    allocation25 = apportion(25, paradox_weights, "paradox")
    allocation26 = apportion(26, paradox_weights, "paradox")
    assert allocation25["D"] == allocation25["E"] == 3
    assert allocation26["D"] == allocation26["E"] == 2
    record("largest_remainder_nonmonotonic_counterexample", "experiment_counterexample", {"weights": dict(paradox_weights), "amounts_sen": [25, 26]}, {"25_sen": allocation25, "26_sen": allocation26})

    rng = random.Random(seed)
    random_assertions = 0
    component_assertions = 0
    max_amount = 0
    for index in range(trials):
        people = ["P" + str(i) for i in range(rng.randint(1, 12))]
        pairs = [(person, Fraction(rng.randint(0, 10000), rng.randint(1, 10000))) for person in people]
        if not any(weight for _, weight in pairs):
            pairs[0] = (people[0], Fraction(1))
        amount = rng.randint(0, 10 ** (24 if index % 20 == 0 else 10))
        max_amount = max(max_amount, amount)
        component_id = "random-" + str(index)
        result = apportion(amount, pairs, component_id)
        assert sum(result.values()) == amount
        assert all(type(value) is int and value >= 0 for value in result.values())
        permuted = list(pairs)
        rng.shuffle(permuted)
        assert apportion(amount, permuted, component_id) == result
        assert apportion(-amount, pairs, component_id) == {person: -value for person, value in result.items()}
        total_weight = sum((weight for _, weight in pairs), Fraction(0))
        assert all(abs(Fraction(result[person]) - Fraction(amount) * weight / total_weight) < 1
                   for person, weight in pairs)
        assert all(result[person] == 0 for person, weight in pairs if weight == 0)
        pay_weights = [(person, rng.randint(0, 100)) for person in people]
        if not any(weight for _, weight in pay_weights):
            pay_weights[0] = (people[0], 1)
        paid = apportion(amount, pay_weights, "payments-" + str(index))
        net = balances(result, paid)
        assert sum(net.values()) == 0
        suggested = suggestions(net)
        transfers = simulate_confirmation(suggested)
        assert balances(result, paid, suggested) == net
        assert len(transfers) <= max(0, len(people) - 1)
        assert not any(balances(result, paid, transfers).values())
        assert sum(sum(transfer[3:4]) for transfer in transfers) == sum(value for value in net.values() if value > 0)
        random_assertions += 11

        # Multi-item scope and component order: all adjustments use a declared
        # original item base here; policy variants above compare changed bases.
        item_map = {}
        for item_index in range(rng.randint(1, 5)):
            item_amount = rng.randint(0, 100000)
            item_map["I" + str(item_index)] = apportion(item_amount, pairs, component_id + "-I" + str(item_index))
        subtotal = sum(sum(item.values()) for item in item_map.values())
        scope = sorted(rng.sample(list(item_map), rng.randint(1, len(item_map))))
        scope_base = sum(sum(item_map[item].values()) for item in scope)
        tax_amount = rng.randint(0, 10000) if scope_base else 0
        discount_amount = -rng.randint(0, scope_base)
        tax = scoped_adjustment(tax_amount, scope, item_map, component_id + "-tax")
        discount = scoped_adjustment(discount_amount, scope, item_map, component_id + "-discount")
        rounding_amount = rng.randint(-2, 2) if subtotal + tax_amount + discount_amount >= 2 else 0
        rounding_base = sum_components(people, list(item_map.values()) + [tax, discount])
        rounding = apportion(rounding_amount, list(rounding_base.items()), component_id + "-rounding")
        consumption = sum_components(people, list(item_map.values()) + [tax, discount, rounding])
        total = subtotal + tax_amount + discount_amount + rounding_amount
        assert sum(consumption.values()) == total
        assert sum(tax.values()) == tax_amount and sum(discount.values()) == discount_amount
        assert all(tax.get(person, 0) == discount.get(person, 0) == 0
                   for person in people if not any(item_map[item].get(person, 0) for item in scope))
        assert review_gate(list(item_map.values()), subtotal, [tax, discount, rounding], total)
        assert sum_components(people, [rounding, discount, tax] + list(reversed(list(item_map.values())))) == consumption
        funded = apportion(total, pay_weights, component_id + "-funded")
        component_net = balances(consumption, funded)
        assert sum(component_net.values()) == 0
        assert not any(balances(consumption, funded, simulate_confirmation(suggestions(component_net))).values())
        component_assertions += 7

    return {"format_version": 1, "scope": "disposable_domain_validation_not_production",
            "access_date": "2026-10-16", "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "python_version": sys.version.split()[0], "seed": seed,
            "money_unit": "integer_MYR_sen", "weights_and_quantities": "exact_rational",
            "concrete_case_count": len(cases), "concrete_cases": cases,
            "randomized": {"trials": trials, "assertions": random_assertions,
                           "multi_component_assertions": component_assertions,
                           "max_amount_sen_decimal_string": str(max_amount),
                           "invariants": ["amount_conserved", "integer_nonnegative_shares", "row_order_independent",
                               "signed_symmetry", "quota_error_below_one_sen", "zero_weights_get_zero",
                               "zero_sum_net", "at_most_n_minus_one_greedy_transfers", "complete_settlement",
                               "settlement_flow_matches_credit", "suggestions_have_no_accounting_effect", "multi_item_charge_conservation",
                               "scope_exclusions", "receipt_reconciliation", "fixed_component_order_independence",
                               "multi_component_funding_and_settlement"], "status": "PASS"}, "status": "PASS"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("results.json"))
    parser.add_argument("--seed", type=int, default=20261016)
    parser.add_argument("--trials", type=int, default=3000)
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be positive")
    output = run(args.seed, args.trials)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: output[key] for key in ("status", "script_sha256", "concrete_case_count", "randomized")}))
