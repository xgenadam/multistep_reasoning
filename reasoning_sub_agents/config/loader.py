import typing
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from .errors import ConfigError
from .registry import validate_component_compatibility
from .schema import OrchestratorConfig


def load_orchestrator_config(path: str | Path) -> OrchestratorConfig:
    raw = _read_yaml(path)
    return parse_orchestrator_config(raw)


def parse_orchestrator_config(raw: dict[str, Any] | None) -> OrchestratorConfig:
    config = OrchestratorConfig.model_validate(raw or {})
    validate_component_compatibility(config.components)
    return config


def apply_overrides(raw: dict[str, Any] | None, overrides: Iterable[str]) -> dict[str, Any]:
    """Return a copy of a raw config dict with `section.key=value` overrides set.

    Values are parsed as YAML (`8` is an int, `null` is None, `off` is the
    thinking switch). Every path is checked against OrchestratorConfig's
    fields first, because pydantic ignores unknown keys and a typo would
    otherwise change nothing silently (Q-02 arms, Q-05 ablations).
    """
    out = _deep_copy(raw or {})
    for item in overrides:
        dotted, sep, value = item.partition('=')
        keys = dotted.strip().split('.')
        if not sep or not all(keys):
            raise ConfigError(f'override {item!r} is not section.key=value')
        _check_path(keys, item)
        node = out
        for key in keys[:-1]:
            child = node.get(key)
            if not isinstance(child, dict):
                child = node[key] = {}
            node = child
        node[keys[-1]] = yaml.safe_load(value) if value.strip() else None
    return out


def _check_path(keys: list[str], item: str) -> None:
    model: Any = OrchestratorConfig
    for depth, key in enumerate(keys):
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            # A dict field (thinking_by_step) takes exactly one key below it.
            if typing.get_origin(model) is dict and depth == len(keys) - 1:
                return
            raise ConfigError(f'override {item!r}: {".".join(keys[:depth])} has no sub-keys')
        field = model.model_fields.get(key)
        if field is None:
            known = ', '.join(sorted(model.model_fields))
            raise ConfigError(f'override {item!r}: unknown key {key!r} (known: {known})')
        model = field.annotation
    if isinstance(model, type) and issubclass(model, BaseModel):
        raise ConfigError(f'override {item!r}: {".".join(keys)} is a section, not a value')


def _deep_copy(raw: dict[str, Any]) -> dict[str, Any]:
    return {k: _deep_copy(v) if isinstance(v, dict) else v for k, v in raw.items()}


def _read_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, encoding='utf-8') as handle:
        loaded = yaml.safe_load(handle)
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f'orchestrator config must be a mapping, got {type(loaded)!r}')
    return loaded
