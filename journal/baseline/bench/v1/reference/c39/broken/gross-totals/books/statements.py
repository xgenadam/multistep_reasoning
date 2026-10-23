"""Trial balance and income statement over the shared account-tree printer."""
from decimal import Decimal

from .accounts import AccountType

ZERO = Decimal(0)


def money(x: Decimal) -> str:
    return f'{x:.2f}'


def tree_lines(journal, start=None, end=None, types=None) -> tuple[list[str], dict]:
    """Account lines for the accounts with activity in the period, in walk order.

    Returns the lines and {root code: balance} for the shown roots.
    """
    lines, roots = [], {}
    for account, depth in journal.chart.walk():
        if types is not None and account.type not in types:
            continue
        if not journal.has_activity(account.code, start, end):
            continue
        bal = journal.balance(account.code, start, end)
        lines.append(f'{"  " * depth}{account.code} {account.name}: {money(bal)}')
        if depth == 0:
            roots[account.code] = bal
    return lines, roots


def trial_balance(journal, as_of=None) -> str:
    title = 'TRIAL BALANCE' if as_of is None else f'TRIAL BALANCE as of {as_of.isoformat()}'
    lines, _ = tree_lines(journal, end=as_of)
    debits = credits = ZERO
    for entry in journal.entries():
        if as_of is None or entry.day <= as_of:
            for line in entry.lines:
                debits += line.debit
                credits += line.credit
    out = [title, *lines, f'Total debits: {money(debits)}', f'Total credits: {money(credits)}']
    return ''.join(line + '\n' for line in out)


def income_statement(journal, start, end) -> str:
    if start > end:
        raise ValueError('start must not be after end')
    out = [f'INCOME STATEMENT {start.isoformat()} to {end.isoformat()}']
    totals = {}
    for heading, acc_type, label in (('Income', AccountType.INCOME, 'Total income'),
                                     ('Expenses', AccountType.EXPENSE, 'Total expenses')):
        lines, roots = tree_lines(journal, start, end, types={acc_type})
        totals[acc_type] = sum(roots.values(), ZERO)
        out += [heading, *lines, f'{label}: {money(totals[acc_type])}']
    net = totals[AccountType.INCOME] - totals[AccountType.EXPENSE]
    out.append(f'Net income: {money(net)}')
    return ''.join(line + '\n' for line in out)
