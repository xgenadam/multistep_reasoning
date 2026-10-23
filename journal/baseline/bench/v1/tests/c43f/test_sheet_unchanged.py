# Copied from c43. Adapted where c43f changes behaviour: text in arithmetic gives #VALUE!
# instead of #ERROR!, and `=AA1` now parses (it evaluates to #REF!), so the unchanged-sheet
# check uses another malformed formula.
import pytest

from sheet import ErrorValue, FormulaError, Sheet


def sheet(**cells):
    s = Sheet()
    for name, raw in cells.items():
        s.set(name, raw)
    return s


def test_constants_and_text():
    s = sheet(A1='5', A2=' -2.5 ', A3='hello world', A4='  pad ', A5='1e3', A6='3.')
    assert s.get('A1') == 5 and type(s.get('A1')) is int
    assert s.get('A2') == -2.5
    assert s.get('A3') == 'hello world'
    assert s.get('A4') == '  pad '
    assert s.get('A5') == '1e3' and s.get('A6') == '3.'
    assert s.raw('A2') == ' -2.5 '
    assert s.get('B1') is None and s.raw('B1') == ''
    with pytest.raises(TypeError):
        s.set('A1', 5)


def test_names_are_case_insensitive():
    s = sheet(b2='4', C2='=b2*2')
    assert s.get('B2') == 4 and s.get('c2') == 8
    assert s.cells() == ['B2', 'C2']
    s = sheet(C2='1', A10='2', B1='3', A2='4')
    assert s.cells() == ['B1', 'A2', 'C2', 'A10']


@pytest.mark.parametrize('name', ['AA1', 'A0', 'A1000', '1A'])
def test_bad_names_raise_value_error(name):
    s = Sheet()
    with pytest.raises(ValueError):
        s.set(name, '1')
    with pytest.raises(ValueError):
        s.get(name)


def test_formulas_follow_their_inputs():
    s = sheet(A1='2', A2='3', A3='=A1*A2', A4='=A3+A1')
    assert s.get('A3') == 6 and s.get('A4') == 8
    s.set('A1', '10')
    assert s.get('A3') == 30 and s.get('A4') == 40
    assert s.raw('A3') == '=A1*A2'
    s = sheet(C1='=A1+B1')              # inputs that do not exist yet
    assert s.get('C1') == 0
    s.set('B1', '4')
    assert s.get('C1') == 4


def test_set_returns_affected_cells_row_major():
    s = sheet(A1='1', B2='=A1', A3='=B2+1', C1='=A1*2', Z9='=7')
    assert s.set('A1', '5') == ['A1', 'C1', 'B2', 'A3']
    assert s.set('Z9', '8') == ['Z9']
    assert s.set('B2', '=Z9') == ['B2', 'A3']
    assert s.get('A3') == 9


def test_set_after_rewiring_drops_old_dependents():
    s = sheet(A1='1', B1='=A1')
    s.set('B1', '=C1')
    assert s.set('A1', '2') == ['A1']
    assert s.get('B1') == 0


def test_evaluations_are_incremental():
    s = sheet(A1='1', B1='=A1+1', C1='=A1*2', D1='=B1+C1', E1='=9', F1='=E1')
    before = s.evaluations
    assert s.set('A1', '2') == ['A1', 'B1', 'C1', 'D1']
    assert s.evaluations == before + 3       # B1, C1, D1 once each; constants are not counted
    assert s.get('D1') == 7
    before = s.evaluations
    s.set('E1', '=3')
    assert s.evaluations == before + 2       # E1 and F1


def test_long_chain_evaluated_once_each():
    s = Sheet()
    s.set('A1', '1')
    for r in range(2, 301):
        s.set(f'A{r}', f'=A{r - 1}+1')
    before = s.evaluations
    changed = s.set('A1', '10')
    assert len(changed) == 300
    assert s.evaluations == before + 299
    assert s.get('A300') == 309


def test_text_and_errors_in_cells():
    s = sheet(A1='abc', B1='=A1', C1='=A1+1', D1='=C1*2', E1='=1/0')
    assert s.get('B1') == 'abc'
    assert s.get('C1') == '#VALUE!' and s.get('D1') == '#VALUE!'
    assert isinstance(s.get('E1'), ErrorValue)
    s.set('A1', '4')
    assert s.get('C1') == 5 and s.get('D1') == 10


def test_cycles_and_their_dependents():
    s = sheet(A1='=B1', B1='=C1+1', C1='=A1', D1='=A1*2', E1='=E1')
    for cell in ('A1', 'B1', 'C1', 'D1', 'E1'):
        assert s.get(cell) == '#CYCLE!'
    assert isinstance(s.get('A1'), ErrorValue)


def test_cycle_cells_not_evaluated():
    s = sheet(A1='1', B1='=A1', C1='=B1')
    before = s.evaluations
    assert s.set('A1', '=C1') == ['A1', 'B1', 'C1']
    assert s.evaluations == before
    assert [s.get(c) for c in ('A1', 'B1', 'C1')] == ['#CYCLE!'] * 3


def test_breaking_a_cycle_recovers():
    s = sheet(A1='=B1+1', B1='=A1', C1='=B1*10')
    assert s.get('C1') == '#CYCLE!'
    assert s.set('B1', '4') == ['A1', 'B1', 'C1']
    assert (s.get('A1'), s.get('B1'), s.get('C1')) == (5, 4, 40)


def test_bad_formula_leaves_sheet_unchanged():
    s = sheet(A1='2', B1='=A1*3')
    before = s.evaluations
    with pytest.raises(FormulaError):
        s.set('A1', '=1+')
    with pytest.raises(FormulaError):
        s.set('B1', '=A1*/2')
    assert s.raw('A1') == '2' and s.get('B1') == 6 and s.raw('B1') == '=A1*3'
    assert s.evaluations == before
    assert s.set('A1', '3') == ['A1', 'B1'] and s.get('B1') == 9


def test_clearing_cells():
    s = sheet(A1='7', B1='=A1+1', C1='x')
    assert s.set('A1', '') == ['A1', 'B1']
    assert s.get('A1') is None and s.get('B1') == 1
    s.set('C1', '')
    assert s.cells() == ['B1']
