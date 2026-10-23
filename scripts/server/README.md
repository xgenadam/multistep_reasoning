# Server launchers

These start the host-side Devstral-123B llama-server on port 8000: the big model and the future judge (Phase Q). They run on the host, not in the container.
The container-side generator (Qwen-27B) is a separate server at `http://host.containers.internal:5000/v1`; point `LLM_BASE_URL` at it.

## Generator launcher (Q-02)

`generator-server.sh` serves one Q-02 generator at a time on this box's four 3090s. The judge stays on `:8092`.

| Generator | Engine | Base URL | Served name (send it as `model`) |
| --- | --- | --- | --- |
| `flash-next` | vLLM, the user's prefix lane (prefix caching on) | `http://localhost:8090/v1` | `qwen3.8-flash-next` |
| `qwen3.8-27b` | llama.cpp, `Qwen3.8-27B-UD-Q6_K.gguf` (dense) | `http://localhost:8093/v1` | `qwen3.8-27b` |
| `qwen3.6-35b-a3b` | llama.cpp, `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` (MoE, 3B active) | `http://localhost:8094/v1` | `qwen3.6-35b-a3b` |

```bash
scripts/server/generator-server.sh qwen3.8-27b             # boot; prints READY after <n>s, VRAM per card, /v1/models
DRY_RUN=1 scripts/server/generator-server.sh flash-next    # print the resolved docker run; start nothing
scripts/server/generator-server.sh stop                    # stop gen_llama / vllm_qwen38fn_3090, wait for < 1 GB per card
```

- **llama.cpp path.** It calls `judge-llama-server.sh` with `NAME=gen_llama`. It uses 5 slots × 65,536 tokens
  (`--parallel 5 --ctx-size 327680`, split per slot) and f16 KV with layer split. `--reasoning-format deepseek`
  puts thinking in `reasoning_content`, and the server-side default is `enable_thinking: false`, as on the vLLM lane.
  Each request's `chat_template_kwargs.enable_thinking` overrides that default.
- **Why 5 × 64K.** The campaign runs 3 jobs at once, and the pipeline makes no concurrent calls inside a turn. A
  single-call arm with 3 "continue" turns at `max_tokens` 8192 reaches about 40K tokens.
- **Why f16 KV and layer split.** Both models are DeltaNet/attention hybrids, so the KV cache is small: 21 GiB
  (27B) and 6 GiB (35B-A3B) at 327,680 tokens. This build cannot row-split the qwen35 architecture.
- **flash-next path.** It runs the lane unmodified with `PORT=8090`, `NAME=vllm_qwen38fn_3090` and
  `GPU_ARGS=--device nvidia.com/gpu=all`. The flash-next judge (tuned lane) uses the same container name, so
  `stop` stops whichever of the two is up.
- **Refusals.** It refuses to boot while `~/models/.gpu-halt` exists, when any card has > 1 GB in use, or when the
  port already answers.
- **Measured 2026-10-23 (llama.cpp c7fc50941), single stream, thinking off:**
  - `qwen3.8-27b`: ready in 10 s from the page cache, about 10.6–11.6 GiB per card, 35 tok/s decode.
  - `qwen3.6-35b-a3b`: ready in 26 s, about 7.2–7.7 GiB per card, 142 tok/s decode.
  - `usage` returns prompt, completion and total tokens plus `prompt_tokens_details.cached_tokens`. It has no
    `completion_tokens_details.reasoning_tokens`, so reasoning tokens are counted inside `completion_tokens`.
