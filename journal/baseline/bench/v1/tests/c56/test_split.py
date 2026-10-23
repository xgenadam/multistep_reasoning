import random
from decimal import Decimal

import pytest

from split import (Equal, Exact, Expense, Group, Percent, Transfer, balances, format_amount,
                   format_balances, format_plan, load_group, parse_amount, settle)

EXAMPLE = {
    'members': ['ana', 'ben', 'cai'],
    'expenses': [
        {'description': 'Dinner', 'paid_by': 'ana', 'amount': '90.00', 'split': {'type': 'equal'}},
        {'description': 'Taxi', 'paid_by': 'ben', 'amount': '20',
         'split': {'type': 'equal', 'members': ['ben', 'cai']}},
        {'description': 'Hotel', 'paid_by': 'cai', 'amount': '300',
         'split': {'type': 'percent', 'shares': {'ana': '50', 'ben': '25', 'cai': '25'}}},
        {'description': 'Wine', 'paid_by': 'ana', 'amount': '30',
         'split': {'type': 'exact', 'shares': {'ben': '10', 'cai': '20.00'}}},
    ],
    'payments': [{'from': 'ben', 'to': 'ana', 'amount': '15'}],
}


# ---------------------------------------------------------------- amounts

def test_parse_amount():
    assert [parse_amount(s) for s in ['12', '12.5', '12.50', '0.05', '0']] == [
        1200, 1250, 1250, 5, 0]


@pytest.mark.parametrize('text', ['-1', '1.234', '.5', '5.', '1,5', '', 'ten', ' 5'])
def test_parse_amount_rejects(text):
    with pytest.raises(ValueError):
        parse_amount(text)


def test_format_amount():
    assert [format_amount(c) for c in [1250, 5, 0, -5, -1995, 100000]] == [
        '12.50', '0.05', '0.00', '-0.05', '-19.95', '1000.00']


# ---------------------------------------------------------------- shares

def test_equal_split_remainder_alphabetical():
    g = Group(['zoe', 'adam', 'mia'])
    shares = g.add_expense(Expense('pizza', 'zoe', 1000, Equal()))
    assert shares == {'zoe': 333, 'adam': 334, 'mia': 333}
    assert list(shares) == ['zoe', 'adam', 'mia']
    shares = g.add_expense(Expense('cab', 'mia', 1001, Equal(['zoe', 'mia'])))
    assert shares == {'zoe': 500, 'mia': 501}


def test_equal_none_means_members_at_that_time():
    g = Group(['a', 'b'])
    g.add_expense(Expense('x', 'a', 100, Equal()))
    g.add_member('c')
    g.add_expense(Expense('y', 'a', 300, Equal()))
    assert [shares for _, shares in g.expenses] == [{'a': 50, 'b': 50},
                                                    {'a': 100, 'b': 100, 'c': 100}]


def test_exact_split():
    g = Group(['a', 'b', 'c'])
    assert g.add_expense(Expense('x', 'a', 500, Exact({'c': 200, 'a': 300, 'b': 0}))) == {
        'a': 300, 'b': 0, 'c': 200}


def test_percent_largest_remainder():
    g = Group(['a', 'b', 'c'])
    # 1000 * 33.5% = 335, 1000 * 33.25% = 332.5, 1000 * 33.25% = 332.5 -> one cent left, tie b/c
    shares = g.add_expense(Expense('x', 'a', 1000, Percent({'a': '33.5', 'b': '33.25',
                                                             'c': Decimal('33.25')})))
    assert shares == {'a': 335, 'b': 333, 'c': 332}
    # 101 * 1/3 each in thirds: fractional parts .67 .67 .66 -> 34 34 33
    shares = g.add_expense(Expense('y', 'b', 101, Percent({'a': '33.34', 'b': '33.33',
                                                            'c': '33.33'})))
    assert shares == {'a': 34, 'b': 34, 'c': 33}
    assert g.add_expense(Expense('z', 'c', 999, Percent({'b': 60, 'c': 40}))) == {
        'b': 599, 'c': 400}


def test_shares_always_sum_to_amount():
    rng = random.Random(56)
    names = ['ana', 'ben', 'cai', 'dee', 'eli']
    g = Group(names)
    for _ in range(300):
        amount = rng.randrange(1, 100000)
        people = rng.sample(names, rng.randrange(1, 6))
        if rng.random() < 0.5:
            split = Equal(people)
        else:
            cuts = sorted(rng.sample(range(1, 10000), len(people) - 1))
            parts = [b - a for a, b in zip([0] + cuts, cuts + [10000])]
            split = Percent({p: Decimal(x) / 100 for p, x in zip(people, parts)})
        shares = g.add_expense(Expense('r', names[0], amount, split))
        assert sum(shares.values()) == amount
        assert set(shares) == set(people)


@pytest.mark.parametrize('expense', [
    Expense('x', 'zed', 100, Equal()),
    Expense('x', 'a', 0, Equal()),
    Expense('x', 'a', -5, Equal()),
    Expense('x', 'a', 100, Equal([])),
    Expense('x', 'a', 100, Equal(['a', 'a'])),
    Expense('x', 'a', 100, Equal(['a', 'zed'])),
    Expense('x', 'a', 100, Exact({'a': 60, 'b': 30})),
    Expense('x', 'a', 100, Exact({'a': 110, 'b': -10})),
    Expense('x', 'a', 100, Percent({'a': '50', 'b': '49.9'})),
    Expense('x', 'a', 100, Percent({'a': '110', 'b': '-10'})),
])
def test_expense_validation(expense):
    g = Group(['a', 'b'])
    with pytest.raises(ValueError):
        g.add_expense(expense)
    assert g.expenses == []


def test_group_and_payment_validation():
    with pytest.raises(ValueError):
        Group(['a', 'a'])
    with pytest.raises(ValueError):
        Group(['a', ''])
    g = Group(['a', 'b'])
    with pytest.raises(ValueError):
        g.add_member('b')
    for args in [('a', 'a', 5), ('a', 'zed', 5), ('a', 'b', 0)]:
        with pytest.raises(ValueError):
            g.add_payment(*args)
    g.add_payment('a', 'b', 5)
    assert g.payments == [('a', 'b', 5)]


# ---------------------------------------------------------------- balances

def test_example_balances():
    g = load_group(EXAMPLE)
    assert g.members == ['ana', 'ben', 'cai']
    assert len(g.expenses) == 4 and g.expenses[3][1] == {'ben': 1000, 'cai': 2000}
    bals = balances(g)
    assert bals == {'ana': -7500, 'ben': -9000, 'cai': 16500}
    assert list(bals) == ['ana', 'ben', 'cai']


def test_balances_alphabetical_and_zero_members():
    g = Group(['zed', 'amy', 'bob'])
    g.add_expense(Expense('x', 'zed', 600, Equal(['zed', 'amy'])))
    assert list(balances(g).items()) == [('amy', -300), ('bob', 0), ('zed', 300)]


def test_format_balances():
    assert format_balances({'cai': 0, 'ana': 1250, 'ben': -5}) == (
        'ana: +12.50\nben: -0.05\ncai: 0.00\n')


def test_load_group_errors_and_defaults():
    assert load_group({'members': ['a']}).expenses == []
    bad = dict(EXAMPLE, expenses=[{'description': 'x', 'paid_by': 'ana', 'amount': '1.234',
                                   'split': {'type': 'equal'}}])
    with pytest.raises(ValueError):
        load_group(bad)
    with pytest.raises(ValueError):
        load_group(dict(EXAMPLE, expenses=[dict(EXAMPLE['expenses'][0],
                                                split={'type': 'weird'})]))


# ---------------------------------------------------------------- settlement

def test_settle_example():
    plan = settle(balances(load_group(EXAMPLE)))
    assert plan == [Transfer('ben', 'cai', 9000), Transfer('ana', 'cai', 7500)]
    assert format_plan(plan) == 'ben pays cai 90.00\nana pays cai 75.00\n'


def test_settle_greedy_order_and_ties():
    bals = {'d': -500, 'a': 300, 'c': -500, 'b': 300, 'e': 400}
    assert settle(bals) == [Transfer('c', 'e', 400), Transfer('d', 'a', 300),
                            Transfer('d', 'b', 200), Transfer('c', 'b', 100)]
    assert bals == {'d': -500, 'a': 300, 'c': -500, 'b': 300, 'e': 400}


def test_settle_nothing_and_unbalanced():
    assert settle({'a': 0, 'b': 0}) == []
    assert format_plan([]) == 'All settled.\n'
    with pytest.raises(ValueError):
        settle({'a': 5, 'b': -4})


def test_paying_the_plan_settles_the_group():
    rng = random.Random(5656)
    names = ['p', 'q', 'r', 's']
    g = Group(names)
    for _ in range(40):
        g.add_expense(Expense('e', rng.choice(names), rng.randrange(1, 5000),
                              Equal(rng.sample(names, rng.randrange(1, 5)))))
    for t in settle(balances(g)):
        g.add_payment(t.payer, t.payee, t.amount)
    assert set(balances(g).values()) == {0}
