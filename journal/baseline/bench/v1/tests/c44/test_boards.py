import pytest

from games import ConnectFour, TicTacToe, connect4_evaluate


def test_tictactoe_empty():
    t = TicTacToe()
    assert t.board == '.........' and t.player == 'X'
    assert t.moves() == list(range(9))
    assert t.winner() is None and not t.is_over()
    assert str(t) == '...\n...\n...'


@pytest.mark.parametrize('board', ['........', 'XA.......', 'OO.X.....'])
def test_tictactoe_bad_boards(board):
    with pytest.raises(ValueError):
        TicTacToe(board)


def test_tictactoe_play_is_immutable_and_alternates():
    t = TicTacToe()
    a = t.play(4)
    b = a.play(0)
    assert t.board == '.........'
    assert (a.board, a.player) == ('....X....', 'O')
    assert (b.board, b.player) == ('O...X....', 'X')
    assert b.moves() == [1, 2, 3, 5, 6, 7, 8]
    assert str(b) == 'O..\n.X.\n...'
    assert TicTacToe.from_moves([4, 0]) == b and hash(TicTacToe('O...X....')) == hash(b)
    assert TicTacToe.from_moves([]) == TicTacToe() and b != a


def test_tictactoe_illegal_moves():
    t = TicTacToe('X...O....')
    for move in (0, 4, 9, -1):
        with pytest.raises(ValueError):
            t.play(move)
    with pytest.raises(ValueError):
        TicTacToe.from_moves([0, 1, 0])


@pytest.mark.parametrize('moves, winner', [
    ([0, 3, 1, 4, 2], 'X'),          # top row
    ([1, 0, 2, 3, 4, 6], 'O'),       # left column
    ([0, 1, 4, 2, 8], 'X'),          # diagonal
    ([0, 2, 1, 4, 8, 6], 'O'),       # anti-diagonal
])
def test_tictactoe_wins(moves, winner):
    t = TicTacToe.from_moves(moves)
    assert t.winner() == winner and t.is_over() and t.moves() == []
    with pytest.raises(ValueError):
        t.play(next(i for i in range(9) if t.board[i] == '.'))


def test_tictactoe_draw():
    t = TicTacToe('XOXXOOOXX')
    assert t.winner() is None and t.is_over() and t.moves() == []


def test_connect4_empty_and_cells():
    c = ConnectFour()
    assert (c.columns, c.rows, c.player) == (7, 6, 'X')
    assert c.moves() == list(range(7))
    assert str(c) == '\n'.join(['.......'] * 6)
    assert c.cell(6, 5) == '.'
    for col, row in ((7, 0), (0, 6), (-1, 0)):
        with pytest.raises(IndexError):
            c.cell(col, row)
    for cols, rows in ((0, 6), (7, 0)):
        with pytest.raises(ValueError):
            ConnectFour(cols, rows)


def test_connect4_pieces_stack():
    c = ConnectFour.from_moves([3, 3, 4, 0, 3])
    assert c.cell(3, 0) == 'X' and c.cell(3, 1) == 'O' and c.cell(3, 2) == 'X'
    assert c.cell(4, 0) == 'X' and c.cell(0, 0) == 'O' and c.player == 'O'
    assert str(c) == '\n'.join(['.......'] * 3 + ['...X...', '...O...', 'O..XX..'])
    assert ConnectFour().play(3).play(3).play(4).play(0).play(3) == c


def test_connect4_full_column_and_range():
    c = ConnectFour.from_moves([0] * 6)
    assert c.moves() == [1, 2, 3, 4, 5, 6]
    for move in (0, 7, -1):
        with pytest.raises(ValueError):
            c.play(move)
    with pytest.raises(ValueError):
        ConnectFour.from_moves([0, 0, 0, 0, 0, 0, 0])


@pytest.mark.parametrize('moves, winner', [
    ([0, 0, 1, 1, 2, 2, 3], 'X'),                       # horizontal
    ([6, 0, 6, 0, 6, 0, 5, 0], 'O'),                    # vertical
    ([0, 1, 1, 2, 2, 3, 2, 3, 3, 6, 3], 'X'),           # diagonal up-right
    ([6, 5, 5, 4, 4, 3, 4, 3, 3, 0, 3], 'X'),           # diagonal up-left
])
def test_connect4_wins(moves, winner):
    c = ConnectFour.from_moves(moves)
    assert c.winner() == winner and c.is_over() and c.moves() == []
    with pytest.raises(ValueError):
        c.play(1 if winner == 'O' else 5)


def test_connect4_small_board_draw():
    c = ConnectFour.from_moves([0, 1, 2, 0, 1, 2], columns=3, rows=2)
    assert c.winner() is None and c.is_over() and c.moves() == []
    assert str(c) == 'OXO\nXOX'


def test_connect4_evaluate_by_hand():
    # one window on a 4x1 board
    assert connect4_evaluate(ConnectFour(4, 1)) == 0
    assert connect4_evaluate(ConnectFour.from_moves([0], 4, 1)) == -1        # O to move
    assert connect4_evaluate(ConnectFour.from_moves([0, 3], 4, 1)) == 0       # mixed window
    # 4x4: (0,0) lies in one horizontal, one vertical and one diagonal window
    assert connect4_evaluate(ConnectFour.from_moves([0], 4, 4)) == -3
    two = ConnectFour.from_moves([0, 3, 0], 4, 4)  # X (0,0),(0,1); O (3,0); O to move
    # X-only windows: column 0 (n=2) 4, row 1 (n=1) 1, diagonal (0,0)-(3,3) (n=1) 1
    # O-only windows: column 3 (n=1) 1, anti-diagonal (0,3)-(3,0) (n=1) 1; row 0 is mixed
    assert connect4_evaluate(two) == -(4 + 1 + 1) + (1 + 1)
