"""Connect-four as an immutable game state."""

DIRECTIONS = ((1, 0), (0, 1), (1, 1))


class ConnectFour:
    def __init__(self, columns: int = 7, rows: int = 6):
        if columns < 1 or rows < 1:
            raise ValueError('a board needs at least one column and one row')
        self.columns = columns
        self.rows = rows
        self._cols: tuple[str, ...] = ('',) * columns  # each column bottom-up
        self.player = 'X'
        self._winner = None
        self._count = 0

    @classmethod
    def from_moves(cls, moves, columns: int = 7, rows: int = 6) -> 'ConnectFour':
        """Play the given columns in order from an empty board."""
        state = cls(columns, rows)
        for move in moves:
            state = state.play(move)
        return state

    def _copy_with(self, column: int) -> 'ConnectFour':
        new = object.__new__(ConnectFour)
        new.columns, new.rows = self.columns, self.rows
        cols = list(self._cols)
        cols[column] += self.player
        new._cols = tuple(cols)
        new.player = 'O' if self.player == 'X' else 'X'
        new._count = self._count + 1
        new._winner = self.player if new._wins_at(column, len(cols[column]) - 1) else None
        return new

    def cell(self, column: int, row: int) -> str:
        """'X', 'O' or '.', row 0 at the bottom."""
        if not (0 <= column < self.columns and 0 <= row < self.rows):
            raise IndexError((column, row))
        col = self._cols[column]
        return col[row] if row < len(col) else '.'

    def _at(self, column: int, row: int) -> str | None:
        if 0 <= column < self.columns and 0 <= row < self.rows:
            return self.cell(column, row)
        return None

    def _wins_at(self, column: int, row: int) -> bool:
        """Whether the piece at (column, row) is part of four in a line."""
        me = self.cell(column, row)
        for dc, dr in DIRECTIONS:
            run = 1
            for sign in (1, -1):
                c, r = column + sign * dc, row + sign * dr
                while self._at(c, r) == me:
                    run += 1
                    c, r = c + sign * dc, r + sign * dr
            if run >= 4:
                return True
        return False

    def winner(self):
        """The player who completed four in a line, else None."""
        return self._winner

    def is_over(self) -> bool:
        """A winner, or every cell filled."""
        return self._winner is not None or self._count == self.columns * self.rows

    def moves(self) -> list[int]:
        """Columns that are not full, ascending; none once the game is over."""
        if self.is_over():
            return []
        return [c for c in range(self.columns) if len(self._cols[c]) < self.rows]

    def play(self, column: int) -> 'ConnectFour':
        """A new state with a piece dropped in `column`."""
        if self.is_over():
            raise ValueError('the game is over')
        if not isinstance(column, int) or not 0 <= column < self.columns \
                or len(self._cols[column]) >= self.rows:
            raise ValueError(f'illegal move {column!r}')
        return self._copy_with(column)

    def __str__(self) -> str:
        return '\n'.join(''.join(self.cell(c, r) for c in range(self.columns))
                         for r in range(self.rows - 1, -1, -1))

    def __repr__(self) -> str:
        return f'ConnectFour({self.columns}, {self.rows}, {self._cols!r})'

    def __eq__(self, other) -> bool:
        return (isinstance(other, ConnectFour) and other.columns == self.columns
                and other.rows == self.rows and other._cols == self._cols)

    def __hash__(self) -> int:
        return hash(('c4', self.columns, self.rows, self._cols))


def _windows(columns: int, rows: int):
    """Every line of four cells that fits on the board, as lists of (column, row)."""
    for c in range(columns):
        for r in range(rows):
            for dc, dr in DIRECTIONS:
                end_c, end_r = c + 3 * dc, r + 3 * dr
                if 0 <= end_c < columns and 0 <= end_r < rows:
                    yield [(c + i * dc, r + i * dr) for i in range(4)]


def evaluate(state: ConnectFour) -> int:
    """Sum of n*n over the one-player windows holding n (1..3) pieces, + for the mover."""
    total = 0
    for window in _windows(state.columns, state.rows):
        cells = [state.cell(c, r) for c, r in window]
        pieces = {ch for ch in cells if ch != '.'}
        if len(pieces) != 1:
            continue
        owner = pieces.pop()
        n = cells.count(owner)
        if n == 4:
            continue
        total += n * n if owner == state.player else -n * n
    return total
