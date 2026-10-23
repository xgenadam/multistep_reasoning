import copy

import pytest

from sudoku import difficulty, hint, parse

SOLUTION = ('534678912672195348198342567859761423426853791713924856'
            '961537284287419635345286179')
PUZZLE = ('53..7....6..195....98....6.8...6...34..8.3..17...2...6'
          '.6....28....419..5....8..79')
# solvable with singles only, and needs hidden singles along the way
MIXED = ('..4.....267.....4.19..4.56..5.76....42..53.9..1.9..8...'
         '...372.4....1.635..5..6...')
# SOLUTION with a 2x2 "deadly rectangle" emptied: two solutions, no singles
TWO = ('534..8912672195348198342567859..1423426853791713924856'
       '961537284287419635345286179')


def grid(cells):
    g = [[0] * 9 for _ in range(9)]
    for (r, c), d in cells.items():
        g[r][c] = d
    return g


def blank(text, *cells):
    g = parse(text)
    for r, c in cells:
        g[r][c] = 0
    return g


def test_naked_single():
    assert hint(blank(SOLUTION, (4, 4))) == (4, 4, 5, 'naked single')


def test_naked_singles_scan_row_major():
    g = blank(SOLUTION, (1, 0), (0, 5))
    assert hint(g) == (0, 5, 8, 'naked single')


def test_hidden_single_in_row():
    g = grid({(1, 3): 1, (2, 6): 1, (3, 1): 1, (6, 2): 1})
    assert hint(g) == (0, 0, 1, 'hidden single in row')


def test_hidden_single_in_column():
    # row 0 still has four places for 1, but column 0 only one
    g = grid({(1, 4): 1, (4, 1): 1, (7, 2): 1, (2, 0): 2})
    assert hint(g) == (0, 0, 1, 'hidden single in column')


def test_hidden_single_in_box():
    g = grid({(1, 4): 1, (7, 2): 1, (0, 1): 5, (2, 0): 2, (2, 1): 3, (2, 2): 4})
    assert hint(g) == (0, 0, 1, 'hidden single in box')


def test_naked_comes_before_hidden():
    assert hint(parse(PUZZLE)) == (4, 4, 5, 'naked single')
    assert hint(parse(MIXED)) == (5, 4, 2, 'naked single')


def test_no_hint():
    assert hint(parse(SOLUTION)) is None
    assert hint(parse('.' * 81)) is None
    assert hint(parse(TWO)) is None


def test_hint_invalid_raises_and_does_not_modify():
    with pytest.raises(ValueError):
        hint(parse('55' + '.' * 79))
    with pytest.raises(ValueError):
        hint([[0] * 9] * 8)
    g = parse(PUZZLE)
    before = copy.deepcopy(g)
    hint(g)
    assert g == before


def test_difficulty_complete_grid():
    assert difficulty(parse(SOLUTION)) == {'naked': 0, 'hidden': 0}


def test_difficulty_naked_only():
    # one blank per row, column and box: every step is a naked single
    cells = [(0, 0), (1, 3), (2, 6), (3, 1), (4, 4), (5, 7), (6, 2), (7, 5), (8, 8)]
    assert difficulty(blank(SOLUTION, *cells)) == {'naked': 9, 'hidden': 0}
    assert difficulty(parse(PUZZLE)) == {'naked': 51, 'hidden': 0}


def test_difficulty_mixed():
    assert difficulty(parse(MIXED)) == {'naked': 38, 'hidden': 12}


def test_difficulty_needs_guessing():
    assert difficulty(parse(TWO)) is None
    assert difficulty(parse('.' * 81)) is None
    # progress is possible at first, but singles run out
    g = grid({(1, 3): 1, (2, 6): 1, (3, 1): 1, (6, 2): 1})
    assert difficulty(g) is None


def test_difficulty_invalid_and_not_modified():
    with pytest.raises(ValueError):
        difficulty(parse('5' + '.' * 8 + '5' + '.' * 71))
    g = parse(MIXED)
    before = copy.deepcopy(g)
    difficulty(g)
    assert g == before
