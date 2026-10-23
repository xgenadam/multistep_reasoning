import argparse
import re
import sys
from collections import Counter

WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)*")


def positive_int(text):
    try:
        n = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f'not an integer: {text!r}') from None
    if n < 1:
        raise argparse.ArgumentTypeError(f'must be at least 1: {text!r}')
    return n


def read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        print(f'wordfreq: cannot read {path}', file=sys.stderr)
        sys.exit(1)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='wordfreq', description='Count word frequencies.')
    parser.add_argument('path')
    parser.add_argument('--top', type=positive_int)
    parser.add_argument('--stopwords')
    args = parser.parse_args(argv)

    stop = set()
    if args.stopwords is not None:
        for line in read(args.stopwords).splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                stop.add(line.casefold())
    text = read(args.path)
    counts = Counter(w.casefold() for w in WORD.findall(text))
    for w in stop:
        counts.pop(w, None)
    rows = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    if args.top is not None:
        rows = rows[:args.top]
    for word, n in rows:
        print(f'{n}\t{word}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
