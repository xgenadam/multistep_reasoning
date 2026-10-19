# Archive (O-02, 2026-10-19)

Stale docs and dead code, kept for reference. Nothing here is current; the
live state is `journal/INDEX.md` (after O-01), the plan
`journal/plan-2026-10-18-approved.md`, and the latest `journal/S-NNN.md`.
Decisions D-C and D-D. Dates are file mtimes.

## Archived

| File here | Origin path | Date | What it was | Why dead |
| --- | --- | --- | --- | --- |
| `2026-10-OBJECTIVE.md` | `OBJECTIVE.md` (ignored) | 2026-10-13 | The original working agreement; PLAN.md cites it | Superseded by the approved roadmap v2 |
| `2026-02-docs-LOG.md` | `docs/LOG.md` (untracked) | 2026-02-03 | Feb 2026 journal attempt: session log | Superseded by `journal/` |
| `2026-02-docs-TODO.md` | `docs/TODO.md` (untracked) | 2026-02-01 | Feb 2026 journal attempt: TODO list | Superseded by tickets |
| `2026-02-docs-new_synthesiser_potential_ideas.md` | `docs/notespace/new_synthesiser_potential_ideas.md` (untracked) | 2026-02-03 | Ideas for a new synthesiser | Composer/consolidation replaced it |
| `2026-01-ANALYSIS.md` | `ANALYSIS.md` (ignored) | 2026-01-27 | AI-generated code audit | Superseded; findings stale |
| `2026-05-TODO.md` | `TODO.md` (ignored) | 2026-05-09 | AI-generated TODO list | Superseded by tickets |
| `2026-05-TODO_ANALYSIS.md` | `TODO_ANALYSIS.md` (ignored) | 2026-05-09 | AI audit of the TODO list | Superseded |
| `2026-05-TODO_CORRECTNESS_CONFIRMATION.md` | `TODO_CORRECTNESS_CONFIRMATION.md` (ignored) | 2026-05-09 | AI check of the TODO audit | Superseded |
| `2026-05-CRITICAL.md` | `CRITICAL.md` (ignored) | 2026-05-09 | AI list of critical defects | Superseded by PLAN.md defect table / plan v2 N-list |
| `2026-05-CRITICAL_ANALYSIS.md` | `CRITICAL_ANALYSIS.md` (ignored) | 2026-05-09 | AI analysis of the critical list | Superseded |
| `2026-05-SYNTHESISER_STATUS_ANALYSIS.md` | `SYNTHESISER_STATUS_ANALYSIS.md` (ignored) | 2026-05-09 | AI status of the synthesiser | Synthesiser broken/unregistered (N10) |
| `2026-09-readme-notes.md` | `README.md` § "TODO/caveats", "Results/thoughts" | 2026-09 | The author's narrative notes, verbatim | O-05 rewrites the README |
| `mcp-deep-reason-schema.md` | `mcp_server/mcp_server.py:30-64, 138-178` (tracked) | 236d168 | `ReasoningSessionStore` + `deep_reason`/`reset_session` tool schema | MCP retired (S-002); kept as the Phase H reference |
| `llama_server.md` | `llama_server.py` (tracked) | 236d168 | llama-server launcher | Needs `requests`, no callers |
| `project_serializer.md` | `project_serializer.py` (tracked) | 236d168 | Dumped the repo into `project_text.txt` | Unreferenced |
| `2026-10-13-PLAN-v1.md` | `journal/PLAN.md` v1 (tracked; O-01) | 2026-10-13 | Plan of record v1: stale "Current state" audit, defect table D1–D10, v1 phases, settled decisions, process section | Rewritten as PLAN.md v2; decisions → `DECISIONS.md`, process → `AGENTS.md`. Kept for the Phase P / T / H design prose v2 condenses |
| `plan-2026-10-18-approved.md` | `journal/plan-2026-10-18-approved.md` (tracked; O-01, `git mv`) | 2026-10-18 | Approved roadmap v2 (S-004): analysis, defects N1–N19, decisions D-A…D-Q, phases | Part 2 now lives in PLAN.md v2; D-A…D-Q map to `DECISIONS.md` D-001…D-012 (each title names its plan letter) |

## Deleted, unarchived

Never in git, or byte-junk with no content worth keeping:
`README_NEW.md` (byte-identical to README), `intermediate_output.md`,
`output_23.md`, `output_24.md`, `output_25.md`, `project_text.txt`,
`project_text.txt.bak`, `resume_grok.txt`, `test_output.txt`,
`parallel_test_agent2.txt`, `main.bak.py`, `requirements.txt.bak` (O-03),
the rest of `docs/` (`docs/notespace/README.md`, empty `docs/OBJECTIVE.md`,
empty `docs/CURRENT_STATUS.md`), `history/` (138 MB), `results/` (576 KB).

Removed from git (recoverable from history before the O-02 commit):
`mcp_server/`, `llama_server.py`, `project_serializer.py`.
Moved: `config.json` → `scripts/server/devstral-123b.llama-server.json`,
`start_llama.sh` → `scripts/server/start-devstral-123b.sh`.

## Local branches (not deleted — the user decides)

| Branch | Ahead of master | Last commit |
| --- | --- | --- |
| `multi-stream-llama-client` | 6 | 2026-01-11 |
| `cline-edits` | 1 | 2026-01-17 |
| `open-webui-edits` | 1 | 2026-01-24 |
| `round_2_improvements` | 1 | 2026-01-12 |
| `round_2_redo` | 1 | 2026-01-14 |
| `cleanup_after_weird_grok_stuff` | 0 (merged) | 2026-09-16 |
| `round_3` | 0 (merged) | 2026-09-14 |
