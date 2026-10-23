"""A tiny shell over FileSystem: run scripts of commands."""

from __future__ import annotations

import shlex
import sys

from .fs import FileSystem, FSError


class _Usage(Exception):
    pass


class _Unknown(Exception):
    pass


def _flag(args: list[str], flag: str) -> tuple[bool, list[str]]:
    on = bool(args) and args[0] == flag
    rest = args[1:] if on else args
    if any(a.startswith('-') for a in rest):
        raise _Usage()
    return on, rest


def _count(args, low, high=None):
    if len(args) < low or (high is not None and len(args) > high):
        raise _Usage()
    if any(a.startswith('-') for a in args):
        raise _Usage()


class Shell:
    def __init__(self, fs: FileSystem | None = None):
        self.fs = fs if fs is not None else FileSystem()

    def _exec(self, cmd: str, args: list[str]) -> str:
        fs = self.fs
        if cmd == 'pwd':
            _count(args, 0, 0)
            return fs.pwd() + '\n'
        if cmd == 'cd':
            _count(args, 1, 1)
            fs.cd(args[0])
            return ''
        if cmd == 'mkdir':
            parents, paths = _flag(args, '-p')
            _count(paths, 1)
            for p in paths:
                fs.mkdir(p, parents=parents)
            return ''
        if cmd == 'ls':
            _count(args, 0, 1)
            return ''.join(e + '\n' for e in fs.ls(*args))
        if cmd == 'rm':
            recursive, paths = _flag(args, '-r')
            _count(paths, 1)
            for p in paths:
                fs.rm(p, recursive=recursive)
            return ''
        if cmd == 'mv':
            _count(args, 2, 2)
            fs.mv(args[0], args[1])
            return ''
        if cmd in ('write', 'append'):
            if not args or args[0].startswith('-'):
                raise _Usage()
            fs.write(args[0], ' '.join(args[1:]) + '\n', append=cmd == 'append')
            return ''
        if cmd == 'cat':
            _count(args, 1)
            return ''.join(fs.read(p) for p in args)
        if cmd == 'find':
            path, pattern = '.', '*'
            rest = list(args)
            if rest and rest[0] != '-name':
                path = rest.pop(0)
                if path.startswith('-'):
                    raise _Usage()
            if rest:
                if len(rest) != 2 or rest[0] != '-name':
                    raise _Usage()
                pattern = rest[1]
            return ''.join(p + '\n' for p in fs.find(path, pattern))
        raise _Unknown(cmd)

    def run(self, script: str) -> tuple[str, int]:
        out: list[str] = []
        status = 0
        for number, raw in enumerate(script.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            cmd = line.split()[0]
            try:
                words = shlex.split(line)
                out.append(self._exec(words[0], words[1:]))
            except FSError as e:
                out.append(f'line {number}: {cmd}: {type(e).__name__}: {e}\n')
                status = status or 1
            except _Unknown:
                out.append(f'line {number}: {cmd}: unknown command\n')
                return ''.join(out), 2
            except (_Usage, ValueError):
                out.append(f'line {number}: {cmd}: usage\n')
                return ''.join(out), 2
        return ''.join(out), status


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print('error: usage: python -m vfs.shell SCRIPT', file=sys.stderr)
        return 2
    try:
        with open(args[0], encoding='utf-8') as f:
            script = f.read()
    except OSError as e:
        print(f'error: cannot read {args[0]}: {e}', file=sys.stderr)
        return 2
    output, status = Shell().run(script)
    sys.stdout.write(output)
    return status


if __name__ == '__main__':
    sys.exit(main())
