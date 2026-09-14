# novel_mcp_server

MCP server for longform workspaces. Grok Build, OpenCode, or Cline is the client — this process only exposes tools.

It lives in this git repo next to `reasoning_sub_agents/` so it can import the library. Split it to its own remote later (`pip install` the library) when the API is stable.

Not an Open WebUI / oobabooga extension.

## Run

From the **repo root**:

```bash
export PYTHONPATH=/path/to/this/repo
export NOVEL_MCP_CONFIG=/path/to/this/repo/novel_mcp_server/config.yaml
python -m novel_mcp_server
```

`config.yaml` points at `../orchestrator.yaml` for the LLM host/port (oobabooga OpenAI API). Inner completions use the skip sentinel so the oobabooga chat extension does not recurse.

## Tools

| Tool | Purpose |
| --- | --- |
| `deep_reason` | Multi-step compose; optional `session_id` / `chat_context` |
| `bind_work` | `session_id` → universe / series / work |
| `list_documents` / `read_document` / `search_workspace` | Bound work (files or in-memory) |
| `append_conversation` / `search_conversation` | Search older summarised turns |
| `reset_session` | Drop memory, bind, and conversation log |

**Bound works always write files.** After `bind_work`, `deep_reason` writes:

`{storage.root}/universes/{universe}/series/{series}/works/{work}/documents/{id}.md`

plus `_index.md` and `_latest.md` (most recent part). Paths are appended to the tool result so the TUI can open them.

Unbound `deep_reason` (no `bind_work`) stays in memory unless you set `output.to_files: true`. Restart + `bind_work` to the same universe/series/work reloads parts from disk.

## Grok Build

`~/.grok/config.toml`:

```toml
[mcp_servers.novel]
command = "python"
args = ["-m", "novel_mcp_server"]
env = { PYTHONPATH = "/path/to/this/repo", NOVEL_MCP_CONFIG = "/path/to/this/repo/novel_mcp_server/config.yaml" }
enabled = true
```

## Cline / OpenCode

Same command, cwd/env: `PYTHONPATH` = repo root, `NOVEL_MCP_CONFIG` = this package’s `config.yaml`.

## Tests

```bash
cd /path/to/this/repo
PYTHONPATH=. pytest novel_mcp_server/tests -q
```

## v1 is not

Editor/proofread loops, plot trackers, Neo4j, ingest of existing novels, or a custom TUI.
