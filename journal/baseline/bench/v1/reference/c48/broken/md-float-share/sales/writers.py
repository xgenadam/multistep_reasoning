"""CSV and markdown renderings of one report table."""

from __future__ import annotations

import csv
import io
from decimal import ROUND_HALF_UP, Decimal

NUMBER_COLUMNS = ('units', 'orders', 'revenue', 'share')


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def _share(revenue: Decimal, total: Decimal) -> str:
    if total == 0:
        return '0.0%'
    pct = (revenue * 100 / total).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    return f'{pct}%'


def table(report) -> tuple[list[str], list[list[str]]]:
    """(header, rows) shared by both writers; the last row is the total."""
    header = list(report.by) + list(NUMBER_COLUMNS)
    total = report.total.revenue
    rows = []
    for g in report.groups:
        rows.append(list(g.key) + [str(g.units), str(g.orders), _money(g.revenue),
                                   _share(g.revenue, total)])
    keys = ['TOTAL'] + [''] * (len(report.by) - 1)
    rows.append(keys + [str(report.total.units), str(report.total.orders), _money(total),
                        '0.0%' if total == 0 else '100.0%'])
    return header, rows


def to_csv(report) -> str:
    header, rows = table(report)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator='\n')
    writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue()


def _md_line(cells) -> str:
    return '| ' + ' | '.join(c.replace('|', '\\|') for c in cells) + ' |\n'


def to_markdown(report) -> str:
    header, rows = table(report)
    total = float(report.total.revenue)
    for row, g in zip(rows, report.groups):
        row[-1] = f'{float(g.revenue) * 100 / total:.1f}%' if total else '0.0%'
    align = ['---'] * len(report.by) + ['---:'] * len(NUMBER_COLUMNS)
    return ''.join([_md_line(header), _md_line(align)] + [_md_line(r) for r in rows])
