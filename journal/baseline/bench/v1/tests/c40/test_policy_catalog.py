from datetime import date

import pytest

from library import POLICY, Book, Catalog, Policy, due_date, fine_for, HOLD_PICKUP_DAYS


def test_policy_table():
    assert HOLD_PICKUP_DAYS == 3
    assert POLICY['standard'] == Policy(5, 21, 2, 25, 1000, 0)
    assert POLICY['student'] == Policy(3, 14, 1, 10, 500, 2)
    assert POLICY['staff'] == Policy(10, 42, 3, 0, 0, 0)
    with pytest.raises(Exception):
        POLICY['staff'].max_loans = 1  # frozen


@pytest.mark.parametrize('start, days, expected', [
    (date(2026, 3, 2), 21, date(2026, 3, 23)),   # Monday + 21 = Monday
    (date(2026, 3, 1), 14, date(2026, 3, 16)),   # lands on Sunday 15th -> Monday
    (date(2026, 3, 7), 1, date(2026, 3, 9)),     # Saturday + 1 = Sunday -> Monday
])
def test_due_date(start, days, expected):
    assert due_date(start, days) == expected


@pytest.mark.parametrize('kind, late, fine', [
    ('standard', 0, 0),
    ('standard', -5, 0),
    ('standard', 1, 25),
    ('student', 2, 0),      # inside the grace period
    ('student', 3, 30),     # every late day counts once past grace
    ('standard', 60, 1000),  # capped
    ('student', 51, 500),
    ('staff', 30, 0),
])
def test_fine_for(kind, late, fine):
    due = date(2026, 3, 10)
    returned = date.fromordinal(due.toordinal() + late)
    assert fine_for(kind, due, returned) == fine


def test_fine_for_unknown_kind():
    with pytest.raises(KeyError):
        fine_for('vip', date(2026, 1, 1), date(2026, 2, 1))


def test_catalog_add_and_errors():
    c = Catalog()
    b = c.add_book('111', 'Dune', 'Frank Herbert', copies=2)
    assert isinstance(b, Book) and b.copies == 2 and c.book('111') is b
    with pytest.raises(ValueError):
        c.add_book('111', 'Dune again', 'X')
    with pytest.raises(ValueError):
        c.add_book('222', 'Zero', 'X', copies=0)
    m = c.add_member('m1', 'Ann')
    assert m.kind == 'standard' and c.member('m1') is m
    with pytest.raises(ValueError):
        c.add_member('m1', 'Ann again')
    with pytest.raises(ValueError):
        c.add_member('m2', 'Bob', kind='vip')
    with pytest.raises(KeyError):
        c.book('999')
    with pytest.raises(KeyError):
        c.member('m9')


def test_add_copies():
    c = Catalog()
    c.add_book('111', 'Dune', 'Frank Herbert')
    assert c.add_copies('111', 2) == 3
    with pytest.raises(ValueError):
        c.add_copies('111', 0)
    with pytest.raises(KeyError):
        c.add_copies('999', 1)


def test_search_ignores_case_and_sorts():
    c = Catalog()
    c.add_book('3', 'The Hobbit', 'J. R. R. Tolkien')
    c.add_book('1', 'Dune', 'Frank Herbert')
    c.add_book('2', 'Children of Dune', 'Frank Herbert')
    c.add_book('0', 'Dune', 'Another Herbert')
    assert [b.isbn for b in c.search('dUNe')] == ['2', '0', '1']
    assert [b.isbn for b in c.search('TOLKIEN')] == ['3']
    assert c.search('nothing') == []
