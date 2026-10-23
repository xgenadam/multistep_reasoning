"""Per-SKU stock valuation: FIFO layers or moving weighted average."""
from collections import deque
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal('0.01')
METHODS = ('fifo', 'average')


def cents(x: Decimal) -> Decimal:
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Valuation:
    qty: int
    value: Decimal
    cogs: Decimal


def fifo(ledger, sku, as_of=None) -> Valuation:
    ledger.item(sku)
    layers: deque[list] = deque()  # [qty left, unit cost], oldest first
    cogs = Decimal(0)
    for m in ledger.movements(sku, as_of):
        if m.kind == 'receive':
            layers.append([m.qty, m.unit_cost])
        elif m.kind == 'issue':
            need = m.qty
            while need:
                layer = layers[0]
                take = min(need, layer[0])
                cogs += take * layer[1]
                layer[0] -= take
                need -= take
                if layer[0] == 0:
                    layers.popleft()
    qty = sum(q for q, _ in layers)
    value = sum((q * c for q, c in layers), Decimal(0))
    return Valuation(qty, cents(value), cents(cogs))


def average(ledger, sku, as_of=None) -> Valuation:
    ledger.item(sku)
    qty, value, cogs = 0, Decimal(0), Decimal(0)
    for m in ledger.movements(sku, as_of):
        if m.kind == 'receive':
            qty += m.qty
            value += m.qty * m.unit_cost
        elif m.kind == 'issue':
            cost = value if m.qty == qty else cents(value * m.qty / qty)
            value -= cost
            qty -= m.qty
            cogs += cost
    return Valuation(qty, cents(value), cents(cogs))


def valuate(ledger, sku, method='fifo', as_of=None) -> Valuation:
    if method == 'fifo':
        return fifo(ledger, sku, as_of)
    if method == 'average':
        return average(ledger, sku, as_of)
    raise ValueError(f'method must be one of {", ".join(METHODS)}, got {method!r}')
