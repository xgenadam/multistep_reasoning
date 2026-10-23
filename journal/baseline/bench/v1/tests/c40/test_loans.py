from datetime import date, timedelta

import pytest

from library import (Blocked, Catalog, DuplicateLoan, Library, LimitReached, Loan, LoanError,
                     NotAvailable, RenewalRefused)


class Clock:
    def __init__(self, today=date(2026, 3, 2)):  # a Monday
        self.today = today

    def __call__(self):
        return self.today

    def advance(self, days):
        self.today += timedelta(days=days)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def catalog():
    c = Catalog()
    c.add_book('B1', 'Dune', 'Frank Herbert', copies=1)
    c.add_book('B2', 'Emma', 'Jane Austen', copies=2)
    for i in range(1, 6):
        c.add_book(f'X{i}', f'Extra {i}', 'Anon', copies=3)
    c.add_member('ann', 'Ann')
    c.add_member('bob', 'Bob')
    c.add_member('cat', 'Cat', kind='student')
    c.add_member('dan', 'Dan', kind='staff')
    return c


@pytest.fixture
def lib(catalog, clock):
    return Library(catalog, clock)


def test_checkout_creates_numbered_loans(lib, clock):
    a = lib.checkout('ann', 'B1')
    b = lib.checkout('cat', 'B2')
    assert isinstance(a, Loan)
    assert (a.loan_id, a.member_id, a.isbn, a.start, a.due, a.renewals, a.returned, a.fine) == \
        (1, 'ann', 'B1', date(2026, 3, 2), date(2026, 3, 23), 0, None, 0)
    assert (b.loan_id, b.due) == (2, date(2026, 3, 16))
    assert lib.available('B1') == 0 and lib.available('B2') == 1


def test_checkout_due_date_skips_sunday(clock):
    c = Catalog()
    c.add_book('B', 'T', 'A')
    c.add_member('s', 'S', kind='student')
    clock.today = date(2026, 3, 1)  # Sunday; +14 is a Sunday too
    assert Library(c, clock).checkout('s', 'B').due == date(2026, 3, 16)


def test_unknown_ids_raise_key_error(lib):
    with pytest.raises(KeyError):
        lib.checkout('zed', 'B1')
    with pytest.raises(KeyError):
        lib.checkout('ann', 'NOPE')
    with pytest.raises(KeyError):
        lib.renew(99)
    with pytest.raises(KeyError):
        lib.checkin(99)


def test_not_available_when_all_copies_out(lib):
    lib.checkout('ann', 'B1')
    with pytest.raises(NotAvailable):
        lib.checkout('bob', 'B1')
    assert issubclass(NotAvailable, LoanError)


def test_duplicate_and_limit(lib):
    lib.checkout('cat', 'B2')
    with pytest.raises(DuplicateLoan):
        lib.checkout('cat', 'B2')
    lib.checkout('cat', 'X1')
    lib.checkout('cat', 'X2')
    with pytest.raises(LimitReached):
        lib.checkout('cat', 'X3')  # students may have 3
    with pytest.raises(DuplicateLoan):
        lib.checkout('cat', 'X1')  # duplicate is checked before the limit


def test_fine_blocks_until_paid_and_blocked_comes_first(lib, clock):
    loan = lib.checkout('ann', 'B2')
    clock.advance(21 + 4)  # 4 days late
    assert lib.checkin(loan.loan_id) == 100
    assert lib.balance('ann') == 100
    lib.checkout('bob', 'B2')
    with pytest.raises(Blocked):
        lib.checkout('ann', 'X1')
    assert lib.pay('ann', 60) == 40
    with pytest.raises(Blocked):
        lib.checkout('ann', 'X1')
    assert lib.pay('ann', 40) == 0
    assert lib.checkout('ann', 'X1').loan_id == 3


def test_checkin_fine_grace_and_double_checkin(lib, clock):
    loan = lib.checkout('cat', 'B1')  # due 2026-03-16
    clock.today = date(2026, 3, 18)  # 2 days late: inside grace
    assert lib.accrued_fine(loan.loan_id) == 0
    clock.today = date(2026, 3, 19)  # 3 days late
    assert lib.accrued_fine(loan.loan_id) == 30
    assert lib.checkin(loan.loan_id) == 30
    assert loan.returned == date(2026, 3, 19) and loan.fine == 30
    clock.advance(10)
    assert lib.accrued_fine(loan.loan_id) == 30  # the stored fine
    with pytest.raises(LoanError):
        lib.checkin(loan.loan_id)
    assert lib.balance('cat') == 30
    assert lib.available('B1') == 1


def test_pay_errors(lib, clock):
    loan = lib.checkout('ann', 'B1')
    clock.advance(22)
    lib.checkin(loan.loan_id)
    assert lib.balance('ann') == 25
    for bad in (0, -5, 26):
        with pytest.raises(ValueError):
            lib.pay('ann', bad)
    assert lib.balance('ann') == 25
    assert lib.balance('bob') == 0


def test_renew_counts_from_old_due_and_runs_out(lib, clock):
    loan = lib.checkout('ann', 'B2')  # due 03-23
    clock.advance(8)
    assert lib.renew(loan.loan_id) == date(2026, 4, 13)
    assert loan.due == date(2026, 4, 13) and loan.renewals == 1
    assert lib.renew(loan.loan_id) == date(2026, 5, 4)
    with pytest.raises(RenewalRefused):
        lib.renew(loan.loan_id)
    assert loan.due == date(2026, 5, 4) and loan.renewals == 2


def test_renew_allowed_on_due_day_refused_after(lib, clock):
    a = lib.checkout('ann', 'B2')
    b = lib.checkout('bob', 'B2')
    clock.today = date(2026, 3, 23)
    assert lib.renew(a.loan_id) == date(2026, 4, 13)
    clock.today = date(2026, 3, 24)
    with pytest.raises(RenewalRefused):
        lib.renew(b.loan_id)


def test_renew_refused_when_held_and_returned_is_loan_error(lib, clock):
    loan = lib.checkout('ann', 'B1')
    lib.place_hold('bob', 'B1')
    with pytest.raises(RenewalRefused):
        lib.renew(loan.loan_id)
    lib.checkin(loan.loan_id)
    with pytest.raises(LoanError) as exc:
        lib.renew(loan.loan_id)
    assert not isinstance(exc.value, RenewalRefused)


def test_loans_and_overdue_sorted(lib, clock):
    a = lib.checkout('ann', 'B2')         # due 03-23
    clock.advance(1)
    b = lib.checkout('ann', 'X1')         # due 03-24
    clock.advance(-1)
    c = lib.checkout('ann', 'X2')         # due 03-23, later id
    d = lib.checkout('cat', 'X3')         # due 03-16
    assert [l.loan_id for l in lib.loans('ann')] == [a.loan_id, c.loan_id, b.loan_id]
    clock.today = date(2026, 3, 24)
    assert [l.loan_id for l in lib.overdue()] == [d.loan_id, a.loan_id, c.loan_id]
    lib.checkin(a.loan_id)
    assert [l.loan_id for l in lib.loans('ann')] == [c.loan_id, b.loan_id]


def test_place_hold_rules_and_positions(lib):
    with pytest.raises(LoanError):
        lib.place_hold('bob', 'B1')  # a copy is available
    lib.checkout('ann', 'B1')
    with pytest.raises(DuplicateLoan):
        lib.place_hold('ann', 'B1')
    assert lib.place_hold('bob', 'B1') == 1
    assert lib.place_hold('cat', 'B1') == 2
    with pytest.raises(DuplicateLoan):
        lib.place_hold('bob', 'B1')
    assert lib.holds('B1') == ['bob', 'cat']
    assert lib.hold_status('cat', 'B1') == ('waiting', 2)
    with pytest.raises(KeyError):
        lib.hold_status('dan', 'B1')


def test_checkin_sets_copy_aside_for_first_hold(lib, clock):
    loan = lib.checkout('ann', 'B1')
    lib.place_hold('bob', 'B1')
    lib.place_hold('cat', 'B1')
    clock.advance(5)
    lib.checkin(loan.loan_id)
    assert lib.available('B1') == 0
    assert lib.hold_status('bob', 'B1') == ('ready', date(2026, 3, 10))
    assert lib.hold_status('cat', 'B1') == ('waiting', 2)
    with pytest.raises(NotAvailable):
        lib.checkout('dan', 'B1')
    with pytest.raises(NotAvailable):
        lib.checkout('cat', 'B1')
    clock.today = date(2026, 3, 10)  # the deadline day still counts
    got = lib.checkout('bob', 'B1')
    assert got.member_id == 'bob'
    assert lib.holds('B1') == ['cat']


def test_expired_holds_chain_by_deadline_not_by_usage(lib, clock):
    loan = lib.checkout('ann', 'B1')
    for m in ('bob', 'cat', 'dan'):
        lib.place_hold(m, 'B1')
    lib.checkin(loan.loan_id)  # 03-02: bob ready until 03-05
    clock.today = date(2026, 3, 12)  # nobody used the library meanwhile
    # bob expires 03-06 -> cat ready until 03-09; cat expires 03-10 -> dan until 03-13
    assert lib.holds('B1') == ['dan']
    assert lib.hold_status('dan', 'B1') == ('ready', date(2026, 3, 13))
    clock.today = date(2026, 3, 14)
    assert lib.holds('B1') == []
    assert lib.available('B1') == 1
    assert lib.checkout('bob', 'B1').loan_id == 2


def test_cancel_ready_hold_passes_copy_from_today(lib, clock):
    loan = lib.checkout('ann', 'B1')
    lib.place_hold('bob', 'B1')
    lib.place_hold('cat', 'B1')
    lib.checkin(loan.loan_id)
    clock.advance(2)
    lib.cancel_hold('bob', 'B1')
    assert lib.hold_status('cat', 'B1') == ('ready', date(2026, 3, 7))
    lib.cancel_hold('cat', 'B1')
    assert lib.available('B1') == 1
    with pytest.raises(KeyError):
        lib.cancel_hold('cat', 'B1')


def test_checkout_removes_waiting_hold_when_copies_added(lib, catalog):
    lib.checkout('ann', 'B1')
    lib.place_hold('bob', 'B1')
    lib.place_hold('cat', 'B1')
    catalog.add_copies('B1', 1)
    assert lib.available('B1') == 1  # added copies are not set aside
    lib.checkout('cat', 'B1')
    assert lib.holds('B1') == ['bob']
    assert lib.hold_status('bob', 'B1') == ('waiting', 1)
