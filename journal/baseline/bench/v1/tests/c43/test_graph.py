from sheet import DependencyGraph


def build(**edges):
    g = DependencyGraph()
    for cell, precs in edges.items():
        g.set_dependencies(cell, precs)
    return g


def test_direct_links_both_ways():
    g = build(B1=['A1'], C1=['A1', 'B1'])
    assert g.precedents('C1') == {'A1', 'B1'}
    assert g.dependents('A1') == {'B1', 'C1'}
    assert g.dependents('C1') == set()
    assert g.precedents('Z9') == set() and g.dependents('Z9') == set()


def test_replacing_and_removing_dependencies():
    g = build(B1=['A1'], C1=['B1'])
    g.set_dependencies('B1', ['D4'])
    assert g.dependents('A1') == set()
    assert g.dependents('D4') == {'B1'}
    assert g.all_dependents('D4') == {'B1', 'C1'}
    g.set_dependencies('C1', [])
    assert g.precedents('C1') == set() and g.dependents('B1') == set()


def test_all_dependents_transitive():
    g = build(B1=['A1'], C1=['B1'], D1=['B1', 'A1'], E1=['Z1'])
    assert g.all_dependents('A1') == {'B1', 'C1', 'D1'}
    assert g.all_dependents('C1') == set()


def test_cycles():
    g = build(A1=['B1'], B1=['C1'], C1=['A1'], D1=['A1'], E1=['E1'], F1=['G1'])
    assert g.cycle_cells() == {'A1', 'B1', 'C1', 'E1'}
    assert g.all_dependents('A1') == {'A1', 'B1', 'C1', 'D1'}
    assert g.all_dependents('D1') == set()
    g.set_dependencies('C1', [])
    assert g.cycle_cells() == {'E1'}
