"""Command parser: one line of player input to a Command."""

from __future__ import annotations

from typing import NamedTuple

from .world import DIRECTIONS

ARTICLES = {'the', 'a', 'an'}
SHORT = {d[0]: d for d in DIRECTIONS}


class ParseError(ValueError):
    pass


class Command(NamedTuple):
    verb: str
    arg: str | None = None


def _direction(word: str) -> str | None:
    if word in DIRECTIONS:
        return word
    return SHORT.get(word)


def _need(words: list[str], question: str) -> str:
    if not words:
        raise ParseError(question)
    return ' '.join(words)


def parse(line: str) -> Command:
    words = line.lower().split()
    if not words:
        raise ParseError('Say something.')
    verb, rest = words[0], [w for w in words[1:] if w not in ARTICLES]
    direction = _direction(verb)
    if direction:
        if rest:
            raise ParseError("I don't understand that.")
        return Command('go', direction)
    if verb == 'go':
        if not rest:
            raise ParseError('Go where?')
        target = _direction(rest[0]) if len(rest) == 1 else None
        if target is None:
            raise ParseError(f'"{" ".join(rest)}" is not a direction.')
        return Command('go', target)
    if verb in ('take', 'get'):
        return Command('take', _need(rest, 'Take what?'))
    if verb == 'drop':
        return Command('drop', _need(rest, 'Drop what?'))
    if verb in ('look', 'l'):
        if rest and rest[0] == 'at':
            return Command('look', _need(rest[1:], 'Examine what?'))
        return Command('look', ' '.join(rest) if rest else None)
    if verb in ('examine', 'x'):
        return Command('look', _need(rest, 'Examine what?'))
    if verb == 'use':
        return Command('use', _need(rest, 'Use what?'))
    if verb == 'score':
        if rest:
            raise ParseError("I don't understand that.")
        return Command('score', None)
    if verb in ('inventory', 'inv', 'i'):
        if rest:
            raise ParseError("I don't understand that.")
        return Command('inventory', None)
    raise ParseError(f'I don\'t know the word "{verb}".')
