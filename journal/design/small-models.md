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
Next candidate: qwen3.5-4b (lower single-call rate, so more room for a gain).
