import dataclasses

import pytest

from games import (ConnectFour, SearchResult, TicTacToe, best_move, connect4_evaluate, play_game,
                   random_agent, search, search_agent)


def test_empty_board_is_a_draw_with_pruning():
    r = search(TicTacToe())
    assert isinstance(r, SearchResult)
    assert r.score == 0 and r.move == 0  # every move draws; the first one is chosen
    assert 9 < r.nodes < 100_000
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.score = 1


def test_takes_the_immediate_win():
    r = search(TicTacToe('XX.OO....'))
    assert (r.score, r.move) == (999, 2)


def test_prefers_the_quickest_win():
    # X wins at once with 6; squares 4, 5 and 8 also win, but later
    r = search(TicTacToe('XOOX.....'))
    assert (r.score, r.move) == (999, 6)


def test_blocks_the_threat():
    r = search(TicTacToe('XX..O....'))
    assert (r.score, r.move) == (0, 2)
    r = search(TicTacToe('X...O...X'))  # O must take an edge, not a corner
    assert (r.score, r.move) == (0, 1)


def test_lost_position_prefers_the_slowest_loss():
    # O to move and lost: blocking at 6 loses on X's second move, anything else on the first
    r = search(TicTacToe('XO.X.....'))
    assert (r.score, r.move) == (-996, 6)


def test_finished_root():
    won = TicTacToe.from_moves([0, 3, 1, 4, 2])  # X has won, O to move
    assert search(won) == SearchResult(-1000, None, 1)
    draw = TicTacToe('XOXXOOOXX')
    assert search(draw) == SearchResult(0, None, 1)
    for state in (won, draw):
        with pytest.raises(ValueError):
            best_move(state)


def test_depth_zero_evaluates_the_root():
    calls = []

    def ev(state):
        calls.append(state)
        return 42

    assert search(TicTacToe(), depth=0, evaluate=ev) == SearchResult(42, None, 1)
    assert calls == [TicTacToe()]


def test_depth_one_uses_evaluate_for_the_player_to_move():
    def ev(state):  # bad for the player to move if the opponent holds the centre
        other = 'O' if state.player == 'X' else 'X'
        return -5 if state.board[4] == other else 0

    r = search(TicTacToe(), depth=1, evaluate=ev)
    assert (r.score, r.move, r.nodes) == (5, 4, 10)


def test_depth_counts_moves():
    s = ConnectFour.from_moves([3, 3, 2, 2])  # X wins in 3 moves with 1 or 4
    assert search(s, depth=2).score == 0
    assert search(s, depth=2).move == 0
    deep = search(s, depth=3)
    assert (deep.score, deep.move) == (997, 1)


def test_connect4_immediate_win_and_block():
    s = ConnectFour.from_moves([0, 6, 1, 6, 2])  # O to move, X threatens column 3
    assert best_move(s, depth=2) == 3
    t = ConnectFour.from_moves([0, 6, 1, 6, 2, 6])  # X to move, wins with 3
    assert search(t, depth=4).score == 999 and best_move(t, depth=1) == 3


def test_connect4_heuristic_prefers_the_centre():
    r = search(ConnectFour(), depth=1, evaluate=connect4_evaluate)
    assert (r.score, r.move) == (7, 3)
    assert best_move(ConnectFour(), depth=1, evaluate=connect4_evaluate) == 3


def test_perfect_play_draws_with_known_line():
    final, moves = play_game(TicTacToe(), {'X': search_agent(), 'O': search_agent()})
    assert final.winner() is None and final.is_over()
    assert moves == [0, 4, 1, 2, 6, 3, 5, 7, 8]
    assert final == TicTacToe('XXOOOXXOX')


@pytest.mark.parametrize('seed', range(4))
def test_perfect_player_never_loses(seed):
    perfect = search_agent()
    for side in ('X', 'O'):
        other = 'O' if side == 'X' else 'X'
        final, moves = play_game(TicTacToe(), {side: perfect, other: random_agent(seed)})
        assert final.winner() in (side, None)
        assert final == TicTacToe.from_moves(moves)


def test_random_agent_is_seeded_and_play_game_validates():
    a = play_game(ConnectFour(5, 4), {'X': random_agent(3), 'O': random_agent(4)})
    b = play_game(ConnectFour(5, 4), {'X': random_agent(3), 'O': random_agent(4)})
    assert a[1] == b[1] and a[0] == b[0] and a[0].is_over()
    assert a[0] == ConnectFour.from_moves(a[1], 5, 4)
    with pytest.raises(ValueError):
        play_game(TicTacToe(), {'X': lambda s: 0, 'O': lambda s: 0})


def test_search_leaves_the_state_alone():
    s = TicTacToe('X...O....')
    search(s)
    assert s.board == 'X...O....' and s.player == 'X'
