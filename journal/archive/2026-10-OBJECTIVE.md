# OBJECTIVE

Long-range plan for the multi-step reasoning harness: make the `Document` flexible,
add tool calling and parallel sub-task execution, and build a retrievable context
layer (RAG + graph) so the model gets the *illusion of infinite context*.

This document is the working agreement between sessions. Each phase lists what it
delivers, which files it touches, and how it is verified with a small local model.

## North star

The model never loads a corpus — it *explores* one through a bounded interface.
Active context (user request, current sub-task, document outline, rolling summary)
stays small and always in-prompt; everything else is on-demand retrieval through
tools the model chooses to call. Corpus unbounded, window bounded.

This collapses every long-term goal (RAG, codebase ingestion, chat memory, books,
legal/science verification) into one architecture: **more backends behind the
oracle's door**.

## Current state (as of this analysis)

- Core pipeline works end-to-end: decompose → execute → compose-ops → render,
  driven by `reasoning_sub_agents/task_orchestrator.py`.
- `Document` (named `Part`s + rolling summary + op log) is the only real memory;
  sub-tasks query it via `DocumentOracle` (`list_parts`, `read_part`, `search`,
  `ask`, `summary`).
- Known limitations confirmed by code audit:
  - `Part.title` and `AddPart.title` are mandatory — every part must have a heading.
  - `MovePart` and `DeletePart` are fully implemented in
    `document/apply.py` but **never mentioned in `COMPOSE_PROMPT`**, so the model
    has no idea it can re-order or delete.
  - No merge operation; deduping means re-typing content, which violates the
    "verbatim in code, model writes glue" design and causes the repetition the
    README admits to.
  - Oracle `search` is literal substring with token fallback; `ask` falls back to
    the *first 8 parts* when nothing matches (`oracle/document_oracle.py`) —
    misleading at corpus scale.
  - `COMPOSE_PROMPT` is framed as "write a report with sections", so output is
    always a markdown report even when the user asked for code.
  - Sub-agent tool calling is limited to the document oracle tools; no pack-level
    tool set (no `run_python`, no `web_search`, ...).
  - Sub-tasks run strictly sequentially; `run_multi_concurrent` exists but is
    unused; llama-server already runs `--parallel 2`.
  - Broken: `reasoning_sub_agents/__main__.py` and `tests/test_mcp_server.py`
    import `reasoning_sub_agents.mcp_server`, which does not exist;
    `RollingDocumentUpdateSynthesiser` has a `NameError` in its
    no-previous-result branch; `tst_new_orchestrator.py` imports a non-existent
    `LLMClientAdapter`.

## Settled decisions

| Decision | Answer | Rationale |
| --- | --- | --- |
| Deployment face | oobabooga extension only. **MCP server is abandoned.** | Keep `mcp_server/` frozen or delete; do not invest beyond that. |
| Vector store | Server-based (Qdrant or Chroma), run separately. | Scales, multi-client; cost is one extra service to run. |
| Graph storage | In-process adjacency (sqlite or NetworkX over a persisted edge list). **No Neo4j initially.** | One/two-hop neighborhood expansion doesn't need a graph DB's query language. Revisit if multi-hop queries become real. |
| Domain packs | Spec now, as a config-bundle layer. | Keeps the core generic; book/legal/science become additive, not forked. |
| Harness-as-tool trigger | Hybrid: heuristics pre-filter + **native llama.cpp tool calling as primary** + the existing text sentinel as universal backstop. | The generating model decides when its client supports tools; the sentinel channel already exists (`[[multistep-inner]]` machinery) and works on any model. |
| Testing | Small local model for fast smoke tests; big model for quality evaluation. | Live end-to-end tests are feasible at low cost. |
| Dependency direction | `context` ← `reasoning` ← (`packs`, `tools`). `context` is standalone. | Regular chat can use context alone; deep reasoning uses context + reasoning. |

## Target package layout

```
reasoning_sub_agents/
  context/                 # LAYER 0 — standalone, no dependency on reasoning/
    store.py               #   ContextStore interface + unified retrieve()
    vector.py              #   Qdrant/Chroma client
    graph.py               #   adjacency, seed -> neighbor expansion
    codebase_ingest.py     #   parse -> chunks -> vectors + graph nodes (offline)
    chat_memory.py         #   chat history as a retrievable store
  reasoning/               # LAYER 1 — today's core; DEPENDS ON context
    document/              #   (moved from reasoning_sub_agents/document)
    task_decomposition/
    executor/
    execution_synthesiser/
    oracle/                #   generalized to query any ContextStore
    task_orchestrator.py
  packs/                   # LAYER 2 — config bundles; DEPENDS ON both
    base.py  code.py  book.py  legal.py  science.py
  tools/                   # "harness as a tool" registration
    register.py            #   exposes deep_reason / retrieve to a host client
```

The `Document` becomes **one kind of store inside `context`**: it is working
memory for the current turn; RAG stores are long-term memory. The oracle queries
both through the same interface.

## Phase 0 — Immediate document fixes (days)

Direct answer to "documents are not flexible enough". Contained to
`document/`, the composer prompt, and tests.

1. **Optional titles.** `Part.title` and `AddPart.title` become
   `str | None = None`. `Document.render()` already handles empty titles
   (no heading; `## file` for untitled file parts). Add one `part.title or ''`
   guard in the oracle's search haystack.
2. **New `merge_parts` op.** `{id, kind, title?, ids: [source ids], after}` —
   code concatenates source bodies verbatim in the given order, inserts the new
   part, deletes the sources. Add the schema model, its `_apply_one` case in
   `document/apply.py`, and tests.
3. **Surface `move_part` / `delete_part` / `merge_parts` in `COMPOSE_PROMPT`**
   and document that titles are optional. Also add the dedupe rule: *if a new
   part overlaps an existing one, prefer `merge_parts` or a targeted patch over a
   near-duplicate `add_part`.* This is the highest-leverage change for the
   known repetition problem.
4. **Output-shape flexibility.** Teach the composer to emit `file` parts for
   code artifacts (rendering already code-fences them with a language inferred
   from the filename). Add an output-shape hint to the decomposer so
   "write me a CLI tool" yields code parts rather than a prose report *about*
   a CLI tool.
5. **Consolidation pass.** One extra composer call after the final sub-task,
   scoped to outline-level cleanup (merge/delete redundancies). Cheap: outline +
   previews only. This is the explicit "revise before presenting" step the
   project's design promises but only applies *between* sub-tasks today.
6. **Integrity check**: `assert_payload_kept` already raises when a merge would
   drop the current sub-task's result; `changed_part_ids` already feeds deleted
   ids into the summary update. No changes needed — just add tests for both
   paths.

Verification (small model): "write a CLI tool" → expect `file` parts, not a
report; "write a report on X" → expect sections; a deliberately overlapping
follow-up question → expect a merge, not a duplicate section.

## Phase 1 — `context` layer: the keystone (weeks)

1. Define the `ContextStore` interface: `list()`, `read(id, start, end)`,
   `search(query) -> ranked hits`, `ask(question) -> answer + citations`,
   `summary(id)`. The in-turn `Document` implements it (wrapping existing
   behavior); Qdrant/Chroma-backed corpus stores implement it over ingested
   chunks.
2. Generalize `DocumentOracle` to query a **set** of `ContextStore`s. Tool names
   gain a store scope (e.g. `search(store=codebase, query=...)`).
3. **Fix retrieval**: replace substring search with ranked retrieval
   (vector scores for corpus stores; TF-IDF or BM25 for the document store —
   pure Python, no new deps). Remove the "first 8 parts" fallback in `ask`
   (replace with a ranked top-k from the store).
4. **Ingest pipeline (offline)**: tree-sitter parse → semantic chunks → Qdrant;
   graph nodes (functions/classes/files) + edges (calls, imports, references,
   same-module) → adjacency table. Retriever: vector search → seed chunks →
   one or two hops along call/import edges → return structurally adjacent code
   the vector pass missed.
5. **Chat memory**: turns/concepts as nodes (mentions-same-entity,
   follows-from, contradicts edges), same neighborhood-expansion retrieval.
   This is the successor to the current `compact_chat_history` (last 6 turns)
   in `oobabooga_extension/chat_adapter.py`.

Prior art to study before implementing the graph: Microsoft GraphRAG, LightRAG,
HippoRAG — all "vectors + entity/relation graph" retrieval.

Verification: ingest a mid-size repo; queries like "where is X called from" and
"what does this module depend on" should return structurally adjacent code.
Oracle `ask` over a large document must cite real parts, never a first-8 guess.

## Phase 2 — Parallel sub-task execution + sub-agent tools (weeks)

### Parallel execution

1. **Schema**: add `depends_on: list[str]` to `DecomposeSubTask`; the decompose
   prompt emits edges, turning the flat task list into a DAG.
2. **Scheduler**: topologically level the DAG. **Execute a frontier in parallel;
   compose serially.** Compose must stay sequential — it mutates shared
   `Document` state (parts, op log, summary). Execute fans out; compose folds
   results back in topological order.
3. **Frozen snapshot**: during a parallel frontier every executor queries a
   document snapshot taken at the frontier's start, not the live document.
   Reads-only during the frontier; mutations only in the serial compose phase.
4. **Graph validation in self-critique**: the critique pass checks the
   dependency graph for missing edges. Parallel siblings cannot see each
   other's intermediate outputs; a wrong graph = a blind sub-task. The
   per-sub-task verifier (Phase 3) is the safety net.
5. Reuse `run_multi_concurrent` (`llama_utils.py`) for the fan-out; llama-server
   `--parallel` already supports concurrent slots.
6. **Retire the legacy path**: the `AccumulatedResult.previous_results` chain
   (`SimpleSynthesiser`, `RollingDocumentUpdateSynthesiser`) is inherently
   sequential; delete it (fix-or-delete; the synthesiser's `NameError` dies with
   it).

### Sub-agent tools

`OracleLoopExecutor` already runs a tool loop; generalize it:

1. Tool *set* becomes configurable per domain pack (a `code` pack adds
   `run_python`/`read_file`; a `research` pack adds `web_search`).
2. Dispatch routes tool names to handlers the way `DocumentOracle._run`
   already does. Reuse the existing loop mechanics as-is: round budget,
   last-turn forcing, empty-result retry, budget-exhausted fallback text.

Verification (small model): a two-branch DAG where the branches are independent
runs concurrently; corrupt an edge (B depends on A but edge missing) and the
verifier flags B's result as context-starved.

## Phase 3 — Domain packs (weeks)

A pack is a **config bundle, not code** — that is what keeps the core generic.

```python
class DomainPack(BaseModel):
    id: str                       # 'code' | 'book' | 'legal' | 'science'
    decomposer: str               # which decomposer + prompt tweaks
    output_shape: OutputShape     # 'prose' | 'code' | 'mixed' — drives render + composer
    sub_task_tools: list[str]     # tools available to executors (Phase 2)
    retrievers: list[str]         # which context stores this pack queries
    verifiers: list[VerifierSpec] # see below
    sources: list[SourceSpec]     # ingested corpora bound to the pack
    verifier_policy: str          # 'block_on_fail' | 'annotate' | 'retry_then_annotate'
```

Per-pack shape:

- **`code`**: `output_shape=code`, tools `[run_python, read_file]`,
  verifier = "does it import & run / pass the given tests".
- **`book`**: `output_shape=prose`, `sources=[the book being continued]`,
  verifier = **consistency check** — retrieve established canon (characters,
  facts, timeline) from the ingested source and check the new chapter against
  it. "Edit past text for consistency" is then: verifier flags a conflict →
  composer issues a `replace_in_part`/`merge_parts` op on the *earlier* chapter
  part. The Document's revision capability is what makes continuation possible.
- **`legal` / `science`**: `sources=[statutes / papers]`, verifier =
  **check-against-source** (retrieve the cited passage, LLM-judge the claim
  against it). Staged: LLM-against-retrieved-source first (reliable, cheap);
  **FOL deep-verification** (emit first-order logic, check entailment/
  consistency with a small prover) as an opt-in flag. FOL is the most
  research-y piece and must not gate the rest.

Build order: **the `code` pack first, end-to-end** (ingest a repo → graph
retrieval → run-python verifier). One pack proves the whole pack contract
before building the others.

## Phase 4 — Harness-as-tool (weeks, overlaps with 2/3)

The main chat model invokes the harness mid-conversation. Hybrid trigger:

1. **Heuristics pre-filter** (`agent_detect.py`, extended): obviously trivial
   turns never enter the harness; obviously complex turns may skip confirmation.
   Cheap, never the sole decider.
2. **Primary: native tool calling.** llama-server's OpenAI-compatible endpoint
   accepts a `tools` param; `create_llama_client` already returns a stock OpenAI
   client pointed at it, and the serving model (Devstral) is tool-capable.
   Expose `deep_reason(prompt, session_id)` and `retrieve(query)` as tools; the
   oobabooga hook executes the call and feeds the result back, and the model
   continues from it.
3. **Backstop: text sentinel.** Reuse the existing sentinel channel
   (`[[multistep-inner]]` and the `should_skip_orchestrator` machinery, turned
   around): a `[[USE-DEEP-REASONING]]` marker (or fenced JSON) that the
   `custom_generate_reply` hook intercepts. Works on any model, kept alive even
   after native tool calling works.

## Cross-cutting work (do alongside the above)

- **Live smoke tests**: a small-model end-to-end pipeline test, gated/skipped by
  default, run explicitly before merging phases. Plus golden-fixture tests that
  feed recorded bad model outputs (truncated JSON, wrong meta-types, junk
  shapes) through the parsers in `llama_utils.py`, to catch silent regressions
  in the repair logic.
- **Cleanup**: remove `mcp_server/` (abandoned) or freeze it; delete
  `main.bak.py`, `tst_new_orchestrator.py`, and the `history_*.json` /
  `results_*.json` / `output_*.md` experiment dumps (they account for most of
  the repo's size); replace the full-machine `requirements.txt` dump with the
  project's real deps (`openai`, `instructor`, `pydantic`, `pyyaml`, `pytest`,
  `tiktoken` optional, plus the Qdrant/Chroma client when Phase 1 lands).
- **Tighten the `ExecutorTurn` validator**: `_flatten_qwen_shape` silently
  converts junk into `result`; add a strict mode so real model failures are
  visible in logs instead of being rescued invisibly.

## Explicit non-goals (considered and rejected)

- **Neo4j or any server-side graph DB initially.** Adjacency tables cover
  one/two-hop expansion; add a real graph DB only if multi-hop query language
  becomes necessary.
- **Recursive self-decomposition** (sub-tasks spawning sub-orchestrations with
  budgets). The budget-constraint problems are exactly the class that
  destabilized the Grok session described in the README caveats.
- **MCP as the deployment face.** Abandoned; oobabooga is the deployment.
- **Concept-graph chat memory (neo4j idea from `main.bak.py`).** The rolling
  summary + oracle already cover the common case; chat *memory* in Phase 1 is
  retrieval over stored turns, not a knowledge graph of concepts.

## Sequencing summary

1. **Phase 0** — flexible documents (optional titles, `merge_parts`, surfaced
   move/delete, output shapes, consolidation pass). *Delivers immediate value;
   unblocks everything else's ergonomics.*
2. **Phase 1** — `context` subpackage + `ContextStore` keystone + Qdrant
   ingestion + graph retrieval + chat memory. *Proves the "infinite context"
   door.*
3. **Phase 2** — parallel execution (DAG + frozen snapshot) + pack-configurable
   sub-agent tools. *Both reuse existing primitives; small model keeps smoke
   tests fast.*
4. **Phase 3** — `code` pack end-to-end, then book/legal/science packs.
   *One pack proves the contract before the others.*
5. **Phase 4** — harness-as-tool (native tool calling + sentinel backstop).
6. **Throughout** — live smoke tests, cleanup, strict parsing mode.

The three load-bearing decisions are: (1) the `ContextStore` is the single door
from day one; (2) native tool calling is primary with the sentinel as backstop;
(3) no Neo4j initially. If any of those change, re-plan around it before
starting the affected phase.