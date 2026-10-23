"""Full justification of text to a fixed width."""


def _pad(words: list[str], width: int) -> str:
    if len(words) == 1:
        return words[0].ljust(width)
    gaps = len(words) - 1
    spaces = width - sum(len(w) for w in words)
    base, extra = divmod(spaces, gaps)
    parts = []
    for i, word in enumerate(words[:-1]):
        parts.append(word)
        parts.append(' ' * (base + (1 if i < extra else 0)))
    parts.append(words[-1])
    return ''.join(parts)


def _lines(words: list[str], width: int) -> list[list[str]]:
    lines: list[list[str]] = []
    current: list[str] = []
    length = 0
    for word in words:
        if len(word) > width:
            if current:
                lines.append(current)
            for k in range(0, len(word), width):
                lines.append([word[k:k + width]])
            current, length = [], 0
            continue
        needed = len(word) if not current else length + 1 + len(word)
        if needed <= width:
            current.append(word)
            length = needed
        else:
            lines.append(current)
            current, length = [word], len(word)
    if current:
        lines.append(current)
    return lines


def justify(text: str, width: int) -> list[str]:
    if width < 1:
        raise ValueError('width must be at least 1')
    lines = _lines(text.split(), width)
    out = []
    for i, words in enumerate(lines):
        last = i == len(lines) - 1
        if last or (len(words) == 1 and len(words[0]) > width):
            out.append(' '.join(words))
        else:
            out.append(_pad(words, width))
    return out
