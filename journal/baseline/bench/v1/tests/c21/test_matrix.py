import copy
from fractions import Fraction as F

import pytest

from matrix import (MatrixError, ShapeError, SingularMatrix, det, identity, inverse, matmul,
                    solve)


def test_det_small():
    assert det([[5]]) == 5
    assert det([[1, 2], [3, 4]]) == -2
    assert det([[2, 0, 1], [1, 3, 2], [1, 1, 1]]) == 0  # 2(3-2) - 0 + 1(1-3)
    assert det([[2, -3, 1], [2, 0, -1], [1, 4, 5]]) == 49


def test_det_returns_fraction():
    d = det([[1, 2], [3, 4]])
    assert isinstance(d, F)
    assert det([[F(1, 2), F(1, 3)], [F(1, 4), F(1, 5)]]) == F(1, 10) - F(1, 12)


def test_det_needs_row_swaps():
    # zero in the top-left corner: elimination must pivot, and the sign must flip
    assert det([[0, 1], [1, 0]]) == -1
    assert det([[0, 2, 1], [1, 0, 0], [0, 0, 3]]) == -6
    assert det([[0, 0, 1], [0, 1, 0], [1, 0, 0]]) == -1


def test_det_singular_is_zero():
    assert det([[1, 2], [2, 4]]) == 0
    assert det([[0, 0], [0, 0]]) == 0


def test_inverse():
    inv = inverse([[4, 7], [2, 6]])
    assert inv == [[F(3, 5), F(-7, 10)], [F(-1, 5), F(2, 5)]]
    assert all(isinstance(x, F) for row in inv for x in row)


def test_inverse_with_pivoting_times_original_is_identity():
    m = [[0, 2, 1], [1, 0, 0], [0, 1, 3]]
    assert matmul(m, inverse(m)) == identity(3)
    assert matmul(inverse(m), m) == identity(3)


def test_inverse_singular():
    with pytest.raises(SingularMatrix):
        inverse([[1, 2], [2, 4]])


def test_solve():
    a = [[2, 1, -1], [-3, -1, 2], [-2, 1, 2]]
    assert solve(a, [8, -11, -3]) == [2, 3, -1]
    x = solve([[0, 1], [3, 0]], [F(1, 2), 1])
    assert x == [F(1, 3), F(1, 2)]
    assert all(isinstance(v, F) for v in x)


def test_solve_singular_and_shapes():
    with pytest.raises(SingularMatrix):
        solve([[1, 1], [2, 2]], [1, 2])
    with pytest.raises(ShapeError):
        solve([[1, 0], [0, 1]], [1, 2, 3])
    with pytest.raises(ShapeError):
        solve([[1, 0, 0], [0, 1, 0]], [1, 2])


def test_matmul_rectangular():
    assert matmul([[1, 2, 3]], [[1], [2], [3]]) == [[14]]
    assert matmul([[1], [2]], [[3, 4]]) == [[3, 4], [6, 8]]
    with pytest.raises(ShapeError):
        matmul([[1, 2]], [[1, 2]])


def test_identity():
    assert identity(2) == [[1, 0], [0, 1]]
    assert all(isinstance(x, F) for row in identity(3) for x in row)
    with pytest.raises(ValueError):
        identity(0)


@pytest.mark.parametrize('bad', [[], [[]], [[1, 2], [3]], [1, 2], 'ab', [[1], [2, 3]]])
def test_shape_errors(bad):
    with pytest.raises(ShapeError):
        det(bad)


def test_not_square():
    for fn in (det, inverse):
        with pytest.raises(ShapeError):
            fn([[1, 2, 3], [4, 5, 6]])


def test_element_types():
    for bad in ([[1.0, 2], [3, 4]], [[True, 0], [0, 1]], [['1', 0], [0, 1]]):
        with pytest.raises(TypeError):
            det(bad)
    with pytest.raises(TypeError):
        solve([[1, 0], [0, 1]], [1.5, 2])


def test_exception_hierarchy():
    assert issubclass(ShapeError, MatrixError)
    assert issubclass(SingularMatrix, MatrixError)
    assert issubclass(MatrixError, Exception)


def test_inputs_not_modified():
    a = [[0, 2, 1], [1, 0, 0], [0, 1, 3]]
    b = [1, 2, 3]
    a0, b0 = copy.deepcopy(a), list(b)
    det(a)
    inverse(a)
    solve(a, b)
    matmul(a, a)
    assert a == a0 and b == b0
    assert all(type(x) is int for row in a for x in row)
