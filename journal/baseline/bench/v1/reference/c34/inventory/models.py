"""Items, movements and the errors the library raises."""
import datetime
from dataclasses import dataclass
from decimal import Decimal

KINDS = ('receive', 'issue', 'transfer')


class InventoryError(Exception):
    """Base class for inventory errors."""


class UnknownItemError(InventoryError):
    """A SKU that was never added."""


class InsufficientStockError(InventoryError):
    """Taking more stock out of a location than it holds."""


@dataclass(frozen=True)
class Item:
    sku: str
    name: str
    category: str


@dataclass(frozen=True)
class Movement:
    seq: int
    day: datetime.date
    kind: str
    sku: str
    qty: int
    location: str
    to_location: str | None = None
    unit_cost: Decimal | None = None
