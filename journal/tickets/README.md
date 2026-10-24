# Tickets

One markdown file per work item: `<id>.md`. Files plus `git log` are the
tracker. This file is the only copy of the ticket rules. `make board` prints
every ticket's front-matter as a table and lints it.

## IDs

- **Ticket IDs** are `<phase>-<NN>`, numbered in order within the phase:
  - phase ∈ {`O`, `0`, `Q`, `A`, `V`, `R`, `B`, `T`, `P`, `C`, `H`};
  - `NN` is zero-padded (`A-01`, `0-14`);
  - a ticket split in two takes a letter suffix (`0-10a`, `0-10b`).
- **Pass-criterion IDs** (`P0-3`, `O-1`, `A-7`, `P-P1`, …) are defined in
  `../PLAN.md`. They go in `criteria:` and are never renumbered.
- **Decision IDs** (`D-nnn`) live in `../DECISIONS.md`.

## Tickets are instantiated when their phase starts

A ticket's Scope is condensed from `../PLAN.md` at instantiation and is the
contract from then on. Phases V, R, B, T, P, C and H have no tickets yet;
PLAN.md's task board holds their model/effort until they do.

## File format

```markdown
---
id: A-02
title: <short imperative title>
phase: A
status: open             # open | in_progress | blocked | done | dropped
criteria: [A-2, A-3]     # pass-criterion IDs from PLAN.md; empty = not a ticket
model: Opus 5.5          # two-stage: "Fable 5.1 → Opus 5.5" (one stage per session)
effort: medium           # low | medium | high | xhigh; two-stage: "high → medium"
needs_server: none       # none | behavioural | timing
needs_planning: false    # false | short (plan mode in-session) | true (own design session)
depends_on: [A-01]       # static ticket IDs that must be done first; [] if none
started:                 # YYYY-MM-DD, set by the ticket's first commit
done:                    # YYYY-MM-DD, set when status -> done
blocked_on:              # live condition only while blocked; empty otherwise
supersedes: []           # stale state docs this work retires
runs: []                 # run files produced (journal/baseline/runs/...)
---

## Scope

<!-- The contract, condensed from PLAN.md at instantiation. -->

## Notes

<!-- Dated bullets, written as work happens: what was tried, dead ends,
     model failures, decisions taken in-session. -->

## Measurements

<!-- Numbers per criterion in `criteria:`, pass/fail each, with the run file
     or command that produced them. The AAR synthesises from this block. -->
```

What the fields mean:
- **`needs_server`:**
  - `none`: no generator calls.
  - `behavioural`: needs generator calls whose outputs and tokens count, but
    whose wall times don't. The agent may be active, and `--jobs 3` is fine.
  - `timing`: its wall times are kept as a clean record. It gates nothing
    (D-025). It needs an idle box and `--jobs 1`, and its times are void if
    the agent was calling the model during the run (see `../../AGENTS.md`
    § Measurement).
- **`depends_on`** is static and **`blocked_on`** is live. A ticket waiting on
  a run window or on the user says so in `blocked_on`; a ticket whose
  prerequisite tickets are not done just has `depends_on`.

## Rules

1. **Status changes are commits.** A ticket's first commit flips it to
   `status: in_progress` and sets `started:`. A `status:` flip with no
   code or context change in the same or an adjacent commit is noise. Ticket
   IDs in commit messages are the audit trail.
2. **Done means every `criteria:` passes**, or an S-entry records an explicit,
   decided waiver. "Code written" is `in_progress` at best.
3. **Evidence lands when it is produced, never at session end.** A run file
   and a dated Notes bullet go in the same commit, the run file's path goes
   into `runs:`, and the numbers go into Measurements. If the session dies,
   the evidence survives.
4. **One active ticket per executor, and one ticket per session.** Parallel
   tickets must not touch the same files.
5. **Retire loudly.** When a ticket completes, check that its `supersedes:`
   entries were deleted or renamed in the same commit.
6. **No orphaned `in_progress`.** A session that finds an `in_progress`
   ticket with no S-entry covering its last commit writes a
   `reconstructed: true` S-entry from `git log`, run files and the ticket,
   **before** any new work. Anything not in those sources is marked unknown,
   not guessed. See `../S-003.md`.
7. **Claim the server.** Before starting any background harness job, and
   again after it ends, update `../INDEX.md` § Resources "server owner".
8. **Run files.**
   - Measurements live in `journal/baseline/runs/` (tracked).
   - Live or scratch run state lives in `/runs/` (ignored).
   - Snapshot bodies in run files are capped. Today's files run 25–525 KB
     each, so a ticket that grows them past ~1 MB trims snapshots first.
9. **Criteria first.** A ticket with no `criteria:` entry is not a ticket.
   Add a criterion to PLAN.md, with the next free ID in its phase, before
   instantiating one.
