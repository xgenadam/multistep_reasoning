"""`section.key=value` overrides (Q-02 stage 0: the arms and Q-05's ablations)."""

import pytest

from reasoning_sub_agents.config import (
    ConfigError,
    IncompatibleComponentsError,
    apply_overrides,
    parse_orchestrator_config,
)


def test_overrides_parse_as_yaml_and_validate():
    raw = apply_overrides({}, [
        'components.executor=simple',
        'components.oracle=null',
        'options.max_oracle_rounds=4',
        'options.thinking=on',
        'options.thinking_by_step.compose=off',
    ])
    config = parse_orchestrator_config(raw)
    assert config.components.executor == 'simple'
    assert config.components.oracle is None
    assert config.options.max_oracle_rounds == 4
    assert config.options.thinking == 'on'  # YAML's bare `on` is the switch, not True
    assert config.options.thinking_by_step == {'compose': 'off'}


def test_overrides_win_over_the_base_and_do_not_mutate_it():
    base = {'options': {'consolidation': False, 'thinking': 'off'}}
    raw = apply_overrides(base, ['options.consolidation=true'])
    assert raw['options'] == {'consolidation': True, 'thinking': 'off'}
    assert base['options']['consolidation'] is False


@pytest.mark.parametrize('item', [
    'options.max_oracle_round=2',     # typo: pydantic alone would ignore it
    'option.consolidation=true',
    'options=3',                      # a section, not a value
    'options.thinking.compose=on',    # a scalar has no sub-keys
    'options.thinking_by_step.compose.x=on',
    'components.executor',            # no '='
    '.executor=simple',
])
def test_bad_paths_raise(item):
    with pytest.raises(ConfigError):
        apply_overrides({}, [item])


def test_bad_values_fail_at_validation():
    with pytest.raises(ValueError):
        parse_orchestrator_config(apply_overrides({}, ['options.thinking_by_step.nonsense=on']))
    with pytest.raises(IncompatibleComponentsError):
        parse_orchestrator_config(apply_overrides({}, ['components.composer=simple']))
