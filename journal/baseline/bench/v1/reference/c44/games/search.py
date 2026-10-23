"""Negamax with alpha-beta pruning over any state with the shared game interface."""
import random
from dataclasses import dataclass
from typing import Any, Protocol

WIN = 1000
INF = float('inf')


class Game(Protocol):
    """The interface every game state offers; the search relies on nothing else."""

    player: str

    def moves(self) -> list[Any]:
        """Legal moves in ascending order; [] once the game is over."""

    def play(self, move) -> 'Game':
        """A new state with the move made."""

    def winner(self) -> str | None:
        """'X', 'O' or None."""

    def is_over(self) -> bool:
        """True when there is a winner or the board is full."""


@dataclass(frozen=True)
class SearchResult:
    score: float
    move: object
    nodes: int


class _Search:
    def __init__(self, depth, evaluate):
        self.depth = depth
        self.evaluate = evaluate
        self.nodes = 0

    def value(self, state, ply: int, alpha: float, beta: float):
        """(score for the player to move, best move)."""
        self.nodes += 1
        if state.is_over():
            if state.winner() is None:
                return 0, None
            return -(WIN - ply), None
        if self.depth is not None and ply >= self.depth:
            return (self.evaluate(state) if self.evaluate else 0), None
        best, best_move = -INF, None
        for move in state.moves():
            child, _ = self.value(state.play(move), ply + 1, -beta, -alpha)
            score = -child
            if score > best:
                best, best_move = score, move
            if best > alpha:
                alpha = best
            if alpha >= beta:
                break
        return best, best_move


def search(state, depth=None, evaluate=None) -> SearchResult:
    """Negamax value and best move of `state` for its player to move."""
    s = _Search(depth, evaluate)
    score, move = s.value(state, 0, -INF, INF)
    return SearchResult(score, move, s.nodes)


def best_move(state, depth=None, evaluate=None):
    """The move search() picks; ValueError on a finished game."""
    if state.is_over():
        raise ValueError('the game is over')
    return search(state, depth, evaluate).move


def search_agent(depth=None, evaluate=None):
    """An agent that plays the search's best move."""
    def agent(state):
        return best_move(state, depth, evaluate)
    return agent


def random_agent(seed):
    """An agent that plays uniformly random legal moves from its own seeded RNG."""
    rng = random.Random(seed)

    def agent(state):
        return rng.choice(state.moves())
    return agent


def play_game(state, agents: dict):
    """Play until the game is over: (final state, moves played)."""
    moves = []
    while not state.is_over():
        move = agents[state.player](state)
        state = state.play(move)
        moves.append(move)
    return state, moves
