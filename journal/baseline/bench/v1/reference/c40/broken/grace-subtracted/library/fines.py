"""Lending policy, due dates and fines."""
from dataclasses import dataclass
from datetime import date, timedelta

HOLD_PICKUP_DAYS = 3


@dataclass(frozen=True)
class Policy:
    max_loans: int
    loan_days: int
    renewals: int
    daily_fine: int
    fine_cap: int
    grace_days: int


POLICY: dict[str, Policy] = {
    'standard': Policy(max_loans=5, loan_days=21, renewals=2, daily_fine=25, fine_cap=1000,
                       grace_days=0),
    'student': Policy(max_loans=3, loan_days=14, renewals=1, daily_fine=10, fine_cap=500,
                      grace_days=2),
    'staff': Policy(max_loans=10, loan_days=42, renewals=3, daily_fine=0, fine_cap=0,
                    grace_days=0),
}


def due_date(start: date, days: int) -> date:
    """start + days, moved from a Sunday to the following Monday."""
    due = start + timedelta(days=days)
    if due.weekday() == 6:
        due += timedelta(days=1)
    return due


def fine_for(kind: str, due: date, returned: date) -> int:
    """The fine in cents for a loan of this member kind returned on `returned`."""
    policy = POLICY[kind]
    late = (returned - due).days
    if late <= policy.grace_days:
        return 0
    return min((late - policy.grace_days) * policy.daily_fine, policy.fine_cap)
