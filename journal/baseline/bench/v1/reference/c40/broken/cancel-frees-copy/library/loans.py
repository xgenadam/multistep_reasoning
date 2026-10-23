"""Loans, renewals, holds and fine balances."""
from dataclasses import dataclass
from datetime import date, timedelta

from .catalog import Catalog
from .fines import HOLD_PICKUP_DAYS, POLICY, due_date, fine_for


class LoanError(Exception):
    pass


class Blocked(LoanError):
    pass


class DuplicateLoan(LoanError):
    pass


class LimitReached(LoanError):
    pass


class NotAvailable(LoanError):
    pass


class RenewalRefused(LoanError):
    pass


@dataclass
class Loan:
    loan_id: int
    member_id: str
    isbn: str
    start: date
    due: date
    renewals: int = 0
    returned: date | None = None
    fine: int = 0


@dataclass
class _Hold:
    member_id: str
    deadline: date | None = None  # None while waiting

    @property
    def ready(self) -> bool:
        return self.deadline is not None


class Library:
    def __init__(self, catalog: Catalog, clock):
        self.catalog = catalog
        self.clock = clock
        self._loans: dict[int, Loan] = {}
        self._next_id = 1
        self._queues: dict[str, list[_Hold]] = {}
        self._balance: dict[str, int] = {}

    # ------------------------------------------------------------ time
    def _today(self) -> date:
        """Today's date, after applying every hold expiry due by then."""
        today = self.clock()
        while True:
            expired = [(h.deadline, isbn, h) for isbn, q in self._queues.items()
                       for h in q if h.ready and h.deadline < today]
            if not expired:
                return today
            deadline, isbn, hold = min(expired, key=lambda x: x[0])
            self._queues[isbn].remove(hold)
            self._pass_copy(isbn, deadline + timedelta(days=1))

    def _pass_copy(self, isbn: str, day: date) -> None:
        """A copy came free on `day`: set it aside for the earliest waiting hold."""
        for hold in self._queues.get(isbn, []):
            if not hold.ready:
                hold.deadline = day + timedelta(days=HOLD_PICKUP_DAYS)
                return

    # ------------------------------------------------------------ helpers
    def _member(self, member_id: str):
        return self.catalog.member(member_id)

    def _policy(self, member_id: str):
        return POLICY[self._member(member_id).kind]

    def _loan(self, loan_id: int) -> Loan:
        return self._loans[loan_id]

    def _active(self):
        return [l for l in self._loans.values() if l.returned is None]

    def _hold(self, member_id: str, isbn: str) -> _Hold | None:
        for hold in self._queues.get(isbn, []):
            if hold.member_id == member_id:
                return hold
        return None

    @staticmethod
    def _order(loans):
        return sorted(loans, key=lambda l: (l.due, l.loan_id))

    # ------------------------------------------------------------ availability
    def available(self, isbn: str) -> int:
        self._today()
        return self._available(isbn)

    def _available(self, isbn: str) -> int:
        book = self.catalog.book(isbn)
        on_loan = sum(1 for l in self._active() if l.isbn == isbn)
        ready = sum(1 for h in self._queues.get(isbn, []) if h.ready)
        return book.copies - on_loan - ready

    # ------------------------------------------------------------ loans
    def checkout(self, member_id: str, isbn: str) -> Loan:
        today = self._today()
        policy = self._policy(member_id)
        self.catalog.book(isbn)
        if self._balance.get(member_id, 0) > 0:
            raise Blocked(member_id)
        mine = [l for l in self._active() if l.member_id == member_id]
        if any(l.isbn == isbn for l in mine):
            raise DuplicateLoan(isbn)
        if len(mine) >= policy.max_loans:
            raise LimitReached(member_id)
        hold = self._hold(member_id, isbn)
        if not (hold is not None and hold.ready) and self._available(isbn) <= 0:
            raise NotAvailable(isbn)
        if hold is not None:
            self._queues[isbn].remove(hold)
        loan = Loan(self._next_id, member_id, isbn, today, due_date(today, policy.loan_days))
        self._loans[loan.loan_id] = loan
        self._next_id += 1
        return loan

    def renew(self, loan_id: int) -> date:
        today = self._today()
        loan = self._loan(loan_id)
        if loan.returned is not None:
            raise LoanError(f'loan {loan_id} already returned')
        policy = self._policy(loan.member_id)
        if today > loan.due:
            raise RenewalRefused('overdue')
        if self._queues.get(loan.isbn):
            raise RenewalRefused('on hold')
        if loan.renewals >= policy.renewals:
            raise RenewalRefused('no renewals left')
        loan.due = due_date(loan.due, policy.loan_days)
        loan.renewals += 1
        return loan.due

    def checkin(self, loan_id: int) -> int:
        today = self._today()
        loan = self._loan(loan_id)
        if loan.returned is not None:
            raise LoanError(f'loan {loan_id} already returned')
        kind = self._member(loan.member_id).kind
        loan.returned = today
        loan.fine = fine_for(kind, loan.due, today)
        self._balance[loan.member_id] = self._balance.get(loan.member_id, 0) + loan.fine
        self._pass_copy(loan.isbn, today)
        return loan.fine

    def accrued_fine(self, loan_id: int) -> int:
        today = self._today()
        loan = self._loan(loan_id)
        if loan.returned is not None:
            return loan.fine
        return fine_for(self._member(loan.member_id).kind, loan.due, today)

    def loans(self, member_id: str) -> list[Loan]:
        self._member(member_id)
        return self._order(l for l in self._active() if l.member_id == member_id)

    def overdue(self) -> list[Loan]:
        today = self._today()
        return self._order(l for l in self._active() if l.due < today)

    # ------------------------------------------------------------ holds
    def place_hold(self, member_id: str, isbn: str) -> int:
        self._today()
        self._member(member_id)
        self.catalog.book(isbn)
        if any(l.member_id == member_id and l.isbn == isbn for l in self._active()):
            raise DuplicateLoan(isbn)
        if self._hold(member_id, isbn) is not None:
            raise DuplicateLoan(isbn)
        if self._available(isbn) > 0:
            raise LoanError(f'{isbn} is available; borrow it instead')
        queue = self._queues.setdefault(isbn, [])
        queue.append(_Hold(member_id))
        return len(queue)

    def cancel_hold(self, member_id: str, isbn: str) -> None:
        today = self._today()
        hold = self._hold(member_id, isbn)
        if hold is None:
            raise KeyError((member_id, isbn))
        self._queues[isbn].remove(hold)

    def holds(self, isbn: str) -> list[str]:
        self._today()
        self.catalog.book(isbn)
        return [h.member_id for h in self._queues.get(isbn, [])]

    def hold_status(self, member_id: str, isbn: str):
        self._today()
        hold = self._hold(member_id, isbn)
        if hold is None:
            raise KeyError((member_id, isbn))
        if hold.ready:
            return ('ready', hold.deadline)
        return ('waiting', self._queues[isbn].index(hold) + 1)

    # ------------------------------------------------------------ money
    def balance(self, member_id: str) -> int:
        self._member(member_id)
        return self._balance.get(member_id, 0)

    def pay(self, member_id: str, amount: int) -> int:
        owed = self.balance(member_id)
        if amount <= 0 or amount > owed:
            raise ValueError(f'cannot pay {amount} against a balance of {owed}')
        self._balance[member_id] = owed - amount
        return self._balance[member_id]
