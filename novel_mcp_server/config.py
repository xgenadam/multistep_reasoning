"""YAML config for the novel MCP server (paths, storage, output)."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
import yaml


class StorageConfig(BaseModel):
    """Where work files live. Bound works always use the filesystem under `root`."""

    backend: Literal['memory', 'filesystem'] = 'memory'
    root: str = './workspaces'
    universe: str | None = None


class OutputConfig(BaseModel):
    """How tool results are delivered. Bound works still write files even if to_files is false."""

    to_client: bool = True
    to_files: bool = False


class NovelOptions(BaseModel):
    """Feature flags. longform_storage is reserved for later studio features."""

    conversation_search: bool = True
    longform_storage: bool = False
    edit_history: Literal['off', 'op_log', 'snapshots'] = 'op_log'
    storage: StorageConfig = Field(default_factory=StorageConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)


class NovelConfig(BaseModel):
    """Top-level novel_mcp_server config.yaml."""

    orchestrator_yaml: str = '../orchestrator.yaml'
    options: NovelOptions = Field(default_factory=NovelOptions)

    @classmethod
    def load(cls, path: str | Path) -> 'NovelConfig':
        """Parse YAML from disk."""
        with open(path, encoding='utf-8') as handle:
            raw = yaml.safe_load(handle) or {}
        return cls.model_validate(raw)

    def orchestrator_path(self, config_file: Path) -> Path:
        """Resolve orchestrator.yaml relative to this config file."""
        path = Path(self.orchestrator_yaml)
        if not path.is_absolute():
            path = (config_file.parent / path).resolve()
        return path

    def storage_root(self, config_file: Path) -> Path:
        """Resolve the workspace root relative to this config file."""
        root = Path(self.options.storage.root)
        if not root.is_absolute():
            root = (config_file.parent / root).resolve()
        return root
