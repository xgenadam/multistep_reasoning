"""A from-scratch JSON parser and serializer."""

from .dump import dumps
from .parser import loads
from .scanner import JSONError, Token, tokenize

__all__ = ['loads', 'dumps', 'tokenize', 'Token', 'JSONError']
