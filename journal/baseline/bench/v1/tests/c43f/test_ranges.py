import pytest

from sheet import ErrorValue, FormulaError, Sheet, evaluate, parse_formula, references


def sheet(**cells):
    s = Sheet()
    for name, raw in cells.items():
        s.set(name, raw)
    return s


def calc(source, **cells):
    return evaluate(parse_formula(source), lambda name: cells.get(name))


GRID = dict(A1='1', B1='2', A2='3', B2='text', A3='', B3='4.5', C1='10')


def test_sum_over_range_skips_text_and_empty():
    s = sheet(**GRID, D1='=SUM(A1:B3)')
    assert s.get('D1') == 10.5
    s.set('B3', '4')
    assert s.get('D1') == 10 and type(s.get('D1')) is int


@pytest.mark.parametrize('formula, expected', [
    ('=AVG(A1:B3)', 2.625),
    ('=MIN(A1:B3)', 1),
    ('=MAX(A1:B3)', 4.5),
    ('=sum(b3:a1)', 10.5),
    ('=SUM(A1:A2, C1, 100)', 114),
    ('=SUM(A1 : B1) * 2 + MAX(C1:C1)', 16),
    ('=SUM(A1:A3, MAX(B1:B3))', 8.5),
])
def test_functions(formula, expected):
    s = sheet(**GRID, E5=formula)
    assert s.get('E5') == expected


def test_avg_is_float_and_sum_int():
    s = sheet(A1='2', A2='4', B1='=AVG(A1:A2)', B2='=SUM(A1:A2)')
    assert type(s.get('B1')) is float and s.get('B1') == 3.0
    assert type(s.get('B2')) is int and s.get('B2') == 6


def test_no_numbers():
    s = sheet(A1='x', B1='=SUM(A1:A3)', B2='=MIN(A1:A3)', B3='=MAX(A1)', B4='=AVG(A1:A3)')
    assert (s.get('B1'), s.get('B2'), s.get('B3')) == (0, 0, 0)
    assert s.get('B4') == '#DIV/0!' and isinstance(s.get('B4'), ErrorValue)


def test_reference_argument_skips_text_but_expression_does_not():
    assert calc('SUM(A1, 2)', A1='hi') == 2
    assert calc('SUM((A1), 2)', A1='hi') == 2
    assert calc('SUM(A1+0, 2)', A1='hi') == '#VALUE!'
    assert calc('MAX(A1*1)', A1='hi') == '#VALUE!'


def test_errors_inside_ranges_propagate_in_order():
    s = sheet(A1='1', B1='=1/0', A2='=Z1+C1', C1='x', D1='=SUM(A1:B2)', D2='=SUM(A2:A2, B1)')
    assert s.get('A2') == '#VALUE!'
    assert s.get('D1') == '#DIV/0!'      # B1 comes before A2 in row-major order
    assert s.get('D2') == '#VALUE!'
    s.set('B1', '5')
    assert s.get('D1') == '#VALUE!'


def test_division_by_zero_and_operand_order():
    assert calc('1/0 + A1', A1='hi') == '#DIV/0!'
    assert calc('A1 + 1/0', A1='hi') == '#DIV/0!'    # an error beats text on either side
    assert calc('A1 + 1', A1='hi') == '#VALUE!'
    assert calc('2/(A1-1)', A1=1) == '#DIV/0!'


def test_ref_errors():
    assert calc('AA1') == '#REF!'
    assert calc('A0 + 1') == '#REF!'
    assert calc('SUM(A1:A1000)') == '#REF!'
    assert calc('SUM(B1000)') == '#REF!'
    assert calc('A01*2') == '#REF!'
    s = sheet(A1='=B1000', B1='=A1+1')
    assert s.get('A1') == '#REF!' and s.get('B1') == '#REF!'
    assert isinstance(s.get('A1'), ErrorValue)


def test_references_expand_ranges():
    assert references(parse_formula('SUM(B2:A1) + c3')) == {'A1', 'B1', 'A2', 'B2', 'C3'}
    assert references(parse_formula('AA1 + SUM(A1:A1000) + B1')) == {'B1'}


@pytest.mark.parametrize('source', [
    'SUMM(A1:A2)', 'SUM', 'SUM + 1', 'SUM()', 'A1:A2', 'SUM(A1:)', 'SUM(A1:A2:A3)',
    'SUM(A1:2)', 'SUM(A1,)',
])
def test_new_parse_errors(source):
    with pytest.raises(FormulaError):
        parse_formula(source)


def test_range_dependencies_drive_recalculation():
    s = sheet(A1='1', A2='2', A3='3', B1='=SUM(A1:A3)', C1='=B1*2', D4='7')
    before = s.evaluations
    assert s.set('A2', '20') == ['B1', 'C1', 'A2']
    assert s.evaluations == before + 2
    assert s.get('C1') == 48
    assert s.set('D4', '8') == ['D4']


def test_range_containing_itself_is_a_cycle():
    s = sheet(A1='1', A2='2', A3='=SUM(A1:A3)', B3='=A3+1')
    assert s.get('A3') == '#CYCLE!' and s.get('B3') == '#CYCLE!'
    s.set('A3', '=SUM(A1:A2)')
    assert s.get('A3') == 3 and s.get('B3') == 4
