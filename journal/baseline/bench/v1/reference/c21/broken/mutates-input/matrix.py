from fractions import Fraction


class MatrixError(Exception):
    pass


class ShapeError(MatrixError):
    pass


class SingularMatrix(MatrixError):
    pass


def _element(x):
    if isinstance(x, bool) or not isinstance(x, (int, Fraction)):
        raise TypeError(f'matrix elements must be int or Fraction, not {type(x).__name__}')
    return Fraction(x)


def _matrix(m):
    if not isinstance(m, list) or not m or not all(isinstance(r, list) for r in m):
        raise ShapeError('a matrix is a non-empty list of lists')
    width = len(m[0])
    if width == 0 or any(len(r) != width for r in m):
        raise ShapeError('rows must be non-empty and of equal length')
    for r in m:
        for i, x in enumerate(r):
            r[i] = _element(x)
    return m


def _square(m):
    rows = _matrix(m)
    if len(rows) != len(rows[0]):
        raise ShapeError('matrix must be square')
    return rows


def _eliminate(rows, rhs):
    """Gauss-Jordan in place on copies; return the determinant (0 if singular)."""
    n = len(rows)
    det = Fraction(1)
    for col in range(n):
        pivot = next((r for r in range(col, n) if rows[r][col] != 0), None)
        if pivot is None:
            return Fraction(0)
        if pivot != col:
            rows[col], rows[pivot] = rows[pivot], rows[col]
            rhs[col], rhs[pivot] = rhs[pivot], rhs[col]
            det = -det
        p = rows[col][col]
        det *= p
        rows[col] = [x / p for x in rows[col]]
        rhs[col] = [x / p for x in rhs[col]]
        for r in range(n):
            if r != col and rows[r][col] != 0:
                f = rows[r][col]
                rows[r] = [a - f * b for a, b in zip(rows[r], rows[col])]
                rhs[r] = [a - f * b for a, b in zip(rhs[r], rhs[col])]
    return det


def det(m):
    rows = _square(m)
    return _eliminate(rows, [[] for _ in rows])


def identity(n):
    if n < 1:
        raise ValueError('n must be at least 1')
    return [[Fraction(int(i == j)) for j in range(n)] for i in range(n)]


def inverse(m):
    rows = _square(m)
    rhs = identity(len(rows))
    if _eliminate(rows, rhs) == 0:
        raise SingularMatrix('matrix is singular')
    return rhs


def solve(a, b):
    rows = _square(a)
    if not isinstance(b, list) or len(b) != len(rows):
        raise ShapeError('b must be a list with one entry per row of a')
    rhs = [[_element(x)] for x in b]
    if _eliminate(rows, rhs) == 0:
        raise SingularMatrix('matrix is singular')
    return [r[0] for r in rhs]


def matmul(a, b):
    ra, rb = _matrix(a), _matrix(b)
    if len(ra[0]) != len(rb):
        raise ShapeError('columns of a must equal rows of b')
    cols = list(zip(*rb))
    return [[sum((x * y for x, y in zip(row, col)), Fraction(0)) for col in cols] for row in ra]
