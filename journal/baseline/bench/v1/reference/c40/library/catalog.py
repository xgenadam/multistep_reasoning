"""Books and members."""
from dataclasses import dataclass

from .fines import POLICY


@dataclass
class Book:
    isbn: str
    title: str
    author: str
    copies: int


@dataclass
class Member:
    member_id: str
    name: str
    kind: str


class Catalog:
    def __init__(self):
        self._books: dict[str, Book] = {}
        self._members: dict[str, Member] = {}

    def add_book(self, isbn: str, title: str, author: str, copies: int = 1) -> Book:
        if isbn in self._books:
            raise ValueError(f'duplicate isbn {isbn!r}')
        if copies < 1:
            raise ValueError('copies must be at least 1')
        book = Book(isbn, title, author, copies)
        self._books[isbn] = book
        return book

    def add_copies(self, isbn: str, n: int) -> int:
        book = self.book(isbn)
        if n < 1:
            raise ValueError('n must be at least 1')
        book.copies += n
        return book.copies

    def add_member(self, member_id: str, name: str, kind: str = 'standard') -> Member:
        if member_id in self._members:
            raise ValueError(f'duplicate member {member_id!r}')
        if kind not in POLICY:
            raise ValueError(f'unknown member kind {kind!r}')
        member = Member(member_id, name, kind)
        self._members[member_id] = member
        return member

    def book(self, isbn: str) -> Book:
        return self._books[isbn]

    def member(self, member_id: str) -> Member:
        return self._members[member_id]

    def search(self, text: str) -> list[Book]:
        needle = text.casefold()
        found = [b for b in self._books.values()
                 if needle in b.title.casefold() or needle in b.author.casefold()]
        return sorted(found, key=lambda b: (b.title, b.isbn))
