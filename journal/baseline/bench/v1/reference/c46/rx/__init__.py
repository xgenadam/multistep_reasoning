"""A small regular-expression engine: parser, Thompson NFA, linear-time matching."""

from .nfa import NFA, compile, findall, match, search
from .parse import (AnyChar, Alt, CharClass, Concat, Empty, Group, Literal, Optional, Plus,
                    RegexError, Star, parse)

__all__ = ['parse', 'compile', 'match', 'search', 'findall', 'RegexError', 'NFA',
           'Empty', 'Literal', 'AnyChar', 'CharClass', 'Concat', 'Alt', 'Star', 'Plus',
           'Optional', 'Group']
