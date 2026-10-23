import datetime
from decimal import Decimal

import pytest

from ledger import (LedgerError, OverdraftError, Transaction, final_balances, parse,
                    running_balances)

D = Decimal

SAMPLE = """date,account,amount
2026-01-03,checking,100.00
2026-01-01,savings,250
2026-01-03,checking,-40.5
2026-01-02,checking,+3.25
"""


def test_parse_fields_and_file_order():
    txs = parse(SAMPLE)
    assert [t.line for t in txs] == [2, 3, 4, 5]
    t = txs[0]
    assert t == Transaction(datetime.date(2026, 1, 3), 'checking', D('100.00'), 2)
    assert isinstance(t.amount, Decimal)
    assert txs[3].amount == D('3.25')
    assert txs[2].amount == D('-40.5')


def test_transaction_is_frozen():
    t = parse(SAMPLE)[0]
    with pytest.raises(Exception):
        t.amount = D('1')


def test_header_any_order_extra_columns_and_spaces():
    text = 'memo,amount,date,account\nrent, -12.00 ,2026-02-01,  main \n'
    [t] = parse(text)
    assert (t.date, t.account, t.amount, t.line) == (datetime.date(2026, 2, 1), 'main', D('-12.00'), 2)


def test_quoted_field_with_comma():
    text = 'date,account,amount,memo\n2026-02-01,main,5,"coffee, beans"\n'
    assert parse(text)[0].amount == D('5')


def test_missing_column_is_line_one():
    with pytest.raises(LedgerError) as e:
        parse('date,amount\n2026-01-01,5\n')
    assert e.value.line == 1


def test_empty_text_is_line_one():
    with pytest.raises(LedgerError) as e:
        parse('')
    assert e.value.line == 1


@pytest.mark.parametrize('row', [
    '2026-13-01,a,5',      # bad month
    '01/02/2026,a,5',      # wrong date format
    '2026-01-01,a,1.234',  # three decimals
    '2026-01-01,a,abc',
    '2026-01-01,a,',
    '2026-01-01,  ,5',     # empty account
    '2026-01-01,a',        # too few fields
])
def test_bad_rows_raise_with_their_line(row):
    text = f'date,account,amount\n2026-01-01,a,1\n{row}\n'
    with pytest.raises(LedgerError) as e:
        parse(text)
    assert e.value.line == 3
    assert not isinstance(e.value, OverdraftError)


def test_blank_lines_skipped_but_counted():
    text = 'date,account,amount\n\n2026-01-01,a,1\n\n\n2026-01-02,a,x\n'
    with pytest.raises(LedgerError) as e:
        parse(text)
    assert e.value.line == 6
    txs = parse('date,account,amount\n\n2026-01-01,a,1\n\n2026-01-02,a,2\n')
    assert [t.line for t in txs] == [3, 5]


def test_running_balances_in_date_order_stable_within_a_day():
    steps = running_balances(parse(SAMPLE))
    assert [(t.line, bal) for t, bal in steps] == [
        (3, D('250')), (5, D('3.25')), (2, D('103.25')), (4, D('62.75'))]


def test_opening_balances_and_final():
    txs = parse(SAMPLE)
    final = final_balances(txs, opening={'checking': D('10'), 'cash': D('7')})
    assert final == {'checking': D('72.75'), 'savings': D('250'), 'cash': D('7')}


def test_overdraft_raises_with_offending_row():
    text = 'date,account,amount\n2026-01-02,a,-30\n2026-01-01,a,20\n2026-01-03,a,5\n'
    with pytest.raises(OverdraftError) as e:
        running_balances(parse(text))
    assert isinstance(e.value, LedgerError)
    assert e.value.line == 2
    assert e.value.account == 'a'
    assert e.value.balance == D('-10')


def test_limit_allows_exactly_minus_limit():
    text = 'date,account,amount\n2026-01-01,a,-50\n'
    steps = running_balances(parse(text), limits={'a': D('50')})
    assert steps[0][1] == D('-50')
    with pytest.raises(OverdraftError):
        running_balances(parse(text), limits={'a': D('49.99')})


def test_zero_balance_is_allowed_without_limit():
    text = 'date,account,amount\n2026-01-01,a,10\n2026-01-02,a,-10\n'
    assert final_balances(parse(text)) == {'a': D('0')}


def test_limit_applies_only_to_its_account():
    text = 'date,account,amount\n2026-01-01,a,-5\n2026-01-01,b,-5\n'
    with pytest.raises(OverdraftError) as e:
        final_balances(parse(text), limits={'a': D('10')})
    assert e.value.account == 'b'
    assert e.value.line == 3


def test_final_balances_checks_overdraft_too():
    text = 'date,account,amount\n2026-01-01,a,-1\n'
    with pytest.raises(OverdraftError):
        final_balances(parse(text))
