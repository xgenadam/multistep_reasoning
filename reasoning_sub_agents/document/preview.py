import hashlib


def preview_text(
    text: str,
    *,
    head: int = 400,
    tail: int = 200,
    full_below: int = 800,
) -> str:
    """
    Compact view of a large payload for prompts.

    Short text is returned in full. Long text is length + hash + head/tail.
    """
    if not text:
        return '(empty)'
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]
    if len(text) <= full_below:
        return f'[len={len(text)} sha256={digest}]\n{text}'
    return (
        f'[len={len(text)} sha256={digest}]\n'
        f'START:\n{text[:head]}\n...\nEND:\n{text[-tail:]}'
    )
