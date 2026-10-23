from datetime import date
from decimal import Decimal

import pytest

from books import (Account, AccountType, Chart, Entry, Journal, LedgerRow, Line,
                   UnbalancedEntryError)


def chart():
    c = Chart()
    c.add('1000', 'Assets', AccountType.ASSET)
    c.add('1200', 'Receivables', 'asset', '1000')
    c.add('1100', 'Cash', 'asset', '1000')
    c.add('2000', 'Liabilities', 'liability')
    c.add('2100', 'Loans', 'liability', '2000')
    c.add('3000', 'Equity', 'equity')
    c.add('3100', 'Capital', 'equity', '3000')
    c.add('4000', 'Revenue', 'income')
    c.add('4100', 'Sales', 'income', '4000')
    c.add('4200', 'Services', 'income', '4000')
    c.add('5000', 'Expenses', 'expense')
    c.add('5100', 'Rent', 'expense', '5000')
    c.add('5200', 'Wages', 'expense', '5000')
    c.add('5300', 'Supplies', 'expense', '5000')
    return c


def dr_cr(j, day, memo, dr, cr, amount):
    return j.post(day, memo, [Line(dr, debit=amount), Line(cr, credit=amount)])


def journal():
    j = Journal(chart())
    dr_cr(j, date(2026, 1, 2), 'Owner investment', '1100', '3100', '5000')
    dr_cr(j, date(2026, 1, 15), 'Loan', '1100', '2100', 2000)
    dr_cr(j, date(2026, 2, 1), 'Rent', '5100', '1100', '600.00')
    dr_cr(j, date(2026, 2, 10), 'Sale', '1200', '4100', Decimal('1000'))
    dr_cr(j, date(2026, 3, 5), 'Consulting', '1100', '4200', '200')
    dr_cr(j, date(2026, 3, 20), 'Supplies', '5300', '1100', '100')
    dr_cr(j, date(2026, 4, 2), 'April sale', '1100', '4100', '300')
    dr_cr(j, date(2026, 1, 10), 'Petty cash', '5300', '1100', '50')  # posted late
    return j


def test_add_returns_account_and_accepts_type_strings():
    c = Chart()
    a = c.add('1000', 'Assets', 'asset')
    assert a == Account('1000', 'Assets', AccountType.ASSET, None)
    assert c.add('1100', 'Cash', AccountType.ASSET, '1000').parent == '1000'
    assert AccountType('expense') is AccountType.EXPENSE
    assert c.get('1100').type is AccountType.ASSET


@pytest.mark.parametrize('args', [
    ('', 'Bad', 'asset', None),
    ('1a0', 'Bad', 'asset', None),
    ('1000', 'Dup', 'asset', None),
    ('1300', 'Bad', 'assets', None),
    ('1300', 'Orphan', 'asset', '9999'),
    ('1300', 'Mixed', 'liability', '1000'),
])
def test_add_rejects_bad_accounts(args):
    c = Chart()
    c.add('1000', 'Assets', 'asset')
    with pytest.raises(ValueError):
        c.add(*args)


def test_tree_queries():
    c = chart()
    with pytest.raises(KeyError):
        c.get('9999')
    assert [a.code for a in c.children('1000')] == ['1100', '1200']
    assert [a.code for a in c.roots()] == ['1000', '2000', '3000', '4000', '5000']
    assert c.is_leaf('1100') and not c.is_leaf('1000')


def test_walk_is_depth_first_in_code_order():
    c = Chart()
    c.add('2000', 'B', 'asset')
    c.add('1000', 'A', 'asset')
    c.add('1500', 'A2', 'asset', '1000')
    c.add('1100', 'A1', 'asset', '1000')
    c.add('1110', 'A1a', 'asset', '1100')
    assert [(a.code, d) for a, d in c.walk()] == [
        ('1000', 0), ('1100', 1), ('1110', 2), ('1500', 1), ('2000', 0)]


def test_post_numbers_entries_and_converts_amounts():
    j = Journal(chart())
    e1 = dr_cr(j, date(2026, 1, 2), 'first', '1100', '3100', '10.50')
    e2 = j.post(date(2026, 1, 1), 'second', [Line('5100', debit=7), Line('1100', credit='3'),
                                            Line('2100', credit=Decimal('4.00'))])
    assert e1 == Entry(1, date(2026, 1, 2), 'first',
                       (Line('1100', Decimal('10.50'), Decimal(0)),
                        Line('3100', Decimal(0), Decimal('10.50'))))
    assert e2.number == 2 and e2.lines[0].debit == Decimal(7)
    assert all(isinstance(x, Decimal) for ln in e2.lines for x in (ln.debit, ln.credit))
    assert [e.number for e in j.entries()] == [1, 2]


@pytest.mark.parametrize('lines, error', [
    ([Line('1100', debit=5)], ValueError),
    ([Line('1100', debit=5), Line('9999', credit=5)], KeyError),
    ([Line('1000', debit=5), Line('3100', credit=5)], ValueError),
    ([Line('1100', debit=5.0), Line('3100', credit=5)], TypeError),
    ([Line('1100', debit='-5'), Line('3100', credit='-5')], ValueError),
    ([Line('1100', debit='1.005'), Line('3100', credit='1.005')], ValueError),
    ([Line('1100', debit=5, credit=5), Line('3100', credit=5), Line('3100', debit=5)], ValueError),
    ([Line('1100'), Line('3100', credit=0)], ValueError),
    ([Line('1100', debit='5.00'), Line('3100', credit='4.99')], UnbalancedEntryError),
])
def test_post_rejects_bad_entries_and_records_nothing(lines, error):
    j = Journal(chart())
    dr_cr(j, date(2026, 1, 1), 'ok', '1100', '3100', 1)
    with pytest.raises(error):
        j.post(date(2026, 1, 2), 'bad', lines)
    assert len(j.entries()) == 1
    assert dr_cr(j, date(2026, 1, 3), 'next', '1100', '3100', 1).number == 2


def test_unbalanced_error_is_a_value_error():
    assert issubclass(UnbalancedEntryError, ValueError)


def test_balances_on_normal_side_with_rollup():
    j = journal()
    assert j.balance('1100') == Decimal('6750')
    assert j.balance('1000') == Decimal('7750')
    assert j.balance('2100') == Decimal('2000')
    assert j.balance('4000') == Decimal('1500')
    assert j.balance('5000') == Decimal('750')
    assert j.balance('5200') == 0
    with pytest.raises(KeyError):
        j.balance('9999')


def test_balance_over_a_period():
    j = journal()
    assert j.balance('1100', end=date(2026, 1, 31)) == Decimal('6950')
    assert j.balance('1100', start=date(2026, 2, 1)) == Decimal('-200')
    assert j.balance('4100', date(2026, 2, 10), date(2026, 2, 10)) == Decimal('1000')
    assert j.balance('4000', date(2026, 1, 1), date(2026, 3, 31)) == Decimal('1200')


def test_ledger_orders_by_day_then_number_with_running_balance():
    rows = journal().ledger('1100')
    assert [r.number for r in rows] == [1, 8, 2, 3, 5, 6, 7]
    assert [r.balance for r in rows] == [Decimal(x) for x in
                                         ('5000', '4950', '6950', '6350', '6550', '6450', '6750')]
    assert rows[1] == LedgerRow(8, date(2026, 1, 10), 'Petty cash', Decimal(0), Decimal('50'),
                                Decimal('4950'))


def test_ledger_of_parent_includes_children_and_credit_side():
    j = journal()
    assert [(r.number, r.balance) for r in j.ledger('1000')][3:5] == [
        (3, Decimal('6350')), (4, Decimal('7350'))]
    assert [(r.number, r.balance) for r in j.ledger('4100')] == [
        (4, Decimal('1000')), (7, Decimal('1300'))]
    assert j.ledger('5200') == []
