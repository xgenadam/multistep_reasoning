# Small models: which gains from the harness? (the user, 2026-10-25, exploratory)

The question: does the harness let a small model, the kind an end user can run, solve what its single call cannot?
v1 is too hard for the 0.6B (smoke tests, `freeform-then-structure.md`), so six more were checked: speed on one
card, then arm a on v1's 70 code prompts. The user's direction: quality first, relaxed token budgets, speed later.

## Models (`~/models/small-*`, referenced by repo and file, not copied)

| Generator | Repo | File |
| --- | --- | --- |
| qwen3-1.7b | Qwen/Qwen3-1.7B-GGUF | Qwen3-1.7B-Q8_0.gguf |
| qwen3.5-2b | unsloth/Qwen3.5-2B-GGUF | Qwen3.5-2B-Q8_0.gguf |
| granite-4.2-3b | ibm-granite/granite-4.2-3b-GGUF | granite-4.2-3b-Q8_0.gguf |
| qwen3.5-4b | unsloth/Qwen3.5-4B-GGUF | Qwen3.5-4B-Q8_0.gguf |
| gemma-4-e4b | unsloth/gemma-4-E4B-it-GGUF | gemma-4-E4B-it-Q8_0.gguf |
| qwen3.5-9b | unsloth/Qwen3.5-9B-GGUF | Qwen3.5-9B-Q6_K.gguf |

## Check (2026-10-25 13:26–16:22Z, commit 2c55da1, llama.cpp server-cuda, 250 W)

Speed: `runs/small-models/speed_llama.py` (the 2026-10-23 method), one card, 8 slots × 16,384; completion tok/s
summed, two runs. Code: arm a, 70 prompts, 8,192 per call + 3 continuations, two cards, 5 × 40,960; run files
`journal/baseline/runs/*_small-a-code_<generator>_<generator>.json` (untracked, like the others).
gemma-4-e4b and qwen3.5-9b ran on cards 2–3 while qwen3.5-4b ran on 0–1 (the user: parallel), so their speed
figures share the host's CPU and PCIe.

| Generator | Prefill | Mixed, 1 / 8 | Decode, 1 / 8 | Mean pass | Any test | All tests | 20–60 % | At the cap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen3-0.6b | 17,700 | 218–239 / 373–402 | 351–412 / 1,195–1,221 | 0.023 | 13 | 0 | 3 | 4 |
| qwen3-1.7b | 11,330 | 155–168 / 311–328 | 228–253 / 903–920 | 0.096 | 28 | 0 | 16 | 5 |
| qwen3.5-2b | 13,600 | 184–192 / 433–437 | 230–232 / 751–756 | 0.060 | 18 | 0 | 6 | 14 |
| granite-4.2-3b | 5,060 | 109–111 / 253–261 | 144–150 / 649–654 | 0.096 | 12 | 1 | 4 | 0 |
| qwen3.5-4b | 6,190 | 92–98 / 224–229 | 120–122 / 448–452 | 0.251 | 37 | 3 | 15 | 0 |
| **gemma-4-e4b** | 6,100 | 86–87 / 234–237 | 105–106 / 430–431 | **0.413** | 46 | 4 | 12 | 0 |
| qwen3.5-9b | 3,560 | 62–66 / 152–153 | 84 / 304–306 | 0.315 | 38 | 5 | 18 | 0 |

For scale: flash-next's arm a on the same prompts is 0.458, at 85–89 mixed tok/s on four cards. Per prompt,
gemma beats it on 17 and trails on 28 of 68.
- Capability jumps between 2B and 4B; below 4B, v1 is mostly out of reach and replies loop to the cap.
- Decode jumps from 5 to 8 concurrent requests on every model (llama.cpp batching); not investigated.
- The 9B's server outlived its container record after `stop qwen3.5-9b` (AGENTS.md's nested-podman case);
  stopped by container id. The relaxed driver now kills by model path if a stop misses.

## Relaxed study (from 2026-10-25 16:25Z, commit 67dee1e, gemma-4-e4b)

Picked by the approved rule: the best single-call pass rate among the fast models. v1's 70 code prompts, every arm
with the same budgets: `--max-tokens 32768 --thinking-allowance 98304`, `options.prompt_token_budget=65536`,
`max_oracle_rounds=16`, `composer_max_retries=5`. Arms: b, b with `options.thinking=on`, a, a1, a2 (budget from
b's file). Two cards, 5 × 131,072 (the model's trained context). Driver `runs/small-models/relaxed.sh`.
Gemma's template takes `enable_thinking` (default off); checked live: thinking on gives separate reasoning
(c06: 3,646 reasoning characters, 4,743 of answer). Readout: per prompt, what b solves that a and a1 do not.
**The user (2026-10-25): gemma-4-e4b is the small model to work with; qwen3.5-4b and qwen3.5-9b are dropped, gemma being both more capable and faster.**

## Decisions and why (in order; D-029 and D-030 hold the load-bearing ones)

- 13:20Z: six models downloaded (Qwen3-1.7B, Qwen3.5-2B/4B/9B, granite-4.2-3b, gemma-4-E4B), from the publishers'
  repos or unsloth, text weights only. Why: a spread over 1.7–9B and four families; Q8_0 except the 9B (Q6_K) to keep
  quantisation loss out of the comparison.
- Speed on one card, arm a on two. Why: one card is what an end user has; the code run's context (5 × 40,960) needs
  more memory than one card for the larger KV caches, and its timing is not a criterion (D-025).
- 15:17Z: gemma and the 9B moved to cards 2–3 in parallel (the user: yes). Why: ~50 min sooner. Cost: their speed
  figures share CPU and PCIe with the other run.
- 16:25Z: gemma picked by the approved rule (best single-call rate among the fast models); D-029.
- 17:45Z: arm a moved ahead of b-think (the agent). Why: the user asked how soon the harness's effectiveness is known;
  b against a at the same budgets needs a, a 20-minute arm, instead of waiting ~3 h behind b-think. No arm changed.
- 17:56Z: b-think and a2 held after b (the agent). Why: b failed 28 of 70 turns on the keep rule, and b-think and a2
  (whose budget comes from b's tokens) would inherit it, wasting ~4 h. a and a1 (single calls) are unaffected and run.
- 18:15Z: the keep rule becomes a setting (D-030, the user: "sounds sensible").
- 18:45Z: D-030 built (`options.keep_rule`, `options.compose_fallback`). Clarification of D-030: the fallback is its
  own option, off by default, rather than on "under any rule", because the harness's default behaviour is frozen until
  Q-02's verdict; the default compose prompt is byte-identical to before (checked). Under `names` / `off` the
  prompt's rule 1 allows merging, deduplication and refactoring instead of "Do not re-type the sub-task result".
- gemma's b runs, after a1: `names` + fallback, `off` + fallback, and `verbatim` + fallback (the agent). Why the
  third: the first b run had no fallback, so without it a gain could not be split between the rule and the fallback.
- 21:22Z: `b-off` failed at startup (the agent's bug): `--set options.keep_rule=off` reaches the config as the YAML
  boolean `false`. Re-run as `--set 'options.keep_rule="off"'` by a new driver (`keep2.sh`, chained after keep.sh by
  `chain_keep2.sh`) rather than by editing the running one. Rejected: mapping `false` to `off` in the config, which
  would change the frozen harness code under a running study for a quoting slip.
- 21:30Z, b-names partial (48 of 54 done prompts scored): 0.312 against a's 0.474 on the same prompts, 0.055 for
  b-verbatim. The scorer's extraction failed on 11 of them (b 0.042, a 0.243 there), but on the 37 clean ones b still
  trails (0.392 against 0.542), so the gap is not only extraction.
- 22:30Z: a trace viewer (the user: "a visualisation tool for the flow of the harness and its prompts ... see where it
  broke"; suspects: sub-tasks get too little information, the composer does not tie it together, or the validity
  criteria are wrong). Runs recorded call counts but no call text and no composer attempts, so the agent added:
  - `arms.py run --trace-calls`: every call's messages, request fields and reply under the turn's intermediates
    (`calls/`), through `MeasuredCompletions.trace`. Opt-in because the text is large (compose prompts run to tens
    of K tokens, about 30 calls per turn); a failing trace never changes a call.
  - The orchestrator's `document` step record gains the sub-task's result and that step's composer attempts, and a
    `compose_failed` record precedes a failed turn. Logging only; no harness behaviour changes.
  - `journal/baseline/trace_view.py` (+ `trace_view.html`): a static page per run under `runs/trace-view/` (one data
    file per turn, loaded on demand, so a 13 MB run opens from file://), with a per-turn "where it went wrong" list.
    Rejected: one self-contained HTML (too large once calls are traced) and a published artifact (the data stays local).
  - Next: re-run about 10 prompts where b lost to a with `--trace-calls` after the running b runs finish.
