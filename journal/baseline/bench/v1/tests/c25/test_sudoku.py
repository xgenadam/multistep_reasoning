import copy

import pytest

from sudoku import count_solutions, is_valid, parse, solve, to_string

PUZZLE = ('53..7....6..195....98....6.8...6...34..8.3..17...2...6'
          '.6....28....419..5....8..79')
SOLUTION = ('534678912672195348198342567859761423426853791713924856'
            '961537284287419635345286179')
# SOLUTION with one 2x2 "deadly rectangle" emptied: exactly two solutions
TWO = ('534..8912672195348198342567859..1423426853791713924856'
       '961537284287419635345286179')
# two independent rectangles emptied: exactly four solutions
FOUR = ('534..89126721953..198342567859..14234268537917139248569'
        '615372..287419635345286179')
# row 0 needs a 9 in column 0, but column 0 already has one: valid, unsolvable
DEAD = '.12345678' + '9........' + '.' * 63


def consistent(puzzle, solved):
    return all(p == 0 or p == s for pr, sr in zip(puzzle, solved) for p, s in zip(pr, sr))


def test_parse_and_to_string_round_trip():
    g = parse(PUZZLE)
    assert len(g) == 9 and all(len(r) == 9 for r in g)
    assert g[0] == [5, 3, 0, 0, 7, 0, 0, 0, 0]
    assert to_string(g) == PUZZLE


def test_parse_zero_whitespace_and_newlines():
    text = '\n'.join(' '.join(PUZZLE[i:i + 9].replace('.', '0')) for i in range(0, 81, 9))
    assert parse(text + '\n\t') == parse(PUZZLE)


@pytest.mark.parametrize('text', [PUZZLE[:-1], PUZZLE + '1', PUZZLE[:-1] + 'x', PUZZLE[:-1] + '|', ''])
def test_parse_errors(text):
    with pytest.raises(ValueError):
        parse(text)


def test_is_valid():
    assert is_valid(parse(PUZZLE))
    assert is_valid(parse(SOLUTION))
    assert is_valid(parse('.' * 81))


def test_is_valid_detects_row_column_and_box_duplicates():
    row = parse('5.......5' + '.' * 72)
    col = parse('5' + '.' * 8 + '5' + '.' * 71)
    box0 = parse('5........' + '.5.......' + '.' * 63)  # same box, different row and column
    box5 = parse('.' * 27 + '.' * 6 + '7..' + '.' * 7 + '7.' + '.' * 36)  # rows 3-4, cols 6-8
    for g in (row, col, box0, box5):
        assert not is_valid(g)


def test_bad_shapes_raise():
    good = parse(PUZZLE)
    bad = [good[:8], [r[:8] for r in good], [r[:] for r in good]]
    bad[2][0][0] = 10
    for g in bad:
        with pytest.raises(ValueError):
            is_valid(g)
        with pytest.raises(ValueError):
            solve(g)
    with pytest.raises(ValueError):
        to_string(bad[0])


def test_solve_unique():
    g = parse(PUZZLE)
    assert to_string(solve(g)) == SOLUTION


def test_solve_does_not_modify_and_returns_new_grid():
    g = parse(PUZZLE)
    before = copy.deepcopy(g)
    out = solve(g)
    assert g == before
    assert out is not g and all(a is not b for a, b in zip(out, g))


def test_solve_multi_solution_returns_a_valid_one():
    g = parse(TWO)
    out = solve(g)
    assert out is not None and is_valid(out)
    assert all(v != 0 for r in out for v in r)
    assert consistent(g, out)


def test_solve_empty_grid():
    out = solve(parse('.' * 81))
    assert is_valid(out) and all(v for r in out for v in r)


def test_solve_unsolvable_and_invalid():
    assert solve(parse(DEAD)) is None
    assert solve(parse('55' + '.' * 79)) is None


def test_solve_complete_grid():
    assert to_string(solve(parse(SOLUTION))) == SOLUTION


def test_count_solutions():
    assert count_solutions(parse(PUZZLE)) == 1
    assert count_solutions(parse(TWO)) == 2
    assert count_solutions(parse(TWO), limit=10) == 2
    assert count_solutions(parse(FOUR), limit=10) == 4
    assert count_solutions(parse(FOUR), limit=3) == 3
    assert count_solutions(parse(TWO), limit=1) == 1
    assert count_solutions(parse('.' * 81)) == 2


def test_count_solutions_unsolvable_invalid_and_limit():
    assert count_solutions(parse(DEAD)) == 0
    assert count_solutions(parse('55' + '.' * 79)) == 0
    with pytest.raises(ValueError):
        count_solutions(parse(PUZZLE), limit=0)


def test_count_does_not_modify():
    g = parse(FOUR)
    before = copy.deepcopy(g)
    count_solutions(g, limit=10)
    assert g == before
