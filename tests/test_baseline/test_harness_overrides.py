"""The harness's --set resolution and run-file provenance (Q-02 stage 0)."""

import pytest

from reasoning_sub_agents.config import ConfigError


def test_harness_resolves_flags_then_overrides(harness):
    cfg = harness.resolve_config(True, 'on', ['options.thinking=off', 'components.executor=simple',
                                              'components.oracle=null'])
    assert cfg.options.consolidation is True
    assert cfg.options.thinking == 'off'
    assert cfg.components.executor == 'simple'
    with pytest.raises(ConfigError):
        harness.resolve_config(False, 'off', ['options.nope=1'])


def test_git_commit_names_head(harness):
    info = harness.git_commit()
    assert len(info['commit']) == 40
    assert isinstance(info['dirty'], bool)
