def _check(grid):
    if (not isinstance(grid, list) or len(grid) != 9
            or any(not isinstance(r, list) or len(r) != 9 for r in grid)
            or any(type(v) is not int or not 0 <= v <= 9 for r in grid for v in r)):
        raise ValueError('a grid is 9 lists of 9 ints from 0 to 9')


def parse(text):
    cells = []
    for ch in text:
        if ch.isspace():
            continue
        if ch == '.':
            cells.append(0)
        elif ch in '0123456789':
            cells.append(int(ch))
        else:
            raise ValueError(f'unexpected character {ch!r}')
    if len(cells) != 81:
        raise ValueError(f'expected 81 cells, got {len(cells)}')
    return [cells[i:i + 9] for i in range(0, 81, 9)]


def to_string(grid):
    _check(grid)
    return ''.join(str(v) if v else '.' for r in grid for v in r)


def _units():
    for i in range(9):
        yield [(i, c) for c in range(9)]
        yield [(r, i) for r in range(9)]
        br, bc = 3 * (i // 3), 3 * (i % 3)
        yield [(br + dr, bc + dc) for dr in range(3) for dc in range(3)]


def is_valid(grid):
    _check(grid)
    for unit in _units():
        seen = [grid[r][c] for r, c in unit if grid[r][c]]
        if len(seen) != len(set(seen)):
            return False
    return True


def _candidates(g, r, c):
    used = set(g[r]) | {g[i][c] for i in range(9)}
    br, bc = r - r % 3, c - c % 3
    used |= {g[br + i][bc + j] for i in range(3) for j in range(3)}
    return [d for d in range(1, 10) if d not in used]


def _search(g, limit, found):
    """Fill g in place by backtracking; append solutions to found until limit."""
    best = None
    for r in range(9):
        for c in range(9):
            if g[r][c] == 0:
                cands = _candidates(g, r, c)
                if best is None or len(cands) < len(best[2]):
                    best = (r, c, cands)
                    if not cands:
                        return
    if best is None:
        found.append([row[:] for row in g])
        return
    r, c, cands = best
    for d in cands:
        g[r][c] = d
        _search(g, limit, found)
        g[r][c] = 0
        if len(found) >= limit:
            return


def solve(grid):
    if not is_valid(grid):
        return None
    found = []
    _search([row[:] for row in grid], 1, found)
    return found[0] if found else None


def count_solutions(grid, limit=2):
    if limit < 1:
        raise ValueError('limit must be at least 1')
    if not is_valid(grid):
        return 0
    found = []
    _search([row[:] for row in grid], limit, found)
    return len(found)


_KINDS = ('row', 'column', 'box')


def _unit_cells(kind, i):
    if kind == 'row':
        return [(i, c) for c in range(9)]
    if kind == 'column':
        return [(r, i) for r in range(9)]
    br, bc = 3 * (i // 3), 3 * (i % 3)
    return [(br + dr, bc + dc) for dr in range(3) for dc in range(3)]


def _hint(g):
    for kind in _KINDS:
        for i in range(9):
            cells = _unit_cells(kind, i)
            present = {g[r][c] for r, c in cells}
            empties = [(r, c, _candidates(g, r, c)) for r, c in cells if g[r][c] == 0]
            for d in range(1, 10):
                if d in present:
                    continue
                spots = [(r, c) for r, c, cands in empties if d in cands]
                if len(spots) == 1:
                    r, c = spots[0]
                    return r, c, d, f'hidden single in {kind}'
    for r in range(9):
        for c in range(9):
            if g[r][c] == 0:
                cands = _candidates(g, r, c)
                if len(cands) == 1:
                    return r, c, cands[0], 'naked single'
    return None


def hint(grid):
    if not is_valid(grid):
        raise ValueError('grid is not valid')
    return _hint(grid)


def difficulty(grid):
    if not is_valid(grid):
        raise ValueError('grid is not valid')
    g = [row[:] for row in grid]
    counts = {'naked': 0, 'hidden': 0}
    while any(v == 0 for row in g for v in row):
        step = _hint(g)
        if step is None:
            return None
        r, c, d, reason = step
        g[r][c] = d
        counts['naked' if reason == 'naked single' else 'hidden'] += 1
    return counts
