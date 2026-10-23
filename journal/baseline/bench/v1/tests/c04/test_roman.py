import itertools

import pytest

from roman import from_roman, to_roman

KNOWN = {
    1: 'I', 3: 'III', 4: 'IV', 9: 'IX', 14: 'XIV', 40: 'XL', 44: 'XLIV',
    49: 'XLIX', 90: 'XC', 99: 'XCIX', 400: 'CD', 444: 'CDXLIV', 500: 'D',
    900: 'CM', 1994: 'MCMXCIV', 2026: 'MMXXVI', 3888: 'MMMDCCCLXXXVIII',
    3999: 'MMMCMXCIX',
}


def assert_rejected(values, exc):
    for s in values:
        with pytest.raises(exc):
            from_roman(s)


def test_to_roman_known_values():
    for n, s in KNOWN.items():
        assert to_roman(n) == s, n


def test_from_roman_known_values():
    for n, s in KNOWN.items():
        assert from_roman(s) == n, s


def test_subtractive_pairs():
    assert [to_roman(n) for n in (4, 9, 40, 90, 400, 900)] == ['IV', 'IX', 'XL', 'XC', 'CD', 'CM']


def test_round_trip_every_value():
    seen = set()
    for n in range(1, 4000):
        s = to_roman(n)
        assert from_roman(s) == n
        seen.add(s)
    assert len(seen) == 3999


@pytest.mark.parametrize('n', [0, -1, 4000])
def test_to_roman_out_of_range(n):
    with pytest.raises(ValueError):
        to_roman(n)


def test_to_roman_type_errors():
    for n in (1.0, '5', None):
        with pytest.raises(TypeError):
            to_roman(n)


def test_to_roman_rejects_bool():
    for n in (True, False):
        with pytest.raises(TypeError):
            to_roman(n)


def test_repeats_rejected():
    assert_rejected(['IIII', 'XXXX', 'CCCC', 'MMMM', 'VV', 'LL', 'DD'], ValueError)


def test_invalid_subtractions_rejected():
    assert_rejected(['VX', 'IC', 'XM', 'IL', 'VL', 'XD', 'LC', 'DM', 'IIV', 'IIX'], ValueError)


def test_repeated_or_misordered_groups_rejected():
    assert_rejected(['CMCM', 'IXIX', 'IXI', 'CDC', 'XCX', 'MCMC', 'IVI', 'XLX'], ValueError)


def test_empty_string_rejected():
    assert_rejected([''], ValueError)


def test_case_and_whitespace_rejected():
    assert_rejected(['xiv', 'Xiv', 'mcmxciv', ' X', 'X ', 'X I', 'IV\n'], ValueError)


def test_other_characters_rejected():
    assert_rejected(['XA', '12', 'IVZ', 'X-I'], ValueError)


def test_from_roman_type_errors():
    assert_rejected([14, None, b'XIV', ['X']], TypeError)


def test_every_short_string_is_canonical_or_rejected():
    canonical = {to_roman(n): n for n in range(1, 4000)}
    for length in range(1, 5):
        for chars in itertools.product('IVXLCDM', repeat=length):
            s = ''.join(chars)
            if s in canonical:
                assert from_roman(s) == canonical[s]
            else:
                with pytest.raises(ValueError):
                    from_roman(s)
