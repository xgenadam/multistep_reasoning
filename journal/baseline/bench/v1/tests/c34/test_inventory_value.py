import random
from datetime import date, timedelta
from decimal import Decimal

import pytest

from inventory import (InsufficientStockError, Item, Ledger, UnknownItemError, Valuation,
                       average, fifo, stock_report, valuate, valuation_report)


def d(day):
    return date(2026, 1, day)


@pytest.fixture
def lg():
    # B-1: 10 @ 2.00, 10 @ 3.00, issue 12, move 3 east->west, 4 @ 4.50 into west, issue 5 in west.
    # FIFO: cogs 10*2 + 2*3 = 26, then 5*3 = 15 -> 41; left 3 @ 3 + 4 @ 4.50 = 27.00.
    # Average: 50 for 20 -> issue 12 costs 30.00 (20.00 left for 8); + 18 -> 38 for 12;
    # issue 5 costs 38*5/12 = 15.833 -> 15.83; left 22.17 for 7; cogs 45.83.
    lg = Ledger()
    lg.add_item(Item('B-1', 'Bolt', 'bolts'))
    lg.add_item(Item('W-2', 'Widget', 'widgets'))
    lg.add_item(Item('N-3', 'Nut', 'bolts'))
    lg.receive(d(5), 'B-1', 'east', 10, '2.00')
    lg.receive(d(10), 'B-1', 'east', 10, '3.00')
    lg.receive(d(10), 'W-2', 'west', 10, '5.50')
    lg.issue(d(12), 'B-1', 'east', 12)
    lg.receive(d(12), 'N-3', 'east', 5, '0.10')
    lg.transfer(d(15), 'B-1', 'east', 'west', 3)
    lg.receive(d(20), 'B-1', 'west', 4, '4.50')
    lg.issue(d(25), 'B-1', 'west', 5)
    lg.issue(d(25), 'N-3', 'east', 5)
    return lg


def money(s):
    return Decimal(s)


def test_fifo_consumes_oldest_layers(lg):
    v = fifo(lg, 'B-1')
    assert v == Valuation(7, money('27.00'), money('41.00'))
    assert str(v.value) == '27.00'


def test_average_cost(lg):
    assert average(lg, 'B-1') == Valuation(7, money('22.17'), money('45.83'))


def test_valuation_as_of(lg):
    assert fifo(lg, 'B-1', as_of=d(12)) == Valuation(8, money('24.00'), money('26.00'))
    assert average(lg, 'B-1', as_of=d(12)) == Valuation(8, money('20.00'), money('30.00'))
    assert fifo(lg, 'B-1', as_of=d(4)) == Valuation(0, money('0.00'), money('0.00'))


def test_issuing_everything_leaves_zero(lg):
    assert average(lg, 'N-3') == Valuation(0, money('0.00'), money('0.50'))
    assert fifo(lg, 'N-3') == Valuation(0, money('0.00'), money('0.50'))


def test_average_issue_cost_rounds_half_up():
    lg = Ledger()
    lg.add_item(Item('A', 'a', 'c'))
    lg.receive(d(1), 'A', 'x', 1, '0.10')
    lg.receive(d(1), 'A', 'x', 1, '0.15')
    lg.issue(d(2), 'A', 'x', 1)  # 0.25 * 1 / 2 = 0.125 -> 0.13
    assert average(lg, 'A') == Valuation(1, money('0.12'), money('0.13'))
    lg.issue(d(3), 'A', 'x', 1)  # the rest costs exactly what is left
    assert average(lg, 'A') == Valuation(0, money('0.00'), money('0.25'))


def test_fifo_rounds_once_at_the_end():
    lg = Ledger()
    lg.add_item(Item('A', 'a', 'c'))
    lg.receive(d(1), 'A', 'x', 3, '0.333')
    lg.issue(d(2), 'A', 'x', 1)
    assert fifo(lg, 'A') == Valuation(2, money('0.67'), money('0.33'))


def test_transfer_changes_no_cost(lg):
    before = (fifo(lg, 'W-2'), average(lg, 'W-2'))
    lg.transfer(d(26), 'W-2', 'west', 'east', 4)
    assert (fifo(lg, 'W-2'), average(lg, 'W-2')) == before


def test_valuate_dispatch_and_errors(lg):
    assert valuate(lg, 'B-1') == fifo(lg, 'B-1')
    assert valuate(lg, 'B-1', 'average', as_of=d(12)) == average(lg, 'B-1', as_of=d(12))
    with pytest.raises(ValueError):
        valuate(lg, 'B-1', 'lifo')
    with pytest.raises(UnknownItemError):
        fifo(lg, 'Z-9')
    with pytest.raises(UnknownItemError):
        average(lg, 'Z-9')


def test_stock_report(lg):
    assert stock_report(lg) == (
        'location,sku,qty\n'
        'east,B-1,5\n'
        'east,TOTAL,5\n'
        'west,B-1,2\n'
        'west,W-2,10\n'
        'west,TOTAL,12\n'
        'TOTAL,,17\n')


def test_stock_report_as_of(lg):
    assert stock_report(lg, as_of=d(12)) == (
        'location,sku,qty\n'
        'east,B-1,8\n'
        'east,N-3,5\n'
        'east,TOTAL,13\n'
        'west,W-2,10\n'
        'west,TOTAL,10\n'
        'TOTAL,,23\n')


def test_stock_report_one_location(lg):
    assert stock_report(lg, location='west') == (
        'location,sku,qty\nwest,B-1,2\nwest,W-2,10\nwest,TOTAL,12\nTOTAL,,12\n')


def test_stock_report_empty(lg):
    assert stock_report(lg, location='south') == 'location,sku,qty\nTOTAL,,0\n'
    assert stock_report(Ledger()) == 'location,sku,qty\nTOTAL,,0\n'


def test_valuation_report_fifo(lg):
    assert valuation_report(lg) == (
        'category,sku,qty,value\n'
        'bolts,B-1,7,27.00\n'
        'bolts,TOTAL,7,27.00\n'
        'widgets,W-2,10,55.00\n'
        'widgets,TOTAL,10,55.00\n'
        'TOTAL,,17,82.00\n')


def test_valuation_report_average(lg):
    assert valuation_report(lg, method='average') == (
        'category,sku,qty,value\n'
        'bolts,B-1,7,22.17\n'
        'bolts,TOTAL,7,22.17\n'
        'widgets,W-2,10,55.00\n'
        'widgets,TOTAL,10,55.00\n'
        'TOTAL,,17,77.17\n')


def test_valuation_report_category_and_as_of(lg):
    assert valuation_report(lg, as_of=d(12), category='bolts') == (
        'category,sku,qty,value\n'
        'bolts,B-1,8,24.00\n'
        'bolts,N-3,5,0.50\n'
        'bolts,TOTAL,13,24.50\n'
        'TOTAL,,13,24.50\n')


def test_valuation_report_empty_and_bad_method(lg):
    assert valuation_report(Ledger()) == 'category,sku,qty,value\nTOTAL,,0,0.00\n'
    assert valuation_report(lg, category='nails') == 'category,sku,qty,value\nTOTAL,,0,0.00\n'
    with pytest.raises(ValueError):
        valuation_report(lg, method='lifo')


def _total(report, col):
    return report.splitlines()[-1].split(',')[col]


def test_random_history_is_consistent():
    rng = random.Random(34)
    lg = Ledger()
    skus = ['A', 'B', 'C']
    for s in skus:
        lg.add_item(Item(s, s, 'cat' + str(skus.index(s) % 2)))
    locs = ['l1', 'l2', 'l3']
    day = date(2026, 3, 1)
    received = {s: Decimal(0) for s in skus}
    for _ in range(300):
        day += timedelta(days=rng.randrange(2))
        s, loc = rng.choice(skus), rng.choice(locs)
        q = rng.randrange(1, 6)
        r = rng.random()
        if r < 0.45:
            cost = Decimal(rng.randrange(1, 2000)) / 100
            lg.receive(day, s, loc, q, cost)
            received[s] += q * cost
        elif r < 0.8:
            if lg.on_hand(s, loc) >= q:
                lg.issue(day, s, loc, q)
            else:
                with pytest.raises(InsufficientStockError):
                    lg.issue(day, s, loc, q)
        else:
            other = rng.choice([x for x in locs if x != loc])
            if lg.on_hand(s, loc) >= q:
                lg.transfer(day, s, loc, other, q)
    total = sum(lg.on_hand(s) for s in skus)
    assert int(_total(stock_report(lg), 2)) == total
    assert int(_total(valuation_report(lg), 2)) == total
    for s in skus:
        for v in (fifo(lg, s), average(lg, s)):
            assert v.qty == lg.on_hand(s)
            assert abs(v.value + v.cogs - received[s]) <= Decimal('0.01')
    fifo_total = sum(fifo(lg, s).value for s in skus)
    assert Decimal(_total(valuation_report(lg), 3)) == fifo_total
