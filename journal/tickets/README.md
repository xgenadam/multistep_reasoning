# Tickets

One markdown file per work item: `<id>.md`. No tracker server — see
`../PLAN.md` → *Process: journal, tickets, wrap-ups* for rationale and
graduation triggers.

## ID scheme

`<phase>-<NN>` where phase ∈ {`0`, `A`, `B`, `C`, `H`, `P`, `T`} and `NN` is
zero-padded, allocated in order within the phase (first ticket of Phase A is
`A-01`).

These are **ticket IDs**. Pass-criterion IDs (`P0-3`, `A-1`, `P-P1`, …) are
single-digit, defined in `../PLAN.md`, and referenced from the `criteria:`
field below. If a string looks like a criterion, treat it as one.

## File format

```markdown
---
id: A-01
title: <short imperative title>
phase: A
status: open          # open | in_progress | blocked | done | dropped
criteria: [A-1, A-5]  # pass-criterion IDs from PLAN.md; empty list = not a ticket
started:              # YYYY-MM-DD, set when work begins
done:                 # YYYY-MM-DD, set when status -> done
blocked_on:           # ticket ID(s) or one-line condition; only while blocked
supersedes:           # stale state docs retired by this work; [] if none
---

## Scope

<!-- Copied/condensed from PLAN.md at instantiation. This is the contract. -->

## Notes

<!-- Session work-notes: what was tried, dead ends, model failures. -->

## Measurements

<!-- Final numbers against each criterion in `criteria:`. Pass/fail per
     criterion. This block is what the AAR synthesizes from. -->
```

## Rules

1. **Status changes are commits.** A `status:` flip with no code/context
   change in the same or an adjacent commit is noise; commit messages
   referencing ticket IDs are the audit trail.
2. **A ticket is done only when its `criteria:` all pass** (or an S-entry
   records an explicit, decided waiver). "Code written" is `in_progress` at
   best.
3. **One active ticket per executor at a time** is a norm, not a law;
   parallel tickets must not touch the same files (that rule exists to keep
   Phase P and Phase B disjoint).
4. **Retire loudly.** When a ticket completes, check its `supersedes:`
   entries actually got deleted/renamed in the same commit.