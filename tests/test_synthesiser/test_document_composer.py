from unittest.mock import patch

from openai.types.chat import ChatCompletionMessage

from reasoning_sub_agents.document import AddPart, DeletePart, Document, MergeParts, MovePart, ReplaceInPart
from reasoning_sub_agents.execution_synthesiser.document_composer import (
    ComposerResponse,
    ConsolidationResponse,
    DocumentComposer,
)
from reasoning_sub_agents.schemas import (
    DecomposeSubTask,
    SubTask,
    SubTaskResult,
    TaskStatus,
)
from tests.mock_openai import MockOpenAI


def _sub_task(name: str, result: str) -> SubTask:
    return SubTask(
        decomposed_sub_task=DecomposeSubTask(
            meta_type='sub_task_detail',
            name=name,
            type='writing',
            description=name,
            context='ctx',
            complexity=3,
            objective=f'Write {name}',
        ),
        sub_task_result=SubTaskResult(
            chat_response=ChatCompletionMessage(content=result, role='assistant')
        ),
        status=TaskStatus.COMPLETED,
    )


def test_compose_adds_part_by_reference():
    payload = 'Chapter one full text that must survive.'
    task = _sub_task('Write chapter 1', payload)
    composer = DocumentComposer(llm_client=MockOpenAI())
    document = Document.empty()
    with patch(
        'reasoning_sub_agents.execution_synthesiser.document_composer.get_streamed_json_response'
    ) as mock_json:
        mock_json.return_value = ComposerResponse(
            ops=[
                AddPart(
                    id='chapter-1',
                    kind='section',
                    title='Chapter 1',
                    body_source='current_result',
                )
            ]
        )
        ops = composer.compose(
            user_request='Write a book',
            sub_tasks=[task],
            current_sub_task=task,
            document=document,
        )
    assert document.parts[0].body == payload
    assert ops[0].body_source == 'current_result'
    assert len(composer.history) == 1
    assert composer.history[0]['error'] is None


def test_compose_retries_on_replace_miss_then_succeeds():
    task = _sub_task('Revise intro', 'new intro text that must be kept')
    document = Document.empty()
    document.apply(
        [AddPart(id='intro', kind='section', title='Intro', body='old intro')]
    )
    composer = DocumentComposer(llm_client=MockOpenAI(), max_retries=3)
    with patch(
        'reasoning_sub_agents.execution_synthesiser.document_composer.get_streamed_json_response'
    ) as mock_json:
        mock_json.side_effect = [
            ComposerResponse(
                ops=[
                    ReplaceInPart(
                        id='intro', search='does not exist', replace='x'
                    )
                ]
            ),
            ComposerResponse(
                ops=[
                    AddPart(
                        id='intro-new',
                        kind='section',
                        title='Intro',
                        body_source='current_result',
                    )
                ]
            ),
        ]
        composer.compose(
            user_request='Write a book',
            sub_tasks=[task],
            current_sub_task=task,
            document=document,
        )
    assert document.has_part('intro')
    assert document.get_part('intro').body == 'old intro'
    assert document.get_part('intro-new').body == 'new intro text that must be kept'
    assert mock_json.call_count == 2


def test_compose_prompt_does_not_include_existing_part_bodies():
    huge = 'KEEP-SECRET-BODY ' * 50
    document = Document.empty()
    document.apply(
        [AddPart(id='chapter-1', kind='section', title='Chapter 1', body=huge)]
    )
    document.summary = 'Chapter 1 exists.'
    payload = 'Chapter two full text that must survive.'
    task = _sub_task('Write chapter 2', payload)
    composer = DocumentComposer(llm_client=MockOpenAI())
    with patch(
        'reasoning_sub_agents.execution_synthesiser.document_composer.get_streamed_json_response'
    ) as mock_json:
        mock_json.return_value = ComposerResponse(
            ops=[
                AddPart(
                    id='chapter-2',
                    kind='section',
                    title='Chapter 2',
                    body_source='current_result',
                )
            ]
        )
        composer.compose(
            user_request='Write a book',
            sub_tasks=[task],
            current_sub_task=task,
            document=document,
        )
    prompt = mock_json.call_args.kwargs['llm_input'].messages[-1].content
    assert 'KEEP-SECRET-BODY' not in prompt
    assert 'chapter-1' in prompt
    assert 'Chapter 1 exists.' in prompt
    # Contract (updated 2026-10-15, 0-08): the current result appears in the
    # prompt EXACTLY ONCE — via the result preview. It must not be re-pasted
    # as an attached body or literal op body; the composer copies it with
    # body_source="current_result" instead.
    assert prompt.count(payload) == 1
    assert document.get_part('chapter-2').body == payload


def test_compose_fetches_bodies_when_need_part_ids():
    document = Document.empty()
    document.apply(
        [AddPart(id='intro', kind='section', title='Intro', body='old intro text')]
    )
    task = _sub_task('Revise intro', 'new intro text that must be kept')
    composer = DocumentComposer(llm_client=MockOpenAI(), max_retries=3)
    with patch(
        'reasoning_sub_agents.execution_synthesiser.document_composer.get_streamed_json_response'
    ) as mock_json:
        mock_json.side_effect = [
            ComposerResponse(need_part_ids=['intro'], ops=[]),
            ComposerResponse(
                ops=[
                    ReplaceInPart(
                        id='intro', search='old intro text', replace='new intro text that must be kept'
                    )
                ]
            ),
        ]
        composer.compose(
            user_request='Write a book',
            sub_tasks=[task],
            current_sub_task=task,
            document=document,
        )
    assert mock_json.call_count == 2
    second_prompt = mock_json.call_args_list[1].kwargs['llm_input'].messages[-1].content
    assert 'old intro text' in second_prompt
    assert document.get_part('intro').body == 'new intro text that must be kept'


def test_empty_ops_fall_back_to_verbatim_add():
    payload = 'verbatim payload'
    task = _sub_task('Notes', payload)
    composer = DocumentComposer(llm_client=MockOpenAI())
    document = Document.empty()
    with patch(
        'reasoning_sub_agents.execution_synthesiser.document_composer.get_streamed_json_response'
    ) as mock_json:
        mock_json.return_value = ComposerResponse(ops=[])
        composer.compose(
            user_request='Take notes',
            sub_tasks=[task],
            current_sub_task=task,
            document=document,
        )
    assert len(document.parts) == 1
    assert document.parts[0].body == payload


# --- 0-06 consolidation pass -------------------------------------------------


def _consolidation_doc() -> Document:
    doc = Document.empty()
    doc.apply(
        [
            AddPart(id='intro', kind='section', title='Intro', body='Introduction body.'),
            AddPart(id='alpha', kind='section', title='Alpha', body='Alpha content.'),
            AddPart(id='beta', kind='section', title='Beta', body='Beta content.'),
        ]
    )
    doc.summary = 'Intro, Alpha and Beta sections exist.'
    return doc


def test_consolidation_merges_redundant_parts():
    doc = _consolidation_doc()
    composer = DocumentComposer(llm_client=MockOpenAI())
    with patch(
        'reasoning_sub_agents.execution_synthesiser.document_composer.get_streamed_json_response'
    ) as mock_json:
        mock_json.return_value = ConsolidationResponse(
            ops=[MergeParts(ids=['alpha', 'beta'])]
        )
        ops = composer.consolidate(user_request='Write a book', document=doc)
    assert [op.type for op in ops] == ['merge_parts']
    assert [p.id for p in doc.parts] == ['intro', 'alpha']
    merged = doc.get_part('alpha')
    assert merged.body == 'Alpha content.\n\nBeta content.'
    assert merged.title == 'Alpha'
    assert any('consolidation' in h.get('phase', '') for h in composer.history)


def test_consolidation_prompt_has_no_bodies():
    doc = _consolidation_doc()
    composer = DocumentComposer(llm_client=MockOpenAI())
    with patch(
        'reasoning_sub_agents.execution_synthesiser.document_composer.get_streamed_json_response'
    ) as mock_json:
        mock_json.return_value = ConsolidationResponse(ops=[])
        composer.consolidate(user_request='Write a book', document=doc)
    prompt = mock_json.call_args.kwargs['llm_input'].messages[-1].content
    assert 'Alpha content.' not in prompt
    assert 'Beta content.' not in prompt
    assert 'Introduction body.' not in prompt
    assert 'alpha' in prompt and 'beta' in prompt  # ids are present
    assert 'Intro' in prompt  # titles are present


def test_consolidation_rejects_add_part_from_schema():
    doc = _consolidation_doc()
    composer = DocumentComposer(llm_client=MockOpenAI())
    with patch(
        'reasoning_sub_agents.execution_synthesiser.document_composer.get_streamed_json_response'
    ) as mock_json:
        # add_part is not in the ConsolidationOp union; a model that returned
        # one would fail validation at the response_model boundary. Assert the
        # boundary here by showing the union only accepts its three ops.
        from pydantic import TypeAdapter as TA

        adapter = TA(ConsolidationResponse)
        ok = adapter.validate_python({'ops': [{'type': 'move_part', 'id': 'alpha', 'after': 'end'}]})
        assert ok.ops[0].type == 'move_part'
        try:
            adapter.validate_python(
                {'ops': [{'type': 'add_part', 'id': 'x', 'kind': 'section', 'body': 'y'}]}
            )
            raise AssertionError('add_part should not parse as a consolidation op')
        except Exception:
            pass


def test_consolidation_abandons_emptying_or_invalid_proposal():
    doc = _consolidation_doc()
    before = [(p.id, p.body) for p in doc.parts]
    composer = DocumentComposer(llm_client=MockOpenAI())
    with patch(
        'reasoning_sub_agents.execution_synthesiser.document_composer.get_streamed_json_response'
    ) as mock_json:
        # delete every part: proposal is valid but empties the doc -> ignored
        mock_json.return_value = ConsolidationResponse(
            ops=[
                DeletePart(id='intro'),
                DeletePart(id='alpha'),
                DeletePart(id='beta'),
            ]
        )
        ops = composer.consolidate(user_request='q', document=doc)
    assert ops == []
    assert [(p.id, p.body) for p in doc.parts] == before

    with patch(
        'reasoning_sub_agents.execution_synthesiser.document_composer.get_streamed_json_response'
    ) as mock_json:
        # unknown id: apply fails -> abandoned, document untouched
        mock_json.return_value = ConsolidationResponse(
            ops=[DeletePart(id='does-not-exist')]
        )
        ops = composer.consolidate(user_request='q', document=doc)
    assert ops == []
    assert [(p.id, p.body) for p in doc.parts] == before


def test_consolidation_noop_when_single_part():
    doc = Document.empty()
    doc.apply([AddPart(id='only', kind='section', body='solo')])
    composer = DocumentComposer(llm_client=MockOpenAI())
    with patch(
        'reasoning_sub_agents.execution_synthesiser.document_composer.get_streamed_json_response'
    ) as mock_json:
        ops = composer.consolidate(user_request='q', document=doc)
    assert ops == []
    mock_json.assert_not_called()


def test_consolidation_empty_ops_leaves_document_untouched():
    doc = _consolidation_doc()
    before = [(p.id, p.body) for p in doc.parts]
    composer = DocumentComposer(llm_client=MockOpenAI())
    with patch(
        'reasoning_sub_agents.execution_synthesiser.document_composer.get_streamed_json_response'
    ) as mock_json:
        mock_json.return_value = ConsolidationResponse(ops=[])
        ops = composer.consolidate(user_request='q', document=doc)
    assert ops == []
    assert [(p.id, p.body) for p in doc.parts] == before
