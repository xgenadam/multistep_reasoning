from datetime import date
from decimal import Decimal

import pytest

from inventory import (InsufficientStockError, InventoryError, Item, Ledger, Movement,
                       UnknownItemError)

D1, D2, D3 = date(2026, 1, 5), date(2026, 1, 10), date(2026, 1, 12)


def ledger(*skus):
    lg = Ledger()
    for sku in skus:
        lg.add_item(Item(sku, sku.lower(), 'cat'))
    return lg


def test_items_sorted_and_duplicates_rejected():
    lg = Ledger()
    lg.add_item(Item('W-2', 'Widget', 'widgets'))
    lg.add_item(Item('B-1', 'Bolt', 'bolts'))
    assert [i.sku for i in lg.items()] == ['B-1', 'W-2']
    assert lg.item('W-2') == Item('W-2', 'Widget', 'widgets')
    with pytest.raises(ValueError):
        lg.add_item(Item('B-1', 'Other', 'x'))


def test_unknown_item_errors_are_inventory_errors():
    lg = ledger('A')
    with pytest.raises(UnknownItemError):
        lg.item('Z')
    with pytest.raises(InventoryError):
        lg.on_hand('Z')
    assert issubclass(InsufficientStockError, InventoryError)


def test_receive_returns_movement_with_decimal_cost():
    lg = ledger('A')
    m1 = lg.receive(D1, 'A', 'east', 5, '2.50')
    m2 = lg.receive(D1, 'A', 'east', 1, 3)
    assert m1 == Movement(1, D1, 'receive', 'A', 5, 'east', None, Decimal('2.50'))
    assert m2.seq == 2 and m2.unit_cost == Decimal(3) and isinstance(m2.unit_cost, Decimal)


def test_issue_and_transfer_movements():
    lg = ledger('A')
    lg.receive(D1, 'A', 'east', 5, '1')
    t = lg.transfer(D2, 'A', 'east', 'west', 2)
    i = lg.issue(D2, 'A', 'west', 1)
    assert t == Movement(2, D2, 'transfer', 'A', 2, 'east', 'west', None)
    assert i == Movement(3, D2, 'issue', 'A', 1, 'west', None, None)


@pytest.mark.parametrize('qty', [0, -1, True, 2.0])
def test_bad_quantity_raises_value_error(qty):
    lg = ledger('A')
    with pytest.raises(ValueError):
        lg.receive(D1, 'A', 'east', qty, '1')
    assert lg.movements() == []


def test_cost_type_and_sign():
    lg = ledger('A')
    with pytest.raises(TypeError):
        lg.receive(D1, 'A', 'east', 1, 1.5)
    with pytest.raises(ValueError):
        lg.receive(D1, 'A', 'east', 1, '-0.01')
    assert lg.receive(D1, 'A', 'east', 1, Decimal('0')).unit_cost == 0


def test_unknown_sku_checked_before_quantity():
    lg = ledger('A')
    with pytest.raises(UnknownItemError):
        lg.receive(D1, 'Z', 'east', 0, '1')
    with pytest.raises(UnknownItemError):
        lg.issue(D1, 'Z', 'east', 1)


def test_days_must_not_go_backwards():
    lg = ledger('A')
    lg.receive(D2, 'A', 'east', 5, '1')
    lg.receive(D2, 'A', 'east', 5, '1')
    with pytest.raises(ValueError):
        lg.issue(D1, 'A', 'east', 1)
    assert len(lg.movements()) == 2


def test_insufficient_stock_is_per_location_and_records_nothing():
    lg = ledger('A')
    lg.receive(D1, 'A', 'east', 5, '1')
    lg.receive(D1, 'A', 'west', 5, '1')
    with pytest.raises(InsufficientStockError):
        lg.issue(D2, 'A', 'east', 6)
    with pytest.raises(InsufficientStockError):
        lg.transfer(D2, 'A', 'west', 'east', 6)
    assert len(lg.movements()) == 2
    assert lg.issue(D2, 'A', 'east', 5).seq == 3
    assert lg.on_hand('A') == 5


def test_transfer_needs_two_locations():
    lg = ledger('A')
    lg.receive(D1, 'A', 'east', 5, '1')
    with pytest.raises(ValueError):
        lg.transfer(D1, 'A', 'east', 'east', 1)


def test_on_hand_movements_and_locations():
    lg = ledger('A', 'B')
    lg.receive(D1, 'A', 'east', 10, '1')
    lg.receive(D2, 'B', 'north', 4, '1')
    lg.transfer(D2, 'A', 'east', 'west', 3)
    lg.issue(D3, 'A', 'west', 1)
    assert lg.on_hand('A') == 9
    assert lg.on_hand('A', 'east') == 7
    assert lg.on_hand('A', 'west') == 2
    assert lg.on_hand('A', 'west', as_of=D2) == 3
    assert lg.on_hand('A', as_of=date(2026, 1, 1)) == 0
    assert lg.on_hand('B', 'east') == 0
    assert [m.seq for m in lg.movements('A')] == [1, 3, 4]
    assert [m.seq for m in lg.movements(as_of=D2)] == [1, 2, 3]
    assert lg.locations() == ['east', 'north', 'west']
