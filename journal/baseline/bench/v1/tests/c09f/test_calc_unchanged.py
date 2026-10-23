from fractions import Fraction

import pytest

from calc import CalcError, evaluate

F = Fraction


def error_at(expr):
    with pytest.raises(CalcError) as info:
        evaluate(expr)
    return info.value.position


def test_integers_and_precedence():
    assert evaluate('1 + 2 * 3') == 7
    assert evaluate('(1 + 2) * 3') == 9
    assert evaluate('2 * 3 + 4 * 5') == 26


def test_result_is_always_a_fraction():
    for expr in ['4', '2 * 3', '1 / 3', '0.5 + 0.5']:
        assert type(evaluate(expr)) is Fraction


def test_exact_decimals():
    assert evaluate('0.1 + 0.2') == F(3, 10)
    assert evaluate('12.50') == F(25, 2)
    assert evaluate('1 / 3 * 3') == 1


def test_division_is_exact():
    assert evaluate('7 / 2') == F(7, 2)
    assert evaluate('1 / 3 + 1 / 6') == F(1, 2)


def test_left_associativity():
    assert evaluate('8 - 3 - 2') == 3
    assert evaluate('8 / 4 / 2') == 1
    assert evaluate('2 - 3 + 4') == 3
    assert evaluate('12 / 3 * 2') == 8


def test_unary_minus():
    assert evaluate('-3 * 2') == -6
    assert evaluate('2 * -3') == -6
    assert evaluate('2 - -3') == 5
    assert evaluate('--4') == 4
    assert evaluate('-(2 + 3)') == -5
    assert evaluate('- - - 1') == -1


def test_whitespace_and_tabs():
    assert evaluate(' \t1+\t2 ') == 3
    assert evaluate('((2))*(3)') == 6


def test_deep_nesting():
    assert evaluate('(' * 50 + '1' + ')' * 50) == 1


def test_syntax_error_positions_from_the_spec():
    cases = {'1 + * 2': 4, '1 2': 2, '(1 + 2': 6, '1 + 2)': 5, '()': 1,
             '2 $ 3': 2, '1.5.2': 3, '': 0, '3 +': 3}
    assert {e: error_at(e) for e in cases} == cases


def test_number_forms():
    assert error_at('.5') == 0
    assert error_at('5.') == 1
    assert error_at('5. + 1') == 1


def test_unary_plus_is_not_allowed():
    assert error_at('+1') == 0
    assert error_at('2 * +1') == 4


def test_more_syntax_errors():
    assert error_at('   ') == 3
    assert error_at('(1 + 2))') == 7
    assert error_at('2 (3)') == 2
    assert error_at('1 +\n2') == 3
    assert error_at('4 / ') == 4
    assert error_at('x') == 0


def test_division_by_zero_position():
    assert error_at('1 + 4 / (2 - 2)') == 6
    assert error_at('1 / 0') == 2
    assert error_at('0 / 0') == 2
    assert error_at('1/0.0') == 1


def test_first_division_by_zero_left_to_right():
    assert error_at('1 / 0 + 2 / 0') == 2
    assert error_at('(1 / 0) / 0') == 3
    assert error_at('5 / (1 - 1 / 1)') == 2


def test_syntax_error_wins_over_division_by_zero():
    assert error_at('1 / 0 +') == 7
    assert error_at('1 / 0 )') == 6


def test_calcerror_is_an_exception_with_position():
    try:
        evaluate('1 +')
    except CalcError as e:
        assert isinstance(e, Exception)
        assert isinstance(e.position, int)
    else:
        pytest.fail('no CalcError')
