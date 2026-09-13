from pathlib import Path
from typing import Any

import yaml

from .registry import validate_component_compatibility
from .schema import OrchestratorConfig


def load_orchestrator_config(path: str | Path) -> OrchestratorConfig:
    raw = _read_yaml(path)
    return parse_orchestrator_config(raw)


def parse_orchestrator_config(raw: dict[str, Any] | None) -> OrchestratorConfig:
    config = OrchestratorConfig.model_validate(raw or {})
    validate_component_compatibility(config.components)
    return config


def _read_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, encoding='utf-8') as handle:
        loaded = yaml.safe_load(handle)
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f'orchestrator config must be a mapping, got {type(loaded)!r}')
    return loaded
