# Labelling app (Q-06, criterion Q-11)

You label pairs of answers side by side. Your labels are the standard the
judges are scored against (Q-1's real pairs, R1–R5).

## Run it on the host

```bash
cd /mnt/myraid/workspace/my_projects/multi_step_reasoning_grok
python3 -c "import yaml" || python3 -m pip install --user pyyaml
python3 labelling_app/server.py
# open http://127.0.0.1:8766/
```

With the assistant, load Qwen3.8-27B in text-generation-webui on `:5000`
first. Don't use flash-next or any Q-04 judge candidate: the labels score
those models.

```bash
python3 labelling_app/server.py \
  --assist-base-url http://127.0.0.1:5000/v1 \
  --assist-model Qwen3.8-27B-UD-Q6_K.gguf
```

Any OpenAI-compatible endpoint works. llama-server ignores the model name,
while vLLM needs the exact one.

## Or with the host's Docker

```bash
cd /mnt/myraid/workspace/my_projects/multi_step_reasoning_grok/labelling_app
UID=$(id -u) GID=$(id -g) docker compose up    # labels.yaml stays owned by you
# with the assistant:
UID=$(id -u) GID=$(id -g) ASSIST_BASE_URL=http://host.docker.internal:5000/v1 \
  ASSIST_MODEL=Qwen3.8-27B-UD-Q6_K.gguf docker compose up
```

This has to be the host's Docker. In the agent container, `docker` is a
nested podman whose published ports stay inside `claude-box`.

## What it does

- It shows the task, then Left and Right. Which candidate sits on which
  side is shuffled per pair and recorded. You never see the run, the source
  or any judge's verdict.
- Pick Left, Tie or Right (keys 1, 2, 3), add a note if you like, then
  Save & next (Ctrl+Enter). Saving a pair again replaces its label, and
  the old label is kept in `history`.
- The assistant answers factual questions, such as whether a requirement
  is met and where. It will not say which side is better. Your questions
  are saved with the label.
- Labels go to `journal/baseline/bench/validation/labels.yaml`. Commit that
  file, or ask the agent to: `quality.py` reads it as the pairs' `expected`,
  and `quality.py report <verdict file> --pairs <manifest>` re-scores
  existing judge runs against it.

Other manifests: `--pairs PATH` (labels go beside it); `--kind` picks pair
kinds (default `real`, only pairs with no `expected`).
