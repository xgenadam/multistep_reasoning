"""Net balance per member."""

from __future__ import annotations

from .model import format_amount


def balances(group) -> dict[str, int]:
    bal = {m: 0 for m in sorted(group.members)}
    for expense, shares in group.expenses:
        bal[expense.paid_by] += expense.amount
        for member, cents in shares.items():
            bal[member] -= cents
    for payer, payee, amount in group.payments:
        bal[payer] += amount
        bal[payee] -= amount
    return bal


def format_balances(bals: dict) -> str:
    lines = []
    for name in sorted(bals):
        cents = bals[name]
        lines.append(f'{name}: {"+" if cents > 0 else ""}{format_amount(cents)}\n')
    return ''.join(lines)
