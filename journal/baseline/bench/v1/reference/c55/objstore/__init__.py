"""A git-style content-addressed object store."""

from .diff import Change, diff_commits, diff_trees, format_changes
from .objects import (Blob, Commit, CorruptObject, Tree, TreeEntry, object_id, parse_object,
                      serialize)
from .store import AmbiguousPrefix, ObjectNotFound, ObjectStore

__all__ = ['Blob', 'Tree', 'TreeEntry', 'Commit', 'serialize', 'object_id', 'parse_object',
           'CorruptObject', 'ObjectStore', 'ObjectNotFound', 'AmbiguousPrefix', 'Change',
           'diff_trees', 'diff_commits', 'format_changes']
