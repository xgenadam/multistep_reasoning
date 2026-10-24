#!/usr/bin/env python3
"""Make the BigCodeBench-Hard JSONL that build.py reads from the pinned parquet.

Usage (from the repo root; `make bench-std` runs it):
  .venv-ifeval/bin/python -I journal/baseline/bench/v1-std/convert_bcb.py [--raw DIR]

If <raw>/BigCodeBench-Hard/v0.1.4.jsonl is already there with its pinned
sha256 there is nothing to do, and any interpreter runs this. Otherwise it
needs pyarrow, which is not part of either venv: without it, it prints the
one-line install and exits 1.

The conversion: the parquet's rows in file order, each written as
`json.dumps(row) + '\\n'` (the stdlib defaults: ASCII escapes, ", " and ": "
separators), with the keys in the parquet schema's order. That is the
format of the JSONL the slice was built from: re-serialising that file's
rows this way reproduces it byte for byte, and the parquet's schema (its
`huggingface` metadata) has the same thirteen columns, in the same order,
with the same types (string, int64 q_idx, float64 score). The output must
match the pinned sha256, or it is refused and nothing is written.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _fetch_module():
    spec = importlib.util.spec_from_file_location('bench_v1_std_fetch', HERE / 'fetch.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def convert(parquet: Path) -> bytes:
    import pyarrow.parquet as pq
    rows = pq.read_table(parquet).to_pylist()
    return ''.join(json.dumps(row) + '\n' for row in rows).encode('utf-8')


def main(argv: list[str] | None = None) -> int:
    fetch = _fetch_module()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--raw', type=Path, default=fetch.DEFAULT_RAW)
    args = ap.parse_args(argv)
    rel, want = fetch.BCB_JSONL
    out, parquet = args.raw / rel, args.raw / fetch.BCB_PARQUET
    try:
        if fetch.present_ok(out, want):
            print(f'ok      {out}')
            return 0
        if not fetch.present_ok(parquet, fetch.RAW_PINS[fetch.BCB_PARQUET]):
            raise fetch.FetchError(f'{parquet} is missing: run fetch.py first')
    except fetch.FetchError as exc:
        print(f'convert_bcb.py: {exc}', file=sys.stderr)
        return 1
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        print('convert_bcb.py: pyarrow is needed to make the JSONL from the parquet. Install it '
              'into the checker venv (make venv-ifeval) and rerun: '
              'uv pip install --python .venv-ifeval/bin/python '
              'pyarrow (without uv: .venv-ifeval/bin/python -m pip install pyarrow)',
              file=sys.stderr)
        return 1
    data = convert(parquet)
    if (got := fetch.sha256_bytes(data)) != want:
        print(f'convert_bcb.py: the converted JSONL has sha256 {got}, pinned {want}; '
              'refusing it (nothing written)', file=sys.stderr)
        return 1
    fetch.write_atomic(out, data)
    print(f'wrote   {out} (sha256 matches the pin)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
