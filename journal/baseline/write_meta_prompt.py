"""Write the frozen planner instructions for `decomposer: meta` (journal/design/meta-prompts.md).

    LLM_MODEL=gemma-4-e4b .venv/bin/python journal/baseline/write_meta_prompt.py \
        --base-url http://localhost:8100/v1 --writer gemma-4-e4b

writes journal/design/meta-prompts/decompose.<writer>.txt (the instructions, used
as written) and a .json beside it (writer, time, the meta prompt's sha256, the
attempt log). Run it once per writer; the files are committed and diffable, and
a run uses one with --set components.decomposer=meta
--set options.meta_prompt_file=<the .txt>.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from reasoning_sub_agents.llama_utils import create_llama_client  # noqa: E402
from reasoning_sub_agents.task_decomposition.meta_decomposition import (  # noqa: E402
    meta_prompt,
    write_instructions,
)

OUT_DIR = REPO_ROOT / 'journal' / 'design' / 'meta-prompts'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base-url', required=True)
    ap.add_argument('--writer', required=True, help='a short name for the writing model, used in the file name')
    ap.add_argument('--out-dir', default=str(OUT_DIR))
    args = ap.parse_args(argv)
    client = create_llama_client(base_url=args.base_url)
    text, log = write_instructions(client, None)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f'decompose.{args.writer}.txt'
    path.write_text(text + '\n')
    path.with_suffix('.json').write_text(json.dumps({
        'writer': args.writer, 'model': os.environ.get('LLM_MODEL', 'llama'), 'base_url': args.base_url,
        'written_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'meta_prompt_sha256': hashlib.sha256(meta_prompt(None).encode()).hexdigest(),
        'instructions_sha256': hashlib.sha256(text.encode()).hexdigest(), 'attempts': log}, indent=1) + '\n')
    print(f'wrote {path} ({len(text)} characters)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
