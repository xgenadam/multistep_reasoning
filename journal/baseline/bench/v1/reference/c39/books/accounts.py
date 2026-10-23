"""Chart of accounts: a tree of typed accounts."""
import enum
from dataclasses import dataclass


class AccountType(enum.Enum):
    ASSET = 'asset'
    LIABILITY = 'liability'
    EQUITY = 'equity'
    INCOME = 'income'
    EXPENSE = 'expense'

    @property
    def debit_normal(self) -> bool:
        return self in (AccountType.ASSET, AccountType.EXPENSE)


@dataclass(frozen=True)
class Account:
    code: str
    name: str
    type: AccountType
    parent: str | None = None


class Chart:
    def __init__(self):
        self._accounts: dict[str, Account] = {}
        self._children: dict[str, list[str]] = {}

    def add(self, code, name, type, parent=None) -> Account:
        if not isinstance(code, str) or not code.isdigit() or not code.isascii():
            raise ValueError(f'account code must be a string of digits, got {code!r}')
        try:
            acc_type = AccountType(type)
        except ValueError:
            raise ValueError(f'unknown account type {type!r}') from None
        if code in self._accounts:
            raise ValueError(f'account {code} already exists')
        if parent is not None:
            if parent not in self._accounts:
                raise ValueError(f'parent account {parent} does not exist')
            if self._accounts[parent].type is not acc_type:
                raise ValueError(f'account {code} must have the same type as its parent {parent}')
        account = Account(code, name, acc_type, parent)
        self._accounts[code] = account
        self._children[code] = []
        if parent is not None:
            self._children[parent].append(code)
            self._children[parent].sort()
        return account

    def get(self, code) -> Account:
        try:
            return self._accounts[code]
        except KeyError:
            raise KeyError(code) from None

    def __contains__(self, code) -> bool:
        return code in self._accounts

    def children(self, code) -> list[Account]:
        self.get(code)
        return [self._accounts[c] for c in self._children[code]]

    def roots(self) -> list[Account]:
        return [a for c, a in sorted(self._accounts.items()) if a.parent is None]

    def is_leaf(self, code) -> bool:
        self.get(code)
        return not self._children[code]

    def walk(self) -> list[tuple[Account, int]]:
        out: list[tuple[Account, int]] = []

        def visit(account: Account, depth: int) -> None:
            out.append((account, depth))
            for child in self.children(account.code):
                visit(child, depth + 1)

        for root in self.roots():
            visit(root, 0)
        return out

    def subtree(self, code) -> list[str]:
        """The code and all its descendants' codes."""
        codes = [code]
        for child in self._children[code]:
            codes.extend(self.subtree(child))
        return codes
