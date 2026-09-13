from unittest.mock import patch

from openai.types.chat import ChatCompletionMessage

from reasoning_sub_agents.document import AddPart, Document, ReplaceInPart
from reasoning_sub_agents.execution_synthesiser.document_composer import (
    ComposerResponse,
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
