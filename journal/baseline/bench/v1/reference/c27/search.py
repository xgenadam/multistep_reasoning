def insertion_point(a, x):
    lo, hi = 0, len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] < x:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _upper(a, x):
    lo, hi = 0, len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if x < a[mid]:
            hi = mid
        else:
            lo = mid + 1
    return lo


def first_index(a, x):
    i = insertion_point(a, x)
    return i if i < len(a) and a[i] == x else -1


def last_index(a, x):
    i = _upper(a, x) - 1
    return i if i >= 0 and a[i] == x else -1


def count(a, x):
    return _upper(a, x) - insertion_point(a, x)


def rotation_offset(a):
    if not a:
        raise ValueError('empty list')
    lo, hi = 0, len(a) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] > a[hi]:
            lo = mid + 1
        else:
            hi = mid
    return lo


def search_rotated(a, x):
    if not a:
        return -1
    lo, hi = 0, len(a) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if a[mid] == x:
            return mid
        if a[lo] <= a[mid]:  # left half sorted
            if a[lo] <= x < a[mid]:
                hi = mid - 1
            else:
                lo = mid + 1
        else:  # right half sorted
            if a[mid] < x <= a[hi]:
                lo = mid + 1
            else:
                hi = mid - 1
    return -1


def isqrt(n):
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError('isqrt needs an int')
    if n < 0:
        raise ValueError('isqrt of a negative number')
    lo, hi = 0, 1 << ((n.bit_length() + 1) // 2 + 1)
    while lo < hi:  # largest r with r*r <= n lies in [lo, hi)
        mid = (lo + hi + 1) // 2
        if mid * mid <= n:
            lo = mid
        else:
            hi = mid - 1
    return lo
