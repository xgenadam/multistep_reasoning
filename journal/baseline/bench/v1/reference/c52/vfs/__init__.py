"""An in-memory filesystem and a tiny shell for it."""

from .fs import (AlreadyExists, FileSystem, FSError, InvalidOperation, IsADirectory,
                 NotADirectory, NotFound)
from .paths import is_within, join, normalize, split
from .shell import Shell

__all__ = ['FileSystem', 'Shell', 'FSError', 'NotFound', 'AlreadyExists', 'NotADirectory',
           'IsADirectory', 'InvalidOperation', 'normalize', 'join', 'split', 'is_within']
