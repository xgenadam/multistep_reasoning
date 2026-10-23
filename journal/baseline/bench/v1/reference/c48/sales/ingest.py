"""CSV ingestion with per-row validation."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import NamedTuple

REQUIRED = ('date', 'region', 'product', 'units', 'unit_price')
_DATE = re.compile(r'\d{4}-\d{2}-\d{2}')
_UNITS = re.compile(r'\d+')
_PRICE = re.compile(r'\d+(\.\d{1,2})?')


class IngestError(ValueError):
    pass


class RowError(NamedTuple):
    line: int
    message: str


@dataclass(frozen=True)
class Sale:
    date: date
    region: str
    product: str
    units: int
    unit_price: Decimal

    @property
    def revenue(self) -> Decimal:
        return self.units * self.unit_price


def _validate(values: dict[str, str]) -> tuple[Sale | None, str | None]:
    raw = values['date']
    if not _DATE.fullmatch(raw):
        return None, 'date: must be YYYY-MM-DD'
    try:
        day = date.fromisoformat(raw)
    except ValueError:
        return None, 'date: not a real calendar date'
    for name in ('region', 'product'):
        if not values[name]:
            return None, f'{name}: must not be empty'
    if not _UNITS.fullmatch(values['units']) or int(values['units']) < 1:
        return None, 'units: must be a whole number of at least 1'
    if not _PRICE.fullmatch(values['unit_price']):
        return None, 'unit_price: must be a non-negative amount with at most two decimals'
    return Sale(day, values['region'], values['product'], int(values['units']),
                Decimal(values['unit_price'])), None


def parse_sales(text: str) -> tuple[list[Sale], list[RowError]]:
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header:
        raise IngestError('no header row')
    names = [h.strip().lower() for h in header]
    for col in REQUIRED:
        if col not in names:
            raise IngestError(f'missing column: {col}')
    index = {col: names.index(col) for col in REQUIRED}
    sales: list[Sale] = []
    errors: list[RowError] = []
    for row in reader:
        if not row:
            continue
        line = reader.line_num
        if len(row) != len(header):
            errors.append(RowError(line, f'row: expected {len(header)} fields, got {len(row)}'))
            continue
        sale, problem = _validate({col: row[i].strip() for col, i in index.items()})
        if problem:
            errors.append(RowError(line, problem))
        else:
            sales.append(sale)
    return sales, errors


def read_sales(path) -> tuple[list[Sale], list[RowError]]:
    with open(path, encoding='utf-8-sig', newline='') as f:
        return parse_sales(f.read())
