import pytest

from trie import Autocomplete


def make(*pairs):
    ac = Autocomplete()
    for word, weight in pairs:
        ac.add(word, weight)
    return ac


def test_orders_by_weight_descending():
    ac = make(('car', 5), ('cart', 9), ('care', 1), ('dog', 100))
    assert ac.complete('car') == ['cart', 'car', 'care']


def test_ties_alphabetical_by_casefold_keeping_spelling():
    ac = make(('apple', 2), ('Apricot', 2), ('APEX', 2), ('apt', 3))
    assert ac.complete('ap') == ['apt', 'APEX', 'apple', 'Apricot']


def test_prefix_is_case_insensitive():
    ac = make(('Python', 1), ('pyramid', 1))
    assert ac.complete('PY') == ['pyramid', 'Python']
    assert ac.complete('pyt') == ['Python']


def test_casefold_not_just_lower():
    ac = make(('Straße', 1))
    assert ac.complete('STRASS') == ['Straße']
    assert 'strasse' in ac


def test_k_limits_results():
    ac = make(*[(f'w{i}', i) for i in range(20)])
    assert ac.complete('w', 3) == ['w19', 'w18', 'w17']
    assert len(ac.complete('w')) == 10
    assert ac.complete('w', 0) == []
    with pytest.raises(ValueError):
        ac.complete('w', -1)


def test_empty_prefix_matches_everything():
    ac = make(('b', 1), ('a', 1), ('c', 2))
    assert ac.complete('') == ['c', 'a', 'b']


def test_word_is_its_own_prefix_and_no_match():
    ac = make(('tea', 1), ('team', 2))
    assert ac.complete('team') == ['team']
    assert ac.complete('teams') == []
    assert ac.complete('x') == []


def test_readd_replaces_spelling_and_weight():
    ac = make(('hello', 1), ('help', 2))
    ac.add('HELLO', 5)
    assert len(ac) == 2
    assert ac.complete('hel') == ['HELLO', 'help']


def test_default_weight_is_one():
    ac = Autocomplete()
    ac.add('beta')
    ac.add('alpha', 1)
    ac.add('gamma', 0.5)
    assert ac.complete('') == ['alpha', 'beta', 'gamma']


def test_add_empty_raises():
    with pytest.raises(ValueError):
        Autocomplete().add('', 1)


def test_delete_case_insensitive():
    ac = make(('Hello', 1), ('help', 1))
    assert ac.delete('HELLO') is True
    assert 'hello' not in ac
    assert len(ac) == 1
    assert ac.complete('he') == ['help']
    assert ac.delete('hello') is False


def test_delete_missing_and_prefix_only():
    ac = make(('team', 1))
    assert ac.delete('tea') is False
    assert ac.delete('teams') is False
    assert ac.complete('te') == ['team']
    assert len(ac) == 1


def test_delete_keeps_longer_and_shorter_words():
    ac = make(('in', 1), ('inn', 2), ('inner', 3))
    assert ac.delete('inn')
    assert ac.complete('in') == ['inner', 'in']
    assert ac.delete('inner')
    assert ac.complete('i') == ['in']


def test_contains_and_len():
    ac = make(('One', 1), ('two', 1))
    assert 'one' in ac and 'TWO' in ac and 'on' not in ac
    assert len(ac) == 2
