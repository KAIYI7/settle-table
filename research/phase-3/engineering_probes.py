"""Independent public-interface review probes; no production/test mutation."""
import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tabwise.calculation import (Adjustment, CalculationError, Item, Meal, Share,
                                 Split, calculate, parse_money)


def main():
    checks = []

    def check(name, action):
        action()
        checks.append({'case':name,'passed':True})

    def reject(call, code):
        try:
            call()
        except CalculationError as exc:
            assert exc.code == code, (exc.code, code)
            assert type(exc.path) is str and exc.path
            return
        raise AssertionError(f'expected {code}')

    equal = Split('equal',(Share('A',1),Share('B',1)))
    base = Meal(('A','B'),(Item('tiny',1,equal),),1,1)

    def tiny_discounts():
        for index in range(20):
            item = replace(base.items[0],id=f'item-{index}')
            meal = replace(base,items=(item,),total_sen=0,
                           adjustments=(Adjustment(f'discount-{index}','discount',-1,eligible_item_ids=(item.id,)),))
            result = calculate(meal)
            assert [p.sen for p in result.consumption] == [0,0]
            assert sum(p.sen for p in result.items[0].shares) == 1
            assert sum(p.sen for p in result.adjustments[0].shares) == -1
    check('20_component_identity_variants_full_tiny_discount_never_creates_negative_sen',tiny_discounts)

    def signed_symmetry():
        item = Item('base',2000,Split('exact',(Share('A',1000),Share('B',1000))))
        outputs = []
        for amount in (-7,7):
            meal = Meal(('A','B'),(item,),2000,2000+amount,
                        adjustments=(Adjustment('round','rounding',amount,split=equal),))
            outputs.append(calculate(meal))
        assert tuple(p.sen for p in outputs[0].adjustments[0].shares) == tuple(-p.sen for p in outputs[1].adjustments[0].shares)
    check('signed_adjustment_exact_magnitude_symmetry',signed_symmetry)

    def zeros_do_not_receive_scoped_fee():
        people = tuple(f'P{i:02}' for i in range(100))
        item = Item('base',1,Split('exact',(Share('P99',1),)))
        meal = Meal(people,(item,),1,8,adjustments=(Adjustment('fee','service',7,eligible_item_ids=('base',)),))
        result = calculate(meal)
        assert all(p.sen == (8 if p.participant_id=='P99' else 0) for p in result.consumption)
    check('100_participants_zero_rounded_bases_cannot_receive_residual_fee',zeros_do_not_receive_scoped_fee)

    def bounded_maximums():
        people = tuple(f'P{i:02}' for i in range(100))
        ids = tuple(f'item-{i}' for i in range(500))
        items = tuple(Item(identity,1,Split('equal',(Share('P00',1),))) for identity in ids)
        changes = tuple(Adjustment(f'round-{i}','rounding',0,eligible_item_ids=ids) for i in range(100))
        result = calculate(Meal(people,items,500,500,adjustments=changes))
        assert (len(result.items),len(result.adjustments),len(result.consumption)) == (500,100,100)
        assert result.consumption[0].sen == 500
        assert sum(p.sen for p in result.consumption) == 500
    check('exact_documented_collection_maxima_are_supported',bounded_maximums)

    def numeric_maximums():
        split = Split('quantity',(Share('A',1000000),))
        result = calculate(Meal(('A',),(Item('max',1000000000,split,quantity=1000000),),1000000000,1000000000))
        assert result.consumption[0].sen == 1000000000
        assert parse_money('10000000.00') == 1000000000
        assert parse_money('0000000000000.01') == 1
        reject(lambda:parse_money('10000000.01'),'money_bound')
    check('documented_money_quantity_and_text_boundaries_are_exact',numeric_maximums)

    def exact_fractional_percent():
        split = Split('percent',tuple(Share(p,Fraction(100,3)) for p in ('A','B','C')))
        result = calculate(Meal(('A','B','C'),(Item('thirds',2,split),),2,2))
        assert sorted(p.sen for p in result.consumption) == [0,1,1]
    check('rational_percentages_sum_exactly_without_float_rounding',exact_fractional_percent)

    def overlapping_discounts():
        items = (Item('x',1,Split('exact',(Share('A',1),))),Item('y',1,Split('exact',(Share('B',1),))))
        adjustments = tuple(Adjustment(f'd{i}','discount',-1,eligible_item_ids=('x',)) for i in range(2))
        reject(lambda:calculate(Meal(('A','B'),items,2,0,adjustments=adjustments)),'negative_consumption')
    check('individually_valid_overlapping_discounts_reject_negative_final_consumption',overlapping_discounts)

    def discount_override_bound():
        changes=(Adjustment('fee','service',10,split=equal),Adjustment('discount','discount',-2,split=equal))
        reject(lambda:calculate(replace(base,total_sen=9,adjustments=changes)),'discount_over_base')
    check('positive_charge_cannot_hide_explicit_discount_above_subtotal',discount_override_bound)

    class TrapTuple(tuple):
        def __iter__(self):
            raise AssertionError('must reject before iterating tuple subclass')

    def shape_first():
        reject(lambda:calculate(replace(base,participants=TrapTuple(('A','B')))),'tuple_required')
        reject(lambda:calculate(replace(base,items=TrapTuple(base.items))),'tuple_required')
        reject(lambda:calculate(replace(base,adjustments=TrapTuple(()))),'tuple_required')
        altered = replace(base.items[0],split=Split('equal',TrapTuple(equal.shares)))
        reject(lambda:calculate(replace(base,items=(altered,))),'tuple_required')
    check('collection_subclasses_reject_before_custom_iteration',shape_first)

    def malformed_boundaries():
        for person in ('A\x00',' A','A ','A\n','é','a/b','a"b','x'*65):
            reject(lambda:calculate(replace(base,participants=(person,))),'invalid_id')
        reject(lambda:calculate(replace(base,included_tax_sen=True)),'money_type')
        for weight,code in ((True,'rational_type'),(1.0,'rational_type'),(Fraction(1,1000001),'rational_bound'),(10**20,'rational_bound')):
            bad = replace(base.items[0],split=Split('weights',(Share('A',weight),)))
            reject(lambda:calculate(replace(base,items=(bad,)) ),code)
    check('malformed_ids_and_rational_types_bounds_reject_structurally',malformed_boundaries)

    def deep_immutability():
        result=calculate(base)
        for obj,field,value in ((base.items[0].split.shares[0],'value',2),
                                (result.items[0].shares[0],'sen',10),
                                (result.items[0],'shares',[])):
            try:
                setattr(obj,field,value)
            except FrozenInstanceError:
                continue
            raise AssertionError('accepted facts/results must be frozen')
        mutable = replace(base.items[0],split=Split('equal',list(equal.shares)))
        reject(lambda:calculate(replace(base,items=(mutable,))),'tuple_required')
        assert calculate(base) == result
    check('accepted_nested_facts_results_are_frozen_and_mutable_shares_reject',deep_immutability)

    report={'scope':'independent public API engineering probes, not production test mutation',
            'passed':len(checks),'failed':0,'checks':checks,
            'module_sha256':hashlib.sha256((ROOT/'tabwise/calculation.py').read_bytes()).hexdigest(),
            'tests_sha256':hashlib.sha256((ROOT/'tests/test_calculation.py').read_bytes()).hexdigest()}
    (Path(__file__).with_name('engineering-probes.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':len(checks),'failed':0}))


if __name__=='__main__':
    main()
