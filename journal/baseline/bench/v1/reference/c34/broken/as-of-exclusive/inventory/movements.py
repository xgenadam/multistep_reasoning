"""The ledger: items and an append-only, date-ordered list of movements."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from .models import InsufficientStockError, Item, Movement, UnknownItemError


def _check_qty(qty) -> int:
    if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
        raise ValueError(f'quantity must be a positive int, got {qty!r}')
    return qty


def _to_cost(unit_cost) -> Decimal:
    if isinstance(unit_cost, float):
        raise TypeError('unit cost must not be a float')
    if isinstance(unit_cost, bool) or not isinstance(unit_cost, (Decimal, int, str)):
        raise TypeError(f'unit cost must be a Decimal, int or str, got {unit_cost!r}')
    try:
        cost = Decimal(unit_cost)
    except InvalidOperation:
        raise ValueError(f'invalid unit cost {unit_cost!r}') from None
    if not cost.is_finite() or cost < 0:
        raise ValueError(f'unit cost must be a non-negative number, got {unit_cost!r}')
    return cost


class Ledger:
    def __init__(self):
        self._items: dict[str, Item] = {}
        self._movements: list[Movement] = []
        self._held: dict[tuple[str, str], int] = defaultdict(int)  # (sku, location) -> qty

    # ------------------------------------------------------------ items
    def add_item(self, item: Item) -> None:
        if item.sku in self._items:
            raise ValueError(f'duplicate SKU {item.sku!r}')
        self._items[item.sku] = item

    def item(self, sku) -> Item:
        try:
            return self._items[sku]
        except KeyError:
            raise UnknownItemError(sku) from None

    def items(self) -> list[Item]:
        return [self._items[s] for s in sorted(self._items)]

    # ------------------------------------------------------------ recording
    def _check(self, day, sku, qty) -> None:
        self.item(sku)
        _check_qty(qty)
        if self._movements and day < self._movements[-1].day:
            raise ValueError(f'{day} is earlier than the last movement '
                             f'({self._movements[-1].day})')

    def _need(self, sku, location, qty) -> None:
        held = self._held[(sku, location)]
        if qty > held:
            raise InsufficientStockError(f'{location} holds {held} of {sku}, need {qty}')

    def _record(self, **fields) -> Movement:
        m = Movement(seq=len(self._movements) + 1, **fields)
        self._movements.append(m)
        return m

    def receive(self, day, sku, location, qty, unit_cost) -> Movement:
        self._check(day, sku, qty)
        cost = _to_cost(unit_cost)
        self._held[(sku, location)] += qty
        return self._record(day=day, kind='receive', sku=sku, qty=qty, location=location,
                            unit_cost=cost)

    def issue(self, day, sku, location, qty) -> Movement:
        self._check(day, sku, qty)
        self._need(sku, location, qty)
        self._held[(sku, location)] -= qty
        return self._record(day=day, kind='issue', sku=sku, qty=qty, location=location)

    def transfer(self, day, sku, from_location, to_location, qty) -> Movement:
        self._check(day, sku, qty)
        if from_location == to_location:
            raise ValueError('a transfer needs two different locations')
        self._need(sku, from_location, qty)
        self._held[(sku, from_location)] -= qty
        self._held[(sku, to_location)] += qty
        return self._record(day=day, kind='transfer', sku=sku, qty=qty,
                            location=from_location, to_location=to_location)

    # ------------------------------------------------------------ queries
    def movements(self, sku=None, as_of=None) -> list[Movement]:
        return [m for m in self._movements
                if (sku is None or m.sku == sku) and (as_of is None or m.day < as_of)]

    def positions(self, as_of=None) -> dict[tuple[str, str], int]:
        """{(sku, location): qty} as of a day, zero positions included."""
        held: dict[tuple[str, str], int] = defaultdict(int)
        for m in self.movements(as_of=as_of):
            if m.kind == 'receive':
                held[(m.sku, m.location)] += m.qty
            elif m.kind == 'issue':
                held[(m.sku, m.location)] -= m.qty
            else:
                held[(m.sku, m.location)] -= m.qty
                held[(m.sku, m.to_location)] += m.qty
        return dict(held)

    def on_hand(self, sku, location=None, as_of=None) -> int:
        self.item(sku)
        return sum(q for (s, loc), q in self.positions(as_of).items()
                   if s == sku and (location is None or loc == location))

    def locations(self) -> list[str]:
        found = set()
        for m in self._movements:
            found.add(m.location)
            if m.to_location is not None:
                found.add(m.to_location)
        return sorted(found)
