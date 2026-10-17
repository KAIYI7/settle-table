"""Public financial seams; expected amounts are independent specification literals."""
import unittest
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
import tabwise.calculation as financial

from tabwise.calculation import Meal, Item, Split, Share, calculate


class CalculationTests(unittest.TestCase):
    def test_all_registry_orders_and_strict_fact_shapes_are_checked(self):
        first = Item("x", 100, Split("exact", (Share("A", 100),)))
        second = Item("y", 200, Split("exact", (Share("B", 200),)))
        meal = Meal(("A", "B"), (second, first), 300, 300)
        self.assertEqual(calculate(meal), calculate(replace(meal, items=(first, second), participants=("B", "A"))))
        self.assertEqual(tuple(a.source_id for a in calculate(meal).items), ("x", "y"))
        malformed = (
            (replace(meal, participants=()), "collection_bound"),
            (replace(meal, items=()), "collection_bound"),
            (replace(meal, items=(first, first)), "duplicate_id"),
            (replace(meal, items=({"id": "x"},)), "fact_type"),
            (replace(meal, items=(replace(first, split=None), second)), "fact_type"),
            (replace(meal, items=(replace(first, split=Split("equal", ())), second)), "collection_bound"),
            (replace(meal, items=(replace(first, split=Split("equal", (None,))), second)), "fact_type"),
            (replace(meal, items=(replace(first, id=".x"), second)), "invalid_id"),
            (replace(meal, items=(replace(first, quantity=1000001), second)), "quantity_bound"),
            (replace(meal, items=(replace(first, split=Split("weights", (Share("A", 1000000001),))), second)), "rational_bound"),
            (replace(meal, adjustments=(None,)), "fact_type"),
        )
        for bad, code in malformed:
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, code):
                calculate(bad)
        for amount in (None, float("nan"), float("inf"), "100", False):
            with self.subTest(amount=amount), self.assertRaisesRegex(ValueError, "money_type"):
                calculate(replace(meal, subtotal_sen=amount))
        with self.assertRaises(financial.CalculationError) as caught:
            calculate({"reviewed": True})
        self.assertEqual((caught.exception.code, caught.exception.path), ("fact_type", "meal"))

    def test_tie_contract_negative_sign_and_input_order_are_stable(self):
        # SHA256 ASCII JSON ['tabwise-apportion-v1','tiny',ID] ranks B (24f2...) before A (2cf0...).
        item = Item("tiny", 1, Split("equal", (Share("A", 1), Share("B", 1))))
        meal = Meal(("A", "B"), (item,), 1, 1)
        result = calculate(meal)
        self.assertEqual(tuple(p.sen for p in result.consumption), (0, 1))
        shuffled = replace(meal, participants=("B", "A"), items=(replace(item, split=Split("equal", (Share("B", 1), Share("A", 1)))),))
        self.assertEqual(calculate(shuffled), result)
        base = Item("base", 2, Split("exact", (Share("A", 1), Share("B", 1))))
        for amount, expected in ((1, (1, 2)), (-1, (1, 0))):
            adjusted = Meal(("A", "B"), (base,), 2, 2 + amount,
                            adjustments=(financial.Adjustment("tiny", "rounding", amount, split=item.split),))
            with self.subTest(amount=amount):
                self.assertEqual(tuple(p.sen for p in calculate(adjusted).consumption), expected)

    def test_largest_remainder_does_not_promise_monotonic_individual_shares(self):
        people = ("A", "B", "C", "D", "E", "F")
        split = Split("weights", tuple(Share(p, w) for p, w in zip(people, (1500, 1500, 900, 500, 500, 200))))
        for amount, expected in ((25, (7, 7, 4, 3, 3, 1)), (26, (8, 8, 5, 2, 2, 1))):
            with self.subTest(amount=amount):
                result = calculate(Meal(people, (Item("dish", amount, split),), amount, amount))
                self.assertEqual(tuple(p.sen for p in result.consumption), expected)

    def test_zero_value_and_fractional_quantity_keep_valid_assignment_rules(self):
        zero = Meal(("A", "B"), (Item("free", 0, Split("weights", (Share("A", 0), Share("B", 0)))),), 0, 0)
        self.assertEqual(tuple(p.sen for p in calculate(zero).consumption), (0, 0))
        with self.assertRaisesRegex(ValueError, "zero_base"):
            calculate(replace(zero, total_sen=1, adjustments=(financial.Adjustment("tax", "tax", 1, eligible_item_ids=("free",)),)))
        explicit = replace(zero, total_sen=1, adjustments=(financial.Adjustment("tax", "tax", 1, split=Split("equal", (Share("A", 1),))),))
        self.assertEqual(tuple(p.sen for p in calculate(explicit).consumption), (1, 0))
        fractional = Meal(("A", "B"), (Item("dish", 1001, Split("quantity", (Share("A", Fraction(1, 2)), Share("B", 1))), quantity=Fraction(3, 2)),), 1001, 1001)
        self.assertEqual(tuple(p.sen for p in calculate(fractional).consumption), (334, 667))

    def test_facts_and_results_are_immutable_and_have_no_review_authority_flag(self):
        meal = Meal(("A",), (Item("dish", 10, Split("equal", (Share("A", 1),))),), 10, 10)
        result = calculate(meal)
        with self.assertRaises(FrozenInstanceError):
            meal.total_sen = 20
        with self.assertRaises(FrozenInstanceError):
            result.consumption[0].sen = 20
        self.assertIs(type(result.items), tuple)
        self.assertEqual(calculate(meal), result)
        with self.assertRaises(TypeError):
            Meal(("A",), meal.items, 10, 10, human_reviewed=True)

    def test_adjustment_scope_sign_and_discount_limits_reject(self):
        valid = Meal(("A",), (Item("dish", 10, Split("equal", (Share("A", 1),))),), 10, 10)
        change = financial.Adjustment("fee", "tax", 0, eligible_item_ids=("dish",))
        for adjustment, code in (
            (replace(change, id="dish"), "duplicate_id"),
            (replace(change, eligible_item_ids=()), "collection_bound"),
            (replace(change, eligible_item_ids=["dish"]), "tuple_required"),
            (replace(change, eligible_item_ids=("missing",)), "foreign_item"),
            (replace(change, eligible_item_ids=("dish", "dish")), "duplicate_scope"),
            (replace(change, eligible_item_ids=None), "adjustment_scope_or_split"),
            (replace(change, split=Split("equal", (Share("A", 1),))), "adjustment_scope_or_split"),
            (replace(change, kind="voucher"), "adjustment_kind"),
            (replace(change, kind="service", amount_sen=-1), "adjustment_sign"),
            (replace(change, kind="discount", amount_sen=1), "adjustment_sign"),
            (replace(change, kind="discount", amount_sen=-11), "discount_over_base"),
            (replace(change, kind="discount", amount_sen=-11, eligible_item_ids=None, split=Split("equal", (Share("A", 1),))), "discount_over_base"),
            (replace(change, eligible_item_ids=None, split=Split("quantity", (Share("A", 1),))), "quantity_items_only"),
            (replace(change, amount_sen=True), "money_type"),
        ):
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, code):
                calculate(replace(valid, adjustments=(adjustment,)))
        for adjustments, code in (((change,) * 101, "collection_bound"), ((change, change), "duplicate_id"), ([change], "tuple_required")):
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, code):
                calculate(replace(valid, adjustments=adjustments))

    def test_decimal_money_parser_never_roundtrips_a_float(self):
        parser = financial.parse_money
        for text, sen in (("12.30", 1230), ("0.1", 10), ("00012", 1200), ("0", 0), ("10000000.00", 1000000000)):
            with self.subTest(text=text):
                self.assertEqual(parser(text), sen)
                self.assertIs(type(parser(text)), int)
        for text in (True, 12.3, None, "", "12.", ".30", "1.234", "-1", "+1", "1,000", "1e2", " 1", "1\n", "１２.３０", "0" * 17, "10000000.01"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parser(text)

    def test_total_reconciliation_and_negative_consumption_are_hard_gates(self):
        valid = Meal(("A",), (Item("dish", 600, Split("exact", (Share("A", 600),))),), 600, 600, included_tax_sen=34)
        self.assertEqual(calculate(valid).consumption[0].sen, 600)  # Gross600/net566/tax34; never 634.
        for meal, code in (
            (replace(valid, total_sen=601), "receipt_total_mismatch"),
            (replace(valid, subtotal_sen=599, total_sen=599), "subtotal_mismatch"),
            (Meal(("A",), (Item("x", 600000000, Split("equal", (Share("A", 1),))),
                            Item("y", 600000000, Split("equal", (Share("A", 1),)))), 1000000000, 1000000000), "aggregate_bound"),
            (Meal(("A", "B"), (Item("x", 100, Split("exact", (Share("A", 1), Share("B", 99)))),), 100, 98,
                  adjustments=(financial.Adjustment("discount", "discount", -2, split=Split("exact", (Share("A", 2),))),)), "negative_consumption"),
        ):
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, code):
                calculate(meal)

    def test_full_one_sen_discount_uses_rounded_item_shares(self):
        meal = Meal(("A", "B"), (Item("tiny", 1, Split("exact", (Share("A", 1), Share("B", 0)))),), 1, 0,
                    adjustments=(financial.Adjustment("free", "discount", -1, eligible_item_ids=("tiny",)),))
        result = calculate(meal)
        self.assertEqual(tuple(p.sen for p in result.consumption), (0, 0))
        self.assertEqual(tuple(p.sen for p in result.adjustments[0].shares), (-1, 0))

    def test_receipt_adjustments_conserve_3365_sen(self):
        adjustment = financial.Adjustment
        item = Item("dish", 3001, Split("exact", (Share("A", 1501), Share("B", 1500))))
        changes = (
            adjustment("discount", "discount", -101, eligible_item_ids=("dish",)),
            adjustment("sst", "tax", 174, eligible_item_ids=("dish",)),
            adjustment("service", "service", 290, eligible_item_ids=("dish",)),
            adjustment("round", "rounding", 1, split=Split("exact", (Share("A", 1),))),
        )
        meal = Meal(("A", "B"), (item,), 3001, 3365, adjustments=changes)
        result = calculate(meal)
        self.assertEqual(tuple((p.participant_id, p.sen) for p in result.consumption), (("A", 1683), ("B", 1682)))
        self.assertEqual(tuple((a.source_id, tuple(p.sen for p in a.shares)) for a in result.adjustments),
                         (("discount", (-51, -50)), ("round", (1,)), ("service", (145, 145)), ("sst", (87, 87))))
        self.assertEqual(calculate(replace(meal, adjustments=tuple(reversed(changes)), participants=("B", "A"))), result)

    def test_each_split_mode_has_its_own_conservation_rule(self):
        valid = Meal(("A", "B"), (Item("dish", 1000, Split("equal", (Share("A", 1), Share("B", 1)))),), 1000, 1000)
        for mode, shares, expected in (
            ("equal", (Share("A", 1), Share("B", 1)), (("A", 500), ("B", 500))),
            ("weights", (Share("A", 1), Share("B", 3)), (("A", 250), ("B", 750))),
            ("percent", (Share("A", 25), Share("B", 75)), (("A", 250), ("B", 750))),
            ("exact", (Share("A", 333), Share("B", 667)), (("A", 333), ("B", 667))),
        ):
            meal = replace(valid, items=(replace(valid.items[0], split=Split(mode, shares)),))
            with self.subTest(mode=mode):
                self.assertEqual(tuple((p.participant_id, p.sen) for p in calculate(meal).consumption), expected)
        for split, code in (
            (Split("percent", (Share("A", 25), Share("B", 70))), "percent_sum"),
            (Split("exact", (Share("A", 999),)), "exact_sum"),
            (Split("exact", (Share("A", Fraction(1000, 1)),)), "money_type"),
            (Split("equal", (Share("A", 2),)), "equal_weight"),
            (Split("weights", (Share("A", -1), Share("B", 2))), "negative_weight"),
            (Split("weights", (Share("A", 0),)), "zero_base"),
            (Split("weights", (Share("A", 1.0),)), "rational_type"),
            (Split("equal", (Share("A", True),)), "rational_type"),
            (Split("equal", (Share("A", 1), Share("A", 1))), "duplicate_participant"),
            (Split("equal", (Share("C", 1),)), "foreign_participant"),
            (Split("equal", [Share("A", 1)]), "tuple_required"),
            (Split("mystery", (Share("A", 1),)), "split_mode"),
        ):
            meal = replace(valid, items=(replace(valid.items[0], split=split),))
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, code):
                calculate(meal)

    def test_malformed_identity_collection_quantity_and_bound_reject(self):
        valid = Meal(("A",), (Item("dish", 10, Split("equal", (Share("A", 1),))),), 10, 10)
        cases = (
            (replace(valid, participants=["A"]), "tuple_required"),
            (replace(valid, participants=("A", "A")), "duplicate_id"),
            (replace(valid, participants=("Ａ",)), "invalid_id"),
            (replace(valid, participants=("x" * 65,)), "invalid_id"),
            (replace(valid, participants=tuple(f"P{i}" for i in range(101))), "collection_bound"),
            (replace(valid, items=valid.items * 501), "collection_bound"),
            (replace(valid, items=(replace(valid.items[0], quantity=True),)), "rational_type"),
            (replace(valid, items=(replace(valid.items[0], quantity=0),)), "quantity_bound"),
            (replace(valid, items=(replace(valid.items[0], quantity=Fraction(1, 1000001)),)), "rational_bound"),
            (replace(valid, items=(replace(valid.items[0], line_sen=1.0),)), "money_type"),
            (replace(valid, total_sen=1000000001), "money_bound"),
        )
        for meal, code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, code):
                calculate(meal)

    def test_boolean_is_not_money(self):
        with self.assertRaisesRegex(ValueError, "money_type"):
            calculate(Meal(("A",), (Item("dish", True, Split("equal", (Share("A", 1),))),), 1, 1))

    def test_quantity_assignment_must_conserve_explicit_quantity(self):
        meal = Meal(("A", "B"), (Item("dish", 1001, Split("quantity", (
            Share("A", 1), Share("B", 1))), quantity=3),), 1001, 1001)
        with self.assertRaisesRegex(ValueError, "quantity_sum"):
            calculate(meal)

    def test_quantity_line_total_is_apportioned_once(self):
        meal = Meal(("A", "B"), (Item("dish", 1001, Split("quantity", (
            Share("A", 1), Share("B", 2))), quantity=3),), 1001, 1001)
        result = calculate(meal)
        self.assertEqual(tuple((p.participant_id, p.sen) for p in result.consumption),
                         (("A", 334), ("B", 667)))


if __name__ == "__main__":
    unittest.main()
