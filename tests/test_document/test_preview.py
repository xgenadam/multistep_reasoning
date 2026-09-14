from reasoning_sub_agents.document import preview_text


def test_short_text_is_included_in_full():
    text = 'hello world'
    preview = preview_text(text)
    assert 'hello world' in preview
    assert 'len=11' in preview
    assert 'sha256=' in preview


def test_long_text_is_head_and_tail_only():
    text = 'A' * 400 + 'MIDDLE-MARKER' + 'Z' * 400
    preview = preview_text(text, head=50, tail=50, full_below=100)
    assert 'MIDDLE-MARKER' not in preview
    assert text.startswith(preview.split('START:\n', 1)[1][:50])
    assert 'len=' in preview
