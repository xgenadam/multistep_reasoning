from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

CENT = Decimal('0.01')


def to_cents(x):
    if isinstance(x, bool) or not isinstance(x, (int, Decimal, str)):
        raise TypeError(f'unsupported amount type: {type(x).__name__}')
    if isinstance(x, str):
        try:
            x = Decimal(x.strip())
        except InvalidOperation:
            raise ValueError(f'not a decimal number: {x!r}') from None
    d = Decimal(x)
    if not d.is_finite():
        raise ValueError(f'not a finite amount: {x!r}')
    return d.quantize(CENT, rounding=ROUND_HALF_EVEN)


def _ratio(r):
    if isinstance(r, bool) or not isinstance(r, (int, Decimal)):
        raise ValueError(f'bad ratio {r!r}')
    r = Decimal(r)
    if not r.is_finite() or r < 0:
        raise ValueError(f'bad ratio {r!r}')
    return r


def allocate(amount, ratios):
    total_amount = to_cents(amount)
    if not isinstance(ratios, list) or not ratios:
        raise ValueError('ratios must be a non-empty list')
    rs = [_ratio(r) for r in ratios]
    total = sum(rs)
    if total <= 0:
        raise ValueError('ratios must have a positive sum')
    if total_amount < 0:
        return [-p for p in allocate(-total_amount, ratios)]
    cents = int(total_amount / CENT)
    shares = [Decimal(cents) * r / total for r in rs]
    base = [int(s) for s in shares]  # floor, shares are non-negative
    left = cents - sum(base)
    order = sorted(range(len(rs)), key=lambda i: (shares[i] - base[i], i), reverse=True)
    for i in order[:left]:
        base[i] += 1
    return [(Decimal(b) * CENT).quantize(CENT) for b in base]


def split_even(amount, n):
    if n < 1:
        raise ValueError('n must be at least 1')
    return allocate(amount, [1] * n)


def format_money(amount):
    d = to_cents(amount)
    if d == 0:
        d = abs(d)
    sign = '-' if d < 0 else ''
    return f'{sign}{abs(d):,.2f}'
