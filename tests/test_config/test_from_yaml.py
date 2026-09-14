from pathlib import Path

from reasoning_sub_agents.config import load_orchestrator_config
from reasoning_sub_agents.execution_synthesiser.document_composer import DocumentComposer
from reasoning_sub_agents.execution_synthesiser.simple_synthesiser import SimpleSynthesiser
from reasoning_sub_agents.executor.oracle_loop_executor import OracleLoopExecutor
from reasoning_sub_agents.executor.simple_executor import SimpleAgentExecutor
from reasoning_sub_agents.task_orchestrator import TaskOrchestrator
from tests.mock_openai import MockOpenAI


def test_load_default_orchestrator_yaml():
    path = Path(__file__).resolve().parents[2] / 'orchestrator.yaml'
    config = load_orchestrator_config(path)
    assert config.components.decomposer == 'self_critique'
    assert config.components.executor == 'oracle_loop'
    assert config.components.composer == 'document'
    assert config.components.oracle == 'document_oracle'
    assert config.options.log_prompts is False


def test_log_prompts_yaml_flag(tmp_path):
    yaml_path = tmp_path / 'orch.yaml'
    yaml_path.write_text(
        """
components:
  decomposer: simple
  executor: simple
  composer: simple
  oracle: null
options:
  log_prompts: true
"""
    )
    orchestrator = TaskOrchestrator.from_yaml(yaml_path, llm_client=MockOpenAI())
    assert orchestrator.options.log_prompts is True


def test_from_yaml_builds_document_stack(tmp_path):
    yaml_path = tmp_path / 'orch.yaml'
    yaml_path.write_text(
        """
components:
  decomposer: simple
  executor: oracle_loop
  composer: document
  oracle: document_oracle
"""
    )
    orchestrator = TaskOrchestrator.from_yaml(yaml_path, llm_client=MockOpenAI())
    assert isinstance(orchestrator.document_composer, DocumentComposer)
    assert isinstance(orchestrator.agent_executor, OracleLoopExecutor)
    assert orchestrator.result_synthesiser is None
    assert orchestrator.oracle_factory is not None


def test_from_yaml_legacy_simple_stack(tmp_path):
    yaml_path = tmp_path / 'legacy.yaml'
    yaml_path.write_text(
        """
components:
  decomposer: simple
  executor: simple
  composer: simple
  oracle: null
"""
    )
    orchestrator = TaskOrchestrator.from_yaml(yaml_path, llm_client=MockOpenAI())
    assert isinstance(orchestrator.result_synthesiser, SimpleSynthesiser)
    assert isinstance(orchestrator.agent_executor, SimpleAgentExecutor)
    assert orchestrator.document_composer is None
    assert orchestrator.oracle_factory is None
