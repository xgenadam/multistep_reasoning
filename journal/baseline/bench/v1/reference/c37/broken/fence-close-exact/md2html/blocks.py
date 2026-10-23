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
    return s == '`' * width


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
    """True when the line begins a block other than a paragraph."""
    return (fence(line) is not None or heading(line) is not None or is_hr(line)
            or line.startswith('>') or list_item(line) is not None)


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
        para = []
        while i < n and not is_blank(lines[i]) and (not para or not starts_block(lines[i])):
            para.append(lines[i].strip())
            i += 1
        blocks.append(('paragraph', '\n'.join(para)))
    return blocks


def _parse_list(lines: list[str], i: int, blocks: list[tuple]) -> int:
    kind, number, text = list_item(lines[i])
    items = [text]
    i += 1
    while i < len(lines) and not is_blank(lines[i]):
        line = lines[i]
        item = list_item(line)
        if item is not None and not is_hr(line):
            if item[0] != kind:
                break
            items.append(item[2])
        elif starts_block(line):
            break
        else:
            items[-1] = items[-1] + '\n' + line.strip() if items[-1] else line.strip()
        i += 1
    blocks.append(('list', kind == '.', number, items))
    return i
