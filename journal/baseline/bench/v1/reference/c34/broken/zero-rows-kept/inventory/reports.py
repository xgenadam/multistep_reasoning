"""CSV reports: stock by location and valuation by category, one shared layout."""
from collections import defaultdict
from decimal import Decimal

from .valuation import METHODS, valuate


def _grouped(rows, header, sums):
    """Render rows of (group, sku, *numbers) with per-group subtotals and a grand total.

    `sums` formats a list of numeric column totals. Rows with a zero first
    number are dropped; empty groups disappear.
    """
    groups: dict[str, list] = defaultdict(list)
    for group, sku, *nums in rows:
        groups[group].append((sku, nums))
    lines = [header]
    grand = None
    for group in sorted(groups):
        members = sorted(groups[group], key=lambda r: r[0])
        total = None
        for sku, nums in members:
            lines.append(','.join([group, sku, *sums(nums)]))
            total = nums if total is None else [a + b for a, b in zip(total, nums)]
        lines.append(','.join([group, 'TOTAL', *sums(total)]))
        grand = total if grand is None else [a + b for a, b in zip(grand, total)]
    if grand is None:
        grand = [0] * (header.count(',') - 1)
    lines.append(','.join(['TOTAL', '', *sums(grand)]))
    return ''.join(line + '\n' for line in lines)


def stock_report(ledger, as_of=None, location=None) -> str:
    rows = [(loc, sku, qty) for (sku, loc), qty in ledger.positions(as_of).items()
            if location is None or loc == location]
    return _grouped(rows, 'location,sku,qty', lambda nums: [str(nums[0])])


def valuation_report(ledger, as_of=None, method='fifo', category=None) -> str:
    if method not in METHODS:
        raise ValueError(f'method must be one of {", ".join(METHODS)}, got {method!r}')
    rows = []
    for item in ledger.items():
        if category is not None and item.category != category:
            continue
        v = valuate(ledger, item.sku, method, as_of)
        rows.append((item.category, item.sku, v.qty, v.value))

    def fmt(nums):
        qty, value = nums
        return [str(qty), f'{Decimal(value):.2f}']
    return _grouped(rows, 'category,sku,qty,value', fmt)
