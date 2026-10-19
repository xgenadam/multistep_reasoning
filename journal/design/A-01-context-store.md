# A-01: `ContextStore` on paper

- **Ticket:** A-01 (criterion A-9). **Date:** 2026-10-19. **Model:** Fable 5.1.
- **Sources:** PLAN § Phase A, D-001, D-004, D-011, D-014; the S-008 input in
  A-01 Notes; the code as of `7560d9f`.
- **Status:** draft for the user's approval. Nothing here is in force until
  the approval bullet lands in `tickets/A-01.md`. The draft decision in § 8
  is appended to DECISIONS.md at that point, not before.

## 0. Summary

1. One protocol, `ContextStore`, with `describe`, `list`, `read`, `search`,
   `ask`, `summary` and a reserved `write`. `Hit` is as PLAN says, with
   `provenance` as the only per-kind slot (§ 1).
2. Every store instance carries a **tier**: `working` > `conversation` >
   `corpus` > `derived`. The oracle merges hits by tier, then by rank, never by
   raw score, and never drops a tier's hits. Answers carry structured
   citations (store id always present), `conflicts` and `unresolved` (§ 2).
3. The dry-run against document, papers, books, code and notes/chat needs
   eleven changes to the plan's signature, all listed in § 3.5. After them every
   cell fits. Two kinds (books, code) override the `ask` default without
   touching the interface.
4. Replies, artifacts and working memory are **not** three documents. They are
   a `role` on `Part` (`artifact` default, `reply`, `scratch`) on the one
   `Document`, plus a pipeline-written `results` store that holds every
   sub-task result as a note. The rolling summary stays in-prompt (D-011).
   D-014 keeps its rule and gains a precise denominator (§ 4).
5. `context/` lands beside the existing packages. `document/` never imports it;
   `oracle/` becomes the door over a set of stores (§ 5).
6. Phase A stays at zero dependencies, zero services and today's prompt cost:
   the default tool scope is the working tier, which is today's behaviour (§ 6).

## 1. The interface

### 1.1 Models

Sketch of `reasoning_sub_agents/context/store.py`, which A-02 lands. Pydantic
models, stdlib only.

```python
Tier = Literal['working', 'conversation', 'corpus', 'derived']
Filters = dict[str, Any]          # keys are store-specific; describe().filters lists them


class Span(BaseModel):
    start: int                    # char offsets in the doc's text, end exclusive
    end: int


class Entry(BaseModel):           # one row of list()
    store_id: str
    doc_id: str
    chunk_id: str | None = None   # set when listing inside one doc (sections, chapters, symbols)
    title: str | None = None
    kind: str                     # store vocabulary: section | file | paper | chapter | symbol | turn | note
    size: int                     # chars
    meta: dict[str, Any] = {}     # store-specific, small (role, year, language, ts ...)


class Listing(BaseModel):
    entries: list[Entry]
    total: int                    # matches before `limit` was applied
    order: str                    # 'position' | 'newest' | 'title' | 'path'


class Excerpt(BaseModel):         # what read() returns
    store_id: str
    doc_id: str
    span: Span                    # the span actually returned, in doc coordinates
    text: str
    truncated: bool = False       # True when the store's read cap cut the request


class Hit(BaseModel):             # PLAN's Hit, unchanged in fields
    store_id: str
    doc_id: str
    chunk_id: str                 # equals doc_id when the chunk is the whole doc
    title: str | None = None
    span: Span                    # doc coordinates of `text`
    score: float                  # store-local, higher is better; only order is comparable across stores
    text: str                     # excerpt, at most the store's excerpt cap
    provenance: dict[str, Any] = {}

    def ref(self) -> str:         # canonical citation string: 'store:doc' or 'store:doc#chunk'
        ...


class Cite(BaseModel):            # a Hit without text and score; what an Answer cites
    store_id: str
    doc_id: str
    chunk_id: str
    span: Span
    title: str | None = None


class Conflict(BaseModel):
    topic: str
    positions: list[tuple[Cite, str]]   # (where, the claim as stated there)


class Answer(BaseModel):
    answer: str
    citations: list[Cite]
    conflicts: list[Conflict] = []
    unresolved: list[str] = []    # refs the model cited that match no retrieved hit


class Note(BaseModel):            # the write-side payload (D-004); declared, not implemented in A
    title: str | None = None
    text: str
    provenance: dict[str, Any]    # author (pack, pipeline, user), ts, run/turn ids
    derived_from: list[Cite] = [] # the sources a derived note rests on


class Receipt(BaseModel):
    store_id: str
    doc_id: str
    chunk_id: str


class StoreInfo(BaseModel):       # what describe() returns; the oracle builds the tool prompt from it
    store_id: str
    kind: str                     # document | notes | chat | papers | books | code
    tier: Tier
    description: str              # one line, for the prompt
    filters: list[str]            # accepted filter keys
    doc_count: int | None
    writable: bool
    read_cap_chars: int
```

### 1.2 Protocol

```python
Answerer = Callable[[str, list[Hit]], Answer]   # the oracle's one LLM-call site


@runtime_checkable
class ContextStore(Protocol):
    store_id: str
    tier: Tier

    def describe(self) -> StoreInfo: ...
    def list(self, filters: Filters | None = None, *, limit: int = 50) -> Listing: ...
    def read(self, id: str, start: int | None = None, end: int | None = None) -> Excerpt: ...
    def search(self, query: str, k: int = 5, filters: Filters | None = None) -> list[Hit]: ...
    def ask(self, question: str, k: int = 5) -> Answer: ...
    def summary(self, id: str | None = None) -> str: ...
    def write(self, note: Note) -> Receipt: ...   # reserved (D-004)


class ContextStoreBase:
    """Defaults every store inherits. A store overrides what its kind needs."""

    def __init__(self, store_id: str, tier: Tier, *, answerer: Answerer | None = None): ...

    def ask(self, question, k=5):           # search, then one answer call
        hits = self.search(question, k)
        if self._answerer is None:
            raise AskUnavailable(self.store_id)
        return self._answerer(question, hits)

    def summary(self, id=None):             # store-level text, else a preview of the doc
        ...

    def write(self, note):                  # read-only unless the store says otherwise
        raise ReadOnlyStore(self.store_id)
```

### 1.3 Contracts per method

- **`describe()`** is cheap and pure. The oracle calls it when it builds the
  executor prompt: one line per store (`store_id`, `tier`, `description`,
  `filters`). Adding a store never touches a prompt template.
- **`list(filters, limit)`** returns at most `limit` entries and the `total`
  before the limit, in the store's natural order (`Listing.order`). With
  `filters={'doc_id': X}` the entries are the chunks of `X` (`chunk_id` set).
  Unknown filter keys raise `BadFilter`; the oracle returns the error text as
  the observation, as `DocumentOracleError` is returned today.
- **`read(id, start, end)`**: `id` is a chunk id or a doc id; the store tries
  the chunk namespace first (in the Document store the two coincide).
  `start`/`end` are relative to the named object. `Excerpt.span` is always in
  doc coordinates, so a caller can widen with `read(doc_id, span.start - 500,
  span.end + 500)`. A request past `read_cap_chars` is cut there and
  `truncated=True`. The oracle's observation cap (`prompt_token_budget // 4`)
  still applies on top.
- **`search(query, k, filters)`** returns the top-`k` hits by the store's own
  ranking, each with an excerpt around the best match. `k` is capped by the
  store (20). No hit means an empty list: there is no fallback to the first
  parts. Stores accept their documented filter keys only.
- **`ask(question, k)`** on one store is `search` plus one answer call through
  the injected `Answerer`. Stores hold no LLM client. The `Answerer` validates
  every citation the model emits against the hits it was shown: a ref that
  matches a hit becomes a `Cite`; one that does not goes to `unresolved`. A-1
  counts `unresolved` and checks `citations` by content. An empty hit list
  yields an honest empty answer, not an answer from unrelated parts.
- **`summary(id)`**: `None` is the store-level summary (the rolling summary
  for the Document store, the corpus description for papers, the chat summary
  for chat). A doc id gives the doc's summary where the store has one
  (abstract, chapter synopsis, module docstring) and a `preview_text` of its
  head otherwise.
- **`write(note)`** is reserved. The default raises `ReadOnlyStore`. A store
  that implements it says so in `describe().writable`, and the oracle exposes a
  write tool only for such stores (none in Phase A). Writing to the Document
  is not part of this interface: the composer's ops are the artifact's write
  path and the executor never edits the artifact through the oracle.
- **Purity.** `describe`, `list`, `read`, `search`, `summary` and `ask` do not
  mutate the store. A frozen view for Phase P is `DocumentStore(document.clone())`.
- **Ids.** `doc_id` and `chunk_id` are store-local strings. The canonical ref
  is `store_id:doc_id` when the chunk is the whole doc, else
  `store_id:doc_id#chunk_id`. Part ids are kebab-case and never contain `:` or
  `#`.
- **Errors.** `ContextStoreError` with `UnknownRef`, `BadFilter`,
  `ReadOnlyStore`, `AskUnavailable`. The oracle turns each into an
  `{'tool', 'store', 'error'}` observation.

## 2. The conflict policy

The three rules from PLAN, each with the mechanism that enforces it.

1. **Working memory outranks corpus for current-task questions.**
   - Every store instance has a `tier`. Tier is per instance, not per kind: a
     notes store is `working` as the run scratchpad and `derived` as the KB.
   - Order: `working` (the Document, the `results` store) > `conversation`
     (chat turns) > `corpus` (papers, books, code) > `derived` (KB notes).
     Within `working`, the Document precedes `results`: the artifact is the
     current state, the results are its history. `derived` is last because
     notes never outrank sources (D-004).
   - A tool call with no `store` targets the working tier. That is today's
     behaviour and today's cost. Corpus stores are queried when named, or when
     `ask` is called with `store='all'`.
   - When more than one store is in scope, the oracle merges per-store
     `search` lists: group by tier in that order, interleave stores within a
     tier by rank (reciprocal rank fusion, `k=60`), cap at the requested `k`.
     Raw scores are never compared across stores.
   - The answer prompt tags each excerpt `[store_id | tier | ref | title]` and
     says: for what the task or document currently says, trust `working` over
     `corpus`; for a claim about the world, cite `corpus`.
2. **Cross-store conflicts are annotated, never silently resolved.**
   - Retrieval never filters one tier out because another answered. Merge,
     do not pick.
   - `Answer.conflicts` is a schema field. The prompt says: when excerpts
     disagree, list both positions with their citations and do not choose.
   - The oracle returns `conflicts` verbatim in the observation. Whether the
     executor carries it into its result is the executor's job, judged by Q.
   - Proposed check (for the user, not added here): V plants one
     contradiction between the document and a paper and expects
     `conflicts` non-empty in 3/3 asks (a V-5 if accepted).
3. **Every citation carries a store id.**
   - `Cite` is built from a retrieved `Hit`, whose `store_id` is required.
     The model never fabricates a citation structure; it names refs, and the
     `Answerer` resolves them. Unresolvable refs are visible in `unresolved`.
   - The Document store's refs are `document:<part-id>`, so a citation in a
     rolling summary or a later part is traceable to a store and a part.

## 3. Dry-run (A-9)

### 3.1 What store, doc and chunk are per kind

| Kind | Store | Doc | Chunk | Doc text (span coordinates) |
| --- | --- | --- | --- | --- |
| document | the `Document` being built (one instance = one store) | a `Part` | the part (A-02); paragraphs `part#n` later, interface unchanged | `part.body` |
| papers | a corpus (V: FTS5 over ~20 papers; B: tier 1) | a paper (`arxiv_id`) | a section or section piece, `paper#ordinal` | the paper's full text |
| books | the books adapter (B2) | a book | a chapter piece, `book#ch03-p12`, with a chapter ordinal | the book's text |
| code | the code adapter (B2) | a file (`path`) | a symbol span, `path#qualified.name` | the file's text |
| notes/chat | chat: stored turns (C). notes: run scratchpad (R) and KB (B3) | a turn, or a note | the turn or note itself; paragraphs later | the turn's or note's text |

### 3.2 Method × kind

"fits" means the final interface (§ 1) serves the kind without change.
"Cn" names the change in § 3.5 that this kind forced. "override" means the
store overrides a base default without touching the interface.

| Method | document | papers | books | code | notes/chat |
| --- | --- | --- | --- | --- | --- |
| `describe` | fits (C6) | fits (C6: filters must be discoverable) | fits | fits | fits |
| `list` | fits: the outline, positional order | C1: bounded, `total`, filters narrow | C1, C2: chapters of one book | C2: symbols of one file; order `path` | C1: `newest` first, time filters |
| `read` | fits: today's `read_part` | C4: read a section, then widen | C3: a chapter exceeds any prompt; cap + `truncated` | fits; provenance carries lines (C3 cap on large files) | fits |
| `search` | fits: BM25 over parts (A-02) | fits; FTS5 `bm25()` negated (C10) | fits; `upto` filter for spoiler-safe canon | fits; graph filters `callers_of`, `callees_of` | fits; recency as the in-store tie-break |
| `ask` | fits (C7, C8 default) | fits (V-1) | fits, override: expand to chunk ±1 before answering | fits, override: include the enclosing symbol's header | fits (C-1) |
| `summary` | C5: `summary()` is the rolling summary; `summary(part)` is a preview | fits: abstract | fits: derived synopsis, else preview | fits: module docstring, else preview | C5: `summary()` is the chat summary (C-2) |
| `write` | fits: `ReadOnlyStore` through the door; the composer's ops are the write path | fits: `ReadOnlyStore` | fits: `ReadOnlyStore` | fits: `ReadOnlyStore` | fits (C9): `write(note)` on scratchpad (R) and KB (B3); chat is written by the face at turn end |
| `Hit` | fits | fits | fits | fits | fits |

### 3.3 `Hit` per kind: provenance is the variable slot

| Kind | `doc_id` / `chunk_id` | `title` | `score` | `provenance` |
| --- | --- | --- | --- | --- |
| document | `report-full` / same (A-02) | part title | BM25 | `{origin_task, role, kind, seq}` (`seq` after A-04) |
| papers | `2401.01234` / `2401.01234#3` | paper title | `-bm25()` (FTS5), hybrid later | `{section, heading_path, year, authors, category}` |
| books | `dune` / `dune#ch03-p12` | "Dune, ch. 3" | BM25 / hybrid | `{chapter, ordinal, canon_upto}` |
| code | `src/main.py` / `src/main.py#greet` | the path | symbol match + BM25 | `{symbol, symbol_kind, lines: [a, b], commit}` |
| chat | `turn-12` / same | "turn 12 (user)" | BM25 × recency | `{chat_id, turn_id, role, ts}` |
| notes | `claim-0007` / same | note title | BM25 | `{author: 'pack:science', ts, run_id, derived_from: [Cite]}` |

### 3.4 `filters` per kind

Shared keys: `doc_id` (restrict to one doc), `kind`. Per kind:

| Kind | Keys |
| --- | --- |
| document | `role` (artifact, reply, scratch), `origin_task`, `ids` |
| papers | `year`, `authors`, `category`, `section`; B-03 adds `cites`, `cited_by` (1–2 hops) |
| books | `book`, `chapter`, `upto` (only chunks up to a chapter ordinal: canon as of chapter N), `entity` (T-book tags) |
| code | `path_prefix`, `language`, `symbol_kind`; B2 adds `callers_of`, `callees_of`, `imports` |
| notes/chat | `role` (user, assistant), `after_ts`, `before_ts`, `author`, `tag`, `run_id` |

Graph expansion is a filter in this reading: it restricts candidates to a
neighbourhood, and ranking stays the store's. Edges themselves are internal
to the store and surface only through filters and provenance. That keeps the
interface at six read methods for every kind.

### 3.5 Changes to the plan's signature, and which kind forced each

The plan's signature was `list(filters)`, `read(id, start, end)`,
`search(query, k, filters) -> list[Hit]`, `ask(question, k)`, `summary(id)`,
a reserved write, and `Hit{store_id, doc_id, chunk_id, title, span, score,
text, provenance}`.

| # | Change | Forced by |
| --- | --- | --- |
| C1 | `list` takes `limit` and returns `Listing{entries, total, order}` | papers (10–20 K docs at tier 1), books; chat needs `newest` order |
| C2 | `list(filters={'doc_id': X})` lists the chunks of `X` (`Entry.chunk_id` set) | books (chapters), code (symbols), papers (sections) |
| C3 | `read` returns `Excerpt{doc_id, span, text, truncated}`; stores declare `read_cap_chars` | books (a chapter is 20–40 K chars), large code files |
| C4 | `read`'s `id` is a chunk id or a doc id; offsets are relative to the named object; `Excerpt.span` is in doc coordinates | papers (read a section, then widen around it) |
| C5 | `summary(id=None)`: `None` is the store-level summary | document (the rolling summary is store-level), chat (C-2) |
| C6 | `describe() -> StoreInfo` and a per-instance `tier` | papers (filters must be discoverable); the multi-store prompt; the conflict policy |
| C7 | `Answer{answer, citations: list[Cite], conflicts, unresolved}` replaces `OracleAnswer{answer, citations: list[str]}` | policy rules 2 and 3; A-1 needs `unresolved` visible |
| C8 | `ask` = `search` + an injected `Answerer`; stores hold no LLM client; the oracle's cross-store `ask` merges `search` lists by tier and calls the same answerer | policy rule 1 (one answer call over tagged excerpts); the stores stay data |
| C9 | `write(note: Note) -> Receipt` with a defined payload (`title`, `text`, `provenance`, `derived_from`) | notes (D-004): "notes never outrank sources" needs the sources on the note |
| C10 | `score` is store-local, higher is better; cross-store order is by rank (RRF), never by score | papers (FTS5 `bm25()` is lower-is-better) against document (BM25 higher-is-better) |
| C11 | `Hit.ref()` gives the canonical `store:doc#chunk` string | citations in prose and in the answer schema need one spelling |

`Hit`'s fields are unchanged. After C1–C11 every cell in § 3.2 fits.

## 4. Artifact, reply, working memory

### 4.1 Evidence (0-16 baseline, `20261019T051008Z_rebaseline-0-16_…json`, s3)

- Run 0, turn 0: `add outline`, `add report-full`, `delete outline`,
  `update report-full`. Turn 1: two draft parts added, merged, patched.
- Run 1, turn 0: `add definition`, `add benefits`, `add drawbacks`, delete all
  three, `add final-report`. Turn 1 adds
  `integrate-migration-section-into-report`, a part named after a process
  step.

Parts named `outline`, `*-draft` and `integrate-*` are working material. They
land in the artifact because sub-task results have nowhere else to go, and
they are deleted or merged when a later sub-task re-emits the whole
deliverable. In a chat turn the whole document is also the reply
(`task_orchestrator.py` renders it as `chat_response`), so a second question
in the same chat inherits parts it does not want.

### 4.2 Design: roles on parts, plus a results store; not three documents

- **`Part.role: Literal['artifact', 'reply', 'scratch'] = 'artifact'`.** A
  defaulted field, so nothing changes until the composer sets it.
  - `artifact`: lives across turns and runs; ids stable; edited by patch ops;
    held to D-014; rendered.
  - `reply`: lives for the turn; rendered as this turn's answer; rebuilt
    freely; not held to identity. At the start of the next turn on the same
    Document (`Document.begin_turn()`), reply parts are removed with
    `delete_part` ops whose `origin_task` is `turn-end`, and handed to the
    chat store (C) as that turn's assistant text. Until C exists they are
    simply removed; the chat UI already holds the text.
  - `scratch`: lives for the run; never rendered; readable and searchable
    through the door; dropped at run end. In chat a turn is a one-milestone
    run.
- **The `results` store**, kind `notes`, tier `working`, written by the
  pipeline, not by any tool call: after each `execute_one` the orchestrator
  writes the sub-task result as a note (`doc_id = <turn_id>/<sub-task name>`,
  provenance `{turn_id, sub_task, seq}`), and the plan as `<turn_id>/plan`.
  It costs no LLM call and one `describe()` line in the executor prompt. The
  composer's `body_source='current_result'` is then literally a copy from the
  latest note. R's "in-run notes scratchpad" is this store with `write`
  enabled for packs, persisted under `/runs/<run_id>/`.
- **The rolling summary** stays in-prompt (D-011). Working memory is the
  summary plus the `results` store plus `scratch` parts.
- **Who sets the role.** The composer, through `add_part.role`. Teaching it
  to do so is a prompt change with a quality gate, so it is a ticket after
  Q-01 (judge) and not part of A. The field, the render filter and the
  `begin_turn` retirement are mechanical and can ride with A-04, which already
  touches `Part` and the snapshot (proposal, § 7).

Why not the S-008 sketch of three documents:
- Ops address parts by id. Three documents need a document selector on every
  op, so the op union, `apply_operations`, snapshots, `check.py` and the
  harness all change, for no Phase A value.
- Promotion ("keep that in the artifact") is a role change on one part, not a
  copy between documents with a new id.
- The compose prompt sees one outline. Compose is 54 % of prompt tokens; three
  outlines would be three listings per call.
- One id space keeps a citation meaningful across roles: `document:report-full`
  names the same text whether the part is artifact or reply.

What the sketch gets right and this design keeps: the reply is rebuilt freely
per turn; short-term memory is separate from the deliverable and never
rendered; both are stores behind the one door, not a separate memory system.

### 4.3 The roles walked through the methods

| Method | artifact | reply | working memory (`scratch` parts, `results` store) |
| --- | --- | --- | --- |
| `list` | in the outline; `filters={'role': 'artifact'}` | in the outline for this turn | `scratch` parts listed with their role; `results` listed newest first |
| `read` | fits | fits | fits |
| `search` | working tier, first in order | working tier | working tier; `results` after the Document |
| `ask` | cited as `document:<part>` | cited as `document:<part>` this turn; as `chat:<turn>` after retirement | cited as `document:<part>` (scratch) or `results:<turn>/<task>`; a scratch note contradicting the artifact is a `conflict` |
| `summary` | covered by the rolling summary | covered this turn | `scratch` excluded from the summary prompt's `changed` list once roles exist; `results` has no summary call |
| `write` | the composer's ops only | the composer's ops only | the pipeline writes `results`; packs write the scratchpad in R |
| `Hit.provenance.role` | `artifact` | `reply` | `scratch`, or the note's `{turn_id, sub_task}` |

Citation stability follows: artifact citations stay valid across turns
(D-014); reply citations are valid within the turn, then resolve through the
chat store; scratch citations die with the run and `unresolved` says so.

### 4.4 Effect on D-014, P0-3 and D-011

- D-014 is unchanged in rule. Its denominator becomes "artifact-role parts"
  once roles exist; chat follow-ups then produce reply parts and are exempt
  by construction rather than by a scenario flag. Its re-open trigger
  ("A-01 splits reply and artifact documents") does not fire: documents are
  not split.
- P0-3's `followup_keeps_parts` keeps working as is until the composer sets
  roles; `check.py` then filters by role.
- D-011 holds: the summary stays in-prompt, and both `results` and chat are
  stores behind the door.

## 5. Mapping to today's code

### 5.1 Layout (D-001: beside, no rename)

```
reasoning_sub_agents/
  document/          unchanged in A-02; A-04 adds Part.role, op-log seq/ts, snapshot/rehydrate
  context/           new
    store.py         models, protocol, ContextStoreBase, errors        (A-02)
    document_store.py  DocumentStore(document, answerer): BM25, one chunk per part  (A-02)
    notes_store.py   in-memory NotesStore for `results`; write() for R   (A-03 or later, § 7)
    fts5_store.py    papers (V), reused by B
  oracle/            the door: a set of stores, the ToolRegistry, the Answerer  (A-03)
```

Dependency direction: `document/` imports nothing from `context/` or
`oracle/`; `context/document_store.py` imports `document/`; `oracle/` imports
`context/`. `context/store.py` imports only pydantic.

### 5.2 Symbol by symbol

| Today | Becomes | Ticket |
| --- | --- | --- |
| `SearchHit{part_id, title, index, excerpt}` (`oracle/tools.py:121`) | `Hit{store_id='document', doc_id=part_id, chunk_id=part_id, title, span, score, text, provenance}`. N5 (offset computed on `title + body`, sliced on `body`) disappears: the span is computed on `body` only | A-02 |
| `OracleAnswer{answer, citations: list[str]}` | `Answer` (C7). The `Answerer` validates refs against the hits it showed | A-02 |
| `DocumentOracle.list_parts / read_part / search / summary` | `DocumentStore.list / read / search / summary` | A-02 |
| `DocumentOracle.ask` and `ASK_PROMPT` | `oracle/answer.py`: the `Answerer` (tagged excerpts, `conflicts`, citation validation). `DocumentStore.ask` uses it through C8 | A-02 |
| the first-8-parts fallback in `ask` | deleted; an empty hit list is an honest empty answer | A-02 |
| `DocumentOracle.dispatch / _run` and the `OracleTool` union | `ToolRegistry` (name, schema, handler); tools `list`, `read`, `search`, `ask`, `summary`, each with a `store` param defaulting to the working tier | A-03 |
| `DocumentOracle.update_summary` | stays on the oracle side (it writes the rolling summary; not a store method) | A-03 |
| `OracleFactory = Callable[[Document], DocumentOracle]` | the oracle takes a list of stores; the factory builds `DocumentStore(document)` plus the stores named in config | A-03 |
| `executor/base.py` hint `oracle: DocumentOracle` | `Oracle` | A-03 |
| `config/schema.py` `components.oracle` | plus `stores: [{id, kind, tier, ...}]`; default `[{id: document, kind: document, tier: working}]` | A-03 |
| `OracleLoopExecutor.SYSTEM_PROMPT` rule 2 (`list_parts / read_part / search`) | names from the registry; the store list from `describe()` | A-03 |
| `Part` | `+ role` (default `artifact`), `render()` skips `scratch`, `begin_turn()` retires `reply` | A-04 (proposal) |
| `harness.py` snapshot / rehydrate | promoted to `document/` (planned) | A-04 |
| `check.py` `followup_keeps_parts` | counts artifact-role parts once roles exist | after the composer sets roles |

In-prompt outline: the executor and composer keep printing
`[{id, kind, title, char_count}]`. `Entry` carries `store_id`, but the oracle
prints it once per store, so the outline's token cost does not change.

### 5.3 Where each later phase plugs in

- **A-05:** A-1, A-4, A-6 against `DocumentStore`. `write` is reserved, so A-4's
  "every method exercised live" excludes it by design; `describe` is exercised
  at prompt build.
- **V:** `Fts5Store` (papers) with `tier='corpus'`. V-1 is the first real test
  of § 3's prediction: a second store with no interface change.
- **R:** `NotesStore.write` for the scratchpad; `results` persisted per run.
- **B / B2 / B3:** adapters as stores; edges stay inside the store (§ 3.4);
  KB notes are `NotesStore(tier='derived')`.
- **C:** `ChatStore` over stored turns, `tier='conversation'`; the last-6
  fallback stays in-prompt (D-011).
- **P:** frontiers read `DocumentStore(document.clone())`.

## 6. Guard-rails for Phase A (A-5, A-6)

- No new runtime dependency: BM25 is hand-rolled; `Fts5Store` is stdlib
  sqlite and belongs to V, not A.
- No new service.
- Tool schema grows by one `store` parameter. The executor prompt grows by one
  line per store. With one store that is one line.
- Default scope is the working tier, so an executor `search` with no `store`
  touches exactly what it touches today.
- `DocumentStore.search` over 30 parts is sub-millisecond; `ask` stays one LLM
  call. A-6 is dominated by that call, as today.
- The observation JSON for a hit changes shape (`part_id` and `index` give way
  to `doc_id`, `chunk_id`, `span`, `score`, `store_id`). That is observation
  content, not a prompt template, and about 15 tokens per hit. A-05 measures
  it; A-02 records it in Notes.

## 7. Questions for the user

1. **Roles plus a results store, not three documents** (§ 4.2). Approve, or
   keep the three-document sketch?
2. **Landing.** `Part.role` (defaulted), the render filter and `begin_turn()`
   ride with A-04; the in-memory `results` store rides with A-03, where the
   oracle takes a set of stores anyway and a second store makes A-4's
   "second store, no interface change" checkable inside A. Alternatively both
   become tickets after A-05. Which?
3. **Default scope** is the working tier (today's behaviour). Agreed?
4. **Tier order** puts `conversation` between `working` and `corpus`: the
   user's words define the task, and the Document is its current state. Agreed?
5. **A planted-conflict criterion** for V (§ 2, rule 2). Add as V-5, or leave
   conflict annotation to the judge?

## 8. Draft decision (appended to DECISIONS.md on approval)

> **D-nnn (the next free ID at approval): ContextStore v1 is tiers, roles on parts and working memory as a store**
> Decision: The `ContextStore` protocol is `journal/design/A-01-context-store.md`
> § 1 (`describe`, `list`, `read`, `search`, `ask`, `summary`; `write`
> reserved; `Hit` with a required store id and per-kind provenance). Every
> store instance has a tier, `working` > `conversation` > `corpus` >
> `derived`; the oracle merges hits by tier then rank, never by raw score,
> never drops a tier's hits, and `Answer` carries `citations` built only from
> retrieved hits, `conflicts` and `unresolved`. Replies, artifacts and working
> memory are not separate documents: `Part.role` in {`artifact`, `reply`,
> `scratch`} (default `artifact`) on the one `Document`, plus a
> pipeline-written `results` store of sub-task results. The rolling summary
> stays in-prompt.
> Why: one id space keeps citations and D-014's identity rule meaningful
> across roles; three documents would change the op union, snapshots, the
> harness and the compose prompt for no Phase A value; the s3 op logs show
> the model needs working memory it can read, which a pipeline-written store
> gives at zero prompt cost. Scores are not comparable across backends, so
> cross-store order must be rank-based.
> Supersedes: none (answers the question D-014 left to A-01).    Re-open if:
> V-1 needs an interface change for the papers store, or the role split fails
> P0-3 or a Q gate once the composer sets roles.

## 9. Approval (2026-10-19, S-017)

The user approved this note. § 8 is recorded, amended, as **D-018**; where
the two differ, D-018 governs.
- § 7.1 and § 7.2: approved as proposed (`Part.role` with A-04, `results`
  with A-03).
- § 7.3: the working tier stays the default scope, but every store in scope
  is listed to the model, which escalates by tier at its own discretion.
  A confidence-driven search depth is A-06's to design.
- § 7.4: the tier order is the provisional default. Context-dependent
  precedence (book continuity vs. canon; a research assumption overturned by
  a source) and escalation of a conflict into a fresh reasoning run are
  A-06's to design.
- § 7.5: V-5 added to PLAN.
