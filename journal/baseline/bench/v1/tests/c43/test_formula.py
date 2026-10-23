import pytest

from sheet import ErrorValue, FormulaError, evaluate, parse_formula, references


def calc(source, **cells):
    return evaluate(parse_formula(source), lambda name: cells.get(name))


@pytest.mark.parametrize('source, expected', [
    ('1+2*3', 7),
    ('(1+2)*3', 9),
    ('10-4-3', 3),
    ('-2*3', -6),
    ('- -4 + +1', 5),
])
def test_arithmetic(source, expected):
    assert calc(source) == expected


def test_number_types():
    assert type(calc('2+3')) is int
    assert type(calc('2+3.0')) is float
    assert type(calc('6/3')) is float and calc('6/3') == 2.0
    assert calc('2*3/4') == 1.5 and calc('7/2') == 3.5
    assert calc(' 1.25 * 4 ') == 5.0


def test_references_and_empty_cells():
    assert calc('a1+B2*2', A1=1, B2=4) == 9
    assert calc('A1+5') == 5            # empty cell counts as 0
    assert calc('A1') == 0
    assert calc('A1', A1='hi') == 'hi'  # a lone reference passes text through
    assert calc('(B3)', B3=2.5) == 2.5


def test_text_and_division_errors():
    assert calc('A1+1', A1='hi') == '#ERROR!'
    assert calc('-A1', A1='hi') == '#ERROR!'
    assert calc('1/0') == '#ERROR!'
    assert calc('1/(A1-A1)', A1=3) == '#ERROR!'
    assert isinstance(calc('1/0'), ErrorValue)


def test_errors_propagate_left_first():
    cyc = ErrorValue('#CYCLE!')
    err = ErrorValue('#ERROR!')
    assert calc('A1*2', A1=cyc) == '#CYCLE!'
    assert calc('A1+B1', A1=cyc, B1=err) == '#CYCLE!'
    assert calc('B1+A1', A1=cyc, B1=err) == '#ERROR!'
    assert calc('A1+B1', A1=cyc, B1='text') == '#CYCLE!'
    assert calc('B1+A1', A1=cyc, B1='text') == '#CYCLE!'   # an error beats text on either side


def test_references_set():
    assert references(parse_formula('a1 + B2*a1 - (C10/2)')) == {'A1', 'B2', 'C10'}
    assert references(parse_formula('3*4')) == set()


@pytest.mark.parametrize('source', [
    '', '1+', '(1+2', '2 3', '1.', 'A1 $ 2', 'AA1', 'B1000', 'A01',
])
def test_parse_errors(source):
    with pytest.raises(FormulaError):
        parse_formula(source)
    assert issubclass(FormulaError, ValueError)
