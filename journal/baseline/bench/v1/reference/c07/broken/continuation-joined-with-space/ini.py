"""A small INI parser: sections, key = value, comments, continuations, typed getters."""
import re

_INT = re.compile(r'[+-]?[0-9]+')
_TRUE = {'true', 'yes', 'on', '1'}
_FALSE = {'false', 'no', 'off', '0'}


class ParseError(ValueError):
    def __init__(self, lineno: int, message: str):
        super().__init__(f'line {lineno}: {message}')
        self.lineno = lineno


class Config:
    def __init__(self):
        self._data: dict[str, dict[str, str]] = {}

    def sections(self) -> list[str]:
        return list(self._data)

    def keys(self, section) -> list[str]:
        return list(self._data[section])

    def get(self, section, key, default=None):
        return self._data.get(section, {}).get(key, default)

    def _raw(self, section, key):
        return self._data.get(section, {}).get(key)

    def getint(self, section, key, default=None):
        value = self._raw(section, key)
        if value is None:
            return default
        if not _INT.fullmatch(value):
            raise ValueError(f'not an integer: {value!r}')
        return int(value)

    def getbool(self, section, key, default=None):
        value = self._raw(section, key)
        if value is None:
            return default
        word = value.lower()
        if word in _TRUE:
            return True
        if word in _FALSE:
            return False
        raise ValueError(f'not a boolean: {value!r}')

    def getlist(self, section, key, default=None):
        value = self._raw(section, key)
        if value is None:
            return default
        return [item.strip() for item in value.split(',') if item.strip()]


def parse(text: str) -> Config:
    config = Config()
    section = None          # the current section's dict
    last_key = None         # the key a continuation line would extend
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped[0] in ';#':
            last_key = None
            continue
        if line[0] in ' \t':
            if last_key is None:
                raise ParseError(lineno, 'unexpected indented line')
            section[last_key] += ' ' + stripped
            continue
        last_key = None
        if stripped.startswith('['):
            if not stripped.endswith(']'):
                raise ParseError(lineno, f'malformed section header: {stripped!r}')
            name = stripped[1:-1].strip()
            if not name:
                raise ParseError(lineno, 'empty section name')
            if name in config._data:
                raise ParseError(lineno, f'duplicate section {name!r}')
            section = config._data[name] = {}
            continue
        if '=' not in stripped:
            raise ParseError(lineno, f'expected key = value: {stripped!r}')
        key, value = (part.strip() for part in stripped.split('=', 1))
        if not key:
            raise ParseError(lineno, 'empty key')
        if section is None:
            raise ParseError(lineno, 'key outside any section')
        if key in section:
            raise ParseError(lineno, f'duplicate key {key!r}')
        section[key] = value
        last_key = key
    return config
