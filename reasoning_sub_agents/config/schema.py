from typing import Literal

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    host: str = '127.0.0.1'
    port: int = 8000


class ComponentsConfig(BaseModel):
    decomposer: str = 'self_critique'
    executor: str = 'oracle_loop'
    composer: str = 'document'
    oracle: str | None = 'document_oracle'


class OptionsConfig(BaseModel):
    max_oracle_rounds: int = 8
    summary_max_words: int = 400
    render: Literal['markdown_with_files', 'sections_only'] = 'markdown_with_files'
    composer_max_retries: int = 3
    prompt_token_budget: int = 16384


class OrchestratorConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    components: ComponentsConfig = Field(default_factory=ComponentsConfig)
    options: OptionsConfig = Field(default_factory=OptionsConfig)
