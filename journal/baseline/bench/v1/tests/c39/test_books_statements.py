import random
from datetime import date, timedelta
from decimal import Decimal

import pytest

from books import Chart, Journal, Line, income_statement, trial_balance
from test_books_journal import chart, dr_cr, journal


def test_trial_balance_as_of():
    assert trial_balance(journal(), date(2026, 3, 31)) == (
        'TRIAL BALANCE as of 2026-03-31\n'
        '1000 Assets: 7450.00\n'
        '  1100 Cash: 6450.00\n'
        '  1200 Receivables: 1000.00\n'
        '2000 Liabilities: 2000.00\n'
        '  2100 Loans: 2000.00\n'
        '3000 Equity: 5000.00\n'
        '  3100 Capital: 5000.00\n'
        '4000 Revenue: 1200.00\n'
        '  4100 Sales: 1000.00\n'
        '  4200 Services: 200.00\n'
        '5000 Expenses: 750.00\n'
        '  5100 Rent: 600.00\n'
        '  5300 Supplies: 150.00\n'
        'Total debits: 8200.00\n'
        'Total credits: 8200.00\n')


def test_trial_balance_all_entries():
    text = trial_balance(journal())
    lines = text.splitlines()
    assert lines[0] == 'TRIAL BALANCE'
    assert '  1100 Cash: 6750.00' in lines
    assert '4000 Revenue: 1500.00' in lines
    assert lines[-2:] == ['Total debits: 8500.00', 'Total credits: 8500.00']
    assert text.endswith('\n')
    assert not any('Wages' in line for line in lines)


def test_trial_balance_before_any_entry():
    assert trial_balance(journal(), date(2025, 12, 31)) == (
        'TRIAL BALANCE as of 2025-12-31\nTotal debits: 0.00\nTotal credits: 0.00\n')


def test_negative_balance_is_printed_with_minus():
    j = Journal(chart())
    dr_cr(j, date(2026, 5, 1), 'Overdrawn rent', '5100', '1100', '99.50')
    assert trial_balance(j) == (
        'TRIAL BALANCE\n'
        '1000 Assets: -99.50\n'
        '  1100 Cash: -99.50\n'
        '5000 Expenses: 99.50\n'
        '  5100 Rent: 99.50\n'
        'Total debits: 99.50\n'
        'Total credits: 99.50\n')


def test_trial_balance_shows_parents_of_deep_accounts_only_when_active():
    c = Chart()
    c.add('1000', 'Assets', 'asset')
    c.add('1100', 'Bank', 'asset', '1000')
    c.add('1110', 'Current', 'asset', '1100')
    c.add('1120', 'Savings', 'asset', '1100')
    c.add('1900', 'Other', 'asset', '1000')
    c.add('3000', 'Equity', 'equity')
    j = Journal(c)
    dr_cr(j, date(2026, 1, 1), 'x', '1120', '3000', '12.34')
    assert trial_balance(j).splitlines()[1:5] == [
        '1000 Assets: 12.34', '  1100 Bank: 12.34', '    1120 Savings: 12.34',
        '3000 Equity: 12.34']


def test_income_statement_quarter():
    assert income_statement(journal(), date(2026, 1, 1), date(2026, 3, 31)) == (
        'INCOME STATEMENT 2026-01-01 to 2026-03-31\n'
        'Income\n'
        '4000 Revenue: 1200.00\n'
        '  4100 Sales: 1000.00\n'
        '  4200 Services: 200.00\n'
        'Total income: 1200.00\n'
        'Expenses\n'
        '5000 Expenses: 750.00\n'
        '  5100 Rent: 600.00\n'
        '  5300 Supplies: 150.00\n'
        'Total expenses: 750.00\n'
        'Net income: 450.00\n')


def test_income_statement_net_loss_and_no_income():
    assert income_statement(journal(), date(2026, 2, 1), date(2026, 2, 5)) == (
        'INCOME STATEMENT 2026-02-01 to 2026-02-05\n'
        'Income\n'
        'Total income: 0.00\n'
        'Expenses\n'
        '5000 Expenses: 600.00\n'
        '  5100 Rent: 600.00\n'
        'Total expenses: 600.00\n'
        'Net income: -600.00\n')


def test_income_statement_single_day_bounds_inclusive():
    text = income_statement(journal(), date(2026, 4, 2), date(2026, 4, 2))
    assert '  4100 Sales: 300.00\n' in text
    assert text.endswith('Net income: 300.00\n')


def test_income_statement_start_after_end():
    with pytest.raises(ValueError):
        income_statement(journal(), date(2026, 3, 1), date(2026, 2, 1))


def test_random_books_balance():
    rng = random.Random(39)
    j = Journal(chart())
    leaves = ['1100', '1200', '2100', '3100', '4100', '4200', '5100', '5200', '5300']
    day = date(2026, 1, 1)
    for _ in range(200):
        day += timedelta(days=rng.randrange(3))
        accounts = rng.sample(leaves, rng.randrange(2, 5))
        amounts = [Decimal(rng.randrange(1, 100000)) / 100 for _ in accounts[1:]]
        lines = [Line(a, debit=x) for a, x in zip(accounts[1:], amounts)]
        lines.append(Line(accounts[0], credit=sum(amounts)))
        rng.shuffle(lines)
        j.post(day, 'r', lines)
    text = trial_balance(j)
    debit_total = text.splitlines()[-2].split(': ')[1]
    credit_total = text.splitlines()[-1].split(': ')[1]
    assert debit_total == credit_total
    b = {code: j.balance(code) for code in ('1000', '2000', '3000', '4000', '5000')}
    assert b['1000'] + b['5000'] == b['2000'] + b['3000'] + b['4000']
    stmt = income_statement(j, date(2026, 1, 1), day)
    assert stmt.endswith(f"Net income: {b['4000'] - b['5000']:.2f}\n")
