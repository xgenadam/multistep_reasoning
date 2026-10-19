# Multi-step reasoning

This is heavily WIP and an ongoing project.

# Multi-step reasoning

A library that turns one user prompt into several sub-tasks, runs those separately, then folds the results into a `Document` instead of rewriting the whole answer each time.

Later sub-tasks do not receive the full document. They get an outline, a rolling summary, and a `DocumentOracle` they can query (`list_parts`, `read_part`, `search`, `ask`).

The aim of this project is to give LLM's more time to think about and solve complex problems as opposed to solving in a single call.
The breakdown into subtasks allows more focus on a single subject, with only the appropriate context, whilst the orchestrator can check the result against the full context. It also reduces bloat of the context window.
Similarly, the use of the `Document` as the final response allows for the editting of earlier parts of the response as the sub tasks complete with the orchestrator integrating the results of sub tasks into this. 

The most powerful aspect of this is that it allows the LLM to revise its earlier response prior to presenting it to the user, the earliest part of the document is not set in stone and can be editted if needed later by the LLM.


## Layout

| Path | Role |
| --- | --- |
| `reasoning_sub_agents/` | Library: decompose → execute → compose |
| `orchestrator.yaml` | Which decomposer / executor / composer / oracle to wire |
| `oobabooga_extension/` | oobabooga hook (`script.py`) |
| `tests/` | Unit tests (no live model required) |


## How a turn works

1. **Decompose** the user request into sub-tasks (`simple` or `self_critique`).
2. **Execute** each sub-task. The oracle-loop executor may query the document in a bounded loop.
3. **Compose** onto a `Document` of named parts (`section` or `file`). New deliverables are copied verbatim (`body_source: current_result`); the model only writes glue and small patches.
4. **Render** `document.render()` as the assistant reply.

Follow-ups in the same oobabooga chat reuse that chat’s `Document`.

## Config

`orchestrator.yaml`:

```yaml
llm:                 # required - there is no default endpoint
  host: 127.0.0.1    # or base_url: http://host:port/v1
  port: 8000         # LLM_BASE_URL in the environment overrides this block

components:
  decomposer: self_critique    # simple | self_critique
  executor: oracle_loop        # simple | oracle_loop
  composer: document           # simple | document
  oracle: document_oracle      # document_oracle | null

options:
  max_oracle_rounds: 8
  summary_max_words: 400
  render: markdown_with_files  # markdown_with_files | sections_only
  composer_max_retries: 3
```

Unknown names and incompatible combinations raise at load time (for example `oracle_loop` without an oracle). A config with no `llm` endpoint and no `LLM_BASE_URL` raises when the client is created; nothing falls back to a guessed server.

From Python:

```python
from reasoning_sub_agents.task_orchestrator import TaskOrchestrator

orch = TaskOrchestrator.from_yaml('orchestrator.yaml')
message = orch.query('Write a report on X')
print(message.content)
```

`from_yaml(..., llm_client=client)` skips creating an HTTP client (the oobabooga extension does this).

## Tests

```bash
pip install pytest openai instructor pydantic pyyaml
pytest tests -q
```

NB: the testing needs to be updated

## oobabooga (text-generation-webui)

oobabooga only loads `script.py` at the **root** of the extension folder. Cloning this repo into `extensions/` is not enough by itself: `script.py` currently lives under `oobabooga_extension/`.

```bash
# folder name = extension name
git clone <this-repo-url> \
  /path/to/text-generation-webui/user_data/extensions/multistep_reasoning

cd /path/to/text-generation-webui/user_data/extensions/multistep_reasoning

# required: script.py must sit next to reasoning_sub_agents/
cp oobabooga_extension/script.py .
cp oobabooga_extension/orchestrator.yaml .   # optional; root orchestrator.yaml is also found
```

as of last revision, it is best to copy all files from the oobabooga extensions to the root of the project, the above is out of date. See TODO list

### Python dependencies

Install into the **same** environment oobabooga uses:

```bash
pip install -r requirements.txt
```

`requirements.txt` is the curated runtime list (Python 3.12). For development: `make venv && make test` (see `pyproject.toml`).

## TODO/caveats
This project was mostly manually done, but I decided to let grok build loose on it to complete the final document oracle composition. This was mostly successful. The pain points came with the integration as an oobabooga extension. It seemed to be getting very bogged down into fetching the correct chat messages, implementing a now deleted scoring system which was sometimes responding to the wrong chat. Reading that was a massive wtf.

It also polluted the multi step reasoning with oobabooga specific code. The `reasoning_sub_agents` module should be all about the reasoning, and be platform agnostic.

I've fixed most of these, but I need to freshly test setting this up as an extension again.

Similarly it added mcp code to the `reasoning_sub_agents` module, but this should deffinitely live elsewhere and wrap that code.

I think there are also probably some cases where there is code that is unused, either introduced through multiple rounds through grok or as leftover from my own edits/deletions.

I'm on the fence about making this a propper package, currently it is only being tested/used as an extension package for oobabooga. However I want to make it more portable.
Early explorations of this via grok build as an MCP server did not result in what I was envisioning. As an MCP server that grok proposed, it would have required a dedicated LLM running as part of the server, however I envision this instead being a reasoning harness that the primary LLM can use. I need to think about how to implement this more (currently I am just exploring whether this reasoning harness results in improved responses).

While this does work, the final document does contain repetition. Currently we have the ability to add/delete/modify parts of a document, but I think we need to introduce the ability to merge and compare them to elimimate this.

Tool use inside the sub agents has not been implemented, and how tool use (such as search) gets handled is something I need to think about and experiment with.
I can see the benefits of each sub task agent being able to call tools, but if not handled appropriately it could become messy and complicated. 

## Results/thoughts

I've run this using Mistral 3.5 128B and Qwen 3.6 35B.
Obviously Mistral is much slower, for a single user input there are multiple calls to the LLM for each response, but it did provide better results in both cases.

For most use cases I think this does not need to be used, I would envision this being something the LLM can decide to use in the event it needs to ruminate more on a result before coming back with an immediate response.

As noted above, the final document does contain repetition, there are a few ways we can handle this, such as adding the ability to merge parts of the document, overhaul the entire thing etc. This needs experimentation to find what works best, and may be dependent on model competence itself.
