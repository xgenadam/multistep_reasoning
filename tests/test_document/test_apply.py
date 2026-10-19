import pytest

from reasoning_sub_agents.document import (
    AddPart,
    AppendToPart,
    DeletePart,
    Document,
    DocumentApplyError,
    DocumentIntegrityError,
    InsertInPart,
    MergeParts,
    MovePart,
    Part,
    PartKind,
    ReplaceInPart,
    UpdatePart,
    assert_payload_kept,
)


def _part(part_id: str, body: str, kind: PartKind = PartKind.SECTION) -> Part:
    return Part(id=part_id, kind=kind, title=part_id, body=body)


def test_add_part_with_literal_body():
    doc = Document.empty()
    doc.apply(
        [
            AddPart(
                id='intro',
                kind='section',
                title='Intro',
                body='Hello',
                after='end',
            )
        ]
    )
    assert len(doc.parts) == 1
    assert doc.parts[0].body == 'Hello'
    assert doc.parts[0].kind == PartKind.SECTION


def test_add_part_body_source_copies_current_result():
    doc = Document.empty()
    payload = 'Chapter one text that must be kept verbatim.'
    doc.apply(
        [
            AddPart(
                id='ch1',
                kind='section',
                title='Chapter 1',
                body_source='current_result',
            )
        ],
        current_result=payload,
        origin_task='Write chapter 1',
    )
    assert doc.parts[0].body == payload
    assert doc.parts[0].origin_task == 'Write chapter 1'


def test_add_part_body_source_without_result_errors():
    doc = Document.empty()
    with pytest.raises(DocumentApplyError, match='current_result'):
        doc.apply(
            [
                AddPart(
                    id='ch1',
                    kind='section',
                    title='Chapter 1',
                    body_source='current_result',
                )
            ]
        )


def test_add_part_duplicate_id_errors_and_is_atomic():
    doc = Document.empty()
    first = _part('a', 'keep me')
    doc.parts.append(first)
    with pytest.raises(DocumentApplyError, match='already exists'):
        doc.apply(
            [
                AddPart(id='b', kind='section', title='B', body='new'),
                AddPart(id='a', kind='section', title='A', body='dup'),
            ]
        )
    assert doc.parts == [first]
    assert doc.parts[0] is first
    assert doc.parts[0].body == 'keep me'


def test_untargeted_parts_keep_identity():
    a = _part('a', 'aaa')
    b = _part('b', 'bbb')
    doc = Document(parts=[a, b])
    doc.apply([ReplaceInPart(id='a', search='aaa', replace='AAA')])
    assert doc.parts[0].body == 'AAA'
    assert doc.parts[1] is b
    assert doc.parts[1].body == 'bbb'


def test_replace_miss_is_error_not_silent():
    doc = Document(parts=[_part('a', 'hello world')])
    with pytest.raises(DocumentApplyError, match='search string not found'):
        doc.apply([ReplaceInPart(id='a', search='missing', replace='x')])
    assert doc.parts[0].body == 'hello world'


def test_replace_only_first_occurrence():
    doc = Document(parts=[_part('a', 'foo foo')])
    doc.apply([ReplaceInPart(id='a', search='foo', replace='bar')])
    assert doc.parts[0].body == 'bar foo'


def test_append_and_insert():
    doc = Document(parts=[_part('a', 'Hello.')])
    doc.apply([AppendToPart(id='a', body=' World.')])
    assert doc.parts[0].body == 'Hello. World.'
    doc.apply([InsertInPart(id='a', anchor='Hello.', body=' There.')])
    assert doc.parts[0].body == 'Hello. There. World.'


def test_insert_anchor_miss_errors():
    doc = Document(parts=[_part('a', 'Hello.')])
    with pytest.raises(DocumentApplyError, match='anchor not found'):
        doc.apply([InsertInPart(id='a', anchor='Nope', body='x')])


def test_update_part_body_source():
    doc = Document(parts=[_part('a', 'old')])
    doc.apply(
        [UpdatePart(id='a', body_source='current_result')],
        current_result='new body',
    )
    assert doc.parts[0].body == 'new body'


def test_move_and_delete():
    doc = Document(
        parts=[_part('a', 'a'), _part('b', 'b'), _part('c', 'c')]
    )
    doc.apply([MovePart(id='c', after='start')])
    assert [p.id for p in doc.parts] == ['c', 'a', 'b']
    doc.apply([DeletePart(id='a')])
    assert [p.id for p in doc.parts] == ['c', 'b']


def test_add_file_part_and_render_modes():
    doc = Document(title='Project')
    doc.apply(
        [
            AddPart(
                id='readme',
                kind='section',
                title='Overview',
                body='A tool.',
            ),
            AddPart(
                id='main-py',
                kind='file',
                title='main.py',
                body='print("hi")',
            ),
        ]
    )
    rendered = doc.render('markdown_with_files')
    assert '# Project' in rendered
    assert '## Overview' in rendered
    assert 'A tool.' in rendered
    assert '## main.py' in rendered
    assert '```py' in rendered
    assert 'print("hi")' in rendered

    sections_only = doc.render('sections_only')
    assert 'A tool.' in sections_only
    assert 'print("hi")' not in sections_only


def test_outline_lists_parts():
    doc = Document(parts=[_part('a', 'abcd'), _part('b', 'xy', PartKind.FILE)])
    outline = doc.outline()
    assert outline[0].id == 'a'
    assert outline[0].char_count == 4
    assert outline[1].kind == PartKind.FILE


def test_integrity_body_source_ok():
    payload = 'keep this payload'
    doc = Document.empty()
    ops = [
        AddPart(
            id='ch1',
            kind='section',
            title='Ch1',
            body_source='current_result',
        )
    ]
    doc.apply(ops, current_result=payload)
    assert_payload_kept(doc, ops, payload)


def test_integrity_literal_body_must_contain_result():
    doc = Document.empty()
    ops = [
        AddPart(
            id='ch1',
            kind='section',
            title='Ch1',
            body='a short summary of the chapter',
        )
    ]
    doc.apply(ops, current_result='the full chapter text')
    with pytest.raises(DocumentIntegrityError, match='was not kept'):
        assert_payload_kept(doc, ops, 'the full chapter text')


def test_integrity_patch_only_does_not_require_payload():
    doc = Document(parts=[_part('a', 'Hello world')])
    ops = [ReplaceInPart(id='a', search='world', replace='there')]
    doc.apply(ops, current_result='a completely different sub-task result')
    assert_payload_kept(doc, ops, 'a completely different sub-task result')
    assert doc.parts[0].body == 'Hello there'


def test_add_part_after_existing_id():
    doc = Document(parts=[_part('a', 'a'), _part('c', 'c')])
    doc.apply(
        [AddPart(id='b', kind='section', title='B', body='b', after='a')]
    )
    assert [p.id for p in doc.parts] == ['a', 'b', 'c']


def test_unknown_part_errors():
    doc = Document.empty()
    with pytest.raises(DocumentApplyError, match='unknown part id'):
        doc.apply([DeletePart(id='missing')])


# --- merge_parts (0-03) ---------------------------------------------------


def test_merge_preserves_all_content_and_keeps_primary():
    doc = Document(parts=[_part('a', 'A body'), _part('b', 'B body'), _part('c', 'C body')])
    doc.apply([MergeParts(ids=['b', 'a'])])
    # b is primary -> survives with b's identity, placed at b's original slot
    assert [p.id for p in doc.parts] == ['b', 'c']
    merged = doc.parts[0]
    assert merged.kind == PartKind.SECTION
    assert merged.body == 'B body\n\nA body'  # ids order
    # no content dropped
    assert 'A body' in merged.body and 'B body' in merged.body


def test_merge_reorders_body_and_survivor_by_ids():
    doc = Document(parts=[_part('a', 'A body'), _part('b', 'B body')])
    doc.apply([MergeParts(ids=['a', 'b'])])
    assert doc.parts[0].id == 'a'
    assert doc.parts[0].body == 'A body\n\nB body'


def test_merge_keeps_primary_metadata():
    primary = Part(id='keep', kind=PartKind.FILE, title='keep.py',
                   body='print(1)', origin_task='task-x')
    other = _part('other', 'prose')
    doc = Document(parts=[other, primary])
    doc.apply([MergeParts(ids=['keep', 'other'])])
    merged = doc.parts[0]
    assert merged.id == 'keep'
    assert merged.kind == PartKind.FILE
    assert merged.title == 'keep.py'
    assert merged.origin_task == 'task-x'
    assert merged.body == 'print(1)\n\nprose'


def test_merge_atomic_on_unknown_id():
    a, b, c = _part('a', 'a'), _part('b', 'b'), _part('c', 'c')
    doc = Document(parts=[a, b, c])
    with pytest.raises(DocumentApplyError, match='unknown part id'):
        doc.apply([MergeParts(ids=['b', 'missing'])])
    # nothing changed
    assert [p.id for p in doc.parts] == ['a', 'b', 'c']
    assert doc.parts[0] is a


def test_merge_untargeted_parts_keep_identity():
    a = _part('a', 'keep me')
    b = _part('b', 'b')
    c = _part('c', 'c')
    doc = Document(parts=[a, b, c])
    doc.apply([MergeParts(ids=['b', 'c'])])
    assert [p.id for p in doc.parts] == ['a', 'b']
    assert doc.parts[0] is a  # untouched part keeps object identity


def test_merge_rejects_duplicate_ids():
    doc = Document(parts=[_part('a', 'a'), _part('b', 'b')])
    with pytest.raises(ValueError, match='must be unique'):
        MergeParts(ids=['a', 'a'])


def test_merge_rejects_single_id():
    with pytest.raises(ValueError):
        MergeParts(ids=['only'])


def test_merge_is_patch_only_for_integrity():
    # A merge does not write a sub-task payload, so it must not require one.
    doc = Document(parts=[_part('a', 'A'), _part('b', 'B')])
    ops = [MergeParts(ids=['a', 'b'])]
    doc.apply(ops, current_result='an unrelated sub-task result')
    assert_payload_kept(doc, ops, 'an unrelated sub-task result')
    assert doc.parts[0].body == 'A\n\nB'


# --- optional titles (0-02 / D1) ------------------------------------------


def test_part_title_is_optional():
    p = Part(id='a', kind=PartKind.SECTION, body='standalone body')
    assert p.title is None


def test_add_part_without_title():
    doc = Document.empty()
    doc.apply([AddPart(id='a', kind='section', body='no heading needed')])
    assert doc.parts[0].title is None
    rendered = doc.render()
    assert '## ' not in rendered
    assert 'no heading needed' in rendered


def test_untitled_file_part_renders_fallback_heading():
    doc = Document.empty()
    doc.apply([AddPart(id='script', kind='file', body='print(1)')])
    rendered = doc.render('markdown_with_files')
    assert '## file' in rendered
    assert 'print(1)' in rendered


def test_title_none_round_trips_through_snapshot():
    doc = Document(
        parts=[Part(id='a', kind=PartKind.SECTION, body='x')],
    )
    snap = doc.to_dict()
    rehydrated = Part.model_validate(snap['parts'][0])
    assert rehydrated.title is None
    # and Document(**snapshot)-style reconstruction via the harness path
    doc2 = Document(
        title=snap['title'],
        parts=[Part.model_validate(p) for p in snap['parts']],
        summary=snap['summary'],
        op_log=[],
        render_mode=snap['render_mode'],
    )
    assert doc2.parts[0].title is None
    assert doc2.outline()[0].title is None


def test_from_dict_round_trips_to_dict():
    doc = Document(
        title='Doc',
        parts=[
            Part(id='a', kind=PartKind.SECTION, title=None, body='body a'),
            Part(id='b', kind=PartKind.FILE, title='f.py', body='print(1)'),
        ],
        summary='old summary',
        render_mode='markdown_with_files',
    )
    doc.apply(
        [MergeParts(ids=['b', 'a']), AddPart(id='c', kind='section', body='new')],
        origin_task='t',
    )
    rehydrated = Document.from_dict(doc.to_dict())
    assert rehydrated.title == doc.title
    assert [type(p) for p in rehydrated.parts] == [Part, Part]
    assert [p.id for p in rehydrated.parts] == [p.id for p in doc.parts]
    assert [p.body for p in rehydrated.parts] == [p.body for p in doc.parts]
    assert [p.kind for p in rehydrated.parts] == [p.kind for p in doc.parts]
    assert rehydrated.summary == doc.summary
    assert len(rehydrated.op_log) == len(doc.op_log)
    assert rehydrated.op_log[0].op.type == 'merge_parts'
    # attribute access that used to crash on raw dicts
    assert [o.id for o in rehydrated.outline()] == [p.id for p in rehydrated.parts]
    assert rehydrated.render('markdown_with_files') == doc.render('markdown_with_files')
    # tolerant of a minimal snapshot (missing optional keys)
    minimal = Document.from_dict({'parts': [{'id': 'x', 'kind': 'section', 'body': 'y'}]})
    assert minimal.parts[0].body == 'y'
    assert minimal.summary == ''


def test_oracle_search_survives_untitled_part():
    from reasoning_sub_agents.oracle.document_oracle import DocumentOracle

    doc = Document(
        parts=[
            Part(id='a', kind=PartKind.SECTION, body='alpha beta gamma'),
            Part(id='b', kind=PartKind.SECTION, title=None, body='delta epsilon'),
        ],
    )
    oracle = DocumentOracle(doc)
    hits = oracle.search('delta')
    assert any(h.part_id == 'b' for h in hits)
    # list_parts (outline) must not crash on None title
    assert [p['id'] for p in oracle.list_parts()] == ['a', 'b']


def test_merge_changed_part_ids_covers_survivor_and_sources():
    from reasoning_sub_agents.execution_synthesiser.document_composer import (
        changed_part_ids,
    )

    ops = [MergeParts(ids=['b', 'a']), UpdatePart(id='c', body='x')]
    assert changed_part_ids(ops) == ['b', 'a', 'c']


def test_merge_records_op_log():
    doc = Document(parts=[_part('a', 'a'), _part('b', 'b')])
    doc.apply([MergeParts(ids=['a', 'b'])], origin_task='consolidate')
    assert len(doc.op_log) == 1
    assert doc.op_log[0].op.type == 'merge_parts'
    assert doc.op_log[0].origin_task == 'consolidate'


# 0-09: a file part's body is raw; render() adds the fence.

FENCED_SCRIPT = '```python\nimport sys\nprint(sys.argv)\n```'


def test_add_file_part_body_source_unwraps_outer_fence():
    doc = Document.empty()
    ops = [
        AddPart(
            id='tool-py',
            kind='file',
            title='tool.py',
            body_source='current_result',
        )
    ]
    doc.apply(ops, current_result=FENCED_SCRIPT)
    assert doc.parts[0].body == 'import sys\nprint(sys.argv)'
    assert doc.render().count('```') == 2
    assert_payload_kept(doc, ops, FENCED_SCRIPT)


def test_update_file_part_body_source_unwraps_outer_fence():
    doc = Document(parts=[_part('tool-py', 'old', PartKind.FILE)])
    ops = [UpdatePart(id='tool-py', body_source='current_result')]
    doc.apply(ops, current_result=FENCED_SCRIPT)
    assert doc.parts[0].body == 'import sys\nprint(sys.argv)'
    assert_payload_kept(doc, ops, FENCED_SCRIPT)


def test_literal_file_body_unwraps_outer_fence():
    doc = Document.empty()
    doc.apply(
        [AddPart(id='run-sh', kind='file', title='run.sh', body='```bash\necho hi\n```')]
    )
    assert doc.parts[0].body == 'echo hi'


def test_section_part_keeps_fence():
    doc = Document.empty()
    doc.apply(
        [AddPart(id='usage', kind='section', body_source='current_result')],
        current_result=FENCED_SCRIPT,
    )
    assert doc.parts[0].body == FENCED_SCRIPT


@pytest.mark.parametrize(
    'body',
    [
        # Two fenced blocks: the first fence is not a wrapper.
        '```bash\npip install x\n```\n\nThen:\n\n```py\nimport x\n```',
        # Commentary after the code: not a pure wrapper, left for the prompt rule.
        '```python\nprint(1)\n```\n\n| check | ok |',
        # No fence at all.
        'print(1)\n',
        # Opening fence only.
        '```python\nprint(1)',
    ],
)
def test_file_part_body_not_a_wrapper_is_untouched(body):
    doc = Document.empty()
    doc.apply(
        [AddPart(id='f', kind='file', title='f.py', body_source='current_result')],
        current_result=body,
    )
    assert doc.parts[0].body == body


def test_file_part_longer_wrapper_keeps_inner_fences():
    readme = '# Tool\n\n```bash\ntool --help\n```'
    doc = Document.empty()
    doc.apply(
        [AddPart(id='readme', kind='file', title='README.md', body_source='current_result')],
        current_result=f'````markdown\n{readme}\n````',
    )
    assert doc.parts[0].body == readme
