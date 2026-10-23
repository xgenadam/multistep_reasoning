import datetime
import re

_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
_MONTH_DAYS = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def _field(text, lo, hi):
    values = set()
    for item in text.split(','):
        m = re.fullmatch(r'(\*|(\d+)-(\d+)|(\d+))(?:/(\d+))?', item)
        if not m:
            raise ValueError(f'bad cron item {item!r}')
        if m.group(1) == '*':
            a, b = lo, hi
        elif m.group(4) is not None:
            if m.group(5) is not None:
                raise ValueError(f'step needs a range: {item!r}')
            a = b = int(m.group(4))
        else:
            a, b = int(m.group(2)), int(m.group(3))
        if not (lo <= a <= hi and lo <= b <= hi) or a > b:
            raise ValueError(f'value out of range in {item!r}')
        step = int(m.group(5)) if m.group(5) is not None else 1
        if step < 1:
            raise ValueError(f'bad step in {item!r}')
        values.update(range(a, b + 1, step))
    return values


def _parse(expr):
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError('a cron expression has five fields')
    fields = [_field(p, lo, hi) for p, (lo, hi) in zip(parts, _RANGES)]
    dow = fields[4]
    if 7 in dow:
        dow = (dow - {7}) | {0}
    fields[4] = dow
    dom_star = parts[2].startswith('*')
    dow_star = parts[4].startswith('*')
    if dow_star and not any(d <= _MONTH_DAYS[m - 1] for d in fields[2] for m in fields[3]):
        raise ValueError('no day can ever match')
    return fields, dom_star, dow_star


def _day_matches(day, dom, dow, dom_star, dow_star):
    in_dom = day.day in dom
    in_dow = (day.isoweekday() % 7) in dow
    if not dom_star and not dow_star:
        return in_dom or in_dow
    return in_dom and in_dow


def next_run(expr, after):
    (minutes, hours, dom, months, dow), dom_star, dow_star = _parse(expr)
    start = after.replace(second=0, microsecond=0)
    if after.second or after.microsecond:
        start += datetime.timedelta(minutes=1)
    day = start.date()
    first = True
    for _ in range(366 * 30):
        if day.month in months and _day_matches(day, dom, dow, dom_star, dow_star):
            for h in sorted(hours):
                if first and h < start.hour:
                    continue
                for mi in sorted(minutes):
                    if first and h == start.hour and mi < start.minute:
                        continue
                    return datetime.datetime(day.year, day.month, day.day, h, mi)
        day += datetime.timedelta(days=1)
        first = False
    raise ValueError('no matching time found')
