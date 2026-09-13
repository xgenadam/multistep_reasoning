import logging
from collections.abc import Callable
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
from .llama_utils import create_llama_client
from .oracle.document_oracle import DocumentOracle
from .schemas import AccumulatedResult, SubTask
from .task_decomposition.base import TaskDecomposerBase

logger = logging.getLogger(__name__)

OracleFactory = Callable[[Document], DocumentOracle]


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

    def query(
        self, user_input: str, return_sub_tasks: bool = False
    ) -> ChatCompletionMessage | tuple[ChatCompletionMessage, AccumulatedResult]:
        sub_tasks = self.decomposer.generate_sub_tasks(user_input)

        logger.debug('executing sub tasks')
        if self.document_composer is not None:
            sub_task_execution_result = self._run_document_pipeline(
                user_input, sub_tasks
            )
            synthesis_history = self.document_composer.history
        else:
            if self.result_synthesiser is None:
                raise RuntimeError('result_synthesiser is required in legacy mode')
            sub_task_execution_result = self.agent_executor.execute_sub_tasks(
                user_request=user_input,
                sub_tasks=sub_tasks,
                synthesiser=self.result_synthesiser,
            )
            synthesis_history = self.result_synthesiser.history

        history_entry: dict[str, Any] = {
            'user_input': user_input,
            'decomposition_history': self.decomposer.history,
            'execution_results': self.agent_executor.history,
            'synthesis_history': synthesis_history,
        }
        if sub_task_execution_result.document_snapshot is not None:
            history_entry['document'] = sub_task_execution_result.document_snapshot
        self.history.append(history_entry)
        if return_sub_tasks:
            return sub_task_execution_result.chat_response, sub_task_execution_result
        return sub_task_execution_result.chat_response

    def _run_document_pipeline(
        self, user_input: str, sub_tasks: list[SubTask]
    ) -> AccumulatedResult:
        if self.document_composer is None:
            raise RuntimeError('document pipeline requires document_composer')
        if not sub_tasks:
            raise RuntimeError(
                'something went wrong here, if this gets raised it '
                'means no sub tasks were executed!'
            )

        document = Document.empty(render_mode=self.options.render)
        oracle = self.oracle_factory(document) if self.oracle_factory else None
        last_task = sub_tasks[0]
        for idx, sub_task in enumerate(sub_tasks):
            logger.info('Executing sub task %s of %s', idx, len(sub_tasks))
            self.agent_executor.execute_one(
                sub_task,
                outline=document.outline(),
                summary=document.summary,
                oracle=oracle,
            )
            ops = self.document_composer.compose(
                user_request=user_input,
                sub_tasks=sub_tasks,
                current_sub_task=sub_task,
                document=document,
            )
            changed = changed_part_ids(ops)
            if oracle is not None:
                oracle.update_summary(changed)
            else:
                update_rolling_summary(
                    document,
                    changed,
                    self.llm_client,
                    max_words=self.options.summary_max_words,
                )
            last_task = sub_task

        return AccumulatedResult(
            previous_results=[],
            current_task=last_task,
            synthesis_prompt='',
            chat_response=ChatCompletionMessage(
                role='assistant', content=document.render()
            ),
            document_snapshot=document.to_dict(),
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
                host=config.llm.host, port=config.llm.port
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
