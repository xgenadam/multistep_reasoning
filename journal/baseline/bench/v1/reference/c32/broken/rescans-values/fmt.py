import re

_PLACEHOLDER = re.compile(r'\{([A-Za-z_][A-Za-z0-9_]*)(?::([^{}]*))?\}')


class TemplateError(ValueError):
    def __init__(self, message, position):
        super().__init__(f'{message} at position {position}')
        self.position = position


class MissingKey(KeyError):
    def __init__(self, name):
        super().__init__(name)
        self.name = name


def _parse(template):
    """Split the template into literal strings and (name, default-or-None) tuples."""
    parts, buf, i = [], [], 0
    while i < len(template):
        ch = template[i]
        if ch == '{':
            if template.startswith('{{', i):
                buf.append('{')
                i += 2
                continue
            m = _PLACEHOLDER.match(template, i)
            if not m:
                raise TemplateError('bad placeholder', i)
            if buf:
                parts.append(''.join(buf))
                buf = []
            parts.append((m.group(1), m.group(2)))
            i = m.end()
        elif ch == '}':
            if template.startswith('}}', i):
                buf.append('}')
                i += 2
                continue
            raise TemplateError('single }', i)
        else:
            buf.append(ch)
            i += 1
    if buf:
        parts.append(''.join(buf))
    return parts


def placeholders(template):
    seen = {}
    for part in _parse(template):
        if isinstance(part, tuple):
            seen.setdefault(part[0], None)
    return list(seen)


def render(template, values):
    for _ in range(10):
        new = _render_once(template, values)
        if new == template or '{' not in new:
            return new
        template = new
    return new


def _render_once(template, values):
    out = []
    for part in _parse(template):
        if isinstance(part, str):
            out.append(part)
            continue
        name, default = part
        if name in values:
            out.append(str(values[name]))
        elif default is not None:
            out.append(default)
        else:
            raise MissingKey(name)
    return ''.join(out)
