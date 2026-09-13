import pytest

from reasoning_sub_agents.document import (
    AddPart,
    AppendToPart,
    DeletePart,
    Document,
    DocumentApplyError,
    DocumentIntegrityError,
    InsertInPart,
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
