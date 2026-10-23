"""A vending machine built on fsm."""
from fsm import InvalidTransition, Machine, Transition

COINS = (100, 25, 10, 5)


class VendingError(Exception):
    pass


class SoldOut(VendingError):
    pass


class InsufficientCredit(VendingError):
    pass


def make_change(amount: int) -> list[int]:
    """Greedy change, largest coin first."""
    out = []
    for coin in COINS:
        while amount >= coin:
            out.append(coin)
            amount -= coin
    return out


class VendingMachine:
    def __init__(self, products: dict[str, tuple[int, int]]):
        self._price = {code: price for code, (price, _) in products.items()}
        self._stock = {code: stock for code, (_, stock) in products.items()}
        self._credit = 0
        self._sales: dict[str, int] = {}
        self._revenue = 0
        self.machine = Machine(
            ['idle', 'credit', 'maintenance'],
            [
                Transition('insert', ['idle', 'credit'], 'credit', action=self._on_insert),
                Transition('select', 'credit', 'idle', action=self._on_select),
                Transition('cancel', 'credit', 'idle', action=self._on_cancel),
                Transition('service', 'idle', 'maintenance'),
                Transition('restock', 'maintenance', None, action=self._on_restock),
                Transition('resume', 'maintenance', 'idle'),
            ],
            initial='idle',
        )

    # ------------------------------------------------------------ views
    @property
    def state(self) -> str:
        return self.machine.state

    @property
    def credit(self) -> int:
        return self._credit

    @property
    def revenue(self) -> int:
        return self._revenue

    def stock(self, code: str) -> int:
        return self._stock[code]

    def price(self, code: str) -> int:
        return self._price[code]

    def sales(self) -> dict[str, int]:
        return dict(self._sales)

    # ------------------------------------------------------------ actions
    def _on_insert(self, machine, ev):
        self._credit += ev.data['coin']

    def _on_select(self, machine, ev):
        code = ev.data['code']
        price = self._price[code]
        self._stock[code] -= 1
        self._sales[code] = self._sales.get(code, 0) + 1
        self._revenue += price
        self._credit = 0

    def _on_cancel(self, machine, ev):
        self._credit = 0

    def _on_restock(self, machine, ev):
        code, qty, price = ev.data['code'], ev.data['qty'], ev.data['price']
        if price is not None:
            self._price[code] = price
        self._stock[code] = self._stock.get(code, 0) + qty

    # ------------------------------------------------------------ operations
    def insert(self, coin: int) -> int:
        """Add a coin to the credit (idle or credit) and return the new credit."""
        if coin not in COINS:
            raise ValueError(f'coin not accepted: {coin!r}')
        self.machine.fire('insert', coin=coin)
        return self._credit

    def _require(self, event: str) -> None:
        """Raise InvalidTransition unless `event` is in the table for this state.

        Used before the domain checks, so that the state error comes first.
        """
        if event not in self.machine.available_events():
            raise InvalidTransition(self.machine.state, event)

    def select(self, code: str) -> list[int]:
        """Sell one unit of `code` and return the change.

        Checks, in order: state, unknown code, stock, credit. A failure changes nothing.
        """
        self._require('select')
        if code not in self._price:
            raise KeyError(code)
        if self._credit < self._price[code]:
            raise InsufficientCredit(code)
        if self._stock[code] < 1:
            raise SoldOut(code)
        change = make_change(self._credit - self._price[code])
        self.machine.fire('select', code=code)
        return change

    def cancel(self) -> list[int]:
        """Refund the whole credit as coins and return to idle."""
        self._require('cancel')
        refund = make_change(self._credit)
        self.machine.fire('cancel')
        return refund

    def service(self) -> None:
        """Enter maintenance (idle only)."""
        self.machine.fire('service')

    def restock(self, code: str, qty: int, price: int | None = None) -> None:
        """Add stock in maintenance; a new code needs a price."""
        self._require('restock')
        if qty < 1:
            raise ValueError('qty must be at least 1')
        if code not in self._price and price is None:
            raise KeyError(code)
        self.machine.fire('restock', code=code, qty=qty, price=price)

    def resume(self) -> None:
        """Leave maintenance."""
        self.machine.fire('resume')
