"""Greedy settlement: largest creditor and largest debtor first."""

from __future__ import annotations

from typing import NamedTuple

from .model import format_amount


class Transfer(NamedTuple):
    payer: str
    payee: str
    amount: int


def settle(bals: dict) -> list[Transfer]:
    if sum(bals.values()) != 0:
        raise ValueError('balances do not add up to zero')
    left = dict(bals)
    plan = []
    while any(left.values()):
        creditor = max((n for n in left if left[n] > 0), key=lambda n: left[n])
        debtor = min((n for n in left if left[n] < 0), key=lambda n: left[n])
        amount = min(left[creditor], -left[debtor])
        plan.append(Transfer(debtor, creditor, amount))
        left[creditor] -= amount
        left[debtor] += amount
    return plan


def format_plan(transfers) -> str:
    if not transfers:
        return 'All settled.\n'
    return ''.join(f'{t.payer} pays {t.payee} {format_amount(t.amount)}\n' for t in transfers)
