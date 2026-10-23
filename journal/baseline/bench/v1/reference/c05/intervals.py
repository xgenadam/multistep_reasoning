"""Sets of integers as lists of half-open intervals [start, end)."""

Interval = tuple[int, int]


def _validated(intervals) -> list[Interval]:
    out = []
    for item in intervals:
        start, end = item
        if start > end:
            raise ValueError(f'invalid interval: {tuple(item)!r}')
        if start < end:
            out.append((start, end))
    return out


def _normal(pairs: list[Interval]) -> list[Interval]:
    """Normal form of already-validated, non-empty pairs."""
    result: list[Interval] = []
    for start, end in sorted(pairs):
        if result and start <= result[-1][1]:
            if end > result[-1][1]:
                result[-1] = (result[-1][0], end)
        else:
            result.append((start, end))
    return result


def merge(intervals) -> list[Interval]:
    return _normal(_validated(intervals))


def insert(intervals, new) -> list[Interval]:
    return _normal(_validated(intervals) + _validated([new]))


def remove(intervals, cut) -> list[Interval]:
    merged = merge(intervals)
    cut_list = _validated([cut])
    if not cut_list:
        return merged
    lo, hi = cut_list[0]
    result = []
    for start, end in merged:
        if end <= lo or start >= hi:
            result.append((start, end))
            continue
        if start < lo:
            result.append((start, lo))
        if end > hi:
            result.append((hi, end))
    return result


def intersect(a, b) -> list[Interval]:
    left, right = merge(a), merge(b)
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        start = max(left[i][0], right[j][0])
        end = min(left[i][1], right[j][1])
        if start < end:
            result.append((start, end))
        if left[i][1] < right[j][1]:
            i += 1
        else:
            j += 1
    return _normal(result)
