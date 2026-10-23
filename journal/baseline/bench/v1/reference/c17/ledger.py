import csv
import datetime
import io
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re


class LedgerError(Exception):
    def __init__(self, message, line):
        super().__init__(f'line {line}: {message}')
        self.line = line


class OverdraftError(LedgerError):
    def __init__(self, line, account, balance):
        super().__init__(f'account {account!r} would go to {balance}', line)
        self.account = account
        self.balance = balance


@dataclass(frozen=True)
class Transaction:
    date: datetime.date
    account: str
    amount: Decimal
    line: int


_AMOUNT = re.compile(r'[+-]?(\d+(\.\d{0,2})?|\.\d{1,2})')
_DATE = re.compile(r'\d{4}-\d{2}-\d{2}')


def _parse_amount(raw, line):
    s = raw.strip()
    if not _AMOUNT.fullmatch(s):
        raise LedgerError(f'bad amount {raw!r}', line)
    try:
        return Decimal(s)
    except InvalidOperation:
        raise LedgerError(f'bad amount {raw!r}', line) from None


def _parse_date(raw, line):
    s = raw.strip()
    if not _DATE.fullmatch(s):
        raise LedgerError(f'bad date {raw!r}', line)
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        raise LedgerError(f'bad date {raw!r}', line) from None


def parse(text):
    reader = csv.reader(io.StringIO(text))
    header = None
    for row in reader:
        if row:
            header = [h.strip() for h in row]
            break
    if header is None:
        raise LedgerError('empty file', 1)
    header_line = reader.line_num
    cols = {}
    for name in ('date', 'account', 'amount'):
        if name not in header:
            raise LedgerError(f'missing column {name!r}', header_line)
        cols[name] = header.index(name)
    need = max(cols.values()) + 1
    out = []
    for row in reader:
        line = reader.line_num
        if not row or (len(row) == 1 and not row[0].strip()):
            continue
        if len(row) < need:
            raise LedgerError('too few fields', line)
        date = _parse_date(row[cols['date']], line)
        account = row[cols['account']].strip()
        if not account:
            raise LedgerError('empty account', line)
        amount = _parse_amount(row[cols['amount']], line)
        out.append(Transaction(date, account, amount, line))
    return out


def _apply(transactions, opening, limits):
    balances = {k: Decimal(v) for k, v in (opening or {}).items()}
    limits = limits or {}
    steps = []
    for t in sorted(transactions, key=lambda t: t.date):
        new = balances.get(t.account, Decimal('0')) + t.amount
        if new < -Decimal(limits.get(t.account, Decimal('0'))):
            raise OverdraftError(t.line, t.account, new)
        balances[t.account] = new
        steps.append((t, new))
    return steps, balances


def running_balances(transactions, opening=None, limits=None):
    return _apply(transactions, opening, limits)[0]


def final_balances(transactions, opening=None, limits=None):
    return _apply(transactions, opening, limits)[1]
