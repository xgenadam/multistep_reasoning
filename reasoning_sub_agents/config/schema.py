from typing import Literal

from pydantic import BaseModel, Field, field_validator

Thinking = Literal['off', 'on']
StructuredOutput = Literal['json_object', 'json_schema', 'two_pass']
StepKind = Literal[
    'decompose', 'decompose_critique', 'executor_turn', 'oracle',
    'compose', 'consolidate', 'summary',
]  # progress.STEP_KINDS


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
    # Experimental, off by default (Q-02, the user, 2026-10-24): a hard cap on
    # one turn's completion tokens. Once a turn has spent this many, no
    # further sub-task starts (nor consolidation) and the turn returns the
    # Document as it stands (every applied op left it valid), so a runaway
    # turn ends with a partial deliverable instead of an error or an endless
    # loop. Q-02 sizes it as 3x the harness's stratum median. Not used by any
    # experiment arm yet: turning it on needs its own metrics first (the
    # quality of the partial Documents it returns against what the full turn
    # would have produced, from the stored intermediate snapshots).
    token_ceiling: int | None = None
    # D-013: every call sends an explicit thinking switch. Off by default and
    # for baselines; thinking_by_step overrides it per call kind. Reasoning
    # text never reaches a prompt; it goes to a JSONL side log, one file per
    # turn under thinking_log_dir/<date>/ (log_thinking None = jsonl when any
    # step thinks, else off).
    thinking: Thinking = 'off'
    thinking_by_step: dict[StepKind, Thinking] = Field(default_factory=dict)
    log_thinking: Literal['off', 'jsonl'] | None = None
    thinking_log_dir: str = 'runs/thinking'
    # How a JSON step asks for its structure (the user, 2026-10-25). json_object,
    # the default and every run before it: the server forces valid JSON, the
    # schema is only in the prompt, checked after the call and retried.
    # json_schema: the server forces the schema itself. two_pass: the model
    # first answers in prose under a heading per field, then a second call,
    # forced to the schema, turns that answer into JSON.
    # structured_output_by_step overrides it per call kind.
    structured_output: StructuredOutput = 'json_object'
    structured_output_by_step: dict[StepKind, StructuredOutput] = Field(default_factory=dict)

    @field_validator('thinking', 'log_thinking', mode='before')
    @classmethod
    def _yaml_switch(cls, value):
        # YAML 1.1 reads a bare off/on as a boolean.
        if value is False:
            return 'off'
        if value is True:
            return 'on'
        return value

    @field_validator('thinking_by_step', mode='before')
    @classmethod
    def _yaml_switches(cls, value):
        if isinstance(value, dict):
            return {k: cls._yaml_switch(v) for k, v in value.items()}
        return value


class OrchestratorConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    components: ComponentsConfig = Field(default_factory=ComponentsConfig)
    options: OptionsConfig = Field(default_factory=OptionsConfig)
