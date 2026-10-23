"""Minimal line diff from a longest common subsequence, with a fixed tie-break."""


def _suffix_lcs(a: list[str], b: list[str]) -> list[list[int]]:
    """table[i][j] = LCS length of a[i:] and b[j:]."""
    n, m = len(a), len(b)
    table = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        row, below = table[i], table[i + 1]
        ai = a[i]
        for j in range(m - 1, -1, -1):
            if ai == b[j]:
                row[j] = below[j + 1] + 1
            else:
                row[j] = below[j] if below[j] >= row[j + 1] else row[j + 1]
    return table


def diff(a: list[str], b: list[str]) -> list[str]:
    # The rule always matches a common prefix, so trim it first.
    # (A common suffix cannot be trimmed: the rule may match those lines earlier.)
    start = 0
    while start < len(a) and start < len(b) and a[start] == b[start]:
        start += 1
    end_a, end_b = len(a), len(b)
    while end_a > start and end_b > start and a[end_a - 1] == b[end_b - 1]:
        end_a -= 1
        end_b -= 1
    mid_a, mid_b = a[start:end_a], b[start:end_b]

    out = [' ' + line for line in a[:start]]
    table = _suffix_lcs(mid_a, mid_b)
    i = j = 0
    while i < len(mid_a) and j < len(mid_b):
        if mid_a[i] == mid_b[j]:
            out.append(' ' + mid_a[i])
            i += 1
            j += 1
        elif table[i + 1][j] >= table[i][j + 1]:
            out.append('-' + mid_a[i])
            i += 1
        else:
            out.append('+' + mid_b[j])
            j += 1
    out.extend('-' + line for line in mid_a[i:])
    out.extend('+' + line for line in mid_b[j:])
    out.extend(' ' + line for line in a[end_a:])
    return out
