"""Disposable independent acceptance probes, not production source or its test suite.

Literal cases were prepared from the specification before reading implementation.
Run only against the frozen review snapshot; writes a dedicated review result.
"""
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tabwise.calculation import (Adjustment, CalculationError, Item, Meal, Share,
                                 Split, calculate, parse_money)


def split(mode="equal", pairs=(("A", 1), ("B", 1))):
    return Split(mode, tuple(Share(person, value) for person, value in pairs))


def meal(item=None, *, subtotal=None, total=None, adjustments=()):
    item = item or Item("item", 100, split())
    return Meal(("A", "B"), (item,), item.line_sen if subtotal is None else subtotal,
                item.line_sen if total is None else total, adjustments)


def amounts(values):
    return {value.participant_id: value.sen for value in values}


def final(value):
    return amounts(calculate(value).consumption)


def run():
    results = []

    def check(name, action):
        try:
            action()
            results.append({"case": name, "status": "PASS"})
        except Exception as error:
            results.append({"case": name, "status": "FAIL", "error": repr(error)})

    def equals(actual, expected):
        assert actual == expected, (actual, expected)

    def rejects(value):
        try:
            calculate(value)
        except CalculationError:
            return
        raise AssertionError("invalid calculation accepted")

    check("quantity_line_not_multiplied", lambda: equals(final(meal(Item("q", 1001,
          split("quantity", (("A", 1), ("B", 2))), 3))), {"A": 334, "B": 667}))
    check("weights_1001_literal", lambda: equals(final(meal(Item("w", 1001,
          split("weights", (("A", 1), ("B", 2)))))), {"A": 334, "B": 667}))
    check("tiny_tie_literal", lambda: equals(final(meal(Item("item", 1, split()))),
                                            {"A": 0, "B": 1}))
    tiny = meal(Item("item", 1, split()), total=0,
                adjustments=(Adjustment("discount", "discount", -1, ("item",)),))
    check("tiny_full_discount_rounded_base", lambda: equals(final(tiny), {"A": 0, "B": 0}))
    check("zero_item_valid", lambda: equals(final(meal(Item("zero", 0, split()))), {"A": 0, "B": 0}))
    check("zero_base_explicit_override", lambda: equals(final(meal(Item("zero", 0, split()), total=10,
          adjustments=(Adjustment("tax", "tax", 10, split=split()),))), {"A": 5, "B": 5}))
    included = replace(meal(Item("gross", 600, split("exact", (("A", 300), ("B", 300))))), included_tax_sen=34)
    check("included_tax_no_addition", lambda: equals(final(included), {"A": 300, "B": 300}))
    multi = meal(Item("food", 3001, split("exact", (("A", 1001), ("B", 2000)))), total=3365,
                 adjustments=tuple(Adjustment(name, kind, sen, ("food",)) for name, kind, sen in
                 (("discount", "discount", -101), ("tax", "tax", 174),
                  ("service", "service", 290), ("rounding", "rounding", 1))))
    check("multi_component_literal_final", lambda: equals(final(multi), {"A": 1122, "B": 2243}))

    def component_literals():
        actual = {source.source_id: amounts(source.shares) for source in calculate(multi).adjustments}
        equals(actual, {"discount": {"A": -34, "B": -67}, "tax": {"A": 58, "B": 116},
                        "service": {"A": 97, "B": 193}, "rounding": {"A": 0, "B": 1}})
    check("multi_component_literal_breakdown", component_literals)
    reordered = replace(multi, participants=tuple(reversed(multi.participants)),
                         adjustments=tuple(reversed(multi.adjustments)),
                         items=(replace(multi.items[0], split=split("exact", (("B", 2000), ("A", 1001)))),))
    check("registry_component_share_permutation", lambda: equals(calculate(reordered), calculate(multi)))
    people = tuple("ABCDEF")
    paradox_split = split("weights", tuple(zip(people, (1500, 1500, 900, 500, 500, 200))))
    for sen, literal in ((25, (7, 7, 4, 3, 3, 1)), (26, (8, 8, 5, 2, 2, 1))):
        value = Meal(people, (Item("paradox", sen, paradox_split),), sen, sen)
        check(f"nonmonotonic_literal_{sen}", lambda value=value, literal=literal: equals(final(value), dict(zip(people, literal))))

    # Invalid examples do not derive expected results from production helpers.
    items = (Item("a", 100, split("exact", (("A", 100), ("B", 0)))),
             Item("b", 100, split("exact", (("A", 0), ("B", 100)))))
    invalid = [
        ("overlapping_discounts_negative_person", Meal(("A", "B"), items, 200, 99,
          (Adjustment("d1", "discount", -100, ("a",)), Adjustment("d2", "discount", -1, ("a",))))),
        ("discount_exceeds_scope_with_other_item", Meal(("A", "B"), items, 200, 99,
          (Adjustment("d", "discount", -101, ("a",)),))),
        ("zero_scope_despite_other_consumption", Meal(("A", "B"),
          (Item("free", 0, split()), Item("paid", 100, split())), 100, 110,
          (Adjustment("tax", "tax", 10, ("free",)),))),
        ("scope_and_explicit", meal(total=110, adjustments=(Adjustment("tax", "tax", 10, ("item",), split()),))),
        ("empty_scope", meal(total=110, adjustments=(Adjustment("tax", "tax", 10, ()),))),
        ("foreign_scope", meal(total=110, adjustments=(Adjustment("tax", "tax", 10, ("missing",)),))),
        ("duplicate_scope", meal(total=110, adjustments=(Adjustment("tax", "tax", 10, ("item", "item")),))),
        ("negative_tax", meal(total=99, adjustments=(Adjustment("tax", "tax", -1, ("item",)),))),
        ("positive_discount", meal(total=101, adjustments=(Adjustment("discount", "discount", 1, ("item",)),))),
        ("unknown_kind", meal(total=101, adjustments=(Adjustment("x", "tip", 1, ("item",)),))),
        ("item_component_id_collision", meal(total=101, adjustments=(Adjustment("item", "tax", 1, ("item",)),))),
        ("quantity_adjustment", meal(total=101, adjustments=(Adjustment("tax", "tax", 1, split=split("quantity")),))),
        ("foreign_person", meal(Item("item", 100, split("weights", (("A", 1), ("X", 1)))))),
        ("duplicate_person", meal(Item("item", 100, split("weights", (("A", 1), ("A", 1)))))),
        ("negative_weight", meal(Item("item", 100, split("weights", (("A", -1), ("B", 2)))))),
        ("zero_weights", meal(Item("item", 100, split("weights", (("A", 0), ("B", 0)))))),
        ("zero_quantity", meal(Item("item", 100, split("quantity"), 0))),
        ("quantity_overclaim", meal(Item("item", 100, split("quantity"), 1))),
        ("percent_incomplete", meal(Item("item", 100, split("percent", (("A", 50), ("B", Fraction(4999, 100))))))),
        ("exact_one_sen_missing", meal(Item("item", 100, split("exact", (("A", 49), ("B", 50)))))),
        ("fraction_denominator_limit", meal(Item("item", 100, split("weights", (("A", Fraction(1, 1000001)), ("B", 1)))))),
        ("fraction_numerator_limit", meal(Item("item", 100, split("weights", (("A", 1000000001), ("B", 1)))))),
        ("one_sen_total_mismatch", meal(total=101)),
        ("canonical_subtotal_mismatch", meal(subtotal=99)),
        ("participant_list_not_tuple", replace(meal(), participants=["A", "B"])),
        ("duplicate_registry", replace(meal(), participants=("A", "A"))),
        ("malformed_id", replace(meal(), participants=(" A", "B"))),
        ("unicode_id", replace(meal(), participants=("Ａ", "B"))),
        ("overlong_id", replace(meal(), participants=("A" * 65, "B"))),
    ]
    for bad in (True, 1.0, None):
        invalid.append((f"money_type_{bad!r}", meal(Item("item", bad, split()), subtotal=100, total=100)))
        invalid.append((f"weight_type_{bad!r}", meal(Item("item", 100, split("weights", (("A", bad), ("B", 1)))))))
    for name, value in invalid:
        check(name, lambda value=value: rejects(value))

    for text, expected in (("12.30", 1230), ("12.3", 1230), ("0", 0), ("00012.3", 1230)):
        check(f"money_text_{text}", lambda text=text, expected=expected: equals(parse_money(text), expected))
    for text in ("-1", "+1", "1,000", "1e2", " 1", "1 ", "１２.３０", ".5", "1.", "1.005", "0" * 17, "10000000.01", True, 12.3):
        def reject_text(text=text):
            try:
                parse_money(text)
            except CalculationError:
                return
            raise AssertionError("invalid money text accepted")
        check(f"money_text_reject_{text!r}", reject_text)
    frozen = calculate(multi)
    def immutable_result():
        try:
            frozen.consumption = ()
        except (FrozenInstanceError, AttributeError):
            return
        raise AssertionError("result mutable")
    check("result_immutable", immutable_result)
    return {"scope": "independent disposable specification probes; no UI/auth/ledger claim",
            "source_sha256": hashlib.sha256((ROOT / "tabwise/calculation.py").read_bytes()).hexdigest(),
            "cases": results, "passed": sum(case["status"] == "PASS" for case in results),
            "failed": sum(case["status"] == "FAIL" for case in results)}


if __name__ == "__main__":
    result = run()
    Path(__file__).with_name("independent-probes.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
