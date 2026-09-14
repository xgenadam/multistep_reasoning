from __future__ import annotations

from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class PromptPiece:
    name: str
    text: str
    priority: int = 1
    truncatable: bool = True


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    try:
        import tiktoken

        enc = tiktoken.get_encoding('cl100k_base')
        return len(enc.encode(text))
    except Exception:
        return max(1, (len(text) + 3) // 4)


def join_pieces(pieces: list[PromptPiece]) -> str:
    return '\n\n'.join(piece.text for piece in pieces if piece.text)


def truncate_to_tokens(text: str, token_budget: int, *, name: str = 'text') -> str:
    if estimate_tokens(text) <= token_budget:
        return text
    original = len(text)
    lo, hi = 0, len(text)
    best = ''
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = text[:mid]
        if estimate_tokens(candidate) <= token_budget:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    marker = f'\n[truncated:{name} from {original} chars]\n'
    # leave room for the marker
    while best and estimate_tokens(best + marker) > token_budget:
        best = best[: max(0, len(best) - 16)]
    return (best + marker).rstrip()


def fit_pieces(pieces: list[PromptPiece], budget: int) -> list[PromptPiece]:
    """
    Shrink or drop pieces until join_pieces is within budget tokens.

    Higher `priority` is dropped first. Priority 0 is kept unless nothing
    else can shrink and the prompt is still over budget.
    budget <= 0 disables fitting.
    """
    fitted = [
        PromptPiece(p.name, p.text, p.priority, p.truncatable) for p in pieces
    ]
    if budget <= 0:
        return fitted
    for _ in range(48):
        if estimate_tokens(join_pieces(fitted)) <= budget:
            return fitted
        shrinkable = [
            p
            for p in fitted
            if p.priority > 0
            and p.text
            and not p.text.startswith('(dropped:')
        ]
        if not shrinkable:
            shrinkable = [
                p for p in fitted if p.truncatable and len(p.text) > 64
            ]
        if not shrinkable:
            logger.warning('prompt still over budget (%s) with nothing to drop', budget)
            return fitted
        target = max(shrinkable, key=lambda p: (p.priority, len(p.text)))
        current = estimate_tokens(target.text)
        if (not target.truncatable) or current < 48:
            target.text = f'(dropped:{target.name})'
            continue
        target.text = truncate_to_tokens(
            target.text, max(24, current // 2), name=target.name
        )
    return fitted


def budgeted_prompt(pieces: list[PromptPiece], budget: int) -> str:
    return join_pieces(fit_pieces(pieces, budget))


def cap_prompt(prompt: str, budget: int, *, tail: str = '') -> str:
    """Keep `tail` (e.g. JSON schema) and shrink `prompt` to fit budget."""
    if budget <= 0:
        return prompt + tail
    combined = prompt + tail
    if estimate_tokens(combined) <= budget:
        return combined
    reserved = estimate_tokens(tail) + 4
    head_budget = max(32, budget - reserved)
    return truncate_to_tokens(prompt, head_budget, name='prompt') + tail
