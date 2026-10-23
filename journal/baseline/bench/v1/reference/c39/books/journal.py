"""Journal entries that must balance, account balances and ledgers."""
import datetime
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import NamedTuple

ZERO = Decimal(0)


class UnbalancedEntryError(ValueError):
    """An entry whose debits and credits differ."""


def to_amount(x) -> Decimal:
    if isinstance(x, float):
        raise TypeError('amounts must not be floats')
    if isinstance(x, bool) or not isinstance(x, (Decimal, int, str)):
        raise TypeError(f'amount must be a Decimal, int or str, got {x!r}')
    try:
        amount = Decimal(x)
    except InvalidOperation:
        raise ValueError(f'invalid amount {x!r}') from None
    if not amount.is_finite() or amount < 0:
        raise ValueError(f'amount must be a non-negative number, got {x!r}')
    if amount != amount.quantize(Decimal('0.01')):
        raise ValueError(f'amount has more than two decimal places: {x!r}')
    return amount


@dataclass(frozen=True)
class Line:
    account: str
    debit: Decimal = ZERO
    credit: Decimal = ZERO


@dataclass(frozen=True)
class Entry:
    number: int
    day: datetime.date
    memo: str
    lines: tuple[Line, ...]


class LedgerRow(NamedTuple):
    number: int
    day: datetime.date
    memo: str
    debit: Decimal
    credit: Decimal
    balance: Decimal


def in_period(day, start=None, end=None) -> bool:
    return (start is None or start <= day) and (end is None or day <= end)


class Journal:
    def __init__(self, chart):
        self.chart = chart
        self._entries: list[Entry] = []

    def post(self, day, memo, lines) -> Entry:
        lines = list(lines)
        if len(lines) < 2:
            raise ValueError('an entry needs at least two lines')
        for line in lines:
            self.chart.get(line.account)
            if not self.chart.is_leaf(line.account):
                raise ValueError(f'account {line.account} has sub-accounts; post to a leaf')
        clean = []
        for line in lines:
            debit, credit = to_amount(line.debit), to_amount(line.credit)
            if (debit != 0) == (credit != 0):
                raise ValueError(f'line for {line.account} needs exactly one of debit or credit')
            clean.append(Line(line.account, debit, credit))
        debits = sum((ln.debit for ln in clean), ZERO)
        credits = sum((ln.credit for ln in clean), ZERO)
        if debits != credits:
            raise UnbalancedEntryError(f'debits {debits} != credits {credits}')
        entry = Entry(len(self._entries) + 1, day, memo, tuple(clean))
        self._entries.append(entry)
        return entry

    def entries(self) -> list[Entry]:
        return list(self._entries)

    def _signed(self, code, line: Line) -> Decimal:
        net = line.debit - line.credit
        return net if self.chart.get(code).type.debit_normal else -net

    def _lines(self, code, start=None, end=None):
        """(entry, index, line) for lines on the account or a descendant, by day then number."""
        codes = set(self.chart.subtree(code))
        found = []
        for entry in sorted(self._entries, key=lambda e: (e.day, e.number)):
            if not in_period(entry.day, start, end):
                continue
            for i, line in enumerate(entry.lines):
                if line.account in codes:
                    found.append((entry, i, line))
        return found

    def balance(self, code, start=None, end=None) -> Decimal:
        self.chart.get(code)
        return sum((self._signed(code, ln) for _, _, ln in self._lines(code, start, end)), ZERO)

    def has_activity(self, code, start=None, end=None) -> bool:
        return bool(self._lines(code, start, end))

    def own_net(self, code, start=None, end=None) -> Decimal:
        """Debits - credits of the account's own lines (no descendants)."""
        total = ZERO
        for entry in self._entries:
            if in_period(entry.day, start, end):
                for line in entry.lines:
                    if line.account == code:
                        total += line.debit - line.credit
        return total

    def ledger(self, code) -> list[LedgerRow]:
        self.chart.get(code)
        rows, running = [], ZERO
        for entry, _, line in self._lines(code):
            running += self._signed(code, line)
            rows.append(LedgerRow(entry.number, entry.day, entry.memo, line.debit, line.credit,
                                  running))
        return rows
