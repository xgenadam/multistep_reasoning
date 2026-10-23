"""Block-level parsing: split a document into headings, paragraphs, lists and so on."""
import re

_HEADING = re.compile(r'(#{1,6})(?: (.*))?$')
_CLOSING_HASHES = re.compile(r'(?:^|\s+)#+$')
_FENCE = re.compile(r'(`{3,})(.*)$')
_BULLET = re.compile(r'([-*+]) (.*)$')
_ORDERED = re.compile(r'(\d{1,9})\. (.*)$')


def is_blank(line: str) -> bool:
    return not line.strip()


def heading(line: str):
    m = _HEADING.match(line)
    if not m:
        return None
    text = _CLOSING_HASHES.sub('', (m.group(2) or '').strip())
    return ('heading', len(m.group(1)), text.strip())


def fence(line: str):
    m = _FENCE.match(line)
    if not m:
        return None
    info = m.group(2).split()
    return len(m.group(1)), info[0] if info else ''


def is_fence_close(line: str, width: int) -> bool:
    s = line.rstrip()
    return len(s) >= width and s == '`' * len(s)


def is_hr(line: str) -> bool:
    if not line or line[0] not in '-*_':
        return False
    s = line.rstrip().replace(' ', '')
    return len(s) >= 3 and s == s[0] * len(s)


def list_item(line: str):
    """(kind, number, text) for a list marker line, else None. kind is the bullet or '.'."""
    m = _BULLET.match(line)
    if m:
        return m.group(1), None, m.group(2).strip()
    m = _ORDERED.match(line)
    if m:
        return '.', int(m.group(1)), m.group(2).strip()
    return None


def starts_block(line: str) -> bool:
    """True when the line begins a block by rules 1-5 (not a table or a paragraph)."""
    return (fence(line) is not None or heading(line) is not None or is_hr(line)
            or line.startswith('>') or list_item(line) is not None)


def split_row(line: str) -> list[str]:
    """The cells of a table row: outer pipes dropped, split on unescaped pipes."""
    s = line.strip()
    if s.startswith('|'):
        s = s[1:]
    if s.endswith('|') and not s.endswith('\\|'):
        s = s[:-1]
    cells, cur, i = [], [], 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s) and s[i + 1] == '|':
            cur.append('|')
            i += 2
            continue
        if s[i] == '|':
            cells.append(''.join(cur).strip())
            cur = []
        else:
            cur.append(s[i])
        i += 1
    cells.append(''.join(cur).strip())
    return cells


_DELIM_CELL = re.compile(r':?-+:?')


def table_start(lines: list[str], i: int):
    """(aligns, header) when lines[i] is a table header row followed by a delimiter row."""
    line = lines[i]
    if '|' not in line or line.startswith(' ') or i + 1 >= len(lines):
        return None
    cells = split_row(lines[i + 1])
    if not all(_DELIM_CELL.fullmatch(c) for c in cells):
        return None
    header = split_row(line)
    if len(header) != len(cells):
        return None
    aligns = []
    for c in cells:
        left, right = c.startswith(':'), c.endswith(':')
        aligns.append('center' if left and right else 'left' if left
                      else 'right' if right else None)
    return aligns, header


def parse_blocks(text: str) -> list[tuple]:
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    return _parse(lines)


def _parse(lines: list[str]) -> list[tuple]:
    blocks: list[tuple] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if is_blank(line):
            i += 1
            continue
        f = fence(line)
        if f is not None:
            width, lang = f
            body = []
            i += 1
            while i < n and not is_fence_close(lines[i], width):
                body.append(lines[i])
                i += 1
            i += 1  # the closing fence, if any
            blocks.append(('code', lang, ''.join(b + '\n' for b in body)))
            continue
        h = heading(line)
        if h is not None:
            blocks.append(h)
            i += 1
            continue
        if is_hr(line):
            blocks.append(('hr',))
            i += 1
            continue
        if line.startswith('>'):
            inner = []
            while i < n and lines[i].startswith('>'):
                rest = lines[i][1:]
                inner.append(rest[1:] if rest.startswith(' ') else rest)
                i += 1
            blocks.append(('blockquote', _parse(inner)))
            continue
        item = list_item(line)
        if item is not None:
            i = _parse_list(lines, i, blocks)
            continue
        if table_start(lines, i) is not None:
            i = _parse_table(lines, i, blocks)
            continue
        para = []
        while i < n and not is_blank(lines[i]) and (
                not para or not (starts_block(lines[i]) or table_start(lines, i))):
            para.append(lines[i].strip())
            i += 1
        blocks.append(('paragraph', '\n'.join(para)))
    return blocks


def _parse_table(lines: list[str], i: int, blocks: list[tuple]) -> int:
    aligns, header = table_start(lines, i)
    width = len(header)
    rows = []
    i += 2
    while (i < len(lines) and not is_blank(lines[i]) and '|' in lines[i]
           and not starts_block(lines[i])):
        cells = split_row(lines[i])[:width]
        rows.append(cells + [''] * (width - len(cells)))
        i += 1
    blocks.append(('table', aligns, header, rows))
    return i


def _new_list(kind: str, number, text: str, indent: int) -> dict:
    return {'kind': kind, 'start': number, 'indent': indent, 'items': [[text, []]]}


def _as_block(lst: dict) -> tuple:
    items = [(text, [_as_block(child) for child in children])
             for text, children in lst['items']]
    return ('list', lst['kind'] == '.', lst['start'], items)


def _parse_list(lines: list[str], i: int, blocks: list[tuple]) -> int:
    kind, number, text = list_item(lines[i])
    root = _new_list(kind, number, text, 0)
    stack = [root]
    i += 1
    while i < len(lines) and not is_blank(lines[i]):
        line = lines[i]
        indent = len(line) - len(line.lstrip(' '))
        if indent == 0 and (is_hr(line) or table_start(lines, i)):
            break
        item = list_item(line[indent:])
        if item is None:
            if indent == 0 and starts_block(line):
                break
            last = stack[-1]['items'][-1]
            last[0] = last[0] + '\n' + line.strip() if last[0] else line.strip()
            i += 1
            continue
        kind, number, text = item
        while len(stack) > 1 and stack[-1]['indent'] > indent:
            stack.pop()
        top = stack[-1]
        if indent > top['indent']:
            new = _new_list(kind, number, text, indent)
            top['items'][-1][1].append(new)
            stack.append(new)
        elif kind == top['kind']:
            top['items'].append([text, []])
        elif len(stack) == 1:
            break
        else:
            stack.pop()
            new = _new_list(kind, number, text, indent)
            stack[-1]['items'][-1][1].append(new)
            stack.append(new)
        i += 1
    blocks.append(_as_block(root))
    return i
