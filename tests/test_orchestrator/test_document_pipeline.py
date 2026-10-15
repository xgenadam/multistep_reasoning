from unittest.mock import MagicMock, patch

from openai.types.chat import ChatCompletionMessage

from reasoning_sub_agents.document import AddPart
from reasoning_sub_agents.execution_synthesiser.document_composer import DocumentComposer
from reasoning_sub_agents.oracle import DocumentOracle
from reasoning_sub_agents.schemas import (
    DecomposeSubTask,
    SubTask,
    SubTaskResult,
    TaskStatus,
)
from reasoning_sub_agents.task_orchestrator import TaskOrchestrator
from tests.mock_openai import MockOpenAI


def _task(name: str, result: str | None = None) -> SubTask:
    task = SubTask(
        decomposed_sub_task=DecomposeSubTask(
            meta_type='sub_task_detail',
            name=name,
            type='writing',
            description=name,
            context='ctx',
            complexity=3,
            objective=name,
        )
    )
    if result is not None:
        task.sub_task_result = SubTaskResult(
            chat_response=ChatCompletionMessage(content=result, role='assistant')
        )
        task.status = TaskStatus.COMPLETED
    return task


def test_document_pipeline_preserves_verbatim_parts():
    task1 = _task('Chapter 1')
    task2 = _task('Chapter 2')
    chapter_one = 'Long chapter one text that must not be summarised away.'
    chapter_two = 'Long chapter two text that must also survive.'

    decomposer = MagicMock()
    decomposer.generate_sub_tasks.return_value = [task1, task2]
    decomposer.history = {}

    executor = MagicMock()

    def run_one(sub_task, **kwargs):
        payload = chapter_one if sub_task is task1 else chapter_two
        sub_task.sub_task_result = SubTaskResult(
            chat_response=ChatCompletionMessage(content=payload, role='assistant')
        )
        sub_task.status = TaskStatus.COMPLETED
        return sub_task

    executor.execute_one.side_effect = run_one
    executor.history = []

    composer = DocumentComposer(llm_client=MockOpenAI())
    add_ops = [
        AddPart(
            id='chapter-1',
            kind='section',
            title='Chapter 1',
            body_source='current_result',
        ),
        AddPart(
            id='chapter-2',
            kind='section',
            title='Chapter 2',
            body_source='current_result',
        ),
    ]

    def fake_json(**kwargs):
        from reasoning_sub_agents.execution_synthesiser.document_composer import (
            ComposerResponse,
        )

        idx = fake_json.calls
        fake_json.calls += 1
        return ComposerResponse(ops=[add_ops[idx]])

    fake_json.calls = 0

    oracle = MagicMock(spec=DocumentOracle)
    oracle.update_summary.return_value = 'summary'

    orchestrator = TaskOrchestrator(
        decomposer=decomposer,
        agent_executor=executor,
        llm_client=MockOpenAI(),
        document_composer=composer,
        oracle_factory=lambda document: oracle,
    )
    with patch(
        'reasoning_sub_agents.execution_synthesiser.document_composer.get_streamed_json_response',
        side_effect=fake_json,
    ):
        response, accumulated = orchestrator.query(
            'Write a book', return_sub_tasks=True
        )

    assert chapter_one in response.content
    assert chapter_two in response.content
    assert accumulated.document_snapshot is not None
    part_bodies = [part['body'] for part in accumulated.document_snapshot['parts']]
    assert part_bodies == [chapter_one, chapter_two]
    assert executor.execute_one.call_count == 2
    assert oracle.update_summary.call_count == 2
    # Second task should have seen chapter 1 in the outline
    second_call = executor.execute_one.call_args_list[1]
    outline = second_call.kwargs['outline']
    assert outline[0].id == 'chapter-1'


def test_document_pipeline_reuses_existing_document():
    from reasoning_sub_agents.document import Document, Part, PartKind

    existing = Document(
        parts=[
            Part(
                id='chapter-1',
                kind=PartKind.SECTION,
                title='Chapter 1',
                body='Already written chapter one.',
            )
        ]
    )
    task = _task('Chapter 2')
    decomposer = MagicMock()
    decomposer.generate_sub_tasks.return_value = [task]
    decomposer.history = {}
    executor = MagicMock()

    def run_one(sub_task, **kwargs):
        sub_task.sub_task_result = SubTaskResult(
            chat_response=ChatCompletionMessage(
                content='Chapter two body', role='assistant'
            )
        )
        sub_task.status = TaskStatus.COMPLETED
        return sub_task

    executor.execute_one.side_effect = run_one
    executor.history = []
    composer = DocumentComposer(llm_client=MockOpenAI())
    oracle = MagicMock(spec=DocumentOracle)
    oracle.update_summary.return_value = 'summary'
    orchestrator = TaskOrchestrator(
        decomposer=decomposer,
        agent_executor=executor,
        llm_client=MockOpenAI(),
        document_composer=composer,
        oracle_factory=lambda document: oracle,
    )
    with patch(
        'reasoning_sub_agents.execution_synthesiser.document_composer.get_streamed_json_response'
    ) as mock_json:
        from reasoning_sub_agents.execution_synthesiser.document_composer import (
            ComposerResponse,
        )

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
        response = orchestrator.query(
            'Write chapter 2',
            document=existing,
            chat_context='User: write chapter 1\nAssistant: Already written chapter one.',
        )

    decomposer.generate_sub_tasks.assert_called_once()
    assert decomposer.generate_sub_tasks.call_args.kwargs['chat_context']
    assert existing.has_part('chapter-1')
    assert existing.has_part('chapter-2')
    assert 'Already written chapter one.' in response.content
    assert 'Chapter two body' in response.content
    outline = executor.execute_one.call_args.kwargs['outline']
    assert outline[0].id == 'chapter-1'


def test_document_pipeline_empty_sub_tasks_uses_fallback():
    decomposer = MagicMock()
    decomposer.generate_sub_tasks.return_value = []
    decomposer.history = {}
    executor = MagicMock()

    def run_one(sub_task, **kwargs):
        sub_task.sub_task_result = SubTaskResult(
            chat_response=ChatCompletionMessage(
                content='Photosynthesis is how plants make food.',
                role='assistant',
            )
        )
        sub_task.status = TaskStatus.COMPLETED
        return sub_task

    executor.execute_one.side_effect = run_one
    executor.history = []
    composer = DocumentComposer(llm_client=MockOpenAI())
    oracle = MagicMock(spec=DocumentOracle)
    oracle.update_summary.return_value = 'summary'
    orchestrator = TaskOrchestrator(
        decomposer=decomposer,
        agent_executor=executor,
        llm_client=MockOpenAI(),
        document_composer=composer,
        oracle_factory=lambda document: oracle,
    )
    with patch(
        'reasoning_sub_agents.execution_synthesiser.document_composer.get_streamed_json_response'
    ) as mock_json:
        from reasoning_sub_agents.execution_synthesiser.document_composer import (
            ComposerResponse,
        )

        mock_json.return_value = ComposerResponse(
            ops=[
                AddPart(
                    id='answer',
                    kind='section',
                    title='Answer',
                    body_source='current_result',
                )
            ]
        )
        response = orchestrator.query('Explain photosynthesis')

    assert executor.execute_one.call_count == 1
    executed = executor.execute_one.call_args.args[0]
    assert 'photosynthesis' in executed.decomposed_sub_task.objective.lower()
    assert 'Photosynthesis is how plants make food.' in response.content


def test_document_pipeline_continues_after_executor_error():
    first = _task('Chapter 1')
    second = _task('Chapter 2')
    decomposer = MagicMock()
    decomposer.generate_sub_tasks.return_value = [first, second]
    decomposer.history = {}
    executor = MagicMock()

    def run_one(sub_task, **kwargs):
        if sub_task is first:
            raise RuntimeError('oracle_loop executor exceeded 8 rounds')
        sub_task.sub_task_result = SubTaskResult(
            chat_response=ChatCompletionMessage(
                content='Chapter two survived.', role='assistant'
            )
        )
        sub_task.status = TaskStatus.COMPLETED
        return sub_task

    executor.execute_one.side_effect = run_one
    executor.history = []
    composer = DocumentComposer(llm_client=MockOpenAI())
    oracle = MagicMock(spec=DocumentOracle)
    oracle.update_summary.return_value = 'summary'
    orchestrator = TaskOrchestrator(
        decomposer=decomposer,
        agent_executor=executor,
        llm_client=MockOpenAI(),
        document_composer=composer,
        oracle_factory=lambda document: oracle,
    )
    with patch(
        'reasoning_sub_agents.execution_synthesiser.document_composer.get_streamed_json_response'
    ) as mock_json:
        from reasoning_sub_agents.execution_synthesiser.document_composer import (
            ComposerResponse,
        )

        mock_json.side_effect = [
            ComposerResponse(
                ops=[
                    AddPart(
                        id='chapter-1',
                        kind='section',
                        title='Chapter 1',
                        body_source='current_result',
                    )
                ]
            ),
            ComposerResponse(
                ops=[
                    AddPart(
                        id='chapter-2',
                        kind='section',
                        title='Chapter 2',
                        body_source='current_result',
                    )
                ]
            ),
        ]
        response = orchestrator.query('Write two chapters')

    assert first.status == TaskStatus.FAILED
    assert 'exceeded 8 rounds' in first.sub_task_result.chat_response.content
    assert 'Chapter two survived.' in response.content
    assert executor.execute_one.call_count == 2


def test_document_pipeline_runs_consolidation_when_enabled():
    from reasoning_sub_agents.config.schema import OptionsConfig
    from reasoning_sub_agents.document import MergeParts
    from reasoning_sub_agents.execution_synthesiser.document_composer import (
        ComposerResponse,
        ConsolidationResponse,
    )

    task1 = _task('Chapter 1')
    task2 = _task('Chapter 2')

    decomposer = MagicMock()
    decomposer.generate_sub_tasks.return_value = [task1, task2]
    decomposer.history = {}
    executor = MagicMock()

    def run_one(sub_task, **kwargs):
        payload = 'one body' if sub_task is task1 else 'two body'
        sub_task.sub_task_result = SubTaskResult(
            chat_response=ChatCompletionMessage(content=payload, role='assistant')
        )
        sub_task.status = TaskStatus.COMPLETED
        return sub_task

    executor.execute_one.side_effect = run_one
    executor.history = []

    composer = DocumentComposer(llm_client=MockOpenAI())
    oracle = MagicMock(spec=DocumentOracle)
    oracle.update_summary.return_value = 'summary'

    orchestrator = TaskOrchestrator(
        decomposer=decomposer,
        agent_executor=executor,
        llm_client=MockOpenAI(),
        document_composer=composer,
        oracle_factory=lambda document: oracle,
        options=OptionsConfig(consolidation=True),
    )
    calls = {'n': 0}

    def fake_json(**kwargs):
        calls['n'] += 1
        if calls['n'] <= 2:
            return ComposerResponse(
                ops=[
                    AddPart(
                        id=f'chapter-{calls["n"]}',
                        kind='section',
                        title=f'Chapter {calls["n"]}',
                        body_source='current_result',
                    )
                ]
            )
        return ConsolidationResponse(ops=[MergeParts(ids=['chapter-1', 'chapter-2'])])

    with patch(
        'reasoning_sub_agents.execution_synthesiser.document_composer.get_streamed_json_response',
        side_effect=fake_json,
    ):
        response, accumulated = orchestrator.query('Write a book', return_sub_tasks=True)

    assert calls['n'] == 3
    assert oracle.update_summary.call_count == 3  # 2 composes + 1 consolidation
    parts = accumulated.document_snapshot['parts']
    assert [p['id'] for p in parts] == ['chapter-1']
    assert parts[0]['body'] == 'one body\n\ntwo body'
    assert 'one body' in response.content and 'two body' in response.content
    phases = [h.get('phase') for h in composer.history]
    assert 'consolidation' in phases


def test_document_pipeline_skips_consolidation_by_default():
    from reasoning_sub_agents.execution_synthesiser.document_composer import (
        ComposerResponse,
    )

    task1 = _task('Chapter 1')

    decomposer = MagicMock()
    decomposer.generate_sub_tasks.return_value = [task1]
    decomposer.history = {}
    executor = MagicMock()
    executor.execute_one.side_effect = lambda sub_task, **kw: (
        setattr(
            sub_task,
            'sub_task_result',
            SubTaskResult(
                chat_response=ChatCompletionMessage(content='body', role='assistant')
            ),
        )
        or setattr(sub_task, 'status', TaskStatus.COMPLETED)
        or sub_task
    )
    executor.history = []

    composer = DocumentComposer(llm_client=MockOpenAI())
    oracle = MagicMock(spec=DocumentOracle)
    oracle.update_summary.return_value = 'summary'

    orchestrator = TaskOrchestrator(
        decomposer=decomposer,
        agent_executor=executor,
        llm_client=MockOpenAI(),
        document_composer=composer,
        oracle_factory=lambda document: oracle,
    )  # default OptionsConfig: consolidation off

    with patch(
        'reasoning_sub_agents.execution_synthesiser.document_composer.get_streamed_json_response'
    ) as mock_json:
        mock_json.return_value = ComposerResponse(
            ops=[AddPart(id='chapter-1', kind='section', body_source='current_result')]
        )
        orchestrator.query('Write a book')

    assert mock_json.call_count == 1  # only the compose, no consolidation call
    assert oracle.update_summary.call_count == 1
    assert all('consolidation' != h.get('phase') for h in composer.history)
