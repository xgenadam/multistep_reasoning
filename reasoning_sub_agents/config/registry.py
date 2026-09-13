from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from openai import OpenAI

from .errors import ConfigError, IncompatibleComponentsError
from .schema import ComponentsConfig, OptionsConfig

Role = Literal['decomposer', 'executor', 'composer', 'oracle']

CAP_COMPOSER_DOCUMENT = 'composer.document'
CAP_COMPOSER_SIMPLE = 'composer.simple'
CAP_EXECUTOR_ORACLE_TOOLS = 'executor.oracle_tools'
CAP_EXECUTOR_SIMPLE = 'executor.simple'
CAP_ORACLE_DOCUMENT = 'oracle.document'


@dataclass(frozen=True)
class BuildContext:
    llm_client: OpenAI
    options: OptionsConfig


@dataclass(frozen=True)
class ComponentSpec:
    name: str
    role: Role
    provides: frozenset[str]
    requires: frozenset[str]
    forbids: frozenset[str]
    factory: Callable[[BuildContext], Any]


def _decomposer_simple(ctx: BuildContext) -> Any:
    from ..task_decomposition.simple_decomposition import SimpleTaskDecomposer

    return SimpleTaskDecomposer(llm_client=ctx.llm_client)


def _decomposer_self_critique(ctx: BuildContext) -> Any:
    from ..task_decomposition.self_critique_decomposition import (
        SelfCritiquingDecomposition,
    )

    return SelfCritiquingDecomposition(llm_client=ctx.llm_client)


def _executor_simple(ctx: BuildContext) -> Any:
    from ..executor.simple_executor import SimpleAgentExecutor

    return SimpleAgentExecutor(llm_client=ctx.llm_client)


def _executor_oracle_loop(ctx: BuildContext) -> Any:
    from ..executor.oracle_loop_executor import OracleLoopExecutor

    return OracleLoopExecutor(
        llm_client=ctx.llm_client,
        max_oracle_rounds=ctx.options.max_oracle_rounds,
    )


def _composer_simple(ctx: BuildContext) -> Any:
    from ..execution_synthesiser.simple_synthesiser import SimpleSynthesiser

    return SimpleSynthesiser(llm_client=ctx.llm_client)


def _composer_document(ctx: BuildContext) -> Any:
    from ..execution_synthesiser.document_composer import DocumentComposer

    return DocumentComposer(
        llm_client=ctx.llm_client,
        max_retries=ctx.options.composer_max_retries,
    )


def _oracle_document(ctx: BuildContext) -> Any:
    # Oracle is bound to a Document at query time; factory returns a builder.
    from ..document import Document
    from ..oracle.document_oracle import DocumentOracle

    def build(document: Document) -> DocumentOracle:
        return DocumentOracle(
            document,
            llm_client=ctx.llm_client,
            summary_max_words=ctx.options.summary_max_words,
        )

    return build


REGISTRY: dict[Role, dict[str, ComponentSpec]] = {
    'decomposer': {
        'simple': ComponentSpec(
            name='simple',
            role='decomposer',
            provides=frozenset(),
            requires=frozenset(),
            forbids=frozenset(),
            factory=_decomposer_simple,
        ),
        'self_critique': ComponentSpec(
            name='self_critique',
            role='decomposer',
            provides=frozenset(),
            requires=frozenset(),
            forbids=frozenset(),
            factory=_decomposer_self_critique,
        ),
    },
    'executor': {
        'simple': ComponentSpec(
            name='simple',
            role='executor',
            provides=frozenset({CAP_EXECUTOR_SIMPLE}),
            requires=frozenset(),
            forbids=frozenset({CAP_ORACLE_DOCUMENT}),
            factory=_executor_simple,
        ),
        'oracle_loop': ComponentSpec(
            name='oracle_loop',
            role='executor',
            provides=frozenset({CAP_EXECUTOR_ORACLE_TOOLS}),
            requires=frozenset({CAP_ORACLE_DOCUMENT, CAP_COMPOSER_DOCUMENT}),
            forbids=frozenset(),
            factory=_executor_oracle_loop,
        ),
    },
    'composer': {
        'simple': ComponentSpec(
            name='simple',
            role='composer',
            provides=frozenset({CAP_COMPOSER_SIMPLE}),
            requires=frozenset(),
            forbids=frozenset({CAP_ORACLE_DOCUMENT, CAP_EXECUTOR_ORACLE_TOOLS}),
            factory=_composer_simple,
        ),
        'document': ComponentSpec(
            name='document',
            role='composer',
            provides=frozenset({CAP_COMPOSER_DOCUMENT}),
            requires=frozenset(),
            forbids=frozenset(),
            factory=_composer_document,
        ),
    },
    'oracle': {
        'document_oracle': ComponentSpec(
            name='document_oracle',
            role='oracle',
            provides=frozenset({CAP_ORACLE_DOCUMENT}),
            requires=frozenset({CAP_COMPOSER_DOCUMENT}),
            forbids=frozenset(),
            factory=_oracle_document,
        ),
    },
}


def lookup(role: Role, name: str) -> ComponentSpec:
    role_registry = REGISTRY[role]
    spec = role_registry.get(name)
    if spec is None:
        valid = ', '.join(sorted(role_registry))
        raise ConfigError(
            f'unknown {role} {name!r}. Valid names: {valid}'
        )
    return spec


def validate_component_compatibility(
    components: ComponentsConfig,
) -> list[ComponentSpec]:
    selected: list[ComponentSpec] = []
    pairs: list[tuple[Role, str | None]] = [
        ('decomposer', components.decomposer),
        ('executor', components.executor),
        ('composer', components.composer),
        ('oracle', components.oracle),
    ]
    for role, name in pairs:
        if name is None:
            continue
        selected.append(lookup(role, name))

    provided: set[str] = set()
    for spec in selected:
        provided |= spec.provides

    for spec in selected:
        missing = spec.requires - provided
        if missing:
            raise IncompatibleComponentsError(
                f'{spec.role} {spec.name!r} requires capabilities '
                f'{sorted(missing)} which are not provided by the selected components'
            )
        forbidden = spec.forbids & provided
        if forbidden:
            raise IncompatibleComponentsError(
                f'{spec.role} {spec.name!r} is incompatible with capabilities '
                f'{sorted(forbidden)} provided by the selected components'
            )
    return selected
