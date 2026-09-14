from reasoning_sub_agents.prompt_budget import (
    PromptPiece,
    budgeted_prompt,
    cap_prompt,
    estimate_tokens,
    fit_pieces,
)


def test_budget_zero_does_not_change_text():
    pieces = [PromptPiece('a', 'hello world', priority=1)]
    assert budgeted_prompt(pieces, 0) == 'hello world'


def test_fit_drops_low_priority_first():
    pieces = [
        PromptPiece('keep', 'OBJECTIVE', priority=0, truncatable=False),
        PromptPiece('drop', 'X' * 4000, priority=5),
    ]
    fitted = fit_pieces(pieces, budget=50)
    text = '\n\n'.join(p.text for p in fitted if p.text)
    assert 'OBJECTIVE' in text
    assert len(fitted[1].text) < 4000


def test_cap_prompt_keeps_tail():
    tail = '\nSCHEMA'
    prompt = 'A' * 5000
    out = cap_prompt(prompt, budget=80, tail=tail)
    assert out.endswith('SCHEMA')
    assert estimate_tokens(out) <= 80 or 'truncated' in out
