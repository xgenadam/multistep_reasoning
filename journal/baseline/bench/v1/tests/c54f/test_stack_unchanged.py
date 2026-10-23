import pytest

from stack import (ControlError, DivisionByZero, Interpreter, StackError, StackUnderflow,
                   StepLimitExceeded, Token, UnknownWord, evaluate, tokenize)


def fails(exc_type, source, interp=None):
    interp = interp or Interpreter()
    with pytest.raises(exc_type) as exc:
        interp.run(source)
    assert isinstance(exc.value, StackError)
    return exc.value


# ---------------------------------------------------------------- lexer

def test_tokenize_numbers_words_positions():
    toks = tokenize('1 -23 DUP\n  - 3x # comment here\n--4 +')
    assert toks == [Token('number', 1, 1, 1), Token('number', -23, 1, 3),
                    Token('word', 'dup', 1, 7), Token('word', '-', 2, 3),
                    Token('word', '3x', 2, 5), Token('word', '--4', 3, 1),
                    Token('word', '+', 3, 5)]


def test_tokenize_comment_only_at_token_start():
    assert [t.value for t in tokenize('a#b 1 #c 2\n3')] == ['a#b', 1, 3]


# ---------------------------------------------------------------- words

@pytest.mark.parametrize('source, expected', [
    ('2 3 + 10 4 - 6 7 *', [5, 6, 42]),
    ('7 2 / -7 2 / 7 -2 mod -7 2 mod', [3, -4, -1, 1]),
    ('5 negate -9 abs', [-5, 9]),
    ('1 dup 2 3 swap 4 drop', [1, 1, 3, 2]),
    ('1 2 over 7 8 9 rot', [1, 2, 1, 8, 9, 7]),
    ('3 3 = 3 4 = 3 4 <> 2 9 < 2 9 > 0 0= 5 0=', [-1, 0, -1, -1, 0, -1, 0]),
    ('12 10 and 12 10 or', [8, 14]),
    ('depth 7 8 depth', [0, 7, 8, 3]),
    ('1 2 DUP Swap', [1, 2, 2]),
])
def test_words(source, expected):
    assert evaluate(source) == expected


def test_dot_appends_output_and_state_persists():
    interp = Interpreter()
    interp.run('1 2 3 . .')
    interp.run('10 + .')
    assert interp.output == [3, 2, 11]
    assert interp.stack == []


# ---------------------------------------------------------------- control

def test_if_then_and_else():
    assert evaluate('1 if 10 then 0 if 20 then') == [10]
    assert evaluate('-1 if 1 else 2 then 0 if 3 else 4 then 7 if 5 then') == [1, 4, 5]


def test_nested_if():
    src = '{} if 1 if 11 else 12 then else 0 if 21 else 22 then then'
    assert evaluate(src.format(1)) == [11]
    assert evaluate(src.format(0)) == [22]


def test_begin_until_runs_body_at_least_once():
    assert evaluate('0 begin 1 + dup 5 = until') == [5]
    assert evaluate('7 begin 1 until') == [7]


def test_sum_example_and_nested_loop():
    assert evaluate('10 0 begin over + swap 1 - swap over 0= until swap drop') == [55]
    # count inner iterations of a 3 x 4 nested loop
    src = ('0 3 begin 4 begin rot 1 + rot rot 1 - dup 0= until drop 1 - dup 0= until drop')
    assert evaluate(src) == [12]


# ---------------------------------------------------------------- errors

@pytest.mark.parametrize('source, word', [
    ('dup', 'dup'), ('1 +', '+'), ('1 2 rot', 'rot'), ('if 1 then', 'if'),
    ('begin until', 'until'), ('.', '.'),
])
def test_underflow(source, word):
    assert fails(StackUnderflow, source).word == word


def test_underflow_leaves_stack_unchanged_but_keeps_earlier_work():
    interp = Interpreter()
    e = fails(StackUnderflow, '5 6 . 9 rot', interp)
    assert (e.line, e.col) == (1, 9)
    interp2 = Interpreter()
    fails(StackUnderflow, '4 rot', interp2)
    assert interp2.stack == [4]
    assert interp.stack == [5, 9] and interp.output == [6]


def test_unknown_word_raised_when_executed():
    interp = Interpreter()
    e = fails(UnknownWord, '1 2\n  frob 3', interp)
    assert (e.word, e.line, e.col) == ('frob', 2, 3)
    assert interp.stack == [1, 2]
    assert evaluate('0 if frob then') == []


def test_division_by_zero():
    assert fails(DivisionByZero, '1 0 /').word == '/'
    assert fails(DivisionByZero, '1 0 mod').word == 'mod'


@pytest.mark.parametrize('source, word, col', [
    ('1 then', 'then', 3),
    ('else', 'else', 1),
    ('1 if 2 else 3 else 4 then', 'else', 15),
    ('until', 'until', 1),
    ('1 if begin then until', 'then', 12),
    ('1 if 2', 'if', 3),
    ('begin 1 if 2 then', 'begin', 1),
    ('if begin if', 'if', 10),
    ('1 then 2 if', 'then', 3),
])
def test_control_errors(source, word, col):
    e = fails(ControlError, source)
    assert (e.word, e.col) == (word, col)


def test_control_error_runs_nothing():
    interp = Interpreter()
    fails(ControlError, '1 2 . 3 then', interp)
    assert interp.stack == [] and interp.output == []


def test_step_limit():
    interp = Interpreter(max_steps=100)
    e = fails(StepLimitExceeded, 'begin 1 0 until', interp)
    assert (e.word, e.col) == ('0', 9)
    assert interp.stack == [1] * 34


def test_step_limit_exact_and_per_run():
    interp = Interpreter(max_steps=3)
    interp.run('1 2 +')
    interp.run('dup if then')     # dup, if = 2 steps
    assert interp.stack == [3]
    fails(StepLimitExceeded, '1 1 1 1', interp)
    assert interp.stack == [3, 1, 1, 1]
