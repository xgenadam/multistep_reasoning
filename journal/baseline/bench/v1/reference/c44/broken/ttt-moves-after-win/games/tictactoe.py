"""Tic-tac-toe as an immutable game state."""

LINES = ((0, 1, 2), (3, 4, 5), (6, 7, 8),
         (0, 3, 6), (1, 4, 7), (2, 5, 8),
         (0, 4, 8), (2, 4, 6))


class TicTacToe:
    __slots__ = ('board', 'player', '_winner')

    def __init__(self, board: str = '.........'):
        if not isinstance(board, str) or len(board) != 9:
            raise ValueError('a board is 9 characters')
        if set(board) - set('XO.'):
            raise ValueError('board characters must be X, O or .')
        x, o = board.count('X'), board.count('O')
        if x - o not in (0, 1):
            raise ValueError('impossible mark counts')
        self.board = board
        self.player = 'X' if x == o else 'O'
        self._winner = self._find_winner()

    @classmethod
    def from_moves(cls, moves) -> 'TicTacToe':
        """Play `moves` in order from the empty board."""
        state = cls()
        for move in moves:
            state = state.play(move)
        return state

    def _find_winner(self):
        for a, b, c in LINES:
            if self.board[a] != '.' and self.board[a] == self.board[b] == self.board[c]:
                return self.board[a]
        return None

    def winner(self):
        """'X' or 'O' with three in a line, else None."""
        return self._winner

    def is_over(self) -> bool:
        """A winner, or no empty square left."""
        return self._winner is not None or '.' not in self.board

    def moves(self) -> list[int]:
        """Empty squares in ascending order; none once the game is over."""
        if '.' not in self.board:
            return []
        return [i for i, ch in enumerate(self.board) if ch == '.']

    def play(self, move: int) -> 'TicTacToe':
        """A new state with `move` made by the player to move."""
        if self.is_over():
            raise ValueError('the game is over')
        if not isinstance(move, int) or not 0 <= move <= 8 or self.board[move] != '.':
            raise ValueError(f'illegal move {move!r}')
        return TicTacToe(self.board[:move] + self.player + self.board[move + 1:])

    def __str__(self) -> str:
        return '\n'.join(self.board[i:i + 3] for i in (0, 3, 6))

    def __repr__(self) -> str:
        return f'TicTacToe({self.board!r})'

    def __eq__(self, other) -> bool:
        return isinstance(other, TicTacToe) and other.board == self.board

    def __hash__(self) -> int:
        return hash(('ttt', self.board))
