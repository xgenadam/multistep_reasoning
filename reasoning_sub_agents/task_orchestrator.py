import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Self

from openai import OpenAI
from openai.types.chat import ChatCompletionMessage

from .config.loader import load_orchestrator_config, parse_orchestrator_config
from .config.registry import BuildContext, validate_component_compatibility
from .config.schema import OptionsConfig, OrchestratorConfig
from .document import Document
from .document.summary import update_rolling_summary
from .execution_synthesiser.base import ExecutorSynthesiserBase
from .execution_synthesiser.document_composer import (
    DocumentComposer,
    changed_part_ids,
)
from .executor.base import ExecutorBase
from .llama_utils import (
    create_llama_client,
    current_token_meter,
    prompt_logging,
    thinking_session,
    token_meter,
)
from .oracle.document_oracle import DocumentOracle
from .progress import (
    live,
    set_document,
    set_phase,
    set_sub_tasks,
    set_task_status,
    set_user_query,
)
from .schemas import AccumulatedResult, SubTask, SubTaskResult, TaskStatus
from .task_decomposition.base import TaskDecomposerBase
from .task_decomposition.simple_decomposition import ensure_sub_tasks

logger = logging.getLogger(__name__)

OracleFactory = Callable[[Document], DocumentOracle]
# on_step(kind, payload): 'plan' once the decomposer has finished, then
# 'document' after each sub-task's compose and summary (and after
# consolidation). Logging only: the orchestrator never reads anything back.
StepObserver = Callable[[str, dict], None]


class TaskOrchestrator:
    def __init__(
        self,
        decomposer: TaskDecomposerBase,
        agent_executor: ExecutorBase,
        result_synthesiser: ExecutorSynthesiserBase | None = None,
        llm_client: OpenAI | None = None,
        history: list | None = None,
        *,
        document_composer: DocumentComposer | None = None,
        oracle_factory: OracleFactory | None = None,
        options: OptionsConfig | None = None,
        on_step: StepObserver | None = None,
    ):
        if llm_client is None:
            raise ValueError('llm_client is required')
        if result_synthesiser is None and document_composer is None:
            raise ValueError('Provide result_synthesiser or document_composer')
        if result_synthesiser is not None and document_composer is not None:
            raise ValueError(
                'Cannot provide both result_synthesiser and document_composer'
            )
        self.decomposer = decomposer
        self.agent_executor = agent_executor
        self.result_synthesiser = result_synthesiser
        self.document_composer = document_composer
        self.oracle_factory = oracle_factory
        self.options = options or OptionsConfig()
        self.llm_client = llm_client
        self.history = [] if history is None else history
        self.on_step = on_step

    def _emit(self, kind: str, payload: dict) -> None:
        if self.on_step is None:
            return
        try:
            self.on_step(kind, payload)
        except Exception:  # noqa: BLE001 - an observer never changes a turn
            logger.exception('on_step observer failed on %s; ignored', kind)

    def query(
        self,
        user_input: str,
        return_sub_tasks: bool = False,
        *,
        document: Document | None = None,
        chat_context: str | None = None,
        on_progress: Callable[[str], None] | None = None,
        turn_id: str | None = None,
    ) -> ChatCompletionMessage | tuple[ChatCompletionMessage, AccumulatedResult]:
        result = None
        for kind, payload in self.iter_query(
            user_input, document=document, chat_context=chat_context, turn_id=turn_id
        ):
            if kind == 'status' and on_progress is not None:
                on_progress(str(payload))
            elif kind == 'done':
                result = payload
        if result is None:
            raise RuntimeError('orchestrator produced no result')
        if return_sub_tasks:
            return result.chat_response, result
        return result.chat_response

    def iter_query(
        self,
        user_input: str,
        *,
        document: Document | None = None,
        chat_context: str | None = None,
        turn_id: str | None = None,
    ) -> Iterator[tuple[str, Any]]:
        """Yield ('status', message) then ('done', AccumulatedResult). Same-thread UI hook.

        turn_id names the turn's thinking side log (D-013); one is made up if
        it is None.
        """
        with prompt_logging(self.options.log_prompts), thinking_session(
            self.options, turn_id=turn_id
        ), token_meter(self.options.token_ceiling):
            yield from self._iter_query(
                user_input, document=document, chat_context=chat_context
            )

    def _iter_query(
        self,
        user_input: str,
        *,
        document: Document | None = None,
        chat_context: str | None = None,
    ) -> Iterator[tuple[str, Any]]:
        self.live_run = live()
        set_user_query(user_input)
        set_phase('Decomposing the request into sub-tasks…')
        yield ('status', 'Decomposing the request into sub-tasks…')
        sub_tasks = self.decomposer.generate_sub_tasks(
            user_input, chat_context=chat_context
        )
        if not sub_tasks:
            logger.warning(
                'Decomposer returned no sub-tasks; using a single fallback task'
            )
            sub_tasks = ensure_sub_tasks(user_input, sub_tasks)
        names = [
            task.decomposed_sub_task.name for task in sub_tasks
        ]
        set_sub_tasks(names, 'queued')
        self._emit('plan', {
            'sub_tasks': [t.decomposed_sub_task.model_dump(mode='json') for t in sub_tasks],
            'decomposition_history': self.decomposer.history,
        })
        yield (
            'status',
            f'Decomposed {len(sub_tasks)} sub-tasks: {", ".join(names) or "(none)"}',
        )

        logger.debug('executing sub tasks')
        if self.document_composer is not None:
            result: AccumulatedResult | None = None
            for kind, payload in self._iter_document_pipeline(
                user_input, sub_tasks, document=document
            ):
                if kind == 'status':
                    yield ('status', payload)
                else:
                    result = payload
            if result is None:
                raise RuntimeError('document pipeline produced no result')
            sub_task_execution_result = result
            synthesis_history = self.document_composer.history
        else:
            if self.result_synthesiser is None:
                raise RuntimeError('result_synthesiser is required in legacy mode')
            yield ('status', 'Executing sub-tasks (legacy synthesiser)…')
            sub_task_execution_result = self.agent_executor.execute_sub_tasks(
                user_request=user_input,
                sub_tasks=sub_tasks,
                synthesiser=self.result_synthesiser,
            )
            synthesis_history = self.result_synthesiser.history

        history_entry: dict[str, Any] = {
            'user_input': user_input,
            'chat_context': chat_context,
            'decomposition_history': self.decomposer.history,
            'execution_results': self.agent_executor.history,
            'synthesis_history': synthesis_history,
        }
        if sub_task_execution_result.document_snapshot is not None:
            history_entry['document'] = sub_task_execution_result.document_snapshot
        meter = current_token_meter()
        history_entry['completion_tokens'] = meter.completion_tokens if meter else None
        history_entry['estimated_calls'] = meter.estimated_calls if meter else None
        history_entry['token_ceiling'] = getattr(self, '_ceiling_stop', None)
        self.history.append(history_entry)
        yield ('done', sub_task_execution_result)

    def _run_document_pipeline(
        self,
        user_input: str,
        sub_tasks: list[SubTask],
        document: Document | None = None,
    ) -> AccumulatedResult:
        result = None
        for kind, payload in self._iter_document_pipeline(
            user_input, sub_tasks, document=document
        ):
            if kind == 'done':
                result = payload
        if result is None:
            raise RuntimeError('document pipeline produced no result')
        return result

    def _iter_document_pipeline(
        self,
        user_input: str,
        sub_tasks: list[SubTask],
        document: Document | None = None,
    ) -> Iterator[tuple[str, Any]]:
        if self.document_composer is None:
            raise RuntimeError('document pipeline requires document_composer')
        if not sub_tasks:
            logger.warning(
                'Document pipeline received no sub-tasks; using a single fallback task'
            )
            sub_tasks = ensure_sub_tasks(user_input, sub_tasks)

        if document is None:
            document = Document.empty(render_mode=self.options.render)
        oracle = self.oracle_factory(document) if self.oracle_factory else None
        last_task = sub_tasks[0]
        total = len(sub_tasks)
        self._ceiling_stop = None
        meter = current_token_meter()
        for idx, sub_task in enumerate(sub_tasks):
            name = sub_task.decomposed_sub_task.name
            if idx and meter is not None and meter.exceeded:
                # options.token_ceiling: stop here and return the Document as
                # it stands; the remaining sub-tasks stay pending.
                skipped = [t.decomposed_sub_task.name for t in sub_tasks[idx:]]
                self._ceiling_stop = {'ceiling': meter.ceiling, 'spent': meter.completion_tokens,
                                      'completed_sub_tasks': idx, 'skipped': skipped}
                logger.warning('token ceiling %s reached (%s spent) after %s/%s sub-tasks; '
                               'returning the document as it stands', meter.ceiling,
                               meter.completion_tokens, idx, total)
                for skipped_name in skipped:
                    set_task_status(skipped_name, 'skipped')
                yield ('status', f'Token ceiling reached after {idx}/{total} sub-tasks')
                break
            logger.info('Executing sub task %s of %s', idx, total)
            set_phase(f'Executing {idx + 1}/{total}: {name}')
            set_task_status(name, 'in_progress')
            yield ('status', f'Executing {idx + 1}/{total}: {name}')
            try:
                self.agent_executor.execute_one(
                    sub_task,
                    outline=document.outline(),
                    summary=document.summary,
                    oracle=oracle,
                    user_request=user_input,
                )
            except Exception as exc:
                logger.exception('sub-task %s failed; continuing with a stub', name)
                set_task_status(name, 'failed')
                sub_task.status = TaskStatus.FAILED
                sub_task.sub_task_result = SubTaskResult(
                    chat_response=ChatCompletionMessage(
                        role='assistant',
                        content=(
                            f'This sub-task failed before producing a deliverable: {exc}\n\n'
                            'Continuing with the remaining sub-tasks so some output '
                            'still reaches the document.'
                        ),
                    )
                )
            else:
                set_task_status(name, 'completed')
            set_phase(f'Composing after {idx + 1}/{total}: {name}')
            yield ('status', f'Composing after {idx + 1}/{total}: {name}')
            ops = self.document_composer.compose(
                user_request=user_input,
                sub_tasks=sub_tasks,
                current_sub_task=sub_task,
                document=document,
            )
            changed = changed_part_ids(ops)
            set_document(document.render())
            yield ('status', f'Updating summary after {idx + 1}/{total}: {name}')
            if oracle is not None:
                oracle.update_summary(changed)
            else:
                update_rolling_summary(
                    document,
                    changed,
                    self.llm_client,
                    max_words=self.options.summary_max_words,
                    prompt_token_budget=self.options.prompt_token_budget,
                )
            last_task = sub_task
            self._emit('document', {
                'step': idx + 1, 'of': total, 'sub_task': name, 'status': str(sub_task.status),
                'completion_tokens': meter.completion_tokens if meter else None,
                'snapshot': document.to_dict(),
            })

        # 0-06: optional consolidation pass after the final sub-task.
        # Outline + rolling summary only (no previews, D-N), merge/move/delete, best-effort.
        if self.options.consolidation and self._ceiling_stop is None:
            set_phase('Consolidating document')
            yield ('status', 'Consolidating document')
            try:
                cons_ops = self.document_composer.consolidate(
                    user_request=user_input,
                    document=document,
                )
            except Exception as exc:  # noqa: BLE001 - consolidation is best-effort
                logger.exception('consolidation pass failed; continuing without it')
                cons_ops = []
            if cons_ops:
                changed = changed_part_ids(cons_ops)
                set_document(document.render())
                yield ('status', 'Updating summary after consolidation')
                if oracle is not None:
                    oracle.update_summary(changed)
                else:
                    update_rolling_summary(
                        document,
                        changed,
                        self.llm_client,
                        max_words=self.options.summary_max_words,
                        prompt_token_budget=self.options.prompt_token_budget,
                    )
                self._emit('document', {
                    'step': 'consolidation', 'of': total, 'sub_task': None, 'status': 'completed',
                    'completion_tokens': meter.completion_tokens if meter else None,
                    'snapshot': document.to_dict(),
                })

        yield (
            'done',
            AccumulatedResult(
                previous_results=[],
                current_task=last_task,
                synthesis_prompt='',
                chat_response=ChatCompletionMessage(
                    role='assistant', content=document.render()
                ),
                document_snapshot=document.to_dict(),
            ),
        )

    @classmethod
    def from_yaml(
        cls, path: str | Path, *, llm_client: OpenAI | None = None
    ) -> Self:
        config = load_orchestrator_config(path)
        return cls.from_orchestrator_config(config, llm_client=llm_client)

    @classmethod
    def from_orchestrator_config(
        cls, config: OrchestratorConfig, *, llm_client: OpenAI | None = None
    ) -> Self:
        if llm_client is None:
            llm_client = create_llama_client(
                base_url=config.llm.resolved_base_url()
            )
        ctx = BuildContext(llm_client=llm_client, options=config.options)
        specs = validate_component_compatibility(config.components)
        built = {spec.role: spec.factory(ctx) for spec in specs}
        decomposer = built['decomposer']
        executor = built['executor']
        composer = built['composer']
        oracle_factory = built.get('oracle')
        if config.components.composer == 'document':
            return cls(
                decomposer=decomposer,
                agent_executor=executor,
                llm_client=llm_client,
                document_composer=composer,
                oracle_factory=oracle_factory,
                options=config.options,
            )
        return cls(
            decomposer=decomposer,
            agent_executor=executor,
            result_synthesiser=composer,
            llm_client=llm_client,
            options=config.options,
        )

    @classmethod
    def instantiate(
        cls, *, config: dict | None = None, llm_client: OpenAI | None = None
    ) -> Self:
        if config is None and llm_client is None:
            raise ValueError('Neither config nor llm_client provided')
        if config and llm_client:
            raise ValueError('Cannot provide both config and llm_client')
        if config is not None and 'key_word_args' in config:
            llm_client = create_llama_client(config)
            orch_config = OrchestratorConfig()
            validate_component_compatibility(orch_config.components)
            return cls.from_orchestrator_config(orch_config, llm_client=llm_client)
        if config is not None:
            orch_config = parse_orchestrator_config(config)
            return cls.from_orchestrator_config(orch_config)
        orch_config = OrchestratorConfig()
        validate_component_compatibility(orch_config.components)
        return cls.from_orchestrator_config(orch_config, llm_client=llm_client)
