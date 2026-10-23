import io
import subprocess
import sys
from pathlib import Path

import pytest

from stack import (CallDepthExceeded, ControlError, Interpreter, StackError, StackUnderflow,
                   StepLimitExceeded, UnknownWord, evaluate)
from stack.interp import main, repl

HERE = Path(__file__).resolve().parent


def fails(exc_type, source, interp=None):
    interp = interp or Interpreter()
    with pytest.raises(exc_type) as exc:
        interp.run(source)
    assert isinstance(exc.value, StackError)
    return exc.value


# ---------------------------------------------------------------- definitions

def test_simple_definition_case_insensitive():
    assert evaluate(': SQUARE dup * ; 7 square 3 Square') == [49, 9]


def test_definitions_persist_and_defined_list():
    interp = Interpreter()
    interp.run(': inc 1 + ; : dbl 2 * ;')
    interp.run('5 inc dbl')
    assert interp.stack == [12]
    assert interp.defined() == ['dbl', 'inc']


def test_recursion_factorial():
    fact = ': fact dup 1 > if dup 1 - fact * then ; '
    assert evaluate(fact + '5 fact 1 fact 10 fact') == [120, 1, 3628800]


def test_late_binding_redefinition():
    interp = Interpreter()
    interp.run(': two 2 ; : four two two + ; four')
    interp.run(': two 20 ; four')
    assert interp.stack == [4, 40]


def test_definition_takes_effect_in_order():
    e = fails(UnknownWord, 'foo : foo 1 ;')
    assert (e.word, e.col) == ('foo', 1)


def test_body_with_control_structures():
    countdown = ': countdown begin dup . 1 - dup 0= until drop ; '
    interp = Interpreter()
    interp.run(countdown + '3 countdown')
    assert interp.output == [3, 2, 1] and interp.stack == []
    assert evaluate(': sign dup 0 < if drop -1 else 0 > if 1 else 0 then then ; '
                    '-5 sign 0 sign 8 sign') == [-1, 0, 1]


def test_error_inside_body_reported_at_inner_token():
    e = fails(StackUnderflow, ': bad\n  drop drop ;\n1 bad')
    assert (e.word, e.line, e.col) == ('drop', 2, 8)


@pytest.mark.parametrize('source, word, col', [
    ('1 ;', ';', 3),
    (': f 1 if 2 ;', ';', 12),
    ('1 if : f 1 ; then', ':', 6),
    ('begin : f ; 1 until', ':', 7),
    (': f : g ; ;', ':', 5),
    (': f 1', ':', 1),
    (': f 1 if', 'if', 7),
    (':', ':', 1),
    (': dup 1 ;', 'dup', 3),
    (': if 1 ;', 'if', 3),
    (': 5 1 ;', '5', 3),
    (': ; 1', ';', 3),
])
def test_definition_control_errors(source, word, col):
    e = fails(ControlError, source)
    assert (e.word, e.col) == (word, col)


def test_control_error_defines_nothing():
    interp = Interpreter()
    fails(ControlError, ': ok 1 ; 1 then', interp)
    assert interp.defined() == [] and interp.stack == []


# ---------------------------------------------------------------- limits

def test_call_depth_limit():
    interp = Interpreter(max_depth=10)
    interp.run(': down dup if 1 - down then ;')
    interp.run('9 down')            # 10 nested calls
    assert interp.stack == [0]
    interp.stack.clear()
    e = fails(CallDepthExceeded, '10 down', interp)
    assert e.word == 'down' and (e.line, e.col) == (1, 19)
    assert interp.stack == [0]


def test_call_depth_resets_between_runs():
    interp = Interpreter(max_depth=3)
    interp.run(': loop loop ;')
    fails(CallDepthExceeded, 'loop', interp)
    interp.run(': three 3 ; three')
    assert interp.stack == [3]


def test_step_limit_inside_word():
    interp = Interpreter(max_steps=5)
    interp.run(': two 1 1 ;')
    e = fails(StepLimitExceeded, 'two two', interp)   # calls and pushes: 6 steps
    assert (e.word, e.line, e.col) == ('1', 1, 9)
    assert interp.stack == [1, 1, 1]


# ---------------------------------------------------------------- REPL

def test_repl_lines():
    lines = io.StringIO(': sq dup * ;\n3 sq .\n1 2 . .\nnope\n\n4 sq\ndrop drop .\n')
    out = io.StringIO()
    assert repl(lines, out) == 0
    assert out.getvalue() == ('ok\n9 ok\n2 1 ok\nerror: UnknownWord: nope\nok\nok\n'
                              'error: StackUnderflow: drop\n')


def test_repl_shares_interpreter():
    interp = Interpreter()
    out = io.StringIO()
    repl(io.StringIO('1 2\n: x + ;\n'), out, interp)
    repl(io.StringIO('x .\n'), out, interp)
    assert out.getvalue() == 'ok\nok\n3 ok\n'
    assert interp.defined() == ['x']


def run_cli(*args, stdin=''):
    return subprocess.run([sys.executable, '-m', 'stack.interp', *args], cwd=HERE, input=stdin,
                          capture_output=True, text=True, timeout=30)


def test_cli_repl_on_stdin():
    r = run_cli(stdin=': cube dup dup * * ;\n2 cube .\nswap\n')
    assert r.returncode == 0
    assert r.stdout == 'ok\n8 ok\nerror: StackUnderflow: swap\n'


def test_cli_file(tmp_path):
    good = tmp_path / 'good.fs'
    good.write_text(': sq dup * ;\n4 sq . 5 sq .\n')
    r = run_cli(str(good))
    assert (r.returncode, r.stdout) == (0, '16 25\n')
    bad = tmp_path / 'bad.fs'
    bad.write_text('1 . 2 .\n  zap\n')
    r = run_cli(str(bad))
    assert r.returncode == 1
    assert r.stdout == '1 2\n'
    assert 'error: UnknownWord: zap at line 2, column 3' in r.stderr.splitlines()
    r = run_cli(str(tmp_path / 'missing.fs'))
    assert r.returncode == 2
    assert any(line.startswith('error:') for line in r.stderr.splitlines())


def test_main_function_with_file(tmp_path, capsys):
    path = tmp_path / 'p.fs'
    path.write_text('6 7 * .')
    assert main([str(path)]) == 0
    assert capsys.readouterr().out == '42\n'
