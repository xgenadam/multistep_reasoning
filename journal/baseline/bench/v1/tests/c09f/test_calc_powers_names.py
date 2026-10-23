from fractions import Fraction

import pytest

from calc import CalcError, evaluate

F = Fraction


def error_at(expr, variables=None):
    with pytest.raises(CalcError) as info:
        evaluate(expr, variables)
    return info.value.position


def test_power_basics():
    assert evaluate('2 ** 10') == 1024
    assert evaluate('(1/2) ** 2') == F(1, 4)
    assert evaluate('2 ** 0') == 1
    assert type(evaluate('3 ** 2')) is Fraction


def test_power_binds_tighter_than_unary_minus_and_groups_right():
    assert evaluate('-2 ** 2') == -4
    assert evaluate('(-2) ** 2') == 4
    assert evaluate('2 ** -1') == F(1, 2)
    assert evaluate('2 ** 3 ** 2') == 512
    assert evaluate('2 ** - - 2') == 4


def test_power_precedence_over_multiplication():
    assert evaluate('3 * 2 ** 2') == 12
    assert evaluate('2 ** 2 * 3') == 12
    assert evaluate('-3 ** 2 + 1') == -8


def test_spaced_stars_are_not_a_power():
    assert error_at('2 * * 3') == 4
    assert error_at('2 ** ** 3') == 5


def test_variables():
    env = {'x': 3, 'rate': F(1, 4), '_n2': -2}
    assert evaluate('x * x', env) == 9
    assert evaluate('rate * 8 + _n2', env) == 0
    assert evaluate('-x ** 2', env) == -9
    assert type(evaluate('x', env)) is Fraction


def test_functions():
    assert evaluate('abs(-3)') == 3
    assert evaluate('min(4, 2, 8)') == 2
    assert evaluate('max(1/3, 0.3)') == F(1, 3)
    assert evaluate('max(7)') == 7
    assert evaluate('abs (2 - 5) * 2') == 6
    assert evaluate('min(max(1, 2), abs(-1.5)) ** 2') == F(9, 4)


def test_function_arguments_are_full_expressions():
    env = {'a': 5, 'b': 2}
    assert evaluate('max(a - b * 3, -(a + b), a / b)', env) == F(5, 2)


def test_syntax_error_examples():
    cases = {'min(1,)': 6, 'max(': 4, 'abs(1 2)': 6, '1, 2': 1}
    assert {e: error_at(e) for e in cases} == cases


def test_more_call_syntax_errors():
    assert error_at('min(1, 2') == 8
    assert error_at('(1, 2)') == 2
    assert error_at('min(,1)') == 4
    assert error_at('2 ** ') == 5


def test_unknown_variable_position():
    assert error_at('1 + y', {'x': 1}) == 4
    assert error_at('x', None) == 0
    assert error_at('2 * total') == 4


def test_unknown_function_and_arity():
    assert error_at('1 + foo(2)') == 4
    assert error_at('2 * min()') == 4
    assert error_at('abs(1, 2)') == 0
    assert error_at('abs()') == 0


def test_name_and_arity_checked_before_arguments():
    assert error_at('foo(1 / 0)') == 0
    assert error_at('abs(1 / 0, 2)') == 0
    assert error_at('max(1, 2 / 0, y)') == 9


def test_power_errors():
    assert error_at('4 ** 0.5') == 2
    assert error_at('2 ** 2 ** -1') == 2
    assert error_at('0 ** -1') == 2
    assert evaluate('0 ** 0') == 1
    assert evaluate('4 ** (1/2 * 2)') == 4


def test_syntax_error_wins_over_evaluation_errors():
    assert error_at('unknown + ') == 10
    assert error_at('0 ** -1 )') == 8


def test_first_evaluation_error_left_to_right():
    assert error_at('a + 1 / 0') == 0
    assert error_at('1 / 0 + a') == 2
    assert error_at('min(b, a)', {'a': 1}) == 4
