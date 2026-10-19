from typing import Literal

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    # D-P: no silent endpoint default. Set base_url, or host + port; the
    # LLM_BASE_URL environment variable overrides both. With none of them
    # create_llama_client raises instead of guessing a server.
    base_url: str | None = None
    host: str | None = None
    port: int | None = None

    def resolved_base_url(self) -> str | None:
        if self.base_url:
            return self.base_url
        if self.host and self.port:
            return f'http://{self.host}:{self.port}/v1'
        return None


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
    log_prompts: bool = False
    # 0-06: run a consolidation pass (merge/delete/move only) after the final
    # sub-task. Off by default so it cannot perturb the baseline or the
    # 0-04/0-05 verification runs.
    consolidation: bool = False


class OrchestratorConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    components: ComponentsConfig = Field(default_factory=ComponentsConfig)
    options: OptionsConfig = Field(default_factory=OptionsConfig)
