import pytest

from reasoning_sub_agents.config import (
    ComponentsConfig,
    ConfigError,
    IncompatibleComponentsError,
    OrchestratorConfig,
    parse_orchestrator_config,
    validate_component_compatibility,
)


def test_default_config_is_compatible():
    specs = validate_component_compatibility(ComponentsConfig())
    names = {(spec.role, spec.name) for spec in specs}
    assert ('decomposer', 'self_critique') in names
    assert ('executor', 'oracle_loop') in names
    assert ('composer', 'document') in names
    assert ('oracle', 'document_oracle') in names


def test_legacy_simple_simple_is_compatible():
    components = ComponentsConfig(
        decomposer='simple',
        executor='simple',
        composer='simple',
        oracle=None,
    )
    specs = validate_component_compatibility(components)
    names = {(spec.role, spec.name) for spec in specs}
    assert ('executor', 'simple') in names
    assert ('composer', 'simple') in names
    assert not any(role == 'oracle' for role, _ in names)


def test_document_composer_with_simple_executor_is_compatible():
    components = ComponentsConfig(
        decomposer='simple',
        executor='simple',
        composer='document',
        oracle=None,
    )
    validate_component_compatibility(components)


def test_oracle_loop_without_oracle_errors():
    components = ComponentsConfig(
        decomposer='simple',
        executor='oracle_loop',
        composer='document',
        oracle=None,
    )
    with pytest.raises(IncompatibleComponentsError, match='oracle.document'):
        validate_component_compatibility(components)


def test_simple_executor_with_oracle_errors():
    components = ComponentsConfig(
        decomposer='simple',
        executor='simple',
        composer='document',
        oracle='document_oracle',
    )
    with pytest.raises(IncompatibleComponentsError, match='oracle.document'):
        validate_component_compatibility(components)


def test_simple_composer_with_oracle_loop_errors():
    components = ComponentsConfig(
        decomposer='simple',
        executor='oracle_loop',
        composer='simple',
        oracle='document_oracle',
    )
    with pytest.raises(IncompatibleComponentsError):
        validate_component_compatibility(components)


def test_simple_composer_with_oracle_errors():
    components = ComponentsConfig(
        decomposer='simple',
        executor='simple',
        composer='simple',
        oracle='document_oracle',
    )
    with pytest.raises(IncompatibleComponentsError):
        validate_component_compatibility(components)


def test_unknown_executor_name_errors():
    components = ComponentsConfig(
        decomposer='simple',
        executor='not-a-real-executor',
        composer='simple',
        oracle=None,
    )
    with pytest.raises(ConfigError, match='unknown executor'):
        validate_component_compatibility(components)


def test_unknown_name_lists_valid_options():
    components = ComponentsConfig(
        decomposer='nope',
        executor='simple',
        composer='simple',
        oracle=None,
    )
    with pytest.raises(ConfigError, match='self_critique'):
        validate_component_compatibility(components)


def test_parse_orchestrator_config_validates_components():
    raw = {
        'components': {
            'decomposer': 'simple',
            'executor': 'oracle_loop',
            'composer': 'document',
            'oracle': None,
        }
    }
    with pytest.raises(IncompatibleComponentsError):
        parse_orchestrator_config(raw)


def test_parse_orchestrator_config_defaults():
    config = parse_orchestrator_config({})
    assert isinstance(config, OrchestratorConfig)
    assert config.components.composer == 'document'
    assert config.components.executor == 'oracle_loop'
