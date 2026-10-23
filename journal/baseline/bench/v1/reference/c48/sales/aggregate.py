"""Grouping sales by month, region and/or product."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

FIELDS = ('month', 'region', 'product')
_MONTH = re.compile(r'\d{4}-(0[1-9]|1[0-2])')


def parse_month(text: str) -> str:
    if not isinstance(text, str) or not _MONTH.fullmatch(text):
        raise ValueError(f'not a YYYY-MM month: {text!r}')
    return text


def month_of(sale) -> str:
    return sale.date.strftime('%Y-%m')


def _value(sale, field: str) -> str:
    return month_of(sale) if field == 'month' else getattr(sale, field)


def filter_months(sales, start=None, end=None) -> list:
    return [s for s in sales
            if (start is None or month_of(s) >= start) and (end is None or month_of(s) <= end)]


@dataclass(frozen=True)
class Group:
    key: tuple
    units: int
    orders: int
    revenue: Decimal


@dataclass(frozen=True)
class Report:
    by: tuple
    groups: list
    total: Group


def check_by(by) -> tuple:
    by = tuple(by)
    if not by or len(set(by)) != len(by) or any(f not in FIELDS for f in by):
        raise ValueError(f'bad grouping fields: {by!r}')
    return by


def _sum(key, sales) -> Group:
    return Group(key, sum(s.units for s in sales), len(sales),
                 sum((s.revenue for s in sales), Decimal('0')))


def aggregate(sales, by) -> list[Group]:
    by = check_by(by)
    buckets: dict[tuple, list] = {}
    for sale in sales:
        buckets.setdefault(tuple(_value(sale, f) for f in by), []).append(sale)
    return [_sum(key, buckets[key]) for key in sorted(buckets)]


def build_report(sales, by) -> Report:
    sales = list(sales)
    return Report(check_by(by), aggregate(sales, by), _sum((), sales))
