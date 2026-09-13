# Multi-step reasoning

A library that turns one user prompt into several sub-tasks, runs those separately, then folds the results into a `Document` instead of rewriting the whole answer each time.

Later sub-tasks do not receive the full document. They get an outline, a rolling summary, and a `DocumentOracle` they can query (`list_parts`, `read_part`, `search`, `ask`).

The same pipeline can run against a local OpenAI-compatible server, or as an **oobabooga** (text-generation-webui) extension so Gradio and Open WebUI both use it.

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
llm:
  host: 127.0.0.1
  port: 8000

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

Unknown names and incompatible combinations raise at load time (for example `oracle_loop` without an oracle).

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

## oobabooga (text-generation-webui)

oobabooga only loads `script.py` at the **root** of the extension folder. Cloning this repo into `extensions/` is not enough by itself: `script.py` currently lives under `oobabooga_extension/`.

### Install the repo as an extension

```bash
# folder name = extension name
git clone <this-repo-url> \
  /path/to/text-generation-webui/user_data/extensions/multistep_reasoning

cd /path/to/text-generation-webui/user_data/extensions/multistep_reasoning

# required: script.py must sit next to reasoning_sub_agents/
cp oobabooga_extension/script.py .
cp oobabooga_extension/orchestrator.yaml .   # optional; root orchestrator.yaml is also found
```

You want:

```text
user_data/extensions/multistep_reasoning/
  script.py                 # required
  orchestrator.yaml
  reasoning_sub_agents/
  requirements.txt
  ...
```

A symlink is fine:

```bash
ln -s oobabooga_extension/script.py script.py
```

### Python dependencies

Install into the **same** environment oobabooga uses:

```bash
pip install -r requirements.txt
```

Minimum for the extension: `openai`, `instructor`, `pydantic`, `pyyaml`.

### Enable

CLI:

```bash
python server.py --extensions openai multistep_reasoning
```

`openai` is oobabooga’s OpenAI-compatible API (Open WebUI). `multistep_reasoning` must match the folder name.

Or in the UI: Session → Extensions → enable **multistep_reasoning** (and **openai** if you use Open WebUI) → apply / restart.

### Check it loaded

- Gradio should show **Enable multi-step reasoning**.
- Logs should contain `multi-step reasoning extension ready`.
- If setup fails, the exception is logged and the extension stays disabled.

### Behaviour

- A user turn runs the full decompose → execute → compose pipeline against the model already loaded in oobabooga.
- Inner LLM calls use `generate_reply_HF` / `generate_reply_custom` directly, not `generate_reply`, so the extension does not recurse.
- The same oobabooga chat keeps editing one `Document`. A new chat starts empty.
- Open WebUI can keep pointing at oobabooga’s OpenAI API; no extra pipeline.
- **Intercept mode** (Gradio): `chat_only` (default) skips Cline / OpenCode / Grok Build tool turns so those agents keep their own loops. `always` intercepts every chat turn except inner orchestrator calls. `never` never intercepts.

### Optional env vars

| Variable | Meaning |
| --- | --- |
| `MULTISTEP_REASONING_ROOT` | Repo root if `import reasoning_sub_agents` fails (not needed when `script.py` is at the repo root) |
| `MULTISTEP_ORCHESTRATOR_YAML` | Path to a specific `orchestrator.yaml` |

### Caveats

- Only one extension may define `custom_generate_reply`. Do not enable another that does the same.
- You do not need a separate llama.cpp server for this path; oobabooga’s loaded model is the backend.

### Alternative: repo elsewhere, extension is a symlink

If you keep the git checkout outside text-generation-webui:

```bash
pip install -e /path/to/this/repo

ln -sfn /path/to/this/repo/oobabooga_extension \
  /path/to/text-generation-webui/user_data/extensions/multistep_reasoning

export MULTISTEP_REASONING_ROOT=/path/to/this/repo
python server.py --extensions openai multistep_reasoning
```

In that layout `script.py` is already at the extension root (`oobabooga_extension/script.py`).

## Cline, OpenCode, and Grok Build

Those tools already run a tool loop (read/edit/shell). This project must **not** steal that loop. Two pieces:

1. Point the **model** at oobabooga with intercept mode `chat_only` (default). Agent-shaped turns (OpenAI `tools`, Cline XML, tool-result messages) fall through to a normal completion.
2. Add this repo as an **MCP server**. The agent can call `deep_reason` when it wants a long plan/analysis `Document`, then apply that with its own tools.

### MCP server

```bash
cd /path/to/this/repo
export MULTISTEP_ORCHESTRATOR_YAML=/path/to/this/repo/orchestrator.yaml
python -m reasoning_sub_agents.mcp_server
```

`orchestrator.yaml` `llm.host` / `llm.port` must be oobabooga’s OpenAI API (often `127.0.0.1:5000`). Inner HTTP calls include a skip sentinel so the extension does not recurse.

Tools:

- `deep_reason(prompt, session_id?, chat_context?)` → markdown document
- `reset_session(session_id)` → drop a stored document

### Grok Build

In `~/.grok/config.toml` or the project `.grok/config.toml`:

```toml
[mcp_servers.multistep-reasoning]
command = "python"
args = ["-m", "reasoning_sub_agents.mcp_server"]
env = { MULTISTEP_ORCHESTRATOR_YAML = "/path/to/this/repo/orchestrator.yaml", PYTHONPATH = "/path/to/this/repo" }
enabled = true
```

Run Grok from a cwd where that `PYTHONPATH` repo is importable, or install the package with `pip install -e /path/to/this/repo`.

### Cline

In Cline MCP settings (`cline_mcp_settings.json`), the same stdio server:

```json
{
  "mcpServers": {
    "multistep-reasoning": {
      "command": "python",
      "args": ["-m", "reasoning_sub_agents.mcp_server"],
      "cwd": "/path/to/this/repo",
      "env": {
        "MULTISTEP_ORCHESTRATOR_YAML": "/path/to/this/repo/orchestrator.yaml",
        "PYTHONPATH": "/path/to/this/repo"
      }
    }
  }
}
```

### OpenCode

Register the same command in OpenCode’s MCP config (`opencode.json` / MCP servers). Command, `cwd`, and env match the snippets above.

If the coding agent’s model is oobabooga, leave intercept mode at `chat_only` (or disable the extension for that profile). Use `deep_reason` only when you want a multi-step document, not for every file edit.
