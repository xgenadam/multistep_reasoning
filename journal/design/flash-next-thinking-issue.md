# Issue brief: flash-next, thinking on, code prompts rarely finish within 32,768 tokens

For the user's flash-next vLLM lane (`~/workspace/AI/Qwen38-Flash-Next-4x3090`).
Written 2026-10-25 by the coordinator (S-022) from Q-02 stage 1. The question:
is this the model, or something in the lane's serving config?

## Symptom

Q-02 arm (a′) `a1`: one chat call per prompt, thinking on
(`chat_template_kwargs: {enable_thinking: true}`), `max_tokens` 32,768, no
temperature sent (so the model's `generation_config.json` applies:
temperature 1.0, top_k 20, top_p 0.95). Run file
`journal/baseline/runs/20261024T204458Z_q02-s1-a1_flash-next.json`
(commit `369419e`, `--jobs 6`).

| Domain | Done | No answer | Of those, hit 32,768 | Of those, stopped with empty content |
| --- | --- | --- | --- | --- |
| code | 70 | 53 | 50 | 3 (c07, c10, c26) |
| report | 54 so far | 2 | — | — |

The 17 code prompts that finished used a median of 24,115 reasoning tokens
(range 3,305–32,235), so the whole distribution sits near or above the
allowance. Report prompts typically finish with 5–19 K reasoning tokens.

## What was ruled out (one full probe, c08)

`runs/flash-next-thinking-issue/a1probe_c08.json` (git-ignored; the script
beside it re-runs it): `finish_reason: length` at 32,768 completion tokens,
115,288 reasoning characters, empty content.
- **Not a repetition loop:** the distinct word-trigram ratio is 0.97 / 0.96
  / 0.95 at the start, middle and end; 1,064 of 1,309 non-blank lines are
  unique.
- **Not the reasoning parser:** no `</think>` inside the reasoning text.
- **What it does:** it plans the spec, checks edge cases (node-semver caret
  rules mid-way), and writes and re-writes **full code drafts inside its
  reasoning** (48 fence markers), still revising at 32,768 tokens (whether
  `bool` counts as an `int`). Coherent throughout.

## Lane config in force (from the vLLM boot log, 2026-10-24T20:15Z)

vLLM `v0.28.1rc1.dev388+g8a728663c` (image `qwen38fn-vllm:8a728663`),
`quantization: gptq_marlin` (w4a16), TP 4 with expert parallel,
**`kv_cache_dtype: fp8_e5m2`**, `mamba_ssm_cache_dtype: bfloat16`,
`mamba_cache_mode: align`, **MTP speculative decoding, 3 tokens**
(`/models/qwen38fn/runtime/mtp-int4-g32`, `disable_eagle_block_drop`),
prefix caching on (disabled in effect: the boot log says MTP plus Mamba
groups prevent reuse), `max_num_batched_tokens` 2,048, `max_num_seqs` 6,
`reasoning_parser: qwen3`, CUDA graphs `FULL_DECODE_ONLY`, compile mode NONE,
the lane's overlays (`ple`, `qsa_e5m2`, `model_state`).

Suspects for longer-than-necessary deliberation without looping, in order:
1. fp8_e5m2 KV (2-bit mantissa) over 20–30 K tokens of context;
2. MTP with 3 draft tokens (acceptance length ≈ 2.2–2.4 in the log);
3. the w4a16 quantisation of the weights (and int4 MTP head);
4. none of these: the model's own behaviour at these sampling settings.

## The test that settles it

The same code prompts, thinking on, `max_tokens` 32,768, no temperature,
each run twice per config, recording finish reason, reasoning tokens and
whether an answer arrived:
- prompts: c02, c08, c12 (empty here), c01, c06 (finished here), from
  `journal/baseline/bench/v1/prompts/`;
- configs: (A) the lane as above; (B) KV bf16/auto, MTP on; (C) KV fp8,
  MTP off; (D) KV bf16, MTP off.

`runs/flash-next-thinking-issue/a1probe.py PROMPT.md OUT.json` sends one
such request to `http://localhost:8090/v1` (`.venv/bin/python -I`).

If B, C or D finish clearly more often or think clearly less than A, the
lane is the cause: fix it, then Q-02 re-runs a1 on flash-next. If not, a1's
code losses stand as a result: reasoning longer than the pre-registered
allowance.
