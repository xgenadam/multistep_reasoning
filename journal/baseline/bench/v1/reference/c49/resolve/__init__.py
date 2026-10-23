"""Package index, version ranges and a backtracking dependency resolver."""

from .index import PackageIndex
from .solver import ResolutionError, resolve
from .versions import Range, Version

__all__ = ['Version', 'Range', 'PackageIndex', 'resolve', 'ResolutionError']
