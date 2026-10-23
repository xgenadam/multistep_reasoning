"""URL slugs: ASCII, lower-case, hyphen-separated, length-limited and unique."""

import re
import unicodedata


def _shorten(slug, limit):
    """Cut slug to at most limit characters, at a '-' where possible."""
    if len(slug) <= limit:
        return slug
    cut = slug.rfind('-', 0, limit + 1)
    if cut <= 0:
        return slug[:limit].rstrip('-')
    return slug[:cut]


def _base(text):
    """Steps 1-4: the slug before shortening and uniqueness."""
    text = text.replace("'", '').replace('’', '')
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii').lower()
    slug = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return slug or 'untitled'


def slugify(text, max_len=50, existing=()):
    """Return a slug for text of at most max_len characters that is not in existing."""
    if max_len < 1:
        raise ValueError('max_len must be at least 1')
    base = _base(text)
    slug = _shorten(base, max_len)
    if slug not in existing:
        return slug
    n = 2
    while True:
        suffix = f'-{n}'
        candidate = slug + suffix
        if candidate not in existing:
            return candidate
        n += 1
