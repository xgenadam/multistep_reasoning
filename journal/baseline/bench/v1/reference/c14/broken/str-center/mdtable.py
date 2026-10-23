"""Render a padded GitHub-flavoured Markdown table."""

_ALIGNMENTS = ('left', 'right', 'center')
_MIN_WIDTH = 3


def _text(value) -> str:
    text = '' if value is None else str(value)
    text = text.replace('|', '\\|')
    return text.replace('\r\n', '<br>').replace('\n', '<br>')


def _pad(text: str, width: int, how: str) -> str:
    gap = width - len(text)
    if how == 'left':
        return text + ' ' * gap
    if how == 'right':
        return ' ' * gap + text
    return text.center(width)


def _rule(width: int, how: str) -> str:
    dashes = ['-'] * width
    if how in ('left', 'center'):
        dashes[0] = ':'
    if how in ('right', 'center'):
        dashes[-1] = ':'
    return ''.join(dashes)


def _line(cells) -> str:
    return '| ' + ' | '.join(cells) + ' |'


def format_table(rows, headers, align=None) -> str:
    headers = [_text(h) for h in headers]
    if not headers:
        raise ValueError('headers must not be empty')
    ncols = len(headers)
    if align is None:
        align = ['left'] * ncols
    align = list(align)
    if len(align) != ncols:
        raise ValueError(f'align has {len(align)} entries for {ncols} columns')
    for how in align:
        if how not in _ALIGNMENTS:
            raise ValueError(f'unknown alignment: {how!r}')
    body = []
    for i, row in enumerate(rows):
        cells = [_text(c) for c in row]
        if len(cells) != ncols:
            raise ValueError(f'row {i} has {len(cells)} cells for {ncols} columns')
        body.append(cells)
    widths = [max([_MIN_WIDTH, len(headers[c])] + [len(r[c]) for r in body])
              for c in range(ncols)]
    lines = [_line(_pad(h, w, a) for h, w, a in zip(headers, widths, align)),
             _line(_rule(w, a) for w, a in zip(widths, align))]
    for cells in body:
        lines.append(_line(_pad(t, w, a) for t, w, a in zip(cells, widths, align)))
    return '\n'.join(lines)
