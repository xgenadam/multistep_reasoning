from decimal import Decimal as D

import pytest

from money import allocate, format_money, split_even, to_cents


@pytest.mark.parametrize('x, expected', [
    ('2.675', '2.68'), ('2.665', '2.66'), ('0.125', '0.12'), ('0.135', '0.14'),
    ('-2.675', '-2.68'), (5, '5.00'), (D('1.005'), '1.00'), ('  3.1 ', '3.10'), ('1e2', '100.00'),
])
def test_to_cents_bankers_rounding(x, expected):
    out = to_cents(x)
    assert isinstance(out, D)
    assert out == D(expected)
    assert out.as_tuple().exponent == -2


def test_to_cents_type_and_value_errors():
    for bad in (1.5, True, None, [1]):
        with pytest.raises(TypeError):
            to_cents(bad)
    for bad in ('abc', '', '1.2.3', 'NaN', 'Infinity', '-inf'):
        with pytest.raises(ValueError):
            to_cents(bad)


def test_allocate_examples():
    assert allocate('100', [1, 1, 1]) == [D('33.34'), D('33.33'), D('33.33')]
    assert allocate('0.05', [3, 7]) == [D('0.02'), D('0.03')]


def test_allocate_largest_remainder_not_position():
    # shares of 1.00 by 1:2:2 are 20, 40, 40 cents: exact
    assert allocate('1.00', [1, 2, 2]) == [D('0.20'), D('0.40'), D('0.40')]
    # 0.10 by 1:1:1:3 -> 1.666, 1.666, 1.666, 5.0 cents; floors 1,1,1,5 leave 2 cents
    assert allocate('0.10', [1, 1, 1, 3]) == [D('0.02'), D('0.02'), D('0.01'), D('0.05')]
    # 1.00 by 1:3:1 -> 20, 60, 20 exact; 1.01 -> 20.2, 60.6, 20.2: the cent goes to the middle
    assert allocate('1.01', [1, 3, 1]) == [D('0.20'), D('0.61'), D('0.20')]


def test_allocate_ties_go_to_earlier_parts():
    assert allocate('0.02', [1, 1, 1]) == [D('0.01'), D('0.01'), D('0.00')]
    assert allocate('0.07', [1, 2, 1, 2]) == [D('0.01'), D('0.03'), D('0.01'), D('0.02')]


def test_allocate_zero_ratio_and_decimal_ratios():
    assert allocate('10', [0, 1, 0, 1]) == [D('0.00'), D('5.00'), D('0.00'), D('5.00')]
    assert allocate('1', [D('0.5'), D('0.25'), D('0.25')]) == [D('0.50'), D('0.25'), D('0.25')]


def test_allocate_negative_amount():
    assert allocate('-100', [1, 1, 1]) == [D('-33.34'), D('-33.33'), D('-33.33')]


def test_allocate_rounds_amount_first():
    assert allocate('0.105', [1, 1]) == [D('0.05'), D('0.05')]  # 0.105 -> 0.10


def test_allocate_always_sums_exactly():
    import random
    rng = random.Random(30)
    for _ in range(300):
        amount = D(rng.randrange(-100000, 100000)) / 100
        ratios = [rng.randrange(0, 7) for _ in range(rng.randrange(1, 8))]
        if not any(ratios):
            ratios[0] = 1
        parts = allocate(amount, ratios)
        assert sum(parts) == amount
        assert len(parts) == len(ratios)
        assert all(p.as_tuple().exponent == -2 for p in parts)
        assert all(p == 0 for p, r in zip(parts, ratios) if r == 0)


def test_allocate_errors():
    for bad in ([], [0, 0], [1, -1], 'ab', [1.5, 1]):
        with pytest.raises(ValueError):
            allocate('1', bad)
    with pytest.raises(TypeError):
        allocate(1.0, [1])


def test_split_even():
    assert split_even('10', 3) == [D('3.34'), D('3.33'), D('3.33')]
    assert split_even(1, 1) == [D('1.00')]
    with pytest.raises(ValueError):
        split_even('10', 0)


def test_format_money():
    cases = [
        ('-1234567.891', '-1,234,567.89'), ('0', '0.00'), ('-0.001', '0.00'),
        ('999.995', '1,000.00'), (12, '12.00'), ('1000', '1,000.00'), ('-5.5', '-5.50'),
    ]
    for x, expected in cases:
        assert format_money(x) == expected, x
