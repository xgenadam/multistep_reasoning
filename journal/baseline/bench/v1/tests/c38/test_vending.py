import pytest

import fsm
from vending import InsufficientCredit, SoldOut, VendingError, VendingMachine


def vm():
    return VendingMachine({'A1': (65, 2), 'B2': (100, 0), 'C3': (5, 1)})


def test_starts_idle_and_is_built_on_fsm():
    v = vm()
    assert v.state == 'idle' and v.credit == 0
    assert isinstance(v.machine, fsm.Machine)
    assert v.machine.state == 'idle'


def test_insert_accumulates_and_moves_to_credit():
    v = vm()
    assert v.insert(25) == 25
    assert v.state == 'credit' and v.machine.state == 'credit'
    assert v.insert(100) == 125
    assert v.credit == 125


@pytest.mark.parametrize('coin', [1, 50, 200])
def test_bad_coin_raises_value_error_and_changes_nothing(coin):
    v = vm()
    with pytest.raises(ValueError):
        v.insert(coin)
    assert v.state == 'idle' and v.credit == 0


def test_select_sells_and_gives_greedy_change():
    v = vm()
    v.insert(100)
    v.insert(10)
    assert v.select('A1') == [25, 10, 10]
    assert v.state == 'idle' and v.machine.state == 'idle' and v.credit == 0
    assert v.stock('A1') == 1
    assert v.sales() == {'A1': 1}
    assert v.revenue == 65


def test_exact_payment_gives_no_change():
    v = vm()
    v.insert(5)
    assert v.select('C3') == []


def test_select_requires_credit_state():
    v = vm()
    with pytest.raises(fsm.InvalidTransition):
        v.select('B2')  # state is checked before stock
    with pytest.raises(fsm.InvalidTransition):
        v.select('nope')


def test_select_check_order_and_failure_keeps_everything():
    v = vm()
    v.insert(25)
    with pytest.raises(KeyError):
        v.select('ZZ')
    with pytest.raises(SoldOut):
        v.select('B2')  # sold out wins over too little credit
    with pytest.raises(InsufficientCredit):
        v.select('A1')
    assert issubclass(SoldOut, VendingError) and issubclass(InsufficientCredit, VendingError)
    assert v.state == 'credit' and v.credit == 25 and v.stock('A1') == 2
    assert v.sales() == {} and v.revenue == 0
    v.insert(25)
    v.insert(25)
    assert v.select('A1') == [10]


def test_cancel_refunds_greedily():
    v = vm()
    for c in (5, 5, 5, 5, 5, 10, 100):
        v.insert(c)
    assert v.cancel() == [100, 25, 10]
    assert v.state == 'idle' and v.credit == 0


def test_cancel_when_idle_is_invalid():
    with pytest.raises(fsm.InvalidTransition):
        vm().cancel()


def test_sold_out_after_last_unit():
    v = vm()
    v.insert(5)
    v.select('C3')
    v.insert(100)
    with pytest.raises(SoldOut):
        v.select('C3')
    assert v.stock('C3') == 0


def test_maintenance_restock_and_price_change():
    v = vm()
    v.service()
    assert v.state == 'maintenance' and v.machine.state == 'maintenance'
    v.restock('B2', 3)
    v.restock('A1', 1, price=70)
    v.restock('D4', 2, price=40)
    with pytest.raises(KeyError):
        v.restock('E5', 1)
    with pytest.raises(ValueError):
        v.restock('A1', 0)
    assert v.state == 'maintenance'
    v.resume()
    assert v.state == 'idle'
    assert (v.stock('B2'), v.stock('A1'), v.price('A1'), v.stock('D4'), v.price('D4')) == \
        (3, 3, 70, 2, 40)
    v.insert(100)
    assert v.select('A1') == [25, 5]


def test_illegal_operations_by_state():
    v = vm()
    with pytest.raises(fsm.InvalidTransition):
        v.restock('A1', 1)
    with pytest.raises(fsm.InvalidTransition):
        v.resume()
    v.insert(25)
    with pytest.raises(fsm.InvalidTransition):
        v.service()
    v.cancel()
    v.service()
    with pytest.raises(fsm.InvalidTransition):
        v.insert(25)
    assert v.credit == 0 and v.state == 'maintenance'


def test_views_and_revenue_over_several_sales():
    v = VendingMachine({'X': (30, 5), 'Y': (45, 5)})
    for code in ('X', 'Y', 'X'):
        v.insert(100)
        v.select(code)
    assert v.sales() == {'X': 2, 'Y': 1}
    assert v.revenue == 105
    with pytest.raises(KeyError):
        v.stock('Q')
    with pytest.raises(KeyError):
        v.price('Q')
    s = v.sales()
    s['X'] = 99
    assert v.sales()['X'] == 2
