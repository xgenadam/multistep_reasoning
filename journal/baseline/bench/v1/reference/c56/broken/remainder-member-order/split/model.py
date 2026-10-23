"""Groups, expenses and how each expense is shared."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal, InvalidOperation

_AMOUNT = re.compile(r'(\d+)(?:\.(\d{1,2}))?')


def parse_amount(text: str) -> int:
    m = _AMOUNT.fullmatch(text) if isinstance(text, str) else None
    if not m:
        raise ValueError(f'bad amount: {text!r}')
    return int(m.group(1)) * 100 + int((m.group(2) or '0').ljust(2, '0'))


def format_amount(cents: int) -> str:
    sign = '-' if cents < 0 else ''
    whole, part = divmod(abs(cents), 100)
    return f'{sign}{whole}.{part:02d}'


def _percent(value) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, str, Decimal)):
        raise ValueError(f'bad percentage: {value!r}')
    try:
        d = Decimal(value)
    except InvalidOperation:
        raise ValueError(f'bad percentage: {value!r}') from None
    if not d.is_finite() or d < 0:
        raise ValueError(f'bad percentage: {value!r}')
    return d


@dataclass(frozen=True)
class Equal:
    members: tuple | None = None


@dataclass(frozen=True)
class Exact:
    shares: dict


@dataclass(frozen=True)
class Percent:
    shares: dict


@dataclass(frozen=True)
class Expense:
    description: str
    paid_by: str
    amount: int
    split: object


class Group:
    def __init__(self, members):
        self.members: list[str] = []
        self.expenses: list[tuple[Expense, dict]] = []
        self.payments: list[tuple[str, str, int]] = []
        for name in members:
            self.add_member(name)

    def add_member(self, name: str) -> None:
        if not isinstance(name, str) or not name or name in self.members:
            raise ValueError(f'bad or repeated member: {name!r}')
        self.members.append(name)

    def _member(self, name) -> str:
        if name not in self.members:
            raise ValueError(f'{name!r} is not a member')
        return name

    def _ordered(self, raw: dict) -> dict:
        return {m: raw[m] for m in self.members if m in raw}

    def shares(self, expense: Expense) -> dict:
        amount, split = expense.amount, expense.split
        if isinstance(split, Equal):
            people = list(self.members if split.members is None else split.members)
            if not people or len(set(people)) != len(people):
                raise ValueError('an equal split needs distinct members')
            for p in people:
                self._member(p)
            base, extra = divmod(amount, len(people))
            lucky = set(people[:extra])
            return self._ordered({p: base + (p in lucky) for p in people})
        if isinstance(split, Exact):
            for p, cents in split.shares.items():
                self._member(p)
                if not isinstance(cents, int) or isinstance(cents, bool) or cents < 0:
                    raise ValueError(f'bad share for {p!r}')
            if sum(split.shares.values()) != amount:
                raise ValueError('exact shares do not add up to the amount')
            return self._ordered(dict(split.shares))
        if isinstance(split, Percent):
            pcts = {self._member(p): _percent(v) for p, v in split.shares.items()}
            if not pcts or sum(pcts.values()) != 100:
                raise ValueError('percentages must add up to 100')
            exact = {p: Decimal(amount) * pct / 100 for p, pct in pcts.items()}
            floors = {p: int(v.to_integral_value(rounding=ROUND_FLOOR)) for p, v in exact.items()}
            missing = amount - sum(floors.values())
            order = sorted(pcts, key=lambda p: (-(exact[p] - floors[p]), p))
            for p in order[:missing]:
                floors[p] += 1
            return self._ordered(floors)
        raise ValueError(f'unknown split: {split!r}')

    def add_expense(self, expense: Expense) -> dict:
        self._member(expense.paid_by)
        if not isinstance(expense.amount, int) or isinstance(expense.amount, bool) \
                or expense.amount <= 0:
            raise ValueError('amount must be a positive number of cents')
        shares = self.shares(expense)
        self.expenses.append((expense, shares))
        return dict(shares)

    def add_payment(self, payer: str, payee: str, amount: int) -> None:
        self._member(payer)
        self._member(payee)
        if payer == payee:
            raise ValueError('a payment needs two different people')
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise ValueError('amount must be positive')
        self.payments.append((payer, payee, amount))


def _split_from(spec: dict):
    kind = spec.get('type')
    if kind == 'equal':
        members = spec.get('members')
        return Equal(tuple(members) if members is not None else None)
    if kind == 'exact':
        return Exact({p: parse_amount(v) for p, v in spec['shares'].items()})
    if kind == 'percent':
        return Percent({p: _percent(v) for p, v in spec['shares'].items()})
    raise ValueError(f'unknown split type: {kind!r}')


def load_group(data: dict) -> Group:
    try:
        group = Group(data['members'])
        for e in data.get('expenses', []):
            group.add_expense(Expense(e['description'], e['paid_by'], parse_amount(e['amount']),
                                      _split_from(e['split'])))
        for p in data.get('payments', []):
            group.add_payment(p['from'], p['to'], parse_amount(p['amount']))
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f'bad group data: {exc}') from exc
    return group
