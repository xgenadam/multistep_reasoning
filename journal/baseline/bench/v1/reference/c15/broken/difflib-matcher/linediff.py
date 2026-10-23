"""Line diff built on difflib (not guaranteed minimal)."""
import difflib


def diff(a: list[str], b: list[str]) -> list[str]:
    out = []
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            out.extend(' ' + x for x in a[i1:i2])
        else:
            out.extend('-' + x for x in a[i1:i2])
            out.extend('+' + x for x in b[j1:j2])
    return out
